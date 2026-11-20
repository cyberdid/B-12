"""Integration tests for Task H3: event-based standing intents."""

import asyncio
import json
import sqlite3
from datetime import UTC, datetime, timedelta

from b12.auth import owner_capabilities
from b12.runtime import open_runtime


def _turn(runtime, actor, session, text, *, timeout_s=60):
    task = runtime.control.create_task(session)
    grant = runtime.control.issue_grant(
        actor.id, session, owner_capabilities(runtime.settings), task_id=task, ttl_s=600
    )
    return runtime.agent.turn(session, grant, text, task_id=task, timeout_s=timeout_s)


async def test_matching_keyword_injects_once_then_cools_down(scripted_ollama, tmp_path):
    state, base = scripted_ollama
    now = datetime(2026, 11, 20, 12, 0, tzinfo=UTC)
    runtime = open_runtime(
        base.model_copy(update={"state_dir": tmp_path / "state", "standing_intents": True})
    )
    try:
        runtime.agent.clock = lambda: now
        runtime.schedules.clock = lambda: now
        actor = runtime.control.create_actor(owner=True, consent=True)
        session = runtime.control.create_session(actor.id)
        intent = runtime.schedules.add_intent(
            actor.id,
            ["принтер", "п'ятниця"],
            "Перевір підтримку CUPS для цього принтера.",
            days=90,
            fires_left=3,
            cooldown_s=86400,
            now=now,
        )

        # Turn 1: matches whole word "принтер" even with punctuation and multi-round tools.
        state["script"] = [
            {"tool_calls": [("current_time", {})]},
            {"content": "Перевірив час і врахував намір."},
        ]
        await _turn(runtime, actor, session, "Який принтер, до речі, краще купити?")
        assert len(state["requests"]) == 2
        assert "Перевір підтримку CUPS" in state["requests"][0]["messages"][0]["content"]
        # Fired only once for the whole multi-round turn: fires_left went 3 -> 2.
        [stored] = runtime.schedules.list_intents(actor.id)
        assert stored["id"] == intent["id"]
        assert stored["fires_left"] == 2

        # Turn 2 immediately after: still inside 86400s cooldown -> must NOT inject.
        state["script"] = [{"content": "Відповідь без повтору."}]
        await _turn(runtime, actor, session, "А цей принтер має Wi-Fi?")
        assert "Перевір підтримку CUPS" not in state["requests"][-1]["messages"][0]["content"]
        assert runtime.schedules.list_intents(actor.id)[0]["fires_left"] == 2

        # Turn 3 after cooldown expires, testing apostrophe normalization ("п’ятницю" vs "п'ятниця"
        # exact whole word "п’ятниця"): fires a second time.
        now += timedelta(seconds=86401)
        state["script"] = [{"content": "Нагадав про п'ятницю."}]
        await _turn(runtime, actor, session, "Сьогодні ж п’ятниця!")
        assert "Перевір підтримку CUPS" in state["requests"][-1]["messages"][0]["content"]
        assert runtime.schedules.list_intents(actor.id)[0]["fires_left"] == 1
    finally:
        runtime.close()


async def test_budget_and_expiry_stop_firing(scripted_ollama, tmp_path):
    state, base = scripted_ollama
    now = datetime(2026, 11, 20, 12, 0, tzinfo=UTC)
    runtime = open_runtime(
        base.model_copy(update={"state_dir": tmp_path / "state", "standing_intents": True})
    )
    try:
        runtime.agent.clock = lambda: now
        runtime.schedules.clock = lambda: now
        actor = runtime.control.create_actor(owner=True, consent=True)
        session = runtime.control.create_session(actor.id)

        budget_intent = runtime.schedules.add_intent(
            actor.id,
            ["роутер"],
            "Перевір прошивку OpenWrt.",
            days=90,
            fires_left=2,
            cooldown_s=60,
            now=now,
        )
        expiring_intent = runtime.schedules.add_intent(
            actor.id,
            ["батарея"],
            "Запитай про ємність LiFePO4.",
            days=1,
            fires_left=5,
            cooldown_s=60,
            now=now,
        )

        # Fire budget_intent twice (budget 2 -> 0 -> exhausted).
        for step in range(2):
            state["script"] = [{"content": f"Про роутер {step}."}]
            await _turn(runtime, actor, session, "Оновити роутер?")
            assert "Перевір прошивку OpenWrt." in state["requests"][-1]["messages"][0]["content"]
            now += timedelta(seconds=61)

        # Third match: budget exhausted, stops firing.
        state["script"] = [{"content": "Про роутер 3."}]
        await _turn(runtime, actor, session, "Ще раз про роутер")
        assert "Перевір прошивку OpenWrt." not in state["requests"][-1]["messages"][0]["content"]
        intents_by_id = {i["id"]: i for i in runtime.schedules.list_intents(actor.id)}
        assert intents_by_id[budget_intent["id"]]["fires_left"] == 0
        assert intents_by_id[budget_intent["id"]]["status"] != "active"

        # Advance past 1-day expiry -> expiring_intent stops firing.
        now += timedelta(days=2)
        state["script"] = [{"content": "Про батарею."}]
        await _turn(runtime, actor, session, "Яка батарея краща?")
        assert "Запитай про ємність LiFePO4." not in state["requests"][-1]["messages"][0]["content"]
        intents_by_id = {i["id"]: i for i in runtime.schedules.list_intents(actor.id)}
        assert intents_by_id[expiring_intent["id"]]["status"] == "expired"
    finally:
        runtime.close()


async def test_no_match_no_block(scripted_ollama, tmp_path):
    state, base = scripted_ollama
    now = datetime(2026, 11, 20, 12, 0, tzinfo=UTC)
    runtime = open_runtime(
        base.model_copy(update={"state_dir": tmp_path / "state", "standing_intents": True})
    )
    try:
        runtime.agent.clock = lambda: now
        runtime.schedules.clock = lambda: now
        actor = runtime.control.create_actor(owner=True, consent=True)
        session = runtime.control.create_session(actor.id)
        runtime.schedules.add_intent(
            actor.id,
            ["принт"],
            "Не повинно збігтись на 'принтер'.",
            days=90,
            now=now,
        )

        # "принтер" is NOT a whole-word match for "принт".
        state["script"] = [{"content": "Звичайна відповідь."}]
        await _turn(runtime, actor, session, "Потрібен новий принтер.")
        req_text = json.dumps(state["requests"][-1], ensure_ascii=False)
        assert "Не повинно збігтись" not in req_text
        assert "наміри власника" not in req_text
        assert runtime.schedules.list_intents(actor.id)[0]["fires_left"] == 3
    finally:
        runtime.close()


async def test_max_three_intents_and_flag_off_and_actor_isolation(scripted_ollama, tmp_path):
    state, base = scripted_ollama
    now = datetime(2026, 11, 20, 12, 0, tzinfo=UTC)

    # Flag off -> nothing injected.
    off_rt = open_runtime(
        base.model_copy(update={"state_dir": tmp_path / "off", "standing_intents": False})
    )
    try:
        actor = off_rt.control.create_actor(owner=True, consent=True)
        session = off_rt.control.create_session(actor.id)
        off_rt.schedules.add_intent(actor.id, ["датчик"], "Секретний намір", now=now)
        state["script"] = [{"content": "Ок."}]
        await _turn(off_rt, actor, session, "Перевір датчик.")
        assert "Секретний намір" not in json.dumps(state["requests"][-1], ensure_ascii=False)
    finally:
        off_rt.close()

    # Flag on -> at most 3 injected, remaining stay untouched; guest does not see owner intents.
    on_rt = open_runtime(
        base.model_copy(update={"state_dir": tmp_path / "on", "standing_intents": True})
    )
    try:
        on_rt.agent.clock = lambda: now
        on_rt.schedules.clock = lambda: now
        owner = on_rt.control.create_actor(owner=True, consent=True)
        guest = on_rt.control.create_actor(owner=False, consent=True)
        owner_sess = on_rt.control.create_session(owner.id)
        guest_sess = on_rt.control.create_session(guest.id)
        created = [
            on_rt.schedules.add_intent(owner.id, ["датчик"], f"Намір {i}", now=now)
            for i in range(5)
        ]

        # Guest turn does not trigger owner's intents.
        guest_task = on_rt.control.create_task(guest_sess)
        guest_grant = on_rt.control.issue_grant(
            guest.id, guest_sess, ("time.read",), task_id=guest_task, ttl_s=600
        )
        state["script"] = [{"content": "Привіт, гостю."}]
        await on_rt.agent.turn(guest_sess, guest_grant, "Розкажи про датчик", task_id=guest_task)
        assert "Намір" not in json.dumps(state["requests"][-1], ensure_ascii=False)

        # Owner turn injects at most 3 intents; 4th and 5th remain unfired (fires_left=3).
        state["script"] = [{"content": "Зрозумів."}]
        await _turn(on_rt, owner, owner_sess, "Що там із датчик?")
        sys_msg = state["requests"][-1]["messages"][0]["content"]
        injected = [i for i in range(5) if f"Намір {i}" in sys_msg]
        assert len(injected) == 3
        by_id = {row["id"]: row for row in on_rt.schedules.list_intents(owner.id)}
        assert sum(1 for row in created if by_id[row["id"]]["fires_left"] == 2) == 3
        assert sum(1 for row in created if by_id[row["id"]]["fires_left"] == 3) == 2
    finally:
        on_rt.close()


async def test_cli_intent_add_and_table_schema(scripted_ollama, tmp_path, monkeypatch, capsys):
    from b12.cli import main

    _, settings = scripted_ollama
    monkeypatch.setenv("B12_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("B12_MODEL", settings.model)
    monkeypatch.setenv("B12_MODEL_PROFILE", str(settings.model_profile))
    monkeypatch.setenv("B12_TOKENIZER_DIR", str(settings.tokenizer_dir))
    monkeypatch.setenv("B12_OLLAMA_URL", settings.ollama_url)
    monkeypatch.setenv("B12_NUM_CTX", str(settings.num_ctx))
    monkeypatch.setenv("B12_OUTPUT_TOKENS", str(settings.output_tokens))

    assert await asyncio.to_thread(main, ["init"]) == 0
    capsys.readouterr()

    assert (
        await asyncio.to_thread(
            main,
            [
                "intent",
                "add",
                "--keyword",
                "принтер",
                "--keyword",
                "сканер",
                "--text",
                "Перевірити драйвер",
                "--days",
                "90",
            ],
        )
        == 0
    )
    created = json.loads(capsys.readouterr().out)
    assert created["keywords"] == ["принтер", "сканер"]
    assert created["fires_left"] == 3
    assert created["cooldown_s"] == 86400
    assert created["status"] == "active"

    assert await asyncio.to_thread(main, ["intent", "list"]) == 0
    assert [row["id"] for row in json.loads(capsys.readouterr().out)] == [created["id"]]
    assert await asyncio.to_thread(main, ["intent", "remove", created["id"]]) == 0
    assert json.loads(capsys.readouterr().out) == {"removed": created["id"]}
    assert await asyncio.to_thread(main, ["intent", "list"]) == 0
    assert json.loads(capsys.readouterr().out) == []

    db = sqlite3.connect(tmp_path / "state" / "goals" / "goals.sqlite3")
    cols = [r[1] for r in db.execute("PRAGMA table_info(intents)")]
    db.close()
    assert {
        "id",
        "actor_id",
        "keywords",
        "text",
        "expires_at",
        "fires_left",
        "cooldown_s",
        "last_fired_at",
        "status",
    } <= set(cols)
