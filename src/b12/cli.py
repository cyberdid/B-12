"""Local owner CLI. Running it is the trusted local control channel for the owner.

Settings: optional TOML (--config, else $XDG_CONFIG_HOME/b12/config.toml), with
B12_* environment values taking precedence. Exit codes: 0 completed/ok,
1 failed/error, 2 waiting for approval, 3 purge still pending, 130 cancelled.
"""

import argparse
import asyncio
import json
import os
import signal
import sys
import tomllib
from pathlib import Path

import httpx

from b12.config import Settings
from b12.model_errors import ModelError

CAPABILITIES = {
    "full": (
        "system.read",
        "process.read",
        "filesystem.read",
        "filesystem.write",
        "process.execute",
        "network.http",
        "memory.read",
        "memory.write",
        "memory.forget",
        "knowledge.read",
        "time.read",
    ),
    "read_only": (
        "system.read",
        "process.read",
        "filesystem.read",
        "memory.read",
        "knowledge.read",
        "time.read",
    ),
    "none": ("time.read",),
}
_EXIT = {"completed": 0, "failed": 1, "awaiting_approval": 2, "cancelled": 130}


def load_settings(config: str | None = None) -> Settings:
    environ = dict(os.environ)
    base = Path(environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")
    path = Path(config) if config else base / "b12" / "config.toml"
    if config or path.exists():
        for key, value in tomllib.loads(path.read_text()).items():
            environ.setdefault(f"B12_{key.upper()}", str(value))
    return Settings.from_env(environ)


def emit_json(value) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2))


def turn_json(result) -> dict:
    return {
        "turn_id": result.turn_id,
        "session_id": result.session_id,
        "state": result.state,
        "content": result.content,
        "error_code": result.error_code,
        "pending_operations": list(result.pending_operations),
        "persisted": result.persisted,
        "tool_results": [r.model_dump(mode="json") for r in result.tool_results],
    }


class Owner:
    """Owner identity and default CLI session stored in ControlStore metadata."""

    def __init__(self, runtime):
        self.runtime = runtime
        control = runtime.control
        self.actor_id = control.get_meta("owner_actor")
        self.session_id = control.get_meta("cli_session")

    @property
    def initialized(self) -> bool:
        return self.actor_id is not None

    def actor(self):
        return self.runtime.control.resolve_actor(self.actor_id)

    def grant(self, timeout_s: float) -> tuple[str, str]:
        control, access = self.runtime.control, self.runtime.settings.host_access
        task = control.create_task(self.session_id)
        grant = control.issue_grant(
            self.actor_id,
            self.session_id,
            CAPABILITIES[access],
            task_id=task,
            ttl_s=timeout_s + 3600,
            full_execution=access == "full",
        )
        return grant, task


def open_or_fail(settings):
    from b12.runtime import open_runtime

    try:
        return open_runtime(settings)
    except ModelError as exc:
        emit_json({"error": exc.code})
        raise SystemExit(1) from None


async def check_model(settings) -> dict:
    from b12.model import OllamaModel
    from b12.model_profile import ModelProfile

    report = {"reachable": False, "version": None, "digest_matches": False}
    try:
        profile = ModelProfile(settings)
    except ModelError as exc:
        report["error"] = exc.code
        return report
    try:
        async with httpx.AsyncClient(
            base_url=settings.ollama_url.rstrip("/") + "/", timeout=5, trust_env=False
        ) as client:
            report["version"] = (await client.get("api/version")).json().get("version")
            report["reachable"] = True
            await OllamaModel._check_deployment(client, profile)
            report["digest_matches"] = True
    except ModelError as exc:
        report["error"] = exc.code
    except (httpx.HTTPError, ValueError):
        report["error"] = "transport_error"
    return report


async def cmd_doctor(args, settings) -> int:
    report = {"state_dir": str(settings.state_dir), "model": await check_model(settings)}
    try:
        runtime = open_or_fail(settings)
    except SystemExit:
        return 1
    try:
        owner = Owner(runtime)
        report["initialized"] = owner.initialized
        report["consent"] = owner.actor().consent if owner.initialized else None
        report["pending_purges"] = sum(
            len(runtime.memory.pending_purges(runtime.control.resolve_actor(actor_id)))
            for actor_id in runtime.control.actor_ids()
        )
        report["pending_approvals"] = len(runtime.control.pending_approvals())
        report["tools"] = len(runtime.registry.catalog())
    finally:
        runtime.close()
    report["ok"] = bool(
        report["initialized"] and report["model"]["digest_matches"] and not report["pending_purges"]
    )
    emit_json(report)
    return 0 if report["ok"] else 1


async def cmd_init(args, settings) -> int:
    runtime = open_or_fail(settings)
    try:
        owner = Owner(runtime)
        if not owner.initialized:
            actor = runtime.control.create_actor(owner=True, consent=not args.no_consent)
            session = runtime.control.create_session(actor.id)
            runtime.control.set_meta("owner_actor", actor.id)
            runtime.control.set_meta("cli_session", session)
            owner = Owner(runtime)
        emit_json(
            {
                "owner_id": owner.actor_id,
                "session_id": owner.session_id,
                "consent": owner.actor().consent,
            }
        )
    finally:
        runtime.close()
    return 0


def require_owner(runtime) -> Owner:
    owner = Owner(runtime)
    if not owner.initialized:
        emit_json({"error": "not_initialized", "hint": "run: b12 init"})
        runtime.close()
        raise SystemExit(1)
    return owner


class Console:
    """Human-readable streaming: reply text on stdout, tool activity on stderr."""

    def __init__(self, quiet: bool):
        self.quiet = quiet

    async def __call__(self, event):
        if self.quiet:
            return
        if event.type == "text_delta":
            sys.stdout.write(event.data["text"])
            sys.stdout.flush()
        elif event.type == "tool_started":
            print(f"[інструмент] {event.data['name']} …", file=sys.stderr)
        elif event.type == "tool_result":
            print(f"[інструмент] {event.data['name']} → {event.data['status']}", file=sys.stderr)
        elif event.type in ("turn_completed", "turn_failed", "turn_cancelled"):
            sys.stdout.write("\n")
            sys.stdout.flush()


async def run_with_interrupt(function, *args, **kwargs):
    """SIGINT sets the turn's cancellation event instead of killing the process."""
    cancel = asyncio.Event()
    loop = asyncio.get_running_loop()
    loop.add_signal_handler(signal.SIGINT, cancel.set)
    try:
        return await function(*args, cancel=cancel, **kwargs)
    finally:
        loop.remove_signal_handler(signal.SIGINT)


async def interactive_approvals(runtime, result, console, timeout_s):
    while result.state == "awaiting_approval":
        approvals = {a["operation_id"]: a for a in runtime.control.pending_approvals()}
        operation = result.pending_operations[0]
        name = approvals.get(operation, {}).get("name", "?")
        print(f"Дозволити {name}? [y/N] ", end="", file=sys.stderr, flush=True)
        answer = (await asyncio.to_thread(sys.stdin.readline)).strip().lower()
        runtime.control.decide_approval(operation, answer in ("y", "yes", "т", "так"))
        result = await run_with_interrupt(
            runtime.agent.resume, result.turn_id, on_event=console, timeout_s=timeout_s
        )
    return result


async def cmd_chat(args, settings) -> int:
    runtime = open_or_fail(settings)
    try:
        owner = require_owner(runtime)
        await runtime.purge.resume()
        if args.message is not None:
            grant, task = owner.grant(args.timeout)
            console = Console(quiet=args.json)
            result = await run_with_interrupt(
                runtime.agent.turn,
                owner.session_id,
                grant,
                args.message,
                task_id=task,
                on_event=console,
                timeout_s=args.timeout,
            )
            if args.json:
                emit_json(turn_json(result))
            return _EXIT[result.state]
        console = Console(quiet=False)
        while True:
            print("ти> ", end="", file=sys.stderr, flush=True)
            line = await asyncio.to_thread(sys.stdin.readline)
            if not line:
                return 0
            if not line.strip():
                continue
            grant, task = owner.grant(args.timeout)
            print("B-12> ", end="", flush=True)
            result = await run_with_interrupt(
                runtime.agent.turn,
                owner.session_id,
                grant,
                line.strip(),
                task_id=task,
                on_event=console,
                timeout_s=args.timeout,
            )
            result = await interactive_approvals(runtime, result, console, args.timeout)
            if result.state != "completed":
                print(f"[{result.state}: {result.error_code}]", file=sys.stderr)
    finally:
        runtime.close()


async def cmd_resume(args, settings) -> int:
    runtime = open_or_fail(settings)
    try:
        require_owner(runtime)
        result = await run_with_interrupt(
            runtime.agent.resume, args.turn_id, on_event=Console(quiet=args.json)
        )
        if args.json:
            emit_json(turn_json(result))
        return _EXIT[result.state]
    finally:
        runtime.close()


async def cmd_decide(args, settings, approve: bool) -> int:
    from b12.control import ControlError

    runtime = open_or_fail(settings)
    try:
        require_owner(runtime)
        try:
            runtime.control.decide_approval(args.operation_id, approve)
        except ControlError as exc:
            emit_json({"error": exc.code})
            return 1
        emit_json({"operation_id": args.operation_id, "approved": approve})
        return 0
    finally:
        runtime.close()


async def cmd_approvals(args, settings) -> int:
    runtime = open_or_fail(settings)
    try:
        require_owner(runtime)
        emit_json(runtime.control.pending_approvals())
        return 0
    finally:
        runtime.close()


async def cmd_memory(args, settings) -> int:
    runtime = open_or_fail(settings)
    try:
        owner = require_owner(runtime)
        actor = owner.actor()
        if args.action == "remember":
            record = runtime.memory.remember(args.value, actor, source="cli")
            emit_json(record.model_dump(mode="json"))
        elif args.action == "search":
            emit_json([r.model_dump(mode="json") for r in runtime.memory.search(args.value, actor)])
        elif args.action == "forget":
            try:
                receipt = await runtime.purge.forget(args.value, actor.id)
            except (KeyError, ValueError):
                emit_json({"error": "not_found"})
                return 1
            emit_json(receipt.model_dump(mode="json"))
            return 0 if receipt.state == "complete" else 3
        elif args.action == "pending":
            emit_json([r.model_dump(mode="json") for r in runtime.memory.pending_purges(actor)])
        return 0
    finally:
        runtime.close()


async def cmd_session_clear(args, settings) -> int:
    runtime = open_or_fail(settings)
    try:
        owner = require_owner(runtime)
        runtime.sessions.clear_session(owner.session_id, owner.actor_id)
        emit_json({"cleared": owner.session_id})
        return 0
    finally:
        runtime.close()


async def cmd_tools(args, settings) -> int:
    runtime = open_or_fail(settings)
    try:
        emit_json(runtime.registry.catalog())
        return 0
    finally:
        runtime.close()


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(prog="b12", description="Локальний компаньйон B-12")
    root.add_argument("--config", help="TOML settings file (B12_* env overrides it)")
    sub = root.add_subparsers(dest="command", required=True)
    sub.add_parser("doctor", help="стан моделі, профілю й сховищ").add_argument(
        "--json", action="store_true"
    )
    init = sub.add_parser("init", help="створити owner і сесію CLI")
    init.add_argument("--no-consent", action="store_true", help="без збереження пам’яті")
    chat = sub.add_parser("chat", help="розмова; -m для одного turn")
    chat.add_argument("-m", "--message")
    chat.add_argument("--json", action="store_true")
    chat.add_argument("--timeout", type=float, default=300.0)
    resume = sub.add_parser("resume", help="продовжити turn після approval")
    resume.add_argument("turn_id")
    resume.add_argument("--json", action="store_true")
    for name in ("approve", "deny"):
        sub.add_parser(name).add_argument("operation_id")
    sub.add_parser("approvals", help="черга approval")
    memory = sub.add_parser("memory", help="пам’ять власника")
    memory.add_argument("action", choices=("remember", "search", "forget", "pending"))
    memory.add_argument("value", nargs="?", default="")
    session = sub.add_parser("session", help="робоча історія CLI")
    session.add_argument("action", choices=("clear",))
    sub.add_parser("tools", help="каталог інструментів")
    return root


def main(argv=None) -> int:
    args = parser().parse_args(argv)
    try:
        settings = load_settings(args.config)
    except (ValueError, OSError, tomllib.TOMLDecodeError) as exc:
        emit_json({"error": "invalid_settings", "detail": type(exc).__name__})
        return 1
    handlers = {
        "doctor": cmd_doctor,
        "init": cmd_init,
        "chat": cmd_chat,
        "resume": cmd_resume,
        "approve": lambda a, s: cmd_decide(a, s, True),
        "deny": lambda a, s: cmd_decide(a, s, False),
        "approvals": cmd_approvals,
        "memory": cmd_memory,
        "session": cmd_session_clear,
        "tools": cmd_tools,
    }
    try:
        return asyncio.run(handlers[args.command](args, settings))
    except SystemExit as exc:
        return int(exc.code or 0)


if __name__ == "__main__":
    sys.exit(main())
