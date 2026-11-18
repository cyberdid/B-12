"""ADR-015 end to end: recall and the model request carry temporal context only with the flag."""

from datetime import UTC, datetime

from b12.runtime import open_runtime

PINNED = datetime(2026, 12, 1, 8, 0, tzinfo=UTC)


def _runtime(settings, tmp_path, temporal):
    runtime = open_runtime(
        settings.model_copy(
            update={
                "state_dir": tmp_path / ("on" if temporal else "off"),
                "memory_temporal": temporal,
                "memory_enrichment": False,
            }
        )
    )
    runtime.agent.clock = lambda: PINNED
    return runtime


async def test_recall_with_flag_shows_history_after_its_replacement(profile_settings, tmp_path):
    runtime = _runtime(profile_settings, tmp_path, True)
    try:
        actor = runtime.control.create_actor(owner=True, consent=True)
        old = runtime.memory.remember("Робоча напруга стенду 12 В.", actor, valid_to="2026-11-15")
        new = runtime.memory.remember(
            "Робоча напруга стенду 24 В.", actor, valid_from="2026-11-15", event_time="2026-11-15"
        )
        runtime.memory.supersede(old.id, actor, replaced_by=new.id)
        evidence = await runtime.agent._recall("напруга стенду", actor)
        ids = [item["id"] for item in evidence]
        assert ids.index(old.id) == ids.index(new.id) + 1
        texts = {item["id"]: item["text"] for item in evidence}
        assert texts[new.id].startswith("[подія 2026-11-15 · записано")
        assert "замінено новішим записом" in texts[old.id]
        assert "чинність минула" in texts[old.id]
    finally:
        runtime.close()


async def test_without_flag_recall_is_unchanged(profile_settings, tmp_path):
    runtime = _runtime(profile_settings, tmp_path, False)
    try:
        actor = runtime.control.create_actor(owner=True, consent=True)
        old = runtime.memory.remember("Робоча напруга стенду 12 В.", actor)
        new = runtime.memory.remember("Робоча напруга стенду 24 В.", actor, event_time="2026-11-15")
        runtime.memory.supersede(old.id, actor, replaced_by=new.id)
        evidence = await runtime.agent._recall("напруга стенду", actor)
        assert [item["id"] for item in evidence] == [new.id]
        assert evidence[0]["text"].startswith(f"[{new.created_at[:10]}] ")
    finally:
        runtime.close()


async def test_model_is_told_today_only_with_the_flag(scripted_ollama, tmp_path):
    state, base = scripted_ollama
    for temporal in (False, True):
        runtime = _runtime(base, tmp_path / str(temporal), temporal)
        try:
            actor = runtime.control.create_actor(owner=True, consent=True)
            session = runtime.control.create_session(actor.id)
            from b12.auth import owner_capabilities

            task = runtime.control.create_task(session)
            grant = runtime.control.issue_grant(
                actor.id, session, owner_capabilities(runtime.settings), task_id=task, ttl_s=600
            )
            state["script"] = [{"content": "Привіт."}]
            await runtime.agent.turn(session, grant, "Привіт", task_id=task, timeout_s=60)
            system = state["requests"][-1]["messages"][0]["content"]
            assert ("Сьогодні: 2026-12-01." in system) is temporal
        finally:
            runtime.close()


async def test_memory_store_offers_temporal_fields_only_with_the_flag(scripted_ollama, tmp_path):
    from b12.auth import owner_capabilities

    state, base = scripted_ollama
    for temporal in (False, True):
        runtime = _runtime(base, tmp_path / f"store-{temporal}", temporal)
        try:
            actor = runtime.control.create_actor(owner=True, consent=True)
            session = runtime.control.create_session(actor.id)
            task = runtime.control.create_task(session)
            grant = runtime.control.issue_grant(
                actor.id, session, owner_capabilities(runtime.settings), task_id=task, ttl_s=600
            )
            call = {"text": "Перший запуск генератора G-4.", "kind": "fact"}
            if temporal:
                call["event_time"] = "2026-10-02"
            state["script"] = [
                {"tool_calls": [("memory_store", call)]},
                {"content": "Запам'ятала."},
            ]
            await runtime.agent.turn(
                session,
                grant,
                "Запам'ятай: генератор G-4 вперше запустили 2 жовтня.",
                task_id=task,
                timeout_s=60,
            )
            store = next(
                t for t in state["requests"][-2]["tools"] if t["function"]["name"] == "memory_store"
            )
            assert ("event_time" in store["function"]["parameters"]["properties"]) is temporal
            [record] = runtime.memory.search("генератора", actor)
            if temporal:
                assert record.event_time == "2026-10-02"
                assert record.temporal_source == "conversation"
            else:
                assert record.event_time is None
        finally:
            runtime.close()
