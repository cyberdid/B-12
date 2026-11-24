"""CliModel: a subscription CLI as Capri's model (ADR-023), tested with a fake runner."""

import asyncio
import json

import pytest

from b12.cloud_model import CliModel, split_messages
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
    assert argv[:2] == ["claude", "-p"] and "Ти Capri." in argv
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
    failing = _runner(RuntimeError("backend exit 1: You've hit your usage limit"))
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
