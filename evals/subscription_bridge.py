"""Eval-only Ollama-compatible bridge to subscription CLIs (Codex, Claude Code). Host side.

The owner has subscriptions, not API keys. This bridge lets the unchanged B-12 runtime use a
subscription model for evaluation: every Ollama route except `POST /api/chat` is proxied to
the real local Ollama (so the pinned model profile checks still pass), and each chat round
is answered by one non-interactive CLI call:

- `claude -p --model <m> --tools ""` — no built-in tools, the runtime's system message as the
  system prompt, structured output enforced by `--json-schema`;
- `codex exec -s read-only --ephemeral --json --output-schema` in an empty directory with every
  configured MCP server, apps and the browser disabled. Its event stream is checked: any item
  other than the final agent message (a command, file change, tool or web call) makes the
  round INVALID and the bridge returns an error instead of the model's answer.

The model sees Capri's own context and tool schemas and must return the next assistant message
as {content, tool_calls[{name, arguments_json}]}. The backend counts tokens with its own
tokenizer and also sees its CLI's own system prompt, so its prompt count cannot be compared
with the runtime's admitted budget: the bridge reports `prompt_eval_count: 0` (the runtime
then only logs a mismatch) and puts the backend's real usage in `bridge_usage` and the bridge
log. Owner decision 18.11.2026: the local 8192 context limit does not apply to cloud models;
bridged runs pass `--num-ctx 200000` so the runtime never trims their context. Latency includes CLI start-up and is not comparable to local models.
"""

import argparse
import asyncio
import json
import tempfile
import time
import tomllib
from pathlib import Path

import httpx
import uvicorn
from fastapi import FastAPI, Request
from starlette.responses import JSONResponse, Response, StreamingResponse

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
ALLOWED_CODEX_ITEMS = {"agent_message", "error", "reasoning"}
PREAMBLE = (
    "You are the language model inside an assistant runtime called B-12/Capri. You have NO "
    "native tools in this session: any direct tool call fails. The runtime, not you, executes "
    "the tools listed below. To use one, put it in the tool_calls array of your JSON answer "
    'with its arguments as a JSON string (for example {"name": "file_read", '
    '"arguments_json": "{\\"path\\": \\"/sandbox/a.txt\\"}"}); the runtime '
    "runs it and returns the result as a tool message in the next round. Never claim a tool ran "
    "or failed unless its result appears in the conversation below. Do not run commands of your "
    "own environment. Return only the next assistant message."
)


class InvalidRound(RuntimeError):
    pass


def split_messages(body):
    """Return (system_text, transcript_text) for one Ollama chat request."""
    system = "\n\n".join(
        m.get("content", "") for m in body.get("messages", []) if m.get("role") == "system"
    )
    rest = [m for m in body.get("messages", []) if m.get("role") != "system"]
    transcript = json.dumps(rest, ensure_ascii=False, indent=1)
    tools = json.dumps(body.get("tools", []), ensure_ascii=False, indent=1)
    text = (
        f"{PREAMBLE}\n\nAVAILABLE TOOLS (JSON schemas):\n{tools}\n\n"
        f"CONVERSATION SO FAR (JSON, oldest first):\n{transcript}\n\n"
        "Respond with the next assistant message."
    )
    return system, text


def to_ollama_message(structured):
    calls = []
    for call in structured.get("tool_calls", []):
        try:
            arguments = json.loads(call.get("arguments_json") or "{}")
        except json.JSONDecodeError as exc:
            raise InvalidRound(f"tool arguments are not JSON: {exc}") from None
        if not isinstance(arguments, dict):
            raise InvalidRound("tool arguments must be a JSON object")
        calls.append({"function": {"name": call["name"], "arguments": arguments}})
    message = {"role": "assistant", "content": structured.get("content", "")}
    if calls:
        message["tool_calls"] = calls
    return message


def codex_events_ok(events_text):
    """Raise InvalidRound if Codex did anything but answer."""
    for line in events_text.splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        item = event.get("item") or {}
        if item and item.get("type") not in ALLOWED_CODEX_ITEMS:
            raise InvalidRound(f"codex used its own environment: {item.get('type')}")


def codex_overrides(config_path):
    args = ["--disable", "apps", "--disable", "browser_use", "--disable", "browser_use_external"]
    try:
        config = tomllib.loads(Path(config_path).read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError):
        config = {}
    for name in config.get("mcp_servers", {}):
        args += ["-c", f'mcp_servers."{name}".enabled=false']
    return args


async def _run(cmd, stdin_text, cwd, timeout):
    process = await asyncio.create_subprocess_exec(
        *cmd,
        cwd=cwd,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        out, err = await asyncio.wait_for(process.communicate(stdin_text.encode()), timeout)
    except TimeoutError:
        process.kill()
        raise InvalidRound("backend timed out") from None
    if process.returncode != 0:
        raise InvalidRound(f"backend exit {process.returncode}: {err.decode()[-300:]}")
    return out.decode()


async def ask_backend(backend, model, body, *, timeout=200, codex_config=None):
    system, text = split_messages(body)
    with tempfile.TemporaryDirectory(prefix="b12-sub-") as tmp:
        tmp = Path(tmp)
        (tmp / "empty").mkdir()
        if backend == "claude":
            out = await _run(
                [
                    "claude",
                    "-p",
                    "--model",
                    model,
                    "--tools",
                    "",
                    "--system-prompt",
                    system,
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
                tmp / "empty",
                timeout,
            )
            result = json.loads(out)
            if result.get("is_error") or not isinstance(result.get("structured_output"), dict):
                raise InvalidRound("claude returned no structured output")
            usage = result.get("usage") or {}
            prompt_tokens = sum(
                int(usage.get(k) or 0)
                for k in ("input_tokens", "cache_read_input_tokens", "cache_creation_input_tokens")
            )
            return result["structured_output"], (
                prompt_tokens,
                int(usage.get("output_tokens") or 0),
            )
        if backend == "codex":
            (tmp / "schema.json").write_text(json.dumps(SCHEMA))
            prompt = f"SYSTEM MESSAGE OF THE RUNTIME:\n{system}\n\n{text}"
            events = await _run(
                [
                    "codex",
                    "exec",
                    "-s",
                    "read-only",
                    "--ephemeral",
                    "--skip-git-repo-check",
                    "--json",
                    "-m",
                    model,
                    "--output-schema",
                    str(tmp / "schema.json"),
                    "-o",
                    str(tmp / "out.json"),
                    *codex_overrides(codex_config or Path.home() / ".codex/config.toml"),
                    "-",
                ],
                prompt,
                tmp / "empty",
                timeout,
            )
            codex_events_ok(events)
            prompt_tokens = completion_tokens = 0
            for line in events.splitlines():
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if event.get("type") == "turn.completed":
                    usage = event.get("usage") or {}
                    prompt_tokens = int(usage.get("input_tokens") or 0)
                    completion_tokens = int(usage.get("output_tokens") or 0)
            structured = json.loads((tmp / "out.json").read_text(encoding="utf-8"))
            return structured, (prompt_tokens, completion_tokens)
    raise ValueError(f"unknown backend {backend!r}")


def bridge_app(upstream, backend, model, *, timeout=200):
    app = FastAPI()
    client = httpx.AsyncClient(
        base_url=upstream, timeout=httpx.Timeout(60, connect=2), trust_env=False
    )
    log = []

    @app.post("/api/chat")
    async def chat(request: Request):
        body = await request.json()
        started = time.monotonic()
        try:
            structured, (prompt_tokens, completion_tokens) = await ask_backend(
                backend, model, body, timeout=timeout
            )
            message = to_ollama_message(structured)
        except (InvalidRound, json.JSONDecodeError, KeyError) as exc:
            log.append({"ok": False, "error": str(exc)[:300]})
            return JSONResponse({"error": f"subscription_bridge_invalid: {exc}"}, status_code=502)
        elapsed = time.monotonic() - started
        log.append(
            {
                "ok": True,
                "seconds": round(elapsed, 2),
                "tool_calls": len(message.get("tool_calls", [])),
                "offered_tools": sorted(
                    (t.get("function") or {}).get("name", "?") for t in body.get("tools", [])
                ),
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
            }
        )
        final = {
            "model": body.get("model"),
            "message": message,
            "done": True,
            "done_reason": "stop",
            "total_duration": int(elapsed * 1e9),
            "prompt_eval_count": 0,
            "eval_count": completion_tokens,
            "bridge_usage": {
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
            },
            "bridge_backend": f"{backend}:{model}",
        }
        if body.get("stream", True) is False:
            return JSONResponse(final)

        async def frames():
            yield (
                json.dumps(
                    {"model": body.get("model"), "message": message, "done": False},
                    ensure_ascii=False,
                )
                + "\n"
            )
            yield (
                json.dumps(
                    {**final, "message": {"role": "assistant", "content": ""}}, ensure_ascii=False
                )
                + "\n"
            )

        return StreamingResponse(frames(), media_type="application/x-ndjson")

    @app.post("/api/generate")
    async def generate(request: Request):
        # Only keep_alive=0 unloads reach here; never unload the shared local model, which a
        # concurrent local run may be using.
        return JSONResponse({"done": True, "done_reason": "unload"})

    @app.get("/bridge/log")
    async def bridge_log():
        return {"backend": f"{backend}:{model}", "rounds": log}

    @app.api_route("/{path:path}", methods=["GET", "POST", "DELETE"])
    async def proxy(path: str, request: Request):
        response = await client.request(
            request.method,
            f"/{path}",
            content=await request.body(),
            headers={"content-type": "application/json"},
        )
        return Response(
            response.content,
            status_code=response.status_code,
            media_type=response.headers.get("content-type"),
        )

    return app


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--backend", choices=("codex", "claude"), required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--port", type=int, default=11500)
    parser.add_argument("--upstream", default="http://127.0.0.1:11434")
    parser.add_argument("--timeout", type=float, default=200)
    args = parser.parse_args(argv)
    app = bridge_app(args.upstream, args.backend, args.model, timeout=args.timeout)
    uvicorn.run(app, host="127.0.0.1", port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
