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


async def test_memory_search_exposes_as_of_only_when_temporal_and_as_of_are_on(
    scripted_ollama, tmp_path
):
    from b12.auth import owner_capabilities

    state, base = scripted_ollama
    combos = (
        (False, False, False),
        (False, True, False),
        (True, False, False),
        (True, True, True),
    )
    for temporal, as_of_flag, expected_prop in combos:
        state["requests"].clear()
        state["script"] = (
            [
                {"tool_calls": [("memory_search", {"query": "Тариф", "as_of": "2026-10-15"})]},
                {"tool_calls": [("memory_search", {"query": "Тариф", "as_of": "вчора"})]},
                {"content": "Тоді діяв 100 грн."},
            ]
            if expected_prop
            else [{"content": "Гаразд."}]
        )
        runtime = open_runtime(
            base.model_copy(
                update={
                    "state_dir": tmp_path / f"t-{temporal}-a-{as_of_flag}",
                    "memory_temporal": temporal,
                    "memory_as_of": as_of_flag,
                }
            )
        )
        try:
            actor = runtime.control.create_actor(owner=True, consent=True)
            old = runtime.memory.remember(
                "Тариф: 100 грн.", actor, valid_from="2026-01-01", valid_to="2026-10-31"
            )
            new = runtime.memory.remember("Тариф: 200 грн.", actor, valid_from="2026-11-01")
            runtime.memory.supersede(old.id, actor, replaced_by=new.id)
            session = runtime.control.create_session(actor.id)
            task = runtime.control.create_task(session)
            grant = runtime.control.issue_grant(
                actor.id, session, owner_capabilities(runtime.settings), task_id=task, ttl_s=600
            )
            await runtime.agent.turn(session, grant, "Привіт", task_id=task, timeout_s=60)
        finally:
            runtime.close()

        search_tool = next(
            t for t in state["requests"][0]["tools"] if t["function"]["name"] == "memory_search"
        )
        assert ("as_of" in search_tool["function"]["parameters"]["properties"]) is expected_prop
        if expected_prop:
            tool_msg = next(m for m in state["requests"][1]["messages"] if m["role"] == "tool")
            assert "100 грн" in tool_msg["content"]
            assert "200 грн" not in tool_msg["content"]
            bad_msg = [m for m in state["requests"][2]["messages"] if m["role"] == "tool"][-1]
            assert "unsupported" in bad_msg["content"]


async def test_memory_ranking_flag_exposes_importance_and_ranks_recall(scripted_ollama, tmp_path):
    from datetime import UTC, datetime

    from b12.auth import owner_capabilities

    state, base = scripted_ollama
    for ranking in (False, True):
        state["requests"].clear()
        state["script"] = (
            [
                {
                    "tool_calls": [
                        (
                            "memory_store",
                            {"text": "Резервний ключ у сейфі.", "kind": "fact", "importance": 9},
                        )
                    ]
                },
                {
                    "tool_calls": [
                        (
                            "memory_store",
                            {"text": "Незначна деталь про ключ.", "kind": "fact", "importance": 0},
                        )
                    ]
                },
                {"content": "Запам'ятала."},
            ]
            if ranking
            else [{"content": "Гаразд."}]
        )
        runtime = open_runtime(
            base.model_copy(
                update={
                    "state_dir": tmp_path / f"rank-{ranking}",
                    "memory_temporal": True,
                    "memory_ranking": ranking,
                }
            )
        )
        try:
            runtime.agent.clock = lambda: datetime(2026, 11, 20, 12, 0, tzinfo=UTC)
            actor = runtime.control.create_actor(owner=True, consent=True)
            # Seed old trivial & recent important records matching "ліхтар" with limit=1 check.
            old_trivial = runtime.memory.remember(
                "Старий ліхтар лежав у коморі.", actor, importance=1
            )
            recent_important = runtime.memory.remember(
                "Аварійний ліхтар біля виходу.", actor, importance=9
            )
            runtime.memory._connection.execute(
                "UPDATE memories SET created_at=? WHERE id=?",
                ("2026-08-01T12:00:00+00:00", old_trivial.id),
            )
            runtime.memory._connection.execute(
                "UPDATE memories SET created_at=? WHERE id=?",
                ("2026-11-19T12:00:00+00:00", recent_important.id),
            )
            recalled = await runtime.agent._recall("Де ліхтар?", actor, limit=1)
            if ranking:
                assert [item["id"] for item in recalled] == [recent_important.id]

            session = runtime.control.create_session(actor.id)
            task = runtime.control.create_task(session)
            grant = runtime.control.issue_grant(
                actor.id, session, owner_capabilities(runtime.settings), task_id=task, ttl_s=600
            )
            await runtime.agent.turn(session, grant, "Привіт", task_id=task, timeout_s=60)
            store_tool = next(
                t for t in state["requests"][0]["tools"] if t["function"]["name"] == "memory_store"
            )
            assert ("importance" in store_tool["function"]["parameters"]["properties"]) is ranking
            if ranking:
                [important_rec] = runtime.memory.search("сейфі", actor)
                [unknown_rec] = runtime.memory.search("Незначна", actor)
                assert important_rec.importance == 9
                assert unknown_rec.importance is None
        finally:
            runtime.close()
