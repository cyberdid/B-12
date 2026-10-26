"""MCP stdio client: external server tools under the same registry/control contract.

The trusted local catalog (state_dir/mcp.json, written by the owner) names each
server's command, capability and risk; model output can never add servers or tools.
Tools register as mcp.<server>.<tool>, so they cannot shadow built-ins. Only input
schemas inside the calibrated renderer subset (object of string/number/integer/
boolean/array-of-primitive properties) are exposed; others are skipped and reported.
A remote tool cannot certify "no effect": unless the catalog marks the server
read_only, errors and interruptions are reported as unknown with a possible effect.
"""

import asyncio
import json
import os
import signal
import time
from pathlib import Path
from typing import Annotated, Any

from pydantic import Field, Strict, create_model

from b12.tools._common import Args, clip
from b12.tools.outcomes import HandlerOutcome, SideEffect
from b12.tools.policy import Risk
from b12.tools.process import _die_with_parent

PROTOCOL = "2025-06-18"
MAX_LINE = 1024 * 1024
_TYPES = {"string": str, "integer": int, "boolean": bool}
_DEFAULTS = {"string": "", "integer": 0, "number": 0.0, "boolean": False, "array": []}


class McpError(Exception):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def _optional(spec: dict) -> tuple[dict, bool]:
    """Normalize anyOf [X, null] (FastMCP Optional) to X; we render our own schema."""
    variants = spec.get("anyOf")
    if isinstance(variants, list) and len(variants) == 2:
        real = [v for v in variants if isinstance(v, dict) and v.get("type") != "null"]
        if len(real) == 1 and any(v.get("type") == "null" for v in variants if isinstance(v, dict)):
            merged = {**real[0], **{k: v for k, v in spec.items() if k == "description"}}
            return merged, True
    return spec, False


def _python_type(spec: dict):
    kind = spec.get("type")
    if kind == "number":
        return Annotated[float, Strict(False)]  # accept JSON integers without anyOf schema
    if kind in _TYPES:
        return _TYPES[kind]
    if kind == "array" and isinstance(spec.get("items"), dict):
        inner = spec["items"].get("type")
        if inner in _TYPES:
            return list[_TYPES[inner]]
    return None


def schema_model(name: str, schema: dict):
    """Strict pydantic model for a supported inputSchema, else None (tool skipped)."""
    if not isinstance(schema, dict) or schema.get("type", "object") != "object":
        return None
    properties = schema.get("properties", {}) or {}
    required = set(schema.get("required", []) or [])
    fields: dict[str, Any] = {}
    for key, spec in properties.items():
        if not isinstance(spec, dict) or not key.isidentifier() or key.startswith("_"):
            return None
        spec, nullable = _optional(spec)
        if nullable:
            required.discard(key)
        python = _python_type(spec)
        if python is None:
            return None
        description = str(spec.get("description", ""))[:300] or None
        if key in required:
            fields[key] = (python, Field(description=description))
        else:
            # Typed default avoids anyOf; unset optionals are never sent to the server.
            fields[key] = (python, Field(default=_DEFAULTS[spec["type"]], description=description))
    return create_model(f"Mcp_{name}", __base__=Args, **fields)


class McpServer:
    def __init__(self, name: str, command: list[str], *, cwd: str | None = None):
        if not name.isidentifier():
            raise ValueError("server name must be an identifier")
        self.name, self.command, self.cwd = name, list(command), cwd
        self.process = None
        self._pending: dict[int, asyncio.Future] = {}
        self._next = 0
        self._reader = None

    async def start(self, timeout_s: float = 10):
        self.process = await asyncio.create_subprocess_exec(
            *self.command,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
            cwd=self.cwd,
            start_new_session=True,
            preexec_fn=_die_with_parent,
            limit=MAX_LINE,
        )
        self._reader = asyncio.create_task(self._read())
        await self.request(
            "initialize",
            {
                "protocolVersion": PROTOCOL,
                "capabilities": {},
                "clientInfo": {"name": "b12", "version": "0.1"},
            },
            timeout_s=timeout_s,
        )
        await self._send({"jsonrpc": "2.0", "method": "notifications/initialized"})

    async def _send(self, message):
        self.process.stdin.write(json.dumps(message).encode() + b"\n")
        await self.process.stdin.drain()

    async def _read(self):
        try:
            while True:
                line = await self.process.stdout.readline()
                if not line:
                    break
                try:
                    message = json.loads(line)
                except ValueError:
                    continue
                future = self._pending.pop(message.get("id"), None)
                if future is not None and not future.done():
                    future.set_result(message)
        except (asyncio.LimitOverrunError, ValueError):
            pass
        finally:
            for future in self._pending.values():
                if not future.done():
                    future.set_exception(McpError("server_closed"))
            self._pending.clear()

    async def request(self, method, params, *, cancel=None, timeout_s: float = 30):
        if self.process is None or self.process.returncode is not None:
            raise McpError("server_closed")
        self._next += 1
        request_id = self._next
        future = asyncio.get_running_loop().create_future()
        self._pending[request_id] = future
        await self._send({"jsonrpc": "2.0", "id": request_id, "method": method, "params": params})
        waiters = {future}
        cancelled = asyncio.create_task(cancel.wait()) if cancel is not None else None
        if cancelled:
            waiters.add(cancelled)
        try:
            done, _ = await asyncio.wait(
                waiters, timeout=timeout_s, return_when=asyncio.FIRST_COMPLETED
            )
        finally:
            if cancelled:
                cancelled.cancel()
        if future not in done:
            self._pending.pop(request_id, None)
            future.cancel()
            await self._send(
                {
                    "jsonrpc": "2.0",
                    "method": "notifications/cancelled",
                    "params": {"requestId": request_id, "reason": "client cancelled"},
                }
            )
            raise McpError("cancelled" if cancel is not None and cancel.is_set() else "timeout")
        message = future.result()
        if "error" in message:
            raise McpError("server_error")
        return message.get("result", {})

    async def list_tools(self) -> list[dict]:
        return (await self.request("tools/list", {})).get("tools", [])

    def close(self):
        if self.process is not None and self.process.returncode is None:
            try:
                os.killpg(self.process.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
        if self._reader is not None:
            self._reader.cancel()

    async def aclose(self, timeout_s: float = 5):
        self.close()
        if self.process is not None:
            try:
                await asyncio.wait_for(self.process.wait(), timeout_s)
            except TimeoutError:
                os.killpg(self.process.pid, signal.SIGKILL)
                await self.process.wait()


async def register_server(
    registry, server: McpServer, *, capability, risk="typed", read_only=False, timeout_s=None
):
    """Discover and register a started server's supported tools; returns skipped names."""
    skipped = []
    for tool in await server.list_tools():
        name = str(tool.get("name", ""))
        model = schema_model(f"{server.name}_{name}", tool.get("inputSchema", {}))
        full = f"mcp.{server.name}.{name}"
        if model is None or not name.replace("_", "").replace("-", "").isalnum():
            skipped.append(name)
            continue
        registry.register(
            full,
            str(tool.get("description") or name)[:500],
            model,
            _handler(server, name, read_only),
            capability,
            risk=Risk(risk),
            timeout_s=timeout_s,
        )
    return skipped


def _handler(server, tool_name, read_only):
    effects = () if read_only else (SideEffect(kind="mcp_call", state="possible"),)

    async def handler(args, guard):
        guard.check()
        timeout = max(0.1, guard.deadline - time.monotonic())
        try:
            result = await server.request(
                "tools/call",
                {"name": tool_name, "arguments": args.model_dump(exclude_unset=True)},
                cancel=guard.cancel,
                timeout_s=timeout,
            )
        except McpError as exc:
            code = "cancelled" if exc.code == "cancelled" else "handler_failed"
            if exc.code == "timeout":
                code = "deadline_exceeded"
            if read_only:
                return HandlerOutcome(status="failed", error_code=code)
            return HandlerOutcome(status="unknown", error_code=code, side_effects=effects)
        texts = [
            item.get("text", "")
            for item in result.get("content", []) or []
            if isinstance(item, dict) and item.get("type") == "text"
        ]
        text, truncated = clip("\n".join(texts), 8192)
        if result.get("isError"):
            if read_only:
                return HandlerOutcome(status="failed", error_code="handler_failed")
            return HandlerOutcome(
                status="unknown",
                error_code="handler_failed",
                content={"text": text},
                truncated=truncated,
                side_effects=effects,
            )
        completed = tuple(e.model_copy(update={"state": "completed"}) for e in effects)
        return HandlerOutcome(content={"text": text}, truncated=truncated, side_effects=completed)

    return handler


async def close_servers(runtime) -> None:
    """Async shutdown of child bridges (MCP servers, embedding bridge) inside the loop."""
    for server in runtime.mcp_servers:
        await server.aclose()
    runtime.mcp_servers.clear()
    if runtime.agent.semantic is not None:
        await runtime.agent.semantic.embedder.aclose()


def catalog_capabilities(state_dir: Path) -> tuple[str, ...]:
    """Owner-only capabilities declared by the trusted catalog (never given to guests)."""
    return tuple(sorted({entry["capability"] for entry in load_catalog(state_dir)}))


def load_catalog(state_dir: Path) -> list[dict]:
    path = Path(state_dir) / "mcp.json"
    if not path.exists():
        return []
    entries = json.loads(path.read_text())
    for entry in entries:
        if set(entry) - {"name", "command", "capability", "risk", "read_only", "cwd", "timeout_s"}:
            raise ValueError("unknown catalog field")
        if not isinstance(entry["command"], list) or not entry["command"]:
            raise ValueError("command must be an argv list")
    return entries


async def attach_catalog(runtime) -> dict:
    """Start every catalog server and register its tools; servers close with the runtime."""
    report = {}
    for entry in load_catalog(runtime.settings.state_dir):
        server = McpServer(entry["name"], entry["command"], cwd=entry.get("cwd"))
        await server.start()
        runtime.mcp_servers.append(server)
        skipped = await register_server(
            runtime.registry,
            server,
            capability=entry["capability"],
            risk=entry.get("risk", "typed"),
            read_only=bool(entry.get("read_only")),
            timeout_s=entry.get("timeout_s"),
        )
        report[entry["name"]] = {"skipped": skipped}
    return report
