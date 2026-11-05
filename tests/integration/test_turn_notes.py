"""Working notes survive history trimming; a long script is read whole in persist turns."""

from tests.integration import test_agent_loop as base

owner = base.owner
run_turn = base.run_turn
runtime_factory = base.runtime_factory  # fixture, re-exported for this module
NOTE_CAPABILITIES = (*base.CAPABILITIES, "turn.notes")


async def test_a_note_survives_history_trimming_in_a_persist_turn(runtime_factory, tmp_path):
    state, factory = runtime_factory
    runtime = factory()
    who = owner(runtime, capabilities=NOTE_CAPABILITIES)
    big = tmp_path / "script.sh"
    big.write_text("echo line\n" * 900)  # about 9 KB: four 2400-byte chunks
    marker = "ФІНДИНГ-17: auditd.conf має admin_space_left_action = HALT"
    state["script"] = [
        {"tool_calls": [("note_add", {"text": marker})]},
        {"tool_calls": [("file_read", {"path": str(big)})]},
        {"tool_calls": [("file_read", {"path": str(big), "offset": 2400})]},
        {"tool_calls": [("file_read", {"path": str(big), "offset": 4800})]},
        {"tool_calls": [("file_read", {"path": str(big), "offset": 7200})]},
        {"tool_calls": [("file_read", {"path": str(big), "offset": 8400})]},
        {"content": "Звіт: " + marker},
    ]
    result, _ = await run_turn(runtime, who, "перевір скрипт", persist=True)
    assert result.state == "completed"
    last_request = state["requests"][-1]["messages"]
    assert [r.status for r in result.tool_results if r.name == "note_add"] == ["completed"]
    journal = [
        m["content"]
        for m in last_request
        if m["role"] == "user" and (m.get("content") or "").startswith("[журнал знахідок]")
    ]
    assert journal and marker in journal[-1], "the journal block is missing from the request"
    assert any(
        (m.get("content") or "").endswith("…[скорочено]")
        for m in last_request
        if m["role"] == "tool"
    ), "history was never trimmed, so the test does not prove anything"


async def test_a_nine_kilobyte_script_is_read_whole_without_the_chunk_stop(
    runtime_factory, tmp_path
):
    state, factory = runtime_factory
    runtime = factory()
    who = owner(runtime, capabilities=NOTE_CAPABILITIES)
    big = tmp_path / "script.sh"
    big.write_text("echo line\n" * 900)
    offsets = [0, 2400, 4800, 7200, 8400]
    state["script"] = [
        {"tool_calls": [("file_read", {"path": str(big), **({"offset": o} if o else {})})]}
        for o in offsets
    ] + [{"content": "прочитано"}]
    result, _ = await run_turn(runtime, who, "прочитай весь файл", persist=True)
    reads = [r for r in result.tool_results if r.name == "file_read"]
    assert len(reads) == len(offsets)
    assert all(r.status == "completed" for r in reads), [r.error_code for r in reads]


async def test_a_persist_turn_shrinks_history_until_the_request_fits(runtime_factory, tmp_path):
    """Regression: a long review ended with context_overflow after 35 calls. When the request does
    not fit, the window must shrink and retry, not end the turn."""
    from b12.model_errors import ModelError

    state, factory = runtime_factory
    runtime = factory()
    who = owner(runtime, capabilities=NOTE_CAPABILITIES)
    original = runtime.agent.builder.build
    refusals = []

    def tight(system, messages, evidence=(), tools=()):
        total = sum(len(m.get("content") or "") for m in messages)
        if total > 4000:
            refusals.append(total)
            raise ModelError("context_overflow", "test budget")
        return original(system, messages, evidence, tools)

    runtime.agent.builder.build = tight
    big = tmp_path / "script.sh"
    big.write_text("echo line\n" * 1500)  # about 15 KB: six chunks
    state["script"] = [
        {"tool_calls": [("file_read", {"path": str(big), "offset": i * 2400})]} for i in range(6)
    ] + [{"content": "Прочитано."}]
    result, _ = await run_turn(runtime, who, "прочитай весь файл", persist=True)
    assert result.state == "completed", result.error_code
    assert refusals, "the tight budget was never hit, so the retry was not exercised"
