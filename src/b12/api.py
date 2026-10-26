"""Loopback HTTP API over the shared runtime; owner/guest identity from bearer tokens.

All routes are async: stores are same-thread SQLite. Request bodies forbid extra
fields, so actor, consent and grants can never come from a body. The guard rejects
unknown Host headers (DNS rebinding), foreign Origins on state changes and bodies
over 64 KiB. Chat/resume stream NDJSON TurnEvents plus a final result line; a client
disconnect cancels the turn.
"""

import asyncio
import json
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator

from b12.auth import GUEST_CAPABILITIES, HOST_CAPABILITIES, Caller, bearer, owner_token
from b12.config import Settings
from b12.control import ControlError

MAX_BODY = 64 * 1024


class _Body(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")


class SessionBody(_Body):
    pass


class ChatBody(_Body):
    session_id: str = Field(min_length=1, max_length=64)
    text: str = Field(min_length=1, max_length=16000)
    timeout_s: float = Field(default=300.0, gt=0, le=3600)


class MemoryBody(_Body):
    text: str = Field(min_length=1, max_length=8192)


class GuestBody(_Body):
    consent: bool
    capabilities: list[str] = Field(max_length=len(GUEST_CAPABILITIES))

    @field_validator("capabilities")
    @classmethod
    def _typed_only(cls, values):
        if not set(values) <= GUEST_CAPABILITIES:
            raise ValueError("guest capabilities are limited to typed non-host tools")
        return values


class ConsentBody(_Body):
    actor_id: str | None = None
    consent: bool


class ApprovalBody(_Body):
    approve: bool


class GoalBody(_Body):
    intent: str = Field(min_length=1, max_length=4000)
    criteria: str = Field(min_length=1, max_length=4000)
    budget_turns: int = Field(default=5, ge=1, le=100)
    review_interval_s: float = Field(default=3600, ge=30, le=7 * 86400)
    allowed_tools: list[str] = Field(default_factory=list, max_length=16)
    check: dict[str, str] | None = None


class GoalStatusBody(_Body):
    status: str = Field(pattern="^(active|paused|abandoned)$")


class AttentionBody(_Body):
    quiet: bool | None = None
    stopped: bool | None = None


class FeedbackBody(_Body):
    outcome: str = Field(pattern="^(engaged|ignored|dismissed)$")


class Guard:
    """Pure ASGI guard: Host allowlist, Origin check and bounded request bodies."""

    def __init__(self, app, *, hosts: set[str], origins: set[str]):
        self.app, self.hosts, self.origins = app, hosts, origins

    async def _reject(self, send, status, code):
        body = json.dumps({"error": code}).encode()
        await send(
            {
                "type": "http.response.start",
                "status": status,
                "headers": [(b"content-type", b"application/json")],
            }
        )
        await send({"type": "http.response.body", "body": body})

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        headers = [(k.decode("latin-1").lower(), v.decode("latin-1")) for k, v in scope["headers"]]
        hosts = [v for k, v in headers if k == "host"]
        if len(hosts) != 1 or hosts[0] not in self.hosts:
            return await self._reject(send, 400, "host_rejected")
        origins = [v for k, v in headers if k == "origin"]
        if scope["method"] not in ("GET", "HEAD", "OPTIONS") and any(
            origin not in self.origins for origin in origins
        ):
            return await self._reject(send, 403, "origin_rejected")
        body, more = b"", True
        while more:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            body += message.get("body", b"")
            more = message.get("more_body", False)
            if len(body) > MAX_BODY:
                return await self._reject(send, 413, "body_too_large")
        delivered = False

        async def replay():
            nonlocal delivered
            if not delivered:
                delivered = True
                return {"type": "http.request", "body": body, "more_body": False}
            return await receive()

        return await self.app(scope, replay, send)


def turn_line(result) -> dict:
    return {
        "type": "result",
        "turn_id": result.turn_id,
        "session_id": result.session_id,
        "state": result.state,
        "content": result.content,
        "error_code": result.error_code,
        "pending_operations": list(result.pending_operations),
        "persisted": result.persisted,
        "tool_results": [r.model_dump(mode="json") for r in result.tool_results],
    }


def _line(value) -> bytes:
    return json.dumps(value, ensure_ascii=False).encode() + b"\n"


def stream_turn(start) -> StreamingResponse:
    """Run start(cancel, on_event) as an independent task; disconnect sets cancel."""
    queue: asyncio.Queue = asyncio.Queue()
    cancel = asyncio.Event()

    async def on_event(event):
        await queue.put(
            {
                "type": event.type,
                "sequence": event.sequence,
                "turn_id": event.turn_id,
                "session_id": event.session_id,
                **event.data,
            }
        )

    task = asyncio.create_task(start(cancel, on_event))

    async def body():
        try:
            while True:
                getter = asyncio.create_task(queue.get())
                done, _ = await asyncio.wait({getter, task}, return_when=asyncio.FIRST_COMPLETED)
                if getter in done:
                    yield _line(getter.result())
                    continue
                getter.cancel()
                while not queue.empty():
                    yield _line(queue.get_nowait())
                try:
                    yield _line(turn_line(task.result()))
                except LookupError:
                    yield _line({"type": "error", "error": "not_waiting"})
                except Exception:
                    yield _line({"type": "error", "error": "internal_error"})
                return
        finally:
            if not task.done():
                cancel.set()  # the turn task finishes on its own and records cancellation

    return StreamingResponse(body(), media_type="application/x-ndjson")


def create_app(
    settings: Settings,
    *,
    port: int = 8712,
    allowed_hosts: tuple[str, ...] = (),
    autonomy: bool = False,
) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        from b12.runtime import open_runtime
        from b12.service import RuntimeLock, configure_logging

        configure_logging(settings.state_dir)
        lock = RuntimeLock(settings.state_dir)
        runtime = open_runtime(settings)
        try:
            owner_id = runtime.control.get_meta("owner_actor")
            if owner_id is None:
                raise RuntimeError("owner not initialized: run b12 init")
            await runtime.purge.resume()
            from b12.tools.mcp import attach_catalog

            await attach_catalog(runtime)
            owner_token(
                runtime.control,
                settings.state_dir,
                owner_id,
                HOST_CAPABILITIES[settings.host_access],
            )
            app.state.runtime = runtime
            stop, background, scheduler = asyncio.Event(), None, None
            if autonomy:
                from b12.autonomy import Scheduler

                scheduler = Scheduler(runtime)
                background = asyncio.create_task(scheduler.run(stop))
            try:
                yield
            finally:
                stop.set()
                if background is not None:
                    for turn_id in list(runtime.agent.active):
                        runtime.agent.active[turn_id].cancel.set()
                    await asyncio.wait({background}, timeout=15)
                    scheduler.close()
        finally:
            for turn_id in list(runtime.agent.active):
                runtime.control.cancel_turn(turn_id)
                runtime.agent.active[turn_id].cancel.set()
            for _ in range(100):  # graceful: let cancelled turns stop their children
                if not runtime.agent.active:
                    break
                await asyncio.sleep(0.05)
            runtime.close()
            lock.release()

    app = FastAPI(title="B-12", lifespan=lifespan, docs_url=None, redoc_url=None)

    def runtime_of(request: Request):
        return request.app.state.runtime

    async def caller(request: Request) -> Caller:
        token = bearer(request.headers.get("authorization"))
        resolved = runtime_of(request).control.resolve_token(token) if token else None
        if resolved is None:
            raise HTTPException(401, "authentication_required")
        return Caller(*resolved)

    Identity = Annotated[Caller, Depends(caller)]

    def require_owner(who: Caller):
        if not who.owner:
            raise HTTPException(403, "owner_required")

    def own_session(request, who: Caller, session_id: str):
        if runtime_of(request).control.session_actor(session_id) != who.actor.id:
            raise HTTPException(403, "session_forbidden")

    def own_turn(request, who: Caller, turn_id: str):
        identity = runtime_of(request).control.turn_identity(turn_id)
        if identity is None or identity["actor_id"] != who.actor.id:
            raise HTTPException(404, "turn_not_found")

    web = Path(__file__).parent / "web"
    security_headers = {
        "Content-Security-Policy": (
            "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; "
            "img-src 'self' data:; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
        ),
        "X-Content-Type-Options": "nosniff",
        "Referrer-Policy": "no-referrer",
    }

    @app.get("/")
    async def index():
        return FileResponse(web / "index.html", headers=security_headers)

    @app.get("/static/{name}")
    async def static(name: str):
        types = {"app.js": "text/javascript", "style.css": "text/css"}
        if name not in types:
            raise HTTPException(404, "not_found")
        return FileResponse(web / name, media_type=types[name], headers=security_headers)

    @app.get("/api/health")
    async def health():
        return {"ok": True}

    @app.get("/api/me")
    async def me(request: Request, who: Identity):
        actor = runtime_of(request).control.resolve_actor(who.actor.id)
        return {
            "actor_id": actor.id,
            "owner": actor.owner,
            "consent": actor.consent,
            "capabilities": list(who.capabilities),
        }

    @app.get("/api/sessions")
    async def session_list(request: Request, who: Identity):
        return runtime_of(request).control.sessions_for(who.actor.id)

    @app.get("/api/tools")
    async def tools(request: Request, who: Identity):
        return runtime_of(request).registry.catalog()

    @app.post("/api/sessions")
    async def sessions(request: Request, body: SessionBody, who: Identity):
        return {"session_id": runtime_of(request).control.create_session(who.actor.id)}

    @app.get("/api/sessions/{session_id}/history")
    async def history(request: Request, session_id: str, who: Identity):
        own_session(request, who, session_id)
        actor = runtime_of(request).control.resolve_actor(who.actor.id)
        return runtime_of(request).agent.history_messages(session_id, actor)

    @app.post("/api/chat")
    async def chat(request: Request, body: ChatBody, who: Identity):
        runtime = runtime_of(request)
        own_session(request, who, body.session_id)
        task = runtime.control.create_task(body.session_id)
        grant = runtime.control.issue_grant(
            who.actor.id,
            body.session_id,
            who.capabilities or ("time.read",),
            task_id=task,
            ttl_s=body.timeout_s + 3600,
            full_execution=who.owner and "process.execute" in who.capabilities,
        )
        return stream_turn(
            lambda cancel, on_event: runtime.agent.turn(
                body.session_id,
                grant,
                body.text,
                task_id=task,
                on_event=on_event,
                cancel=cancel,
                timeout_s=body.timeout_s,
            )
        )

    @app.post("/api/turns/{turn_id}/resume")
    async def resume(request: Request, turn_id: str, who: Identity):
        own_turn(request, who, turn_id)
        runtime = runtime_of(request)
        return stream_turn(
            lambda cancel, on_event: runtime.agent.resume(turn_id, on_event=on_event, cancel=cancel)
        )

    @app.post("/api/turns/{turn_id}/cancel")
    async def cancel(request: Request, turn_id: str, who: Identity):
        own_turn(request, who, turn_id)
        runtime_of(request).control.cancel_turn(turn_id)
        return {"cancelled": turn_id}

    @app.get("/api/memory")
    async def memory_search(request: Request, q: str, who: Identity):
        runtime = runtime_of(request)
        if "memory.read" not in who.capabilities:
            raise HTTPException(403, "capability_denied")
        try:
            records = runtime.memory.search(q[:256], runtime.control.resolve_actor(who.actor.id))
        except PermissionError:
            raise HTTPException(403, "consent_required") from None
        return [r.model_dump(mode="json") for r in records]

    @app.post("/api/memory")
    async def memory_remember(request: Request, body: MemoryBody, who: Identity):
        runtime = runtime_of(request)
        if "memory.write" not in who.capabilities:
            raise HTTPException(403, "capability_denied")
        try:
            record = runtime.memory.remember(
                body.text, runtime.control.resolve_actor(who.actor.id), source="api"
            )
        except PermissionError:
            raise HTTPException(403, "consent_required") from None
        return record.model_dump(mode="json")

    @app.delete("/api/memory/{memory_id}")
    async def memory_forget(request: Request, memory_id: str, who: Identity):
        # Erasing one's own namespace is a right, not a delegated capability.
        try:
            receipt = await runtime_of(request).purge.forget(memory_id, who.actor.id)
        except (KeyError, ValueError):
            raise HTTPException(404, "memory_not_found") from None
        data = receipt.model_dump(mode="json")
        return JSONResponse(data, status_code=200 if receipt.state == "complete" else 202)

    @app.get("/api/approvals")
    async def approvals(request: Request, who: Identity):
        require_owner(who)
        return runtime_of(request).control.pending_approvals()

    @app.post("/api/approvals/{operation_id}")
    async def decide(request: Request, operation_id: str, body: ApprovalBody, who: Identity):
        require_owner(who)
        try:
            runtime_of(request).control.decide_approval(operation_id, body.approve)
        except ControlError as exc:
            raise HTTPException(409, exc.code) from None
        return {"operation_id": operation_id, "approved": body.approve}

    @app.post("/api/guests")
    async def guests(request: Request, body: GuestBody, who: Identity):
        require_owner(who)
        control = runtime_of(request).control
        actor = control.create_actor(owner=False, consent=body.consent)
        token = control.issue_token(actor.id, tuple(body.capabilities))
        return {"actor_id": actor.id, "token": token, "consent": body.consent}

    @app.delete("/api/guests/{actor_id}")
    async def revoke_guest(request: Request, actor_id: str, who: Identity):
        require_owner(who)
        control = runtime_of(request).control
        try:
            actor = control.resolve_actor(actor_id)
        except ControlError:
            raise HTTPException(404, "actor_not_found") from None
        if actor.owner:
            raise HTTPException(403, "owner_token_not_revocable_here")
        control.revoke_tokens(actor_id)
        return {"revoked": actor_id}

    @app.get("/api/status")
    async def service_status(request: Request, who: Identity):
        from b12.telemetry import status

        require_owner(who)
        return status(runtime_of(request))

    @app.get("/api/backups")
    async def backups_list(request: Request, who: Identity):
        require_owner(who)
        return runtime_of(request).operations.inventory()

    @app.post("/api/backups")
    async def backups_create(request: Request, who: Identity):
        require_owner(who)  # synchronous copy inside the event loop: consistent across stores
        return runtime_of(request).operations.create_snapshot()

    @app.get("/api/goals")
    async def goal_list(request: Request, who: Identity):
        return runtime_of(request).goals.for_actor(who.actor.id)

    @app.post("/api/goals")
    async def goal_create(request: Request, body: GoalBody, who: Identity):
        require_owner(who)  # goals run tools autonomously under owner grants
        runtime = runtime_of(request)
        session = runtime.control.create_session(who.actor.id)
        try:
            return runtime.goals.create(
                who.actor.id,
                session,
                body.intent,
                body.criteria,
                allowed_tools=tuple(set(body.allowed_tools) & set(who.capabilities)),
                budget_turns=body.budget_turns,
                review_interval_s=body.review_interval_s,
                check=body.check,
            )
        except ValueError as exc:
            raise HTTPException(422, "invalid_goal") from exc

    @app.post("/api/goals/{goal_id}/status")
    async def goal_status(request: Request, goal_id: str, body: GoalStatusBody, who: Identity):
        try:
            return runtime_of(request).goals.set_status(
                goal_id, who.actor.id, body.status, "owner_control"
            )
        except KeyError:
            raise HTTPException(404, "goal_not_found") from None

    @app.get("/api/attention")
    async def attention_state(request: Request, who: Identity):
        return runtime_of(request).attention.state(who.actor.id)

    @app.post("/api/attention")
    async def attention_set(request: Request, body: AttentionBody, who: Identity):
        attention = runtime_of(request).attention
        if body.quiet is not None:
            attention.set_quiet(who.actor.id, body.quiet)
        if body.stopped is not None:
            attention.set_stopped(who.actor.id, body.stopped)
        return attention.state(who.actor.id)

    @app.get("/api/proposals")
    async def proposals(request: Request, who: Identity):
        return runtime_of(request).goals.proposals(who.actor.id)

    @app.post("/api/proposals/{proposal_id}/feedback")
    async def proposal_feedback(
        request: Request, proposal_id: str, body: FeedbackBody, who: Identity
    ):
        runtime = runtime_of(request)
        match = [p for p in runtime.goals.proposals(who.actor.id) if p["id"] == proposal_id]
        if not match:
            raise HTTPException(404, "proposal_not_found")
        if match[0]["attention_id"]:
            runtime.attention.feedback(match[0]["attention_id"], body.outcome)
        return {"proposal_id": proposal_id, "outcome": body.outcome}

    @app.post("/api/control/consent")
    async def consent(request: Request, body: ConsentBody, who: Identity):
        target = body.actor_id or who.actor.id
        if not who.owner and (target != who.actor.id or body.consent):
            raise HTTPException(403, "owner_required")
        control = runtime_of(request).control
        try:
            control.set_consent(target, body.consent)
        except ControlError:
            raise HTTPException(404, "actor_not_found") from None
        return {"actor_id": target, "consent": body.consent}

    app.add_middleware(
        Guard,
        hosts={f"127.0.0.1:{port}", f"localhost:{port}", *allowed_hosts},
        origins={f"http://127.0.0.1:{port}", f"http://localhost:{port}"},
    )
    return app
