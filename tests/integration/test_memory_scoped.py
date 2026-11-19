"""ADR-016 end to end: decision packet, conflicts, no-evidence note, protected commitments."""

from datetime import UTC, datetime

import pytest

from b12.auth import owner_capabilities
from b12.runtime import open_runtime

PINNED = datetime(2026, 12, 1, 8, 0, tzinfo=UTC)


def _runtime(settings, tmp_path, scoped=True):
    runtime = open_runtime(
        settings.model_copy(
            update={
                "state_dir": tmp_path / ("on" if scoped else "off"),
                "memory_scoped": scoped,
                "memory_enrichment": False,
            }
        )
    )
    runtime.agent.clock = lambda: PINNED
    return runtime


async def test_packet_carries_state_scope_and_origin(profile_settings, tmp_path):
    runtime = _runtime(profile_settings, tmp_path)
    try:
        actor = runtime.control.create_actor(owner=True, consent=True)
        night = runtime.memory.remember(
            "Не надсилати нагадувань до 14:00 під час нічних змін.",
            actor,
            kind="preference",
            applies_when="коли власник працює в нічну зміну",
            origin="explicit",
        )
        diet = runtime.memory.remember(
            "Не пропонувати солодкого під час дієти.", actor, kind="preference",
            valid_to="2026-11-25",
        )
        later = runtime.memory.remember(
            "З 10 грудня нагадування о 7:00.", actor, kind="preference", valid_from="2026-12-10"
        )
        evidence = await runtime.agent._recall("нагадувань солодкого нагадування", actor)
        meta = {item["id"]: item["meta"] for item in evidence}
        assert meta[night.id]["state"] == "чинне"
        assert meta[night.id]["applies_when"] == "коли власник працює в нічну зміну"
        assert meta[night.id]["origin"] == "власник сказав прямо"
        assert meta[diet.id]["state"] == "минуло"
        assert meta[later.id]["state"] == "ще не чинне"
    finally:
        runtime.close()


async def test_replaced_history_is_marked_and_revoked_never_offered(profile_settings, tmp_path):
    runtime = _runtime(profile_settings, tmp_path)
    try:
        actor = runtime.control.create_actor(owner=True, consent=True)
        old = runtime.memory.remember("Пароль гостьового Wi-Fi сосна-27.", actor)
        new = runtime.memory.remember("Пароль гостьового Wi-Fi ялина-41.", actor)
        runtime.memory.supersede(old.id, actor, replaced_by=new.id)
        rule = runtime.memory.remember("Звіти про гостьового Wi-Fi лише у PDF.", actor)
        runtime.memory.supersede(rule.id, actor)
        evidence = await runtime.agent._recall("пароль гостьового Wi-Fi", actor)
        meta = {item["id"]: item["meta"] for item in evidence}
        assert meta[new.id]["state"] == "чинне"
        assert meta[old.id]["state"] == "замінено"
        assert rule.id not in meta
    finally:
        runtime.close()


async def test_revoked_record_is_not_returned_by_memory_search(
    scripted_ollama, tmp_path
):
    import json

    state, settings = scripted_ollama
    runtime = _runtime(settings, tmp_path)
    try:
        actor, session, task, grant = await _turn(runtime, state, "")
        revoked = runtime.memory.remember("Домофонний код — 4512.", actor)
        state["script"] = [
            {"tool_calls": [("memory_supersede", {"memory_id": revoked.id, "replaced_by": ""})]},
            {"tool_calls": [("memory_search", {"query": "домофонний код"})]},
            {"content": "Готово."},
        ]
        await runtime.agent.turn(
            session, grant, "Знайди код домофона в моїх записах.", task_id=task, timeout_s=60
        )
        tool_result = [
            message for message in state["requests"][-1]["messages"] if message["role"] == "tool"
        ][-1]
        assert revoked.id not in json.dumps(tool_result, ensure_ascii=False)
    finally:
        runtime.close()


async def test_two_current_records_that_disagree_are_linked(profile_settings, tmp_path):
    runtime = _runtime(profile_settings, tmp_path)
    try:
        actor = runtime.control.create_actor(owner=True, consent=True)
        a = runtime.memory.remember("Код домофона в під'їзді — 4512.", actor)
        b = runtime.memory.remember("Код домофона в під'їзді — 4521.", actor)
        other = runtime.memory.remember("Донька займається плаванням по середах.", actor)
        evidence = await runtime.agent._recall("код домофона під'їзді плаванням", actor)
        meta = {item["id"]: item["meta"] for item in evidence}
        assert meta[a.id]["conflicts_with"] == [b.id]
        assert meta[b.id]["conflicts_with"] == [a.id]
        assert "conflicts_with" not in meta[other.id]
    finally:
        runtime.close()


async def test_without_the_flag_evidence_keeps_id_and_text_only(profile_settings, tmp_path):
    runtime = _runtime(profile_settings, tmp_path, scoped=False)
    try:
        actor = runtime.control.create_actor(owner=True, consent=True)
        runtime.memory.remember("Код домофона — 4512.", actor, applies_when="завжди")
        evidence = await runtime.agent._recall("код домофона", actor)
        assert evidence and all(set(item) == {"id", "text"} for item in evidence)
    finally:
        runtime.close()


async def _turn(runtime, state, text):
    actor = runtime.control.create_actor(owner=True, consent=True)
    session = runtime.control.create_session(actor.id)
    task = runtime.control.create_task(session)
    grant = runtime.control.issue_grant(
        actor.id, session, owner_capabilities(runtime.settings), task_id=task, ttl_s=600
    )
    return actor, session, task, grant


async def test_prompt_has_rules_no_evidence_note_and_split_goals(scripted_ollama, tmp_path):
    state, base = scripted_ollama
    runtime = open_runtime(
        base.model_copy(update={"state_dir": tmp_path / "s", "memory_scoped": True})
    )
    try:
        actor, session, task, grant = await _turn(runtime, state, "")
        runtime.goals.create(actor.id, session, "Пофарбувати паркан.", "готово")
        gate = runtime.goals.create(actor.id, session, "Пофарбувати ворота.", "готово")
        runtime.goals.set_status(gate["id"], actor.id, "abandoned", "власник передумав")
        state["script"] = [{"content": "Паркан."}]
        await runtime.agent.turn(session, grant, "Що ще фарбувати?", task_id=task, timeout_s=60)
        system = state["requests"][-1]["messages"][0]["content"]
        assert "state «чинне»" in system
        assert "Доказів із пам'яті для цього запиту немає" in system
        assert "Відкриті задачі співрозмовника" in system and "Пофарбувати паркан." in system
        assert "не відновлювати без прямої вказівки власника" in system
        opened = system.split("Закриті")[0]
        assert "Пофарбувати ворота." not in opened
    finally:
        runtime.close()


async def test_prompt_prefers_explicit_owner_memory_over_assistant_inference(
    scripted_ollama, tmp_path
):
    state, base = scripted_ollama
    runtime = open_runtime(
        base.model_copy(update={"state_dir": tmp_path / "s", "memory_scoped": True})
    )
    try:
        actor, session, task, grant = await _turn(runtime, state, "")
        state["script"] = [{"content": "Одна ложка."}]
        await runtime.agent.turn(
            session, grant, "Скільки цукру класти в каву?", task_id=task, timeout_s=60
        )
        system = state["requests"][-1]["messages"][0]["content"]
        assert "віддай перевагу запису «власник сказав прямо»" in system
        assert "а інший «помічник вивів»" in system
        assert "origin є позначкою моделі, а не незалежною перевіркою походження" in system
        assert "В інших поточних конфліктах наведи обидва джерела й попроси уточнення" in system
    finally:
        runtime.close()


async def test_achieved_goal_with_superseded_evidence_is_flagged(scripted_ollama, tmp_path):
    state, base = scripted_ollama
    runtime = open_runtime(
        base.model_copy(update={"state_dir": tmp_path / "s", "memory_scoped": True})
    )
    try:
        actor, session, task, grant = await _turn(runtime, state, "")
        passed = runtime.memory.remember("Калібрування ваг: PASS.", actor)
        goal = runtime.goals.create(actor.id, session, "Відкалібрувати ваги.", "PASS")
        runtime.goals.complete(goal["id"], actor, [passed.id], lambda e: True)
        failed = runtime.memory.remember("Повторна перевірка ваг: FAIL.", actor)
        runtime.memory.supersede(passed.id, actor, replaced_by=failed.id)
        state["script"] = [{"content": "Ні."}]
        await runtime.agent.turn(session, grant, "Ваги відкалібровані?", task_id=task, timeout_s=60)
        system = state["requests"][-1]["messages"][0]["content"]
        assert "Відкалібрувати ваги. (доказ виконання вже не чинний)" in system
    finally:
        runtime.close()


def test_closed_goal_cannot_become_active_without_reopen(tmp_path):
    from b12.goals import GoalStore

    store = GoalStore(tmp_path / "goals.sqlite3")
    try:
        goal = store.create("owner", "session", "Звіт для клубу.", "звіт")
        store.set_status(goal["id"], "owner", "abandoned", "скасовано")
        with pytest.raises(PermissionError):
            store.set_status(goal["id"], "owner", "active", "autonomy")
        assert store.get(goal["id"], "owner")["status"] == "abandoned"
        reopened = store.set_status(goal["id"], "owner", "active", "owner", reopen=True)
        assert reopened["status"] == "active"
    finally:
        store.close()


def test_abandoned_goal_cannot_be_completed_by_autonomy_without_reopen(tmp_path):
    from types import SimpleNamespace
    from uuid import uuid4

    from b12.goals import GoalStore

    store = GoalStore(tmp_path / "goals.sqlite3")
    try:
        goal = store.create("owner", "session", "Перевірити звіт.", "звіт")
        store.set_status(goal["id"], "owner", "abandoned", "власник скасував")
        with pytest.raises(PermissionError, match="abandoned goal"):
            store.complete(
                goal["id"], SimpleNamespace(id="owner"), [str(uuid4())], lambda _: True
            )
        assert store.get(goal["id"], "owner")["status"] == "abandoned"
    finally:
        store.close()
