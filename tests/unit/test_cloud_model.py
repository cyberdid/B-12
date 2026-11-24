"""CliModel: a subscription CLI as Capri's model (ADR-023), tested with a fake runner."""

import asyncio
import json
import os
import time as _time
from pathlib import Path

import pytest

from b12.cloud_model import CliModel, _run, split_messages
from b12.model_errors import ModelError


class Request:
    """The two fields CliModel reads from an AdmittedRequest."""

    def __init__(self, messages, tools=()):
        self.messages = tuple(messages)
        self.tools = tuple(tools)


REQUEST = Request(
    [
        {"role": "system", "content": "Ти Capri."},
        {"role": "user", "content": "Що в /tmp?"},
    ],
    [{"type": "function", "function": {"name": "file_list", "parameters": {}}}],
)


def _claude(structured):
    return json.dumps({"is_error": False, "structured_output": structured, "usage": {}})


def _runner(output, seen=None):
    async def run(argv, stdin_text, cwd, timeout):
        if seen is not None:
            seen.append((argv, stdin_text))
        if isinstance(output, Exception):
            raise output
        return output

    return run


async def test_claude_reply_becomes_model_reply_with_tool_calls():
    seen = []
    answer = {
        "content": "Дивлюсь.",
        "tool_calls": [{"name": "file_list", "arguments_json": '{"path": "/tmp"}'}],
    }
    model = CliModel("claude", "claude-opus-5-5", runner=_runner(_claude(answer), seen))
    deltas = []

    async def on_delta(text):
        deltas.append(text)

    reply = await model.chat(REQUEST, on_delta=on_delta)
    assert reply.content == "Дивлюсь." and deltas == ["Дивлюсь."]
    (call,) = reply.tool_calls
    assert (call.name, call.arguments) == ("file_list", {"path": "/tmp"})
    assert reply.finish_reason == "stop"
    argv, stdin_text = seen[0]
    assert argv[:2] == ["claude", "-p"] and "--system-prompt-file" in argv
    assert "file_list" in stdin_text


async def test_arguments_that_are_not_an_object_are_rejected():
    answer = {"content": "", "tool_calls": [{"name": "file_list", "arguments_json": "[1]"}]}
    model = CliModel("claude", "m", runner=_runner(_claude(answer)))
    with pytest.raises(ModelError, match="invalid_tool_call"):
        await model.chat(REQUEST)


async def test_codex_round_that_ran_its_own_command_is_rejected(tmp_path):
    events = "\n".join(
        [
            json.dumps({"type": "item.completed", "item": {"type": "command_execution"}}),
            json.dumps({"type": "turn.completed", "usage": {}}),
        ]
    )
    model = CliModel("codex", "gpt-6-luna", runner=_runner(events))
    with pytest.raises(ModelError, match="invalid_round"):
        await model.chat(REQUEST)


async def test_codex_answer_is_read_from_its_output_file():
    answer = {"content": "Готово.", "tool_calls": []}

    async def run(argv, stdin_text, cwd, timeout):
        out = argv[argv.index("-o") + 1]
        with open(out, "w", encoding="utf-8") as handle:
            json.dump(answer, handle, ensure_ascii=False)
        return json.dumps({"type": "item.completed", "item": {"type": "agent_message"}})

    reply = await CliModel("codex", "gpt-6-luna", runner=run).chat(REQUEST)
    assert reply.content == "Готово." and reply.tool_calls == ()


async def test_agy_response_json_is_parsed():
    answer = {"content": "Привіт.", "tool_calls": []}
    out = json.dumps({"status": "SUCCESS", "response": json.dumps(answer, ensure_ascii=False)})
    reply = await CliModel("agy", "", runner=_runner(out)).chat(REQUEST)
    assert reply.content == "Привіт."


async def test_cli_failure_is_a_transport_error():
    failing = _runner(RuntimeError("backend exit 1: connection reset by peer"))
    with pytest.raises(ModelError, match="transport_error"):
        await CliModel("codex", "gpt-6-luna", runner=failing).chat(REQUEST)


async def test_cancel_before_the_call_returns_cancelled():
    cancel = asyncio.Event()
    cancel.set()
    model = CliModel("claude", "m", runner=_runner(_claude({"content": "x", "tool_calls": []})))
    with pytest.raises(ModelError, match="cancelled"):
        await model.chat(REQUEST, cancel=cancel)


def test_prompt_carries_tools_and_conversation_but_not_the_system_text():
    system, text = split_messages(
        {"messages": list(REQUEST.messages), "tools": list(REQUEST.tools)}
    )
    assert system == "Ти Capri."
    assert "Що в /tmp?" in text and "file_list" in text and "Ти Capri." not in text


# --- final review fixes (24.11.2026) ---


def _sleeping_runner(pid_box):
    """A real subprocess standing in for the CLI: records its pid, then sleeps."""

    async def run(argv, stdin_text, cwd, timeout):
        pid_file = Path(cwd) / "pid"
        return (
            await _run(
                ["bash", "-c", f"echo $$ > {pid_file}; exec sleep 30"], stdin_text, cwd, timeout
            )
            if not pid_box.append(pid_file)
            else None
        )

    return run


def _wait_gone(pid, seconds=3.0):
    end = _time.monotonic() + seconds
    while _time.monotonic() < end:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return True
        _time.sleep(0.05)
    return False


async def _pid(pid_box):
    for _ in range(100):
        if pid_box and pid_box[0].exists() and pid_box[0].read_text().strip():
            return int(pid_box[0].read_text())
        await asyncio.sleep(0.05)
    raise AssertionError("CLI stand-in did not start")


async def test_cancel_kills_the_cli_process():
    box, cancel = [], asyncio.Event()
    model = CliModel("claude", "m", runner=_sleeping_runner(box))
    call = asyncio.create_task(model.chat(REQUEST, cancel=cancel))
    pid = await _pid(box)
    cancel.set()
    with pytest.raises(ModelError, match="cancelled"):
        await call
    assert _wait_gone(pid)


async def test_cancelling_the_turn_task_kills_the_cli_process():
    box = []
    model = CliModel("claude", "m", runner=_sleeping_runner(box))
    call = asyncio.create_task(model.chat(REQUEST))
    pid = await _pid(box)
    call.cancel()
    with pytest.raises(asyncio.CancelledError):
        await call
    assert _wait_gone(pid)


async def test_the_runner_gets_the_deadline_not_the_default_timeout():
    seen = []

    async def run(argv, stdin_text, cwd, timeout):
        seen.append(timeout)
        return _claude({"content": "ok", "tool_calls": []})

    await CliModel("claude", "m", runner=run).chat(REQUEST, deadline=_time.monotonic() + 5)
    assert seen and seen[0] <= 5


async def test_claude_gets_the_system_prompt_from_a_file_not_argv():
    seen = []
    await CliModel(
        "claude", "m", runner=_runner(_claude({"content": "x", "tool_calls": []}), seen)
    ).chat(REQUEST)
    argv = seen[0][0]
    assert "--system-prompt-file" in argv and "Ти Capri." not in argv


async def test_agy_refuses_a_prompt_too_long_for_one_argument():
    long = Request([{"role": "system", "content": "s"}, {"role": "user", "content": "я" * 80000}])
    called = []
    with pytest.raises(ModelError, match="prompt_too_long"):
        await CliModel("agy", "", runner=_runner("{}", called)).chat(long)
    assert called == []


async def test_cli_failure_keeps_the_stdout_tail(tmp_path):
    with pytest.raises(RuntimeError, match="usage limit"):
        await _run(["bash", "-c", "echo 'You hit your usage limit'; exit 1"], "", tmp_path, 10)


async def test_a_subscription_limit_has_its_own_code():
    failing = _runner(
        RuntimeError("backend exit 1: You've hit your usage limit. Try again at 11:58")
    )
    with pytest.raises(ModelError, match="quota_exceeded"):
        await CliModel("codex", "gpt-6-luna", runner=failing).chat(REQUEST)
