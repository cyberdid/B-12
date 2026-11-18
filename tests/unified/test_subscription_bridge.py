"""The subscription bridge translates Ollama chat rounds and rejects backend side effects."""

import json

import pytest

from evals.subscription_bridge import (
    InvalidRound,
    codex_events_ok,
    codex_overrides,
    split_messages,
    to_ollama_message,
)


def test_system_message_is_separated_and_tools_are_listed():
    body = {
        "messages": [
            {"role": "system", "content": "Ти Capri."},
            {"role": "user", "content": "Привіт"},
        ],
        "tools": [{"type": "function", "function": {"name": "file_read"}}],
    }
    system, text = split_messages(body)
    assert system == "Ти Capri."
    assert "file_read" in text and "Привіт" in text and "Ти Capri." not in text


def test_structured_answer_becomes_an_ollama_tool_call():
    message = to_ollama_message(
        {
            "content": "",
            "tool_calls": [
                {"name": "file_read", "arguments_json": json.dumps({"path": "/sandbox/a"})}
            ],
        }
    )
    assert message["tool_calls"] == [
        {"function": {"name": "file_read", "arguments": {"path": "/sandbox/a"}}}
    ]
    with pytest.raises(InvalidRound):
        to_ollama_message({"content": "", "tool_calls": [{"name": "x", "arguments_json": "[1]"}]})


def test_codex_side_effects_invalidate_the_round():
    ok = "\n".join(
        json.dumps(e)
        for e in [
            {"type": "item.completed", "item": {"type": "error", "message": "deprecated"}},
            {"type": "item.completed", "item": {"type": "agent_message", "text": "{}"}},
        ]
    )
    codex_events_ok(ok)
    bad = json.dumps({"type": "item.completed", "item": {"type": "command_execution"}})
    with pytest.raises(InvalidRound, match="command_execution"):
        codex_events_ok(bad)


def test_every_configured_mcp_server_is_disabled(tmp_path):
    config = tmp_path / "config.toml"
    config.write_text(
        '[mcp_servers.android]\ncommand = "x"\n[mcp_servers."ida-pro-mcp"]\ncommand = "y"\n',
        encoding="utf-8",
    )
    args = codex_overrides(config)
    assert "mcp_servers.android.enabled=false" in args
    assert "mcp_servers.ida-pro-mcp.enabled=false" in args
    assert args[:2] == ["--disable", "apps"]
