"""A subscription CLI (Codex, Claude Code, Antigravity) as Capri's model (ADR-023).

The owner has subscriptions, not API keys. Each model round is one non-interactive CLI call that
must return the next assistant message as {content, tool_calls[{name, arguments_json}]}. The CLI
gets no tools of its own: Capri's tools still run locally under the same grants, and a Codex round
that used its own environment is refused. Same `chat` signature as `OllamaModel`.

The prompt and command lines follow `evals/subscription_bridge.py`, the eval-only bridge that
measured these models (kept separate so measurements on it stay unchanged).
"""

from __future__ import annotations

import asyncio
import json
import os
import signal
import tempfile
import time
from collections.abc import Awaitable, Callable
from pathlib import Path
from uuid import uuid4

from b12.contracts import ModelReply, ToolCall
from b12.model_errors import ModelError

SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["content", "tool_calls"],
    "properties": {
        "content": {"type": "string"},
        "tool_calls": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["name", "arguments_json"],
                "properties": {"name": {"type": "string"}, "arguments_json": {"type": "string"}},
            },
        },
    },
}
PREAMBLE = (
    "You are the language model inside an assistant runtime called B-12/Capri. You have NO "
    "native tools in this session: any direct tool call fails. The runtime, not you, executes "
    "the tools listed below. To use one, put it in the tool_calls array of your JSON answer "
    'with its arguments as a JSON string (for example {"name": "file_read", '
    '"arguments_json": "{\\"path\\": \\"/home/owner/a.txt\\"}"}); the runtime runs it and '
    "returns the result as a tool message in the next round. Never claim a tool ran or failed "
    "unless its result appears in the conversation below. Do not run commands of your own "
    "environment: the CLI hosting you may describe its own sandbox or disabled shell, which "
    "describes only the host, never the runtime. When a listed tool fits the task, call it "
    "through tool_calls; never say a listed tool is unavailable. Return only the next assistant "
    "message."
)
_CODEX_ITEMS = {"agent_message", "error", "reasoning"}
_CODEX_FLAGS = [
    "--ignore-user-config",
    "--ignore-rules",
    "-c",
    'web_search="disabled"',
    *[
        arg
        for feature in (
            "apps",
            "browser_use",
            "browser_use_external",
            "in_app_browser",
            "shell_tool",
            "unified_exec",
        )
        for arg in ("--disable", feature)
    ],
]

Runner = Callable[[list[str], str, Path, float], Awaitable[str]]


class _Invalid(Exception):
    pass


class _TooLong(Exception):
    pass


_MAX_ARG_BYTES = 120_000  # one argv string; Linux caps it at 128 KiB


async def _kill(process) -> None:
    """Kill the CLI and everything it started (the CLIs are node programs with children)."""
    if process.returncode is not None:
        return
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError):
        process.kill()
    await process.wait()


async def _run(argv: list[str], stdin_text: str, cwd: Path, timeout: float) -> str:
    process = await asyncio.create_subprocess_exec(
        *argv,
        cwd=cwd,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        start_new_session=True,  # its own process group, so a kill reaches the children
    )
    try:
        out, err = await asyncio.wait_for(process.communicate(stdin_text.encode()), timeout)
    except TimeoutError:
        await _kill(process)
        raise RuntimeError("backend timed out") from None
    except BaseException:  # cancelled turn or owner stop: never leave the CLI running
        await asyncio.shield(_kill(process))
        raise
    if process.returncode != 0:
        tail = (err.decode(errors="replace") + " " + out.decode(errors="replace")).strip()
        raise RuntimeError(f"backend exit {process.returncode}: {tail[-300:]}")
    return out.decode()


def split_messages(body: dict) -> tuple[str, str]:
    """Return (system text, prompt with tools and the conversation) for one round."""
    messages = body.get("messages", [])
    system = "\n\n".join(m.get("content", "") for m in messages if m.get("role") == "system")
    rest = [m for m in messages if m.get("role") != "system"]
    transcript = json.dumps(rest, ensure_ascii=False, indent=1)
    tools = json.dumps(body.get("tools", []), ensure_ascii=False, indent=1)
    text = (
        f"{PREAMBLE}\n\nAVAILABLE TOOLS (JSON schemas):\n{tools}\n\n"
        f"CONVERSATION SO FAR (JSON, oldest first):\n{transcript}\n\n"
        "Respond with the next assistant message."
    )
    return system, text


def _codex_ok(events_text: str) -> None:
    for line in events_text.splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        item = event.get("item") or {}
        if item and item.get("type") not in _CODEX_ITEMS:
            raise _Invalid(f"codex used its own environment: {item.get('type')}")


def _thaw(value):
    if isinstance(value, dict) or hasattr(value, "items"):
        return {k: _thaw(v) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return [_thaw(v) for v in value]
    return value


class CliModel:
    def __init__(self, backend: str, model: str, *, timeout_s: float = 230, runner=None):
        if backend not in ("claude", "codex", "agy"):
            raise ValueError(f"unknown backend {backend!r}")
        self.backend, self.model, self.timeout_s = backend, model, timeout_s
        self._runner: Runner = runner or _run

    async def unload(self, **_) -> bool:
        return True  # nothing is held between calls

    async def _ask(self, system: str, text: str, tmp: Path, timeout: float) -> dict:
        empty = tmp / "empty"
        empty.mkdir()
        if self.backend == "claude":
            (tmp / "system.txt").write_text(system, encoding="utf-8")
            out = await self._runner(
                [
                    "claude",
                    "-p",
                    "--model",
                    self.model,
                    "--tools",
                    "",
                    "--system-prompt-file",
                    str(tmp / "system.txt"),
                    "--json-schema",
                    json.dumps(SCHEMA),
                    "--output-format",
                    "json",
                    "--no-session-persistence",
                    "--strict-mcp-config",
                    "--setting-sources",
                    "",
                ],
                text,
                empty,
                timeout,
            )
            result = json.loads(out)
            if result.get("is_error") or not isinstance(result.get("structured_output"), dict):
                raise _Invalid("claude returned no structured output")
            return result["structured_output"]
        if self.backend == "codex":
            (tmp / "schema.json").write_text(json.dumps(SCHEMA))
            out_file = tmp / "out.json"
            events = await self._runner(
                [
                    "codex",
                    "exec",
                    "-s",
                    "read-only",
                    "--ephemeral",
                    "--skip-git-repo-check",
                    "--json",
                    "-m",
                    self.model,
                    "--output-schema",
                    str(tmp / "schema.json"),
                    "-o",
                    str(out_file),
                    *_CODEX_FLAGS,
                    "-",
                ],
                f"SYSTEM MESSAGE OF THE RUNTIME:\n{system}\n\n{text}",
                empty,
                timeout,
            )
            _codex_ok(events)
            return json.loads(out_file.read_text(encoding="utf-8"))
        prompt = f"SYSTEM MESSAGE OF THE RUNTIME:\n{system}\n\n{text}"
        argv = [
            "agy",
            "--mode",
            "plan",
            "--output-format",
            "json",
            "--json-schema",
            json.dumps(SCHEMA),
        ]
        if self.model:
            argv += ["--model", self.model]
        if len(prompt.encode()) > _MAX_ARG_BYTES:
            raise _TooLong("conversation too long for agy (one command-line argument)")
        out = await self._runner([*argv, "-p", prompt], "", empty, timeout)
        result = json.loads(out)
        if result.get("status") != "SUCCESS" or not result.get("response"):
            raise _Invalid("agy returned no answer")
        return json.loads(result["response"])

    async def chat(self, request, *, on_delta=None, cancel=None, deadline=None) -> ModelReply:
        if cancel is not None and cancel.is_set():
            raise ModelError("cancelled", "request cancelled")
        started = time.monotonic()
        timeout = self.timeout_s
        if deadline is not None:
            timeout = min(timeout, deadline - started)
            if timeout <= 0:
                raise ModelError("deadline_exceeded", "request deadline elapsed")
        body = {"messages": _thaw(request.messages), "tools": _thaw(request.tools)}
        system, text = split_messages(body)
        with tempfile.TemporaryDirectory(prefix="b12-cloud-") as tmp:
            ask = asyncio.create_task(self._ask(system, text, Path(tmp), timeout))
            waiters = [ask]
            stop = asyncio.create_task(cancel.wait()) if cancel is not None else None
            if stop is not None:
                waiters.append(stop)
            try:
                done, _ = await asyncio.wait(
                    waiters, timeout=timeout + 5, return_when="FIRST_COMPLETED"
                )
            finally:
                if stop is not None:
                    stop.cancel()
                if not ask.done():
                    # Cancelled, timed out, or this task itself cancelled: kill the CLI before
                    # its working directory goes away.
                    ask.cancel()
                    await asyncio.shield(asyncio.gather(ask, return_exceptions=True))
            if ask not in done:
                if cancel is not None and cancel.is_set():
                    raise ModelError("cancelled", "request cancelled")
                raise ModelError("deadline_exceeded", "cloud model did not answer in time")
            try:
                structured = ask.result()
            except _TooLong as exc:
                raise ModelError("prompt_too_long", str(exc)) from exc
            except _Invalid as exc:
                raise ModelError("invalid_round", str(exc)[:200]) from exc
            except (json.JSONDecodeError, OSError, RuntimeError) as exc:
                message = str(exc)
                quota = any(w in message.lower() for w in ("usage limit", "quota", "rate limit"))
                raise ModelError(
                    "quota_exceeded" if quota else "transport_error", message[:200]
                ) from exc
        content = structured.get("content") if isinstance(structured, dict) else None
        if not isinstance(content, str):
            raise ModelError("invalid_round", "answer has no content")
        calls = []
        for index, call in enumerate(structured.get("tool_calls") or []):
            try:
                arguments = json.loads(call.get("arguments_json") or "{}")
            except (AttributeError, json.JSONDecodeError) as exc:
                raise ModelError("invalid_tool_call", "tool arguments are not JSON") from exc
            if not isinstance(arguments, dict):
                raise ModelError("invalid_tool_call", "tool arguments must be an object")
            try:
                calls.append(
                    ToolCall(
                        id=f"call-{uuid4().hex[:12]}-{index}",
                        name=call["name"],
                        arguments=arguments,
                    )
                )
            except (KeyError, ValueError) as exc:
                raise ModelError("invalid_tool_call", "invalid tool call") from exc
        if content and on_delta is not None:
            await on_delta(content)
        elapsed = time.monotonic() - started
        return ModelReply(
            content=content,
            tool_calls=tuple(calls),
            metrics={"ttft_s": elapsed, "elapsed_s": elapsed, "eval_count": 0},
            finish_reason="stop",
        )
