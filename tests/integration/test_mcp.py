"""MCP bridge over a real stdio child process and the real registry/control path."""

import asyncio
import json
import os
import sys
from pathlib import Path

import pytest

from b12.contracts import ToolCall

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "mcp_server.py"


@pytest.fixture
async def bridge(host_factory):
    from b12.tools.mcp import McpServer, register_server

    rig = host_factory(capabilities=("mcp.fixture", "time.read"))
    server = McpServer("fixture", [sys.executable, str(FIXTURE)])
    await server.start()
    skipped = await register_server(rig.registry, server, capability="mcp.fixture")
    yield rig, server, skipped
    await server.aclose()


async def call(rig, name, **arguments):
    from uuid import uuid4

    return await rig.registry.execute(
        ToolCall(id=str(uuid4()), name=name, arguments=arguments), rig.context
    )


async def test_discovery_registers_supported_tools_and_skips_unsupported(bridge):
    rig, _, skipped = bridge
    names = {s["function"]["name"] for s in rig.registry.schemas(rig.context)}
    assert {"mcp.fixture.echo", "mcp.fixture.add", "mcp.fixture.write_note"} <= names
    assert skipped == ["union"]
    assert "anyOf" not in json.dumps(rig.registry.schemas(rig.context))


async def test_results_errors_and_argument_validation_pass_through_policy(bridge, tmp_path):
    rig, _, _ = bridge
    echo = await call(rig, "mcp.fixture.echo", text="привіт")
    assert (echo.status, echo.content["text"]) == ("completed", "привіт")
    total = await call(rig, "mcp.fixture.add", a=2, b=3.5)
    assert total.content["text"] == "5.5"
    bad = await call(rig, "mcp.fixture.add", a="x", b=1)
    assert (bad.status, bad.error_code) == ("denied", "invalid_arguments")
    extra = await call(rig, "mcp.fixture.echo", text="x", injected=True)
    assert extra.error_code == "invalid_arguments"
    failed = await call(rig, "mcp.fixture.fail")
    assert failed.status == "unknown" and failed.outcome_unknown
    assert failed.side_effects[0]["kind"] == "mcp_call"
    note = tmp_path / "note.txt"
    written = await call(rig, "mcp.fixture.write_note", path=str(note), text="з MCP")
    assert written.status == "completed" and note.read_text() == "з MCP"


async def test_capability_is_enforced_by_control(host_factory):
    from b12.tools.mcp import McpServer, register_server

    rig = host_factory(capabilities=("time.read",))
    server = McpServer("fixture", [sys.executable, str(FIXTURE)])
    await server.start()
    try:
        await register_server(rig.registry, server, capability="mcp.fixture")
        assert not any("mcp." in s["function"]["name"] for s in rig.registry.schemas(rig.context))
        denied = await call(rig, "mcp.fixture.echo", text="x")
        assert denied.error_code == "capability_denied"
    finally:
        await server.aclose()


async def test_cancel_notifies_server_and_reports_unknown(bridge):
    rig, _, _ = bridge
    task = asyncio.create_task(call(rig, "mcp.fixture.slow", seconds=30))
    await asyncio.sleep(0.3)
    rig.context.cancel.set()
    result = await asyncio.wait_for(task, 5)
    assert result.status == "unknown" and result.error_code == "cancelled"


async def test_builtin_names_cannot_be_shadowed(host_factory):
    from b12.tools.mcp import McpServer, register_server

    rig = host_factory(capabilities=("mcp.fixture",))
    server = McpServer("fixture", [sys.executable, str(FIXTURE)])
    await server.start()
    try:
        await register_server(rig.registry, server, capability="mcp.fixture")
        with pytest.raises(ValueError):
            await register_server(rig.registry, server, capability="mcp.fixture")
        assert "file_read" in {t["name"] for t in rig.registry.catalog()}
        assert all(
            t["name"].startswith("mcp.") or t["capability"] != "mcp.fixture"
            for t in rig.registry.catalog()
        )
    finally:
        await server.aclose()


async def test_close_terminates_server_process_group(host_factory):
    from b12.tools.mcp import McpServer

    server = McpServer("fixture", [sys.executable, str(FIXTURE)])
    await server.start()
    pid = server.process.pid
    await server.aclose()
    with pytest.raises(ProcessLookupError):
        os.kill(pid, 0)


async def test_catalog_attaches_to_runtime_and_agent_uses_mcp_tool(scripted_ollama, tmp_path):
    from b12.runtime import open_runtime
    from b12.tools.mcp import attach_catalog

    state, base = scripted_ollama
    settings = base.model_copy(update={"state_dir": tmp_path / "state"})
    settings.state_dir.mkdir(parents=True)
    (settings.state_dir / "mcp.json").write_text(
        json.dumps(
            [
                {
                    "name": "fixture",
                    "command": [sys.executable, str(FIXTURE)],
                    "capability": "mcp.fixture",
                }
            ]
        )
    )
    runtime = open_runtime(settings)
    try:
        report = await attach_catalog(runtime)
        assert report == {"fixture": {"skipped": ["union"]}}
        actor = runtime.control.create_actor(owner=True, consent=True)
        session = runtime.control.create_session(actor.id)
        grant = runtime.control.issue_grant(actor.id, session, ("mcp.fixture",))
        state["script"] = [
            {"tool_calls": [("mcp.fixture.add", {"a": 40, "b": 2})]},
            lambda request: {
                "content": "Сума: "
                + json.loads(request["messages"][-1]["content"])["content"]["text"]
            },
        ]
        result = await runtime.agent.turn(session, grant, "додай")
        assert result.state == "completed" and result.content == "Сума: 42.0"
    finally:
        runtime.close()


async def test_optional_parameters_are_normalized_and_omitted_when_unset(bridge):
    rig, _, _ = bridge
    schema = next(
        s for s in rig.registry.schemas(rig.context) if s["function"]["name"] == "mcp.fixture.maybe"
    )
    assert "anyOf" not in json.dumps(schema)
    assert schema["function"]["parameters"].get("required", []) == []
    unset = await call(rig, "mcp.fixture.maybe")
    assert unset.content["text"] == "{}"
    given = await call(rig, "mcp.fixture.maybe", v="так")
    assert given.content["text"] == "{'v': 'так'}"
