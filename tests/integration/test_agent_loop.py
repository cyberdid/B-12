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


def body(content):
    """The reply without the journal footer the agent adds for persist turns with reads."""
    return content.split("\n\nПрочитано за журналом")[0]


def tool_messages(request):
    return [m for m in request["messages"] if m["role"] == "tool"]


def test_project_review_guidance_uses_granted_file_tools():
    from b12.agent import SYSTEM_PROMPT

    assert "ОДИН run_command" not in SYSTEM_PROMPT
    assert "file_list" in SYSTEM_PROMPT and "file_read" in SYSTEM_PROMPT
    assert "Не повторюй відмовлений виклик" in SYSTEM_PROMPT
    assert "не пиши проміжних звітів" in SYSTEM_PROMPT
    assert "Не завершуй аудит переліком прочитаних файлів" in SYSTEM_PROMPT
    assert "шлях:рядок" in SYSTEM_PROMPT
    assert "Не підміняй висновок загальними ризиками" in SYSTEM_PROMPT


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
                ("file_read", {"path": str(tmp_path / "a"), "bogus": 1}),
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


def test_context_evictions_are_returned_as_untrusted_continuity_excerpts(
    runtime_factory, profile_settings
):
    from b12.context import ContextBuilder

    _, factory = runtime_factory
    runtime = factory()
    agent = runtime.agent
    agent.builder = ContextBuilder(
        profile_settings.model_copy(update={"num_ctx": 3072, "output_tokens": 32})
    )
    history = [
        {
            "id": "old-user",
            "turn_id": "old-turn",
            "role": "user",
            "content": "Перед помилкою ми налаштовували NVIDIA NeMo Agent Toolkit. " + "A" * 3500,
        },
        {
            "id": "old-assistant",
            "turn_id": "old-turn",
            "role": "assistant",
            "content": "Далі треба було описати встановлення й перевірити вимоги. " + "B" * 3500,
        },
    ]
    state = {
        "turn_messages": [{"id": "current", "role": "user", "content": "Що було перед цим?"}],
        "evidence": [],
        "notes": [],
    }

    request = agent._admit("system", history, state, [], persist=False)

    continuity = request.messages[0]["content"]
    assert "NVIDIA NeMo Agent Toolkit" in continuity
    assert "встановлення й перевірити вимоги" in continuity
    assert "недовірені" in continuity
    assert "не стверджуй, що попередніх повідомлень не було" in continuity.lower()
    assert {"old-user", "old-assistant"}.issubset(request.dropped_ids)
    assert request.messages[-1]["content"] == "Що було перед цим?"


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
    # An unfinished turn is kept with a status marker, so its work survives a reload.
    assert result.persisted
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
    assert result.state == "completed" and body(result.content).endswith("ГОТОВО")
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
    from b12.agent import PERSIST_GENERIC

    state, factory = runtime_factory
    runtime = factory()
    who = owner(runtime)
    state["script"] = [{"content": f"крок {n}"} for n in range(PERSIST_GENERIC + 5)]
    result, _ = await run_turn(runtime, who, "Роби без кінця", persist=True)
    assert result.state == "completed" and len(state["requests"]) == PERSIST_GENERIC + 1


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
    assert body(result.content) == "Повний підсумок. ГОТОВО"
    sent = state["requests"][3]["messages"]
    unread = [m for m in sent if m["content"].startswith("[авто-продовження] Ти ще не")]
    assert unread and "b.py" in unread[0]["content"] and "notes.md" not in unread[0]["content"]


async def test_persist_finishes_paginated_directory_listing_before_report(
    runtime_factory, tmp_path
):
    state, factory = runtime_factory
    runtime = factory()
    who = owner(runtime)
    folder = tmp_path / "many_entries"
    folder.mkdir()
    for n in range(201):
        (folder / f"entry-{n:03}.txt").write_text("data")

    def next_page(request):
        nudges = [
            m["content"]
            for m in request["messages"]
            if m["role"] == "user" and m["content"].startswith("[авто-продовження]")
        ]
        assert nudges and f"path={folder}" in nudges[-1] and "offset=200" in nudges[-1]
        return {"tool_calls": [("file_list", {"path": str(folder), "offset": 200})]}

    state["script"] = [
        {"tool_calls": [("file_list", {"path": str(folder)})]},
        {"content": "Перша сторінка переглянута. ГОТОВО"},
        {"tool_calls": [("file_list", {"path": str(folder), "offset": 400})]},
        {"content": "І ця сторінка готова. ГОТОВО"},
        next_page,
        {"content": "Список переглянуто. ГОТОВО"},
    ]

    result, _ = await run_turn(runtime, who, "Переглянь теку", persist=True)

    assert result.state == "completed"
    assert [r.name for r in result.tool_results] == ["file_list"] * 3
    assert [r.content["offset"] for r in result.tool_results] == [0, 400, 200]


async def test_persist_keeps_tools_available_past_report_reserve_when_coverage_is_incomplete(
    runtime_factory, tmp_path, monkeypatch
):
    import b12.agent as agent_module

    monkeypatch.setattr(agent_module, "PERSIST_ROUNDS", 4)
    monkeypatch.setattr(agent_module, "PERSIST_COVERAGE_EXTRA_ROUNDS", 4, raising=False)
    monkeypatch.setattr(agent_module, "PERSIST_REPORT_ROUNDS", 1)
    state, factory = runtime_factory
    runtime = factory()
    who = owner(runtime)
    folder = tmp_path / "review"
    folder.mkdir()
    (folder / "a.py").write_text("# a")
    (folder / "b.py").write_text("# b")
    state["script"] = [
        {"tool_calls": [("file_list", {"path": str(folder)})]},
        {"tool_calls": [("file_read", {"path": str(folder / "a.py")})]},
        {"content": "Частковий звіт. ГОТОВО"},
        {"tool_calls": [("file_read", {"path": str(folder / "b.py")})]},
        {"content": "Повний звіт. ГОТОВО"},
    ]

    result, _ = await run_turn(runtime, who, "Прочитай обидва файли", persist=True)

    assert result.state == "completed"
    assert body(result.content) == "Повний звіт. ГОТОВО"
    assert [r.name for r in result.tool_results] == ["file_list", "file_read", "file_read"]


async def test_persist_continues_a_partially_read_file_from_the_exact_offset(
    runtime_factory, tmp_path
):
    state, factory = runtime_factory
    runtime = factory()
    who = owner(runtime)
    big = tmp_path / "long.txt"
    big.write_text("x" * 1800)  # two 1600-byte chunks, ASCII so the size is exact
    first = {"tool_calls": [("file_read", {"path": str(big), "max_bytes": 1600})]}

    def follow(request):
        sent = request["messages"]
        nudge = [m for m in sent if m["content"].startswith("[авто-продовження] Файл")]
        assert nudge, "no continuation nudge"
        offset = int(nudge[-1]["content"].split("offset=")[1])
        return {
            "tool_calls": [("file_read", {"path": str(big), "max_bytes": 1600, "offset": offset})]
        }

    state["script"] = [
        first,
        {"content": "Перша частина прочитана."},
        follow,
        {"content": "Готово."},
    ]
    result, _ = await run_turn(runtime, who, "Прочитай файл повністю", persist=True)
    reads = [r for r in result.tool_results if r.name == "file_read"]
    assert len(reads) == 2 and reads[1].content["offset"] > 0
    assert (result.state, result.error_code, body(result.content)) == ("completed", None, "Готово.")


def test_head_and_tail_survive_truncation_with_an_omission_marker():
    from b12.agent import _head_tail

    text = "START" + "x" * 5000 + "RESULT: 42 files"
    clipped = _head_tail(text, 400)
    assert len(clipped.encode()) <= 400
    assert clipped.startswith("START") and clipped.endswith("RESULT: 42 files")
    assert "пропущено" in clipped
    assert _head_tail("short", 400) == "short"


async def test_persist_refuses_the_same_call_a_third_time(runtime_factory, tmp_path):
    """Regression: the model re-read the same chunk in a loop until the round budget ran out."""
    state, factory = runtime_factory
    runtime = factory()
    who = owner(runtime)
    target = tmp_path / "loop.txt"
    target.write_text("текст " * 300)
    same = {"tool_calls": [("file_read", {"path": str(target), "max_bytes": 1600, "offset": 0})]}
    state["script"] = [same, same, same, same, {"content": "Зупиняюся. ГОТОВО"}]
    result, _ = await run_turn(runtime, who, "Прочитай файл", persist=True)
    codes = [r.error_code for r in result.tool_results]
    assert codes.count("repeated_call") >= 1
    assert [r.status for r in result.tool_results][:2] == ["completed", "completed"]


async def test_persist_stops_when_the_model_repeats_the_same_answer(runtime_factory):
    """Regression: the model repeated 'Я опрацював …' without doing anything new."""
    state, factory = runtime_factory
    runtime = factory()
    who = owner(runtime)
    state["script"] = [{"content": "Я опрацював файл."}, {"content": "Я опрацював файл."}]
    result, _ = await run_turn(runtime, who, "Аналізуй", persist=True)
    assert result.state == "failed" and result.error_code == "stalled"


async def test_stall_redirects_to_the_unfinished_file_instead_of_ending_the_turn(
    runtime_factory, tmp_path
):
    """Regression: a repeated report ended the turn while the file was still half-read."""
    state, factory = runtime_factory
    runtime = factory()
    who = owner(runtime)
    big = tmp_path / "big.txt"
    big.write_text("x" * 1800)
    first = {"tool_calls": [("file_read", {"path": str(big), "max_bytes": 1600})]}
    rest = {"tool_calls": [("file_read", {"path": str(big), "max_bytes": 1600, "offset": 1600})]}
    state["script"] = [
        first,
        {"content": "Звіт."},
        {"content": "Звіт."},
        rest,
        {"content": "Фінал. ГОТОВО"},
    ]
    result, _ = await run_turn(runtime, who, "Прочитай файл повністю", persist=True)
    assert (result.state, result.error_code) == ("completed", None)
    assert body(result.content) == "Фінал. ГОТОВО"


async def test_a_stalled_turn_is_saved_with_its_status_marker(runtime_factory):
    """Regression: work from a turn that did not finish was lost on reload."""
    state, factory = runtime_factory
    runtime = factory()
    who = owner(runtime)
    state["script"] = [{"content": "Звіт."}, {"content": "Звіт."}]
    result, _ = await run_turn(runtime, who, "Аналізуй", persist=True)
    assert result.state == "failed" and result.error_code == "stalled"
    actor = runtime.control.resolve_actor(who.actor.id)
    history = runtime.agent.history_messages(who.session, actor)
    assert any("хід не завершено: stalled" in m["content"] for m in history)
    assert any(m["content"] == "Звіт." for m in history)


async def test_same_failing_program_is_refused_after_two_failures_in_any_mode(runtime_factory):
    """Regression: the model retried `ls -1` with different argv forever."""
    state, factory = runtime_factory
    runtime = factory()
    who = owner(runtime)
    failing = {"executable": "/bin/false", "argv": [], "cwd": "/tmp", "declared_effects": ["noop"]}
    state["script"] = [
        {"tool_calls": [("shell_exec", dict(failing))]},
        {"tool_calls": [("shell_exec", dict(failing, argv=["x"]))]},
        {"tool_calls": [("shell_exec", dict(failing, argv=["y"]))]},
        {"content": "Не вийшло."},
    ]
    result, _ = await run_turn(runtime, who, "запусти")
    statuses = [(r.status, r.error_code) for r in result.tool_results]
    assert statuses[2] == ("denied", "repeated_failure"), statuses


async def test_stalled_turn_with_partial_reads_cannot_complete_coverage(runtime_factory, tmp_path):
    """A report on a partial read stays failed even when it is non-empty."""
    state, factory = runtime_factory
    runtime = factory()
    who = owner(runtime)
    big = tmp_path / "big.txt"
    big.write_text("x" * 1800)
    first = {"tool_calls": [("file_read", {"path": str(big), "max_bytes": 1600})]}
    repeat = {"content": "Аналіз."}
    state["script"] = [
        first,
        repeat,
        repeat,
        repeat,
        repeat,
        repeat,
        {"content": "Звіт: прочитано частину."},
    ]
    result, _ = await run_turn(runtime, who, "Проаналізуй файл", persist=True)
    assert (result.state, result.error_code) == ("failed", "incomplete_coverage")
    assert body(result.content).startswith("Звіт: прочитано частину.")
    assert "не дочитано до кінця" in result.content.lower()
    assert state["requests"][-1]["tools"] == []


def test_file_read_chunk_is_larger_and_fits_its_budget():
    from b12.tools.filesystem import ReadArgs

    default = ReadArgs(path="/tmp/x").max_bytes
    assert default >= 2400
    assert ReadArgs.model_fields["max_bytes"].metadata[-1].le >= 2400


async def test_persist_report_lists_what_was_actually_read(runtime_factory, tmp_path):
    """Regression: the model listed files it never read; the list now comes from the journal."""
    state, factory = runtime_factory
    runtime = factory()
    who = owner(runtime)
    real = tmp_path / "real.py"
    real.write_text("print('hi')\n")
    state["script"] = [
        {"tool_calls": [("file_read", {"path": str(real)})]},
        {"content": "Звіт готовий. ГОТОВО"},
    ]
    result, _ = await run_turn(runtime, who, "Проаналізуй файл", persist=True)
    assert result.content.startswith("Звіт готовий. ГОТОВО")
    assert "real.py" in result.content and "за журналом" in result.content
    assert "nvidia" not in result.content.lower()  # never a file the turn did not read


async def test_journal_footer_keeps_same_named_files_distinct(runtime_factory, tmp_path):
    """Regression: two CMakeLists.txt files were shown as one name repeated."""
    state, factory = runtime_factory
    runtime = factory()
    who = owner(runtime)
    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    (tmp_path / "a" / "CMakeLists.txt").write_text("a")
    (tmp_path / "b" / "CMakeLists.txt").write_text("b")
    state["script"] = [
        {"tool_calls": [("file_read", {"path": str(tmp_path / "a" / "CMakeLists.txt")})]},
        {"tool_calls": [("file_read", {"path": str(tmp_path / "b" / "CMakeLists.txt")})]},
        {"content": "Готово. ГОТОВО"},
    ]
    result, _ = await run_turn(runtime, who, "Прочитай", persist=True)
    footer = result.content.split("Прочитано за журналом інструментів: ")[1]
    assert "a/CMakeLists.txt" in footer and "b/CMakeLists.txt" in footer


async def test_text_written_as_a_tool_call_is_not_a_final_answer(runtime_factory):
    """Regression: `memory_store(text=...)` was printed as the reply and nothing was stored."""
    state, factory = runtime_factory
    runtime = factory()
    who = owner(runtime)
    state["script"] = [
        # The whole reply is the call: it runs (formerly it was nudged and repeated natively).
        {"content": 'memory_store(text="бірюзовий", kind="fact")'},
        {"content": "Запам'ятав. ГОТОВО"},
    ]
    result, _ = await run_turn(runtime, who, "запам'ятай колір")
    assert result.state == "completed"
    assert [r.name for r in result.tool_results] == ["memory_store"]
    assert body(result.content) == "Запам'ятав. ГОТОВО"


async def test_a_large_file_is_not_read_chunk_by_chunk_forever(runtime_factory, tmp_path):
    """Regression: a 140 KB file was read in 2.4 KB chunks for 60 rounds."""
    state, factory = runtime_factory
    runtime = factory()
    who = owner(runtime)
    big = tmp_path / "big.py"
    big.write_text("def f():\n    pass\n" * 4000)
    script = [
        {"tool_calls": [("file_read", {"path": str(big), "offset": i * 2400})]} for i in range(14)
    ]
    state["script"] = script + [{"content": "ГОТОВО"}]
    result, _ = await run_turn(runtime, who, "прочитай", persist=True)
    codes = [r.error_code for r in result.tool_results]
    assert codes.count("use_search") >= 1
    assert codes[:12] == [None] * 12  # 12 chunks (about 28 KB) are allowed before the stop


async def test_a_closed_file_is_not_sent_back_to_file_read(runtime_factory, tmp_path):
    """Regression: after the chunk limit, a continue-nudge sent the model back to that file."""
    state, factory = runtime_factory
    runtime = factory()
    who = owner(runtime)
    big = tmp_path / "big.md"
    big.write_text("# readme\n" + "line of text\n" * 3000)
    script = [
        {"tool_calls": [("file_read", {"path": str(big), "offset": i * 2400})]} for i in range(13)
    ]
    script += [
        {"content": "Не можу продовжити читання."},
        {"content": "Звіт з прочитаного. ГОТОВО"},
    ]
    state["script"] = script
    await run_turn(runtime, who, "прочитай", persist=True)
    nudges = [m["content"] for r in state["requests"] for m in r["messages"] if m["role"] == "user"]
    assert not any(f"file_read з path={big}" in n or f"path={big}" in n for n in nudges)


def _small_files(tmp_path, count):
    paths = []
    for i in range(count):
        p = tmp_path / f"part{i}.cc"
        p.write_text(f"int f{i}() {{ return {i}; }}\n")
        paths.append(str(p))
    return paths


async def test_report_is_requested_before_the_round_budget_ends(
    runtime_factory, tmp_path, monkeypatch
):
    """Regression: the round budget ran out while the model was still reading files."""
    import b12.agent as agent_mod

    monkeypatch.setattr(agent_mod, "PERSIST_ROUNDS", 8)
    monkeypatch.setattr(agent_mod, "PERSIST_REPORT_ROUNDS", 3)
    state, factory = runtime_factory
    runtime = factory()
    who = owner(runtime)
    paths = _small_files(tmp_path, 8)
    state["script"] = [{"tool_calls": [("file_read", {"path": p})]} for p in paths[:4]]
    state["script"] += [{"content": "Звіт з прочитаного. ГОТОВО"}]
    result, _ = await run_turn(runtime, who, "аналіз", persist=True)
    assert result.state == "completed"
    report_round = state["requests"][4]
    assert report_round["tools"] == []
    last_user = [m["content"] for m in report_round["messages"] if m["role"] == "user"][-1]
    assert "звіт" in last_user.lower()


async def test_round_budget_end_without_a_report_is_failed_not_completed(
    runtime_factory, tmp_path, monkeypatch
):
    """Regression: the last round ended on a progress note and was recorded as completed."""
    import b12.agent as agent_mod

    monkeypatch.setattr(agent_mod, "PERSIST_ROUNDS", 3)
    monkeypatch.setattr(agent_mod, "PERSIST_REPORT_ROUNDS", 0)  # the budget ends on this turn
    state, factory = runtime_factory
    runtime = factory()
    who = owner(runtime)
    (path,) = _small_files(tmp_path, 1)
    state["script"] = [
        {"tool_calls": [("file_read", {"path": path})]},
        {"content": "Я прочитав файл, наступний — ще один."},
        {"content": "Далі ще читаю і не встигаю звіт."},
    ]
    result, _ = await run_turn(runtime, who, "аналіз", persist=True)
    assert result.state == "failed"
    assert result.error_code == "max_rounds"
    assert "не встигаю звіт" in result.content


async def test_report_with_finish_marker_does_not_complete_with_unread_code_files(
    runtime_factory, tmp_path, monkeypatch
):
    """Even after the bounded extension, an incomplete report must remain failed."""
    import b12.agent as agent_mod

    monkeypatch.setattr(agent_mod, "PERSIST_ROUNDS", 3)
    monkeypatch.setattr(agent_mod, "PERSIST_COVERAGE_EXTRA_ROUNDS", 0)
    monkeypatch.setattr(agent_mod, "PERSIST_REPORT_ROUNDS", 1)
    state, factory = runtime_factory
    runtime = factory()
    who = owner(runtime)
    root = tmp_path / "project"
    root.mkdir()
    first, second = root / "first.py", root / "second.py"
    first.write_text("print('read')\n")
    second.write_text("print('unread')\n")
    state["script"] = [
        {"tool_calls": [("file_list", {"path": str(root)})]},
        {"tool_calls": [("file_read", {"path": str(first)})]},
        {"content": "Перевірив перший файл. ГОТОВО"},
    ]

    result, _ = await run_turn(runtime, who, "проаналізуй усі файли теки", persist=True)

    assert result.state == "failed"
    assert result.error_code == "incomplete_coverage"
    assert "ГОТОВО" in result.content
    assert "second.py" in result.content


async def test_continue_nudge_skips_a_file_at_the_chunk_limit(
    runtime_factory, tmp_path, monkeypatch
):
    """Regression: after the chunk limit, the continue-nudge still pointed at the file."""
    import b12.agent as agent_mod

    monkeypatch.setattr(agent_mod, "_LARGE_FILE_CHUNKS", 3)
    state, factory = runtime_factory
    runtime = factory()
    big = tmp_path / "big.md"
    big.write_text("# readme\n" + "line of text\n" * 3000)
    state["script"] = [
        {"tool_calls": [("file_read", {"path": str(big), "offset": i * 2400})]} for i in range(3)
    ]
    state["script"] += [{"content": "Прочитано частково."}, {"content": "Звіт. ГОТОВО"}]
    await run_turn(runtime, owner(runtime), "прочитай", persist=True)
    nudges = [m["content"] for r in state["requests"] for m in r["messages"] if m["role"] == "user"]
    assert not any(f"path={big}" in n for n in nudges if n.startswith("[авто"))


def test_unread_coverage_counts_code_files_after_a_readme(tmp_path):
    """Regression: after README.md was read, the source files were not counted as unread."""
    from b12.agent import Agent

    state = {
        "listed": {
            "/p/README.md": True,
            "/p/build.sh": False,
            "/p/src/main.cc": False,
            "/p/LICENSE": False,
            "/p/.gitignore": False,
            "/p/data.bin": False,
        },
        "closed": [],
    }
    unread = Agent._unread_listed(state)
    assert "/p/build.sh" in unread and "/p/src/main.cc" in unread
    assert "/p/LICENSE" not in unread and "/p/.gitignore" not in unread
    assert "/p/data.bin" not in unread


async def test_model_native_call_syntax_in_text_is_not_a_final_answer(runtime_factory):
    """Regression: a call in the model's token syntax, followed by the marker, was the report."""
    state, factory = runtime_factory
    runtime = factory()
    who = owner(runtime)
    state["script"] = [
        {"content": 'memory_store{kind:<|"|>fact<|"|>,text:<|"|>x<|"|>}\n\nГОТОВО'},
        {"content": "Звіт з прочитаного. ГОТОВО"},
    ]
    result, _ = await run_turn(runtime, who, "аналіз", persist=True)
    assert result.state == "completed"
    assert "<|" not in result.content
    assert "memory_store{" not in result.content


async def test_native_call_text_is_executed_not_reported(runtime_factory):
    """A whole reply in native call syntax is the call itself (formerly it failed the turn)."""
    state, factory = runtime_factory
    runtime = factory()
    who = owner(runtime)
    state["script"] = [
        {"content": 'memory_store{kind:<|"|>fact<|"|>,text:<|"|>x<|"|>}'},
        {"content": "Записав."},
    ]
    result, _ = await run_turn(runtime, who, "запам'ятай x")
    assert result.state == "completed" and result.content == "Записав."
    assert [r.name for r in result.tool_results] == ["memory_store"]


async def test_repeated_native_call_mixed_with_text_ends_as_failed(runtime_factory):
    state, factory = runtime_factory
    runtime = factory()
    who = owner(runtime)
    bad = {"content": 'Зараз: memory_store{kind:<|"|>fact<|"|>,text:<|"|>x<|"|>}'}
    state["script"] = [bad, bad, bad, bad]
    result, _ = await run_turn(runtime, who, "аналіз")
    assert result.state == "failed"
    assert result.error_code == "pseudo_call"


async def test_unlisted_subfolder_is_covered_before_a_persist_turn_ends(runtime_factory, tmp_path):
    """Regression: a project's src/ was never listed, so its code never counted as unread."""
    state, factory = runtime_factory
    runtime = factory()
    who = owner(runtime)
    folder = tmp_path / "proj"
    (folder / "src").mkdir(parents=True)
    (folder / "README.md").write_text("# proj")
    (folder / "src" / "main.cc").write_text("int main() {}")
    state["script"] = [
        {"tool_calls": [("file_list", {"path": str(folder)})]},
        {"tool_calls": [("file_read", {"path": str(folder / "README.md")})]},
        {"content": "Прочитано. ГОТОВО"},  # premature: src/ was never looked into
        {"tool_calls": [("file_list", {"path": str(folder / "src")})]},
        {"tool_calls": [("file_read", {"path": str(folder / "src" / "main.cc")})]},
        {"content": "Повний звіт. ГОТОВО"},
    ]
    result, _ = await run_turn(runtime, who, "аналіз", persist=True)
    reads = [r.name for r in result.tool_results]
    assert reads == ["file_list", "file_read", "file_list", "file_read"]
    assert body(result.content) == "Повний звіт. ГОТОВО"


async def test_a_nearly_identical_report_is_treated_as_a_repeat(runtime_factory, tmp_path):
    """Regression: the model rewrote the same report with a few words changed; only an exact
    repeat was caught, so the loop ran on for minutes."""
    import b12.agent as agent_mod

    state, factory = runtime_factory
    runtime = factory()
    who = owner(runtime)
    folder = tmp_path / "proj"
    folder.mkdir()
    (folder / "README.md").write_text("# proj")
    (folder / "a.cc").write_text("int a() { return 1; }")
    base = "Звіт: LTESniffer — це інструмент для прослуховування LTE. " * 3
    state["script"] = [
        {"tool_calls": [("file_list", {"path": str(folder)})]},
        {"tool_calls": [("file_read", {"path": str(folder / "README.md")})]},
        {"content": base},
        {"content": base.replace("інструмент", "засіб", 1)},
        {"content": "Далі. ГОТОВО"},
    ]
    await run_turn(runtime, who, "аналіз", persist=True)
    after_second = state["requests"][4]  # the nudge that follows the second, near-identical reply
    last_user = [m["content"] for m in after_second["messages"] if m["role"] == "user"][-1]
    assert last_user.startswith(agent_mod._NUDGE_REDIRECT)


async def test_long_persist_turn_keeps_the_window_within_a_fixed_budget(
    runtime_factory, tmp_path, monkeypatch
):
    """Regression: the window grew linearly with rounds (fixed per-message cuts) and overflowed."""
    import b12.agent as agent_mod

    monkeypatch.setattr(agent_mod, "PERSIST_HISTORY_CHARS", 6000)
    monkeypatch.setattr(agent_mod, "_LARGE_FILE_CHUNKS", 1000)
    state, factory = runtime_factory
    runtime = factory()
    who = owner(runtime)
    files = []
    for i in range(30):
        p = tmp_path / f"f{i}.cc"
        p.write_text(f"// file {i}\n" + "int x = 1; " * 250)
        files.append(str(p))
    state["script"] = [{"tool_calls": [("file_read", {"path": p})]} for p in files]
    state["script"] += [{"content": "Звіт. ГОТОВО"}]
    await run_turn(runtime, who, "прочитай", persist=True)
    last = state["requests"][-1]["messages"]
    # The window is what grows with rounds; the system prompt (persona, rules) is constant.
    total = sum(len(m.get("content") or "") for m in last if m["role"] != "system")
    assert total < 6000 + 4000, total


async def test_search_results_do_not_claim_full_file_or_directory_coverage(
    runtime_factory, tmp_path
):
    """Searching a file or directory does not count as a full read or listing."""
    state, factory = runtime_factory
    runtime = factory()
    who = owner(runtime)
    folder = tmp_path / "proj"
    (folder / "sub").mkdir(parents=True)
    (folder / "a.py").write_text("def a(): return 1\n")
    (folder / "b.py").write_text("def b(): return 2\n")
    (folder / "sub" / "c.py").write_text("def c(): return 3\n")
    state["script"] = [
        {"tool_calls": [("file_list", {"path": str(folder)})]},
        {"tool_calls": [("file_read", {"path": str(folder / "a.py")})]},
        {
            "tool_calls": [
                (
                    "run_command",
                    {"command": f"sed -n '1,10p' {folder / 'b.py'}", "cwd": str(folder)},
                )
            ]
        },
        {"tool_calls": [("file_search", {"path": str(folder / "sub"), "query": "def c"})]},
        {"content": "Повний звіт. ГОТОВО"},
        {"tool_calls": [("file_read", {"path": str(folder / "b.py")})]},
        {"tool_calls": [("file_list", {"path": str(folder / "sub")})]},
        {"tool_calls": [("file_read", {"path": str(folder / "sub" / "c.py")})]},
        {"content": "Фінальний звіт після читання. ГОТОВО"},
    ]
    result, _ = await run_turn(runtime, who, "Проаналізуй проєкт", persist=True)
    assert result.state == "completed"
    assert body(result.content) == "Фінальний звіт після читання. ГОТОВО"
    assert len(state["requests"]) == 9
    assert "a.py" in result.content and "b.py" in result.content and "sub/c.py" in result.content


async def test_pseudo_call_catches_file_search_and_knowledge_search_written_as_text(
    runtime_factory, tmp_path
):
    """All built-in tool names written as prose trigger the pseudo-call nudge."""
    state, factory = runtime_factory
    runtime = factory()
    who = owner(runtime)
    target = tmp_path / "sample.py"
    target.write_text("def hello(): pass\n")
    state["script"] = [
        # Inside prose a call is not executed: the model is nudged to make the real call.
        {"content": f'Шукаю:\nfile_search(path="{tmp_path}", query="hello")'},
        {"tool_calls": [("file_search", {"path": str(tmp_path), "query": "hello"})]},
        {"content": "Знайдено функцію hello."},
    ]
    result, _ = await run_turn(runtime, who, "знайди hello")
    assert result.state == "completed"
    assert [r.name for r in result.tool_results] == ["file_search"]
    assert result.content == "Знайдено функцію hello."


async def test_resumed_persist_turn_keeps_extended_deadline_and_persist_coverage(
    runtime_factory, tmp_path
):
    """A persist turn paused on approval resumes with persist=True and >=1800s deadline."""
    import time

    state, factory = runtime_factory
    runtime = factory()
    who = owner(runtime)
    record = runtime.memory.remember("тимчасовий запис", who.actor)
    folder = tmp_path / "proj"
    folder.mkdir()
    (folder / "a.py").write_text("x = 1\n")
    (folder / "b.py").write_text("y = 2\n")
    seen_remaining = []

    def check_deadline(request):
        turn_id = next(iter(runtime.control._runtime))
        remaining = runtime.control._runtime[turn_id][0] - time.monotonic()
        seen_remaining.append(remaining)
        return {"content": "Проміжний текст без маркера."}

    state["script"] = [
        {"tool_calls": [("file_list", {"path": str(folder)})]},
        {"tool_calls": [("file_read", {"path": str(folder / "a.py")})]},
        {"tool_calls": [("memory_forget", {"memory_id": record.id})]},
        check_deadline,  # after resume: b.py is still unread, so persist must nudge
        {"tool_calls": [("file_read", {"path": str(folder / "b.py")})]},
        {"content": "Усе прочитано. ГОТОВО"},
    ]
    waiting, _ = await run_turn(runtime, who, "Очисти і прочитай", persist=True)
    assert waiting.state == "awaiting_approval"
    runtime.control.decide_approval(waiting.pending_operations[0], True)
    done = await runtime.agent.resume(waiting.turn_id)
    assert done.state == "completed"
    assert body(done.content) == "Усе прочитано. ГОТОВО"
    assert seen_remaining and seen_remaining[0] > 1500.0


async def test_a_tool_name_mentioned_in_prose_is_not_a_pseudo_call(runtime_factory):
    """Regression: a report naming a tool in a sentence was taken for a call written as text."""
    state, factory = runtime_factory
    runtime = factory()
    who = owner(runtime)
    state["script"] = [{"content": "Інструмент file_read(path) читає файл. ГОТОВО"}]
    result, _ = await run_turn(runtime, who, "опиши інструменти", persist=True)
    assert result.state == "completed"
    assert len(state["requests"]) == 1


async def test_forgetting_a_fact_also_removes_the_later_turn_that_quoted_it(runtime_factory):
    """Regression (A-03): turn 2 repeated a fact it had from turn 1's history, and forgetting the
    memory left turn 2 in the session with the fact in it."""
    state, factory = runtime_factory
    runtime = factory()
    who = owner(runtime)
    fact = runtime.memory.remember("Бірюзовий колір — улюблений", who.actor)
    state["script"] = [
        {"tool_calls": [("memory_search", {"query": "колір"})]},
        {"content": "Ви любите бірюзовий."},
        {"content": "Пам'ятаю: улюблений колір — бірюзовий."},
    ]
    await run_turn(runtime, who, "який мій колір?")
    await run_turn(runtime, who, "нагадай ще раз")
    await runtime.purge.forget(fact.id, who.actor.id)
    remaining = [m["content"] for m in runtime.sessions.history(who.session, who.actor.id)]
    assert not any("бірюзовий" in (c or "") for c in remaining)


async def test_a_partly_read_file_is_continued_in_normal_mode_too(runtime_factory, tmp_path):
    """Regression: a normal turn stopped after the first 2400 bytes of a script and asked the user
    whether to go on; the continue-reading nudge only existed in persist mode."""
    state, factory = runtime_factory
    runtime = factory()
    who = owner(runtime)
    big = tmp_path / "script.sh"
    big.write_text("echo line\n" * 600)  # about 6 KB: three 2400-byte pieces
    state["script"] = [
        {"tool_calls": [("file_read", {"path": str(big)})]},
        {"content": "Прочитав першу частину. Продовжити?"},
        {"tool_calls": [("file_read", {"path": str(big), "offset": 2400})]},
        {"tool_calls": [("file_read", {"path": str(big), "offset": 4800})]},
        {"content": "Файл прочитано повністю."},
    ]
    result, _ = await run_turn(runtime, who, "прочитай всі частини")
    assert result.state == "completed"
    reads = [r for r in result.tool_results if r.name == "file_read"]
    assert len(reads) == 3, [r.name for r in result.tool_results]
    nudge = [m["content"] for m in state["requests"][2]["messages"] if m["role"] == "user"][-1]
    assert "offset=2400" in nudge


async def test_guest_prompt_names_the_guest_and_carries_no_owner_data(runtime_factory):
    from pathlib import Path

    from b12.auth import GUEST_CAPABILITIES

    state, factory = runtime_factory
    runtime = factory()
    who = owner(runtime)
    secret = "кодовий пароль стенда AURORA-77"
    runtime.memory.remember(secret, who.actor)
    guest = runtime.control.create_actor(owner=False, consent=True)
    session = runtime.control.create_session(guest.id)
    task = runtime.control.create_task(session)
    grant = runtime.control.issue_grant(
        guest.id, session, tuple(sorted(GUEST_CAPABILITIES)), task_id=task
    )
    state["script"] = [{"content": "Це конфіденційні дані власника."}]
    result = await runtime.agent.turn(session, grant, "Який кодовий пароль стенда?", task_id=task)
    assert result.state == "completed"
    request = state["requests"][-1]
    everything = json.dumps(request["messages"], ensure_ascii=False)
    assert "AURORA" not in everything
    assert str(Path.home()) not in everything
    assert "гість" in request["messages"][0]["content"]

    state["script"] = [{"content": "AURORA-77."}]
    await run_turn(runtime, who, "Який кодовий пароль стенда?")
    system = state["requests"][-1]["messages"][0]["content"]
    assert "власник" in system and str(Path.home()) in system and "AURORA-77" in system


async def test_memory_store_reports_low_disk_and_writes_nothing(runtime_factory):
    import shutil

    state, factory = runtime_factory
    runtime = factory()
    who = owner(runtime)
    free_mb = shutil.disk_usage(runtime.settings.state_dir).free // 2**20
    runtime.memory.min_free_bytes = (free_mb + 1024) * 2**20
    state["script"] = [
        {"tool_calls": [("memory_store", {"text": "запис при нестачі місця"})]},
        {"content": "Не вдалося зберегти: замало місця на диску."},
    ]
    result, _ = await run_turn(runtime, who, "Запам'ятай: запис при нестачі місця")
    stored = [r for r in result.tool_results if r.name == "memory_store"]
    assert [(r.status, r.error_code) for r in stored] == [("failed", "disk_space_low")]
    assert runtime.memory.search("нестачі", who.actor) == []


async def test_repeated_prose_call_text_ends_as_failed_not_as_an_answer(runtime_factory):
    state, factory = runtime_factory
    runtime = factory()
    who = owner(runtime)
    bad = {"content": "Читаю:\nfile_read(path='secrets/api_token.env')"}
    state["script"] = [bad, bad, bad, bad]
    result, _ = await run_turn(runtime, who, "прочитай токен")
    assert (result.state, result.error_code) == ("failed", "pseudo_call")
    assert result.tool_results == ()


async def test_prompt_states_memory_is_off_without_consent(runtime_factory):
    state, factory = runtime_factory
    runtime = factory()
    who = owner(runtime, consent=False)
    state["script"] = [{"content": "Пам'ять вимкнена, тож не збережу."}]
    await run_turn(runtime, who, "Запам'ятай: день народження мами 15 травня.")
    system = state["requests"][-1]["messages"][0]["content"]
    assert "згоди на пам'ять немає" in system


def test_system_prompt_forbids_offering_workarounds_for_unavailable_tools():
    from b12.agent import SYSTEM_PROMPT

    assert "не пропонуй обхід" in SYSTEM_PROMPT


def test_system_prompt_asks_to_retry_memory_search_with_specific_names():
    from b12.agent import SYSTEM_PROMPT

    assert "повтори його конкретними назвами" in SYSTEM_PROMPT


async def test_native_call_syntax_as_text_runs_as_a_real_tool_call(runtime_factory):
    state, factory = runtime_factory
    runtime = factory()
    who = owner(runtime)
    runtime.memory.remember("Ємність батареї стенда: 48V 20Ah.", who.actor)
    state["script"] = [
        {"content": 'memory_search{query:<|"|>батареї<|"|>,limit:3}'},
        {"content": "Ємність батареї: 48V 20Ah."},
    ]
    result, _ = await run_turn(runtime, who, "Яка ємність батареї?")
    assert result.state == "completed"
    assert [(r.name, r.status) for r in result.tool_results] == [("memory_search", "completed")]
    assert result.tool_results[0].content["records"][0]["text"].startswith("Ємність")
    assert result.content == "Ємність батареї: 48V 20Ah."


def test_native_call_parser_accepts_only_a_whole_well_formed_call():
    from b12.agent import _native_text_call

    call = _native_text_call('memory_search{query:<|"|>a, b<|"|>,limit:2,exact:true}')
    assert (call.name, call.arguments) == (
        "memory_search", {"query": "a, b", "limit": 2, "exact": True}
    )
    assert _native_text_call('Ось виклик: memory_search{query:<|"|>x<|"|>}') is None
    assert _native_text_call('unknown_tool{query:<|"|>x<|"|>}') is None
    assert _native_text_call("memory_search{query:<|\"|>x}") is None


async def test_current_preferences_reach_the_prompt_for_their_own_actor_only(runtime_factory):
    from b12.auth import GUEST_CAPABILITIES

    state, factory = runtime_factory
    runtime = factory()
    who = owner(runtime)
    runtime.goals.set_preference(who.actor.id, "editor", "vim", "сказав власник")
    runtime.goals.set_preference(who.actor.id, "editor", "neovim", "власник змінив")
    runtime.goals.set_preference(who.actor.id, "temperature_units", "°C", "сказав власник")
    state["script"] = [{"content": "Neovim."}]
    await run_turn(runtime, who, "Який редактор я використовую?")
    system = state["requests"][-1]["messages"][0]["content"]
    assert "editor: neovim" in system and "vim;" not in system
    assert "temperature_units: °C" in system

    guest = runtime.control.create_actor(owner=False, consent=True)
    session = runtime.control.create_session(guest.id)
    task = runtime.control.create_task(session)
    grant = runtime.control.issue_grant(
        guest.id, session, tuple(sorted(GUEST_CAPABILITIES)), task_id=task
    )
    state["script"] = [{"content": "Не знаю."}]
    await runtime.agent.turn(session, grant, "Який редактор у власника?", task_id=task)
    assert "neovim" not in state["requests"][-1]["messages"][0]["content"]


def test_whole_reply_python_call_is_parsed_but_prose_is_not():
    from b12.agent import _text_call

    call = _text_call("memory_store(text='Живу у Львові', kind='fact')")
    assert call.name == "memory_store"
    assert call.arguments == {"text": "Живу у Львові", "kind": "fact"}
    assert _text_call("Ось як: memory_store(text='x')") is None
    assert _text_call("```\nmemory_store(text='x')\n```") is None
    assert _text_call("memory_store(text=open('/etc/passwd').read())") is None
    assert _text_call("memory_store('x')") is None  # positional: ambiguous
    assert _text_call("unknown_tool(x=1)") is None


async def test_whole_reply_python_call_runs_as_a_real_tool_call(runtime_factory):
    state, factory = runtime_factory
    runtime = factory()
    who = owner(runtime)
    state["script"] = [
        {"content": "memory_store(text='Власник живе у Львові біля Стрийського парку.')"},
        {"content": "Запам'ятав: Львів."},
    ]
    result, _ = await run_turn(runtime, who, "Я переїхав до Львова.")
    assert result.state == "completed" and result.content == "Запам'ятав: Львів."
    assert [(r.name, r.status) for r in result.tool_results] == [("memory_store", "completed")]
    assert runtime.memory.search("Львові", who.actor)
