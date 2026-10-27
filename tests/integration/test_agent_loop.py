"""Agent loop over real stores, real host tools and real HTTP/NDJSON transport."""

import asyncio
import json
from types import SimpleNamespace

import pytest

CAPABILITIES = (
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
)
TERMINAL = {"turn_completed", "turn_failed", "turn_cancelled"}


@pytest.fixture
def runtime_factory(scripted_ollama, tmp_path):
    from b12.runtime import open_runtime

    state, base = scripted_ollama
    opened = []

    def factory(**overrides):
        settings = base.model_copy(update={"state_dir": tmp_path / "state", **overrides})
        runtime = open_runtime(settings)
        opened.append(runtime)
        return runtime

    yield state, factory
    for runtime in opened:
        runtime.close()


def owner(runtime, *, consent=True, capabilities=CAPABILITIES):
    actor = runtime.control.create_actor(owner=True, consent=consent)
    session = runtime.control.create_session(actor.id)
    task = runtime.control.create_task(session)
    grant = runtime.control.issue_grant(
        actor.id, session, capabilities, task_id=task, full_execution=True
    )
    return SimpleNamespace(actor=actor, session=session, task=task, grant=grant)


async def run_turn(runtime, who, text, **kwargs):
    events = []

    async def record(event):
        events.append(event)

    result = await runtime.agent.turn(
        who.session, who.grant, text, task_id=who.task, on_event=record, **kwargs
    )
    return result, events


def assert_event_stream(events, result, *, terminal):
    assert [e.sequence for e in events] == list(range(1, len(events) + 1))
    assert {(e.turn_id, e.session_id) for e in events} == {(result.turn_id, result.session_id)}
    assert events[0].type == "turn_started"
    assert [e.type for e in events if e.type in TERMINAL] == [terminal]
    assert events[-1].type == terminal


def tool_messages(request):
    return [m for m in request["messages"] if m["role"] == "tool"]


async def test_model_drives_real_file_write_then_read_and_grounded_final(runtime_factory, tmp_path):
    state, factory = runtime_factory
    runtime = factory()
    who = owner(runtime)
    target = tmp_path / "sandbox" / "note.txt"
    target.parent.mkdir()

    def final(request):
        observed = json.loads(tool_messages(request)[-1]["content"])
        return {"content": "Файл містить: " + observed["content"]["text"]}

    state["script"] = [
        {"tool_calls": [("file_write", {"path": str(target), "text": "синтетичний вміст 42"})]},
        {"tool_calls": [("file_read", {"path": str(target)})]},
        final,
    ]
    result, events = await run_turn(runtime, who, "Запиши і прочитай файл")
    assert target.read_text() == "синтетичний вміст 42"
    assert result.state == "completed" and result.persisted
    assert result.content == "Файл містить: синтетичний вміст 42"
    assert [(r.name, r.status) for r in result.tool_results] == [
        ("file_write", "completed"),
        ("file_read", "completed"),
    ]
    assert_event_stream(events, result, terminal="turn_completed")
    started = [e.data["call_id"] for e in events if e.type == "tool_started"]
    finished = [e.data["call_id"] for e in events if e.type == "tool_result"]
    assert started == finished == [r.call_id for r in result.tool_results]
    third = state["requests"][2]
    assert [m["tool_call_id"] for m in tool_messages(third)] == started
    assert "".join(e.data["text"] for e in events if e.type == "text_delta") == result.content


async def test_errors_unknown_and_invalid_calls_become_structured_results(
    runtime_factory, tmp_path
):
    state, factory = runtime_factory
    runtime = factory()
    who = owner(runtime)
    state["script"] = [
        {
            "tool_calls": [
                ("teleport", {"where": "Mars"}),
                ("file_read", {"path": "relative/path"}),
                ("file_read", {"path": str(tmp_path / "missing")}),
            ]
        },
        {"content": "Жоден виклик не вдався."},
    ]
    result, events = await run_turn(runtime, who, "спробуй")
    assert result.state == "completed"
    assert [(r.status, r.error_code) for r in result.tool_results] == [
        ("denied", "unknown_tool"),
        ("denied", "invalid_arguments"),
        ("failed", "not_found"),
    ]
    payloads = [json.loads(m["content"]) for m in tool_messages(state["requests"][1])]
    assert [p["error_code"] for p in payloads] == ["unknown_tool", "invalid_arguments", "not_found"]
    assert_event_stream(events, result, terminal="turn_completed")


async def test_duplicate_call_id_across_rounds_is_not_executed_again(runtime_factory, tmp_path):
    state, factory = runtime_factory
    runtime = factory()
    who = owner(runtime)
    target = tmp_path / "dup.txt"
    call = ("file_write", {"path": str(target), "text": "once"}, "dup-id")
    state["script"] = [{"tool_calls": [call]}, {"tool_calls": [call]}, {"content": "ok"}]
    target_text = []

    result, _ = await run_turn(runtime, who, "двічі")
    target_text.append(target.read_text())
    assert [(r.status, r.error_code) for r in result.tool_results] == [
        ("completed", None),
        ("denied", "duplicate_call_id"),
    ]
    assert target_text == ["once"]


async def test_tool_call_budget_blocks_excess_calls_without_effects(runtime_factory, tmp_path):
    state, factory = runtime_factory
    runtime = factory(max_tool_calls=2)
    who = owner(runtime)
    paths = [tmp_path / f"f{i}" for i in range(3)]
    state["script"] = [
        {"tool_calls": [("file_write", {"path": str(p), "text": "x"}) for p in paths]},
        {"content": "ліміт"},
    ]
    result, _ = await run_turn(runtime, who, "три файли")
    assert [p.exists() for p in paths] == [True, True, False]
    assert result.tool_results[-1].error_code == "tool_call_limit"


async def test_round_limit_withholds_tools_and_fails_honestly(runtime_factory, tmp_path):
    state, factory = runtime_factory
    runtime = factory(max_rounds=2)
    who = owner(runtime)
    call = ("current_time", {})
    state["script"] = [{"tool_calls": [call]}, {"tool_calls": [call]}]
    result, events = await run_turn(runtime, who, "цикл")
    assert state["requests"][0]["tools"] and state["requests"][1]["tools"] == []
    assert result.state == "failed" and result.error_code == "max_rounds"
    assert not result.persisted
    assert_event_stream(events, result, terminal="turn_failed")


async def test_cancel_during_stream_discards_text_and_persists_nothing(runtime_factory):
    state, factory = runtime_factory
    runtime = factory()
    who = owner(runtime)
    cancel = asyncio.Event()
    state["script"] = [{"content": "частковий текст", "hang": True}]
    task = asyncio.create_task(run_turn(runtime, who, "довго", cancel=cancel))
    await asyncio.wait_for(state["chat_started"].wait(), 2)
    await asyncio.sleep(0.05)
    cancel.set()
    result, events = await asyncio.wait_for(task, 2)
    assert result.state == "cancelled" and result.content == "" and not result.persisted
    assert_event_stream(events, result, terminal="turn_cancelled")
    assert runtime.sessions.history(who.session, who.actor.id) == []


async def test_no_consent_history_is_volatile_and_tools_are_withheld(runtime_factory):
    state, factory = runtime_factory
    runtime = factory()
    who = owner(runtime, consent=False)
    state["script"] = [{"content": "перша"}, {"content": "друга"}]
    first, _ = await run_turn(runtime, who, "Мене звати Тест")
    second, _ = await run_turn(runtime, who, "Як мене звати?")
    assert first.state == second.state == "completed"
    assert not first.persisted and not second.persisted
    assert state["requests"][0]["tools"] == []
    contents = [m["content"] for m in state["requests"][1]["messages"]]
    assert "Мене звати Тест" in contents and "перша" in contents
    assert runtime.sessions.history(who.session, who.actor.id) == []
    runtime.close()
    fresh = factory()
    state["script"] = [{"content": "нова"}]
    await fresh.agent.turn(who.session, who.grant, "привіт", task_id=who.task)
    assert "Мене звати Тест" not in json.dumps(state["requests"][-1], ensure_ascii=False)


async def test_same_session_turns_serialize_and_share_history(runtime_factory):
    state, factory = runtime_factory
    runtime = factory()
    who = owner(runtime)
    state["script"] = [{"content": "A"}, {"content": "B"}]
    results = await asyncio.gather(run_turn(runtime, who, "перше"), run_turn(runtime, who, "друге"))
    assert {r.state for r, _ in results} == {"completed"}
    second_request = [m["content"] for m in state["requests"][1]["messages"]]
    assert "A" in second_request
    assert len(runtime.sessions.history(who.session, who.actor.id)) == 4


async def test_grant_from_another_session_is_rejected_before_events(runtime_factory):
    state, factory = runtime_factory
    runtime = factory()
    first, second = owner(runtime), owner(runtime)
    events = []

    async def record(event):
        events.append(event)

    with pytest.raises(PermissionError):
        await runtime.agent.turn(
            second.session, first.grant, "чужий grant", task_id=first.task, on_event=record
        )
    assert events == [] and state["requests"] == []


async def test_memory_store_recall_forget_and_restart_leave_no_payload(runtime_factory):
    state, factory = runtime_factory
    runtime = factory()
    who = owner(runtime)
    secret = "мій тестовий PIN 4321"
    state["script"] = [
        {"tool_calls": [("memory_store", {"text": secret})]},
        {"content": "Запам'ятав."},
    ]
    stored, _ = await run_turn(runtime, who, "Запам'ятай: " + secret)
    memory_id = stored.tool_results[0].content["id"]
    assert stored.persisted
    runtime.close()

    runtime = factory()
    state["script"] = [{"content": "Твій PIN 4321."}]
    recalled, _ = await run_turn(runtime, who, "Який мій тестовий PIN?")
    system = state["requests"][-1]["messages"][0]["content"]
    assert memory_id in system and "4321" in system
    assert recalled.persisted

    state["script"] = [
        {"tool_calls": [("memory_forget", {"memory_id": memory_id})]},
        {"content": "Забув."},
    ]
    waiting, events = await run_turn(runtime, who, "Забудь мій PIN")
    assert waiting.state == "awaiting_approval" and waiting.pending_operations
    assert events[-1].type == "approval_pending"
    assert not [e for e in events if e.type in TERMINAL]
    runtime.control.decide_approval(waiting.pending_operations[0], True)
    resumed_events = []

    async def record(event):
        resumed_events.append(event)

    done = await runtime.agent.resume(waiting.turn_id, on_event=record)
    assert done.state == "completed", done
    forget = done.tool_results[-1]
    assert forget.name == "memory_forget" and forget.status == "completed"
    assert forget.content["receipt"]["state"] == "complete"
    assert resumed_events[0].sequence == events[-1].sequence + 1
    assert [e.type for e in resumed_events if e.type in TERMINAL] == ["turn_completed"]
    assert not done.persisted
    assert state["unloads"] >= 1
    runtime.close()

    runtime = factory()
    assert runtime.memory.search("PIN", who.actor) == []
    assert runtime.sessions.history(who.session, who.actor.id) == []
    state_dir = runtime.settings.state_dir
    for path in state_dir.rglob("*"):
        if path.is_file():
            assert b"PIN 4321" not in path.read_bytes(), path


async def test_approval_checkpoint_survives_restart(runtime_factory):
    state, factory = runtime_factory
    runtime = factory()
    who = owner(runtime)
    record = runtime.memory.remember("тимчасовий факт", who.actor)
    state["script"] = [{"tool_calls": [("memory_forget", {"memory_id": record.id})]}]
    waiting, _ = await run_turn(runtime, who, "забудь")
    runtime.close()
    runtime = factory()
    runtime.control.decide_approval(waiting.pending_operations[0], True)
    state["script"] = [{"content": "Готово."}]
    done = await runtime.agent.resume(waiting.turn_id)
    assert done.state == "completed"
    assert not runtime.memory.is_live(record.id, who.actor)


async def test_denied_approval_returns_structured_result_without_effect(runtime_factory):
    state, factory = runtime_factory
    runtime = factory()
    who = owner(runtime)
    record = runtime.memory.remember("залишити", who.actor)
    state["script"] = [
        {"tool_calls": [("memory_forget", {"memory_id": record.id})]},
        {"content": "Не забуто."},
    ]
    waiting, _ = await run_turn(runtime, who, "забудь")
    runtime.control.decide_approval(waiting.pending_operations[0], False)
    done = await runtime.agent.resume(waiting.turn_id)
    assert done.state == "completed"
    assert (done.tool_results[-1].status, done.tool_results[-1].error_code) == (
        "denied",
        "approval_denied",
    )
    assert runtime.memory.is_live(record.id, who.actor)


async def test_purge_invalidates_active_turn_of_same_actor(runtime_factory):
    state, factory = runtime_factory
    runtime = factory()
    who = owner(runtime)
    record = runtime.memory.remember("видалити під час turn", who.actor)
    receipts = []

    async def purge_while_waiting(request):
        receipts.append(await runtime.purge.forget(record.id, who.actor.id))
        return {"tool_calls": [("memory_store", {"text": "пізній запис"})]}

    state["script"] = [purge_while_waiting]
    result, events = await run_turn(runtime, who, "щось")
    assert result.state == "cancelled" and not result.persisted
    for _ in range(100):  # the owner purge finishes after it has stopped the turn
        if receipts:
            break
        await asyncio.sleep(0.02)
    assert receipts[0].state == "complete"
    assert runtime.memory.search("пізній", who.actor) == []
    assert_event_stream(events, result, terminal="turn_cancelled")


async def test_provider_reset_failure_keeps_receipt_pending_across_restart(runtime_factory):
    state, factory = runtime_factory
    runtime = factory()
    who = owner(runtime)
    state["loaded"] = True
    state["unload_status"] = 500
    record = runtime.memory.remember("кешований факт", who.actor)
    receipt = await runtime.purge.forget(record.id, who.actor.id)
    assert receipt.state == "pending" and receipt.pending_stores == ("provider_cache",)
    runtime.close()
    state["unload_status"] = 200
    runtime = factory()
    resumed = await runtime.purge.resume()
    assert [r.state for r in resumed] == ["complete"]
    assert await runtime.purge.resume() == []


async def test_document_removal_hides_and_purges_dependent_turns(runtime_factory, tmp_path):
    state, factory = runtime_factory
    runtime = factory()
    who = owner(runtime)
    source = tmp_path / "doc.txt"
    source.write_text("Синтетичний документ: код калібрування 9876")
    runtime.knowledge.index_document(source, who.actor)
    state["script"] = [
        {"tool_calls": [("knowledge_search", {"query": "калібрування"})]},
        {"content": "Код 9876."},
    ]
    found, _ = await run_turn(runtime, who, "знайди код")
    assert found.persisted and found.tool_results[0].content["hits"]
    runtime.knowledge.remove_document(source, who.actor)
    assert runtime.agent.history_messages(who.session, who.actor) == []
    applied = await runtime.purge.sync_knowledge(who.actor)
    assert applied and await runtime.purge.sync_knowledge(who.actor) == []
    assert runtime.sessions.history(who.session, who.actor.id) == []
    sessions_db = runtime.settings.state_dir / "sessions" / "sessions.sqlite3"
    assert "калібрування 9876".encode() not in sessions_db.read_bytes()


async def test_resume_of_cancelled_or_revoked_turn_ends_without_model_call(runtime_factory):
    state, factory = runtime_factory
    runtime = factory()
    who = owner(runtime)
    record = runtime.memory.remember("не чіпати", who.actor)
    for revoke in (False, True):
        state["script"] = [{"tool_calls": [("memory_forget", {"memory_id": record.id})]}]
        waiting, _ = await run_turn(runtime, who, "забудь")
        runtime.control.decide_approval(waiting.pending_operations[0], True)
        if revoke:
            runtime.control.revoke_grant(who.grant)
        else:
            runtime.control.cancel_turn(waiting.turn_id)
        before = len(state["requests"])
        done = await runtime.agent.resume(waiting.turn_id)
        assert done.state == ("failed" if revoke else "cancelled")
        assert done.error_code == ("grant_revoked" if revoke else "cancelled")
        assert len(state["requests"]) == before
        assert [e.type for e in done.events if e.type in TERMINAL] == [
            "turn_failed" if revoke else "turn_cancelled"
        ]
        assert runtime.memory.is_live(record.id, who.actor)


async def test_reply_language_follows_the_user_message_script(runtime_factory):
    state, factory = runtime_factory
    runtime = factory()
    who = owner(runtime)
    state["script"] = [{"content": "ok"}, {"content": "ок"}, {"content": "ok"}]
    await run_turn(runtime, who, "Explain in one sentence what a CPU does.")
    await run_turn(runtime, who, "Поясни одним реченням, що таке процесор.")
    await run_turn(runtime, who, "42")
    systems = [r["messages"][0]["content"] for r in state["requests"]]
    assert systems[0].endswith("Answer in English.")
    assert systems[1].endswith("українська.")
    assert not systems[2].endswith(("English.", "українська."))


async def test_finished_turns_release_runtime_control_state(runtime_factory):
    state, factory = runtime_factory
    runtime = factory()
    who = owner(runtime)
    state["script"] = [{"content": "ok"} for _ in range(5)]
    for _ in range(5):
        await run_turn(runtime, who, "привіт")
    assert runtime.control._runtime == {} and runtime.agent.active == {}
    record = runtime.memory.remember("не чіпати", who.actor)
    state["script"] = [{"tool_calls": [("memory_forget", {"memory_id": record.id})]}]
    waiting, _ = await run_turn(runtime, who, "забудь")
    assert waiting.state == "awaiting_approval"
    assert runtime.control._runtime == {}  # waiting turns are resumed with a fresh context


async def test_persist_mode_continues_after_text_only_replies_until_marker(
    runtime_factory, tmp_path
):
    state, factory = runtime_factory
    runtime = factory()
    who = owner(runtime)
    files = []
    for n in range(3):
        path = tmp_path / f"part{n}.txt"
        path.write_text(f"частина {n}")
        files.append(path)
    state["script"] = [
        {"tool_calls": [("file_read", {"path": str(files[0])})]},
        {"content": "Прочитав першу частину."},
        {"tool_calls": [("file_read", {"path": str(files[1])})]},
        {"content": "Прочитав другу частину."},
        {"tool_calls": [("file_read", {"path": str(files[2])})]},
        {"content": "Підсумок по трьох частинах. ГОТОВО"},
    ]
    result, _ = await run_turn(runtime, who, "Прочитай усе до кінця", persist=True)
    assert result.state == "completed" and result.content.endswith("ГОТОВО")
    assert [r.name for r in result.tool_results] == ["file_read"] * 3
    sent = state["requests"][-1]["messages"]
    nudges = [m for m in sent if m["content"].startswith("[авто-продовження]")]
    assert len(nudges) == 2


async def test_without_persist_a_text_only_reply_ends_the_turn(runtime_factory, tmp_path):
    state, factory = runtime_factory
    runtime = factory()
    who = owner(runtime)
    state["script"] = [{"content": "Прочитав першу частину."}, {"content": "не має настати"}]
    result, _ = await run_turn(runtime, who, "Прочитай усе до кінця")
    assert result.content == "Прочитав першу частину." and len(state["requests"]) == 1


async def test_persist_nudges_are_bounded(runtime_factory):
    from b12.agent import PERSIST_NUDGES

    state, factory = runtime_factory
    runtime = factory()
    who = owner(runtime)
    state["script"] = [{"content": f"крок {n}"} for n in range(PERSIST_NUDGES + 5)]
    result, _ = await run_turn(runtime, who, "Роби без кінця", persist=True)
    assert result.state == "completed" and len(state["requests"]) == PERSIST_NUDGES + 1


async def test_empty_final_reply_is_retried_once_then_answered(runtime_factory):
    state, factory = runtime_factory
    runtime = factory()
    who = owner(runtime)
    state["script"] = [{"content": ""}, {"content": "Ось відповідь."}]
    result, _ = await run_turn(runtime, who, "Скажи щось")
    assert result.state == "completed" and result.content == "Ось відповідь."


async def test_persist_blocks_early_finish_while_listed_files_are_unread(runtime_factory, tmp_path):
    state, factory = runtime_factory
    runtime = factory()
    who = owner(runtime)
    folder = tmp_path / "proj"
    folder.mkdir()
    for name in ("a.py", "b.py", "c.py"):
        (folder / name).write_text(f"# {name}")
    (folder / "notes.md").write_text("не код")

    def read(name):
        return {"tool_calls": [("file_read", {"path": str(folder / name)})]}

    state["script"] = [
        {"tool_calls": [("file_list", {"path": str(folder)})]},
        read("a.py"),
        {"content": "Підсумок. ГОТОВО"},  # premature: b.py and c.py are still unread
        read("b.py"),
        read("c.py"),
        {"content": "Повний підсумок. ГОТОВО"},
    ]
    result, _ = await run_turn(runtime, who, "Прочитай кожен .py", persist=True)
    reads = [r.name for r in result.tool_results]
    assert reads == ["file_list", "file_read", "file_read", "file_read"]
    assert result.content == "Повний підсумок. ГОТОВО"
    sent = state["requests"][3]["messages"]
    unread = [m for m in sent if m["content"].startswith("[авто-продовження] Ти ще не")]
    assert unread and "b.py" in unread[0]["content"] and "notes.md" not in unread[0]["content"]
