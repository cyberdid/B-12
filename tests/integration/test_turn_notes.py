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
        {"tool_calls": [("file_read", {"path": str(big), "offset": offset})]}
        for offset in range(0, big.stat().st_size, 2400)
    ] + [{"content": "Прочитано."}]
    result, _ = await run_turn(runtime, who, "прочитай весь файл", persist=True)
    assert result.state == "completed", result.error_code
    assert refusals, "the tight budget was never hit, so the retry was not exercised"


async def test_a_persist_read_result_reminds_the_model_to_write_findings(runtime_factory, tmp_path):
    """Regression: 80 reads and no note_add; the report covered only the first file."""
    state, factory = runtime_factory
    runtime = factory()
    who = owner(runtime, capabilities=NOTE_CAPABILITIES)
    small = tmp_path / "a.sh"
    small.write_text("echo one\n")
    state["script"] = [
        {"tool_calls": [("file_read", {"path": str(small)})]},
        {"content": "Прочитано."},
    ]
    await run_turn(runtime, who, "прочитай", persist=True)
    tool_texts = [m["content"] for m in state["requests"][-1]["messages"] if m["role"] == "tool"]
    assert any("note_add" in text for text in tool_texts), "the read result carries no reminder"


async def test_rereading_a_chunk_does_not_consume_the_new_chunk_budget(runtime_factory, tmp_path):
    state, factory = runtime_factory
    runtime = factory()
    who = owner(runtime, capabilities=NOTE_CAPABILITIES)
    target = tmp_path / 'script.sh'
    target.write_text('x' * 17000)
    offsets = [offset for offset in range(0, 14400, 2400) for _ in range(2)] + [14400]
    state['script'] = [
        {'tool_calls': [('file_read', {'path': str(target), 'offset': offset})]}
        for offset in offsets
    ] + [{'content': 'прочитано'}]
    result, _ = await run_turn(runtime, who, 'прочитай файл', persist=True)
    reads = [r for r in result.tool_results if r.name == 'file_read']
    assert len(reads) == 13
    assert all(r.status == 'completed' for r in reads), [r.error_code for r in reads]


async def test_grep_does_not_count_as_reading_a_listed_file(runtime_factory, tmp_path):
    state, factory = runtime_factory
    runtime = factory()
    who = owner(runtime, capabilities=NOTE_CAPABILITIES)
    folder = tmp_path / 'project'
    folder.mkdir()
    target = folder / 'review.sh'
    target.write_text('echo needle\necho important\n')
    state['script'] = [
        {'tool_calls': [('file_list', {'path': str(folder)})]},
        {'tool_calls': [('run_command', {'command': f'grep needle {target}',
                                        'cwd': str(folder), 'declared_effects': ['read-only']})]},
        {'content': 'ГОТОВО'},
        {'tool_calls': [('file_read', {'path': str(target)})]},
        {'content': 'Прочитано. ГОТОВО'},
    ]
    result, _ = await run_turn(runtime, who, 'прочитай всі файли', persist=True)
    assert any(r.name == 'run_command' and r.status == 'completed' for r in result.tool_results)
    assert any(r.name == 'file_read' and r.status == 'completed' for r in result.tool_results)


async def test_reading_only_the_tail_does_not_claim_full_coverage(runtime_factory, tmp_path):
    state, factory = runtime_factory
    runtime = factory()
    who = owner(runtime, capabilities=NOTE_CAPABILITIES)
    target = tmp_path / 'tail.py'
    target.write_text('x' * 3000)
    state['script'] = [
        {'tool_calls': [('file_read', {'path': str(target), 'offset': 2400})]},
        {'content': 'ГОТОВО'},
        {'tool_calls': [('file_read', {'path': str(target), 'offset': 0})]},
        {'content': 'Тепер файл прочитано. ГОТОВО'},
    ]
    result, _ = await run_turn(runtime, who, 'прочитай весь файл', persist=True)
    reads = [r for r in result.tool_results if r.name == 'file_read']
    assert [r.content['offset'] for r in reads] == [2400, 0]
    assert 'Не дочитано' not in result.content
