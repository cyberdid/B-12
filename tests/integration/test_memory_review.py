"""ADR-020: post-turn memory review (C1a)."""

import asyncio
import json
from uuid import uuid4

from b12.auth import owner_capabilities
from b12.runtime import open_runtime


async def _start_http(body: bytes = b"external-payload"):
    async def handle(reader, writer):
        await reader.readuntil(b"\r\n\r\n")
        writer.write(
            b"HTTP/1.1 200 OK\r\nContent-Length: "
            + str(len(body)).encode()
            + b"\r\nConnection: close\r\n\r\n"
            + body
        )
        await writer.drain()
        writer.close()
        await writer.wait_closed()

    return await asyncio.start_server(handle, "127.0.0.1", 0)


async def test_review_records_grounded_fact_with_turn_locator(scripted_ollama, tmp_path):
    from b12.memory_review import MemoryReviewer
    from b12.reflection import GROUNDING

    state, base = scripted_ollama
    runtime = open_runtime(
        base.model_copy(
            update={"state_dir": tmp_path / "state", "memory_review": True, "output_tokens": 2048}
        )
    )
    try:
        actor = runtime.control.create_actor(owner=True, consent=True)
        session = runtime.control.create_session(actor.id)
        task = runtime.control.create_task(session)
        grant = runtime.control.issue_grant(
            actor.id, session, owner_capabilities(runtime.settings), task_id=task, ttl_s=600
        )
        state["script"] = [{"content": "Зрозуміло, буду це враховувати."}]
        turn = await runtime.agent.turn(
            session, grant, "Запам'ятай: у мене алергія на горіхи.", task_id=task, timeout_s=60
        )
        assert turn.state == "completed"
        assert runtime.memory.recent(actor) == []

        def review_reply(request):
            system = request["messages"][0]["content"]
            assert GROUNDING in system
            assert turn.turn_id in request["messages"][-1]["content"]
            return {
                "content": json.dumps(
                    {
                        "candidates": [
                            {
                                "text": "У власника алергія на горіхи",
                                "kind": "fact",
                                "turn_id": turn.turn_id,
                            }
                        ]
                    },
                    ensure_ascii=False,
                )
            }

        state["script"] = [review_reply]
        outcome = await MemoryReviewer(runtime).review(actor)
        assert outcome["state"] == "recorded"
        assert outcome["count"] == 1
        records = runtime.memory.recent(actor)
        assert len(records) == 1
        record = records[0]
        assert record.text == "У власника алергія на горіхи"
        assert record.kind == "fact"
        assert record.source == "post_turn_review"
        assert record.origin == "explicit"
        assert record.source_locator == f"turn:{turn.turn_id}"

        # Cursor advanced: second run sees no new turns and makes no model call.
        before = len(state["requests"])
        second = await MemoryReviewer(runtime).review(actor)
        assert second == {"state": "skipped", "reason": "no_turns"}
        assert len(state["requests"]) == before
    finally:
        runtime.close()


async def test_review_skips_duplicates(scripted_ollama, tmp_path):
    from b12.memory_review import MemoryReviewer

    state, base = scripted_ollama
    runtime = open_runtime(
        base.model_copy(
            update={"state_dir": tmp_path / "state", "memory_review": True, "output_tokens": 2048}
        )
    )
    try:
        actor = runtime.control.create_actor(owner=True, consent=True)
        seeded = runtime.memory.remember("Власник п’є каву без цукру.", actor)
        session = runtime.control.create_session(actor.id)
        turn_id = str(uuid4())
        runtime.sessions.commit_turn(
            session,
            actor.id,
            turn_id,
            [
                {"role": "user", "content": "Я п'ю каву без цукру."},
                {"role": "assistant", "content": "Добре."},
            ],
            tags={},
        )
        state["script"] = [
            {
                "content": json.dumps(
                    {
                        "candidates": [
                            {
                                "text": "Власник п'є каву без цукру",
                                "kind": "fact",
                                "turn_id": turn_id,
                            }
                        ]
                    },
                    ensure_ascii=False,
                )
            }
        ]
        outcome = await MemoryReviewer(runtime).review(actor)
        assert outcome["state"] == "skipped"
        records = runtime.memory.recent(actor)
        assert [r.id for r in records] == [seeded.id]
    finally:
        runtime.close()


async def test_review_rejects_invalid_output(scripted_ollama, tmp_path):
    from b12.memory_review import MemoryReviewer

    state, base = scripted_ollama
    runtime = open_runtime(
        base.model_copy(
            update={"state_dir": tmp_path / "state", "memory_review": True, "output_tokens": 2048}
        )
    )
    try:
        actor = runtime.control.create_actor(owner=True, consent=True)
        other = runtime.control.create_actor(owner=False, consent=True)
        session = runtime.control.create_session(actor.id)
        other_session = runtime.control.create_session(other.id)
        turn_id = str(uuid4())
        foreign_turn_id = str(uuid4())
        runtime.sessions.commit_turn(
            session,
            actor.id,
            turn_id,
            [
                {"role": "user", "content": "Я працюю у Львові."},
                {"role": "assistant", "content": "Гаразд."},
            ],
            tags={},
        )
        runtime.sessions.commit_turn(
            other_session,
            other.id,
            foreign_turn_id,
            [
                {"role": "user", "content": "Чужий факт."},
                {"role": "assistant", "content": "Добре."},
            ],
            tags={},
        )

        reviewer = MemoryReviewer(runtime)
        bad_outputs = [
            "не JSON зовсім",
            json.dumps({"wrong_key": []}),
            json.dumps(
                {
                    "candidates": [
                        {"text": "Факт", "kind": "fact", "turn_id": foreign_turn_id},
                    ]
                }
            ),
            json.dumps(
                {
                    "candidates": [
                        {"text": "Факт", "kind": "unknown_kind", "turn_id": turn_id},
                    ]
                }
            ),
            json.dumps(
                {
                    "candidates": [
                        {"text": "   ", "kind": "fact", "turn_id": turn_id},
                    ]
                }
            ),
        ]
        for payload in bad_outputs:
            state["script"] = [{"content": payload}]
            outcome = await reviewer.review(actor)
            assert outcome == {"state": "rejected", "reason": "invalid_output"}
            assert runtime.memory.recent(actor) == []
    finally:
        runtime.close()


async def test_purge_during_review_rejects_the_write(scripted_ollama, tmp_path):
    from b12.memory_review import MemoryReviewer

    state, base = scripted_ollama
    runtime = open_runtime(
        base.model_copy(
            update={"state_dir": tmp_path / "state", "memory_review": True, "output_tokens": 2048}
        )
    )
    try:
        actor = runtime.control.create_actor(owner=True, consent=True)
        secret = runtime.memory.remember("Тимчасовий секрет", actor)
        other = runtime.memory.remember("Ще один запис", actor)
        session = runtime.control.create_session(actor.id)
        turn_id = str(uuid4())
        runtime.sessions.commit_turn(
            session,
            actor.id,
            turn_id,
            [
                {"role": "user", "content": "Запам'ятай: улюблений колір зелений."},
                {"role": "assistant", "content": "Добре."},
            ],
            tags={},
        )

        # Case 1: full PurgeCoordinator.forget runs mid-call (cancels active work + bumps revision).
        receipts = []

        async def purge_mid_call(request):
            receipts.append(await runtime.purge.forget(secret.id, actor.id))
            return {
                "content": json.dumps(
                    {
                        "candidates": [
                            {"text": "Улюблений колір зелений", "kind": "fact", "turn_id": turn_id}
                        ]
                    }
                )
            }

        state["script"] = [purge_mid_call]
        outcome1 = await MemoryReviewer(runtime).review(actor)
        assert outcome1 == {"state": "rejected", "reason": "stale_deletion_revision"}
        for _ in range(100):
            if receipts:
                break
            await asyncio.sleep(0.02)
        assert receipts and receipts[0].state == "complete"
        assert [r.id for r in runtime.memory.recent(actor)] == [other.id]

        # Case 2: direct MemoryStore.forget mid-call bumps deletion_revision without cancel.
        def direct_forget_mid_call(request):
            assert runtime.memory.forget(other.id, actor) is True
            return {
                "content": json.dumps(
                    {
                        "candidates": [
                            {"text": "Улюблений колір зелений", "kind": "fact", "turn_id": turn_id}
                        ]
                    }
                )
            }

        state["script"] = [direct_forget_mid_call]
        outcome2 = await MemoryReviewer(runtime).review(actor)
        assert outcome2 == {"state": "rejected", "reason": "stale_deletion_revision"}
        assert runtime.memory.recent(actor) == []
    finally:
        runtime.close()


async def test_review_never_forgets_or_supersedes(scripted_ollama, tmp_path, monkeypatch):
    from b12.memory_review import MemoryReviewer

    state, base = scripted_ollama
    runtime = open_runtime(
        base.model_copy(
            update={"state_dir": tmp_path / "state", "memory_review": True, "output_tokens": 2048}
        )
    )
    try:
        actor = runtime.control.create_actor(owner=True, consent=True)
        old = runtime.memory.remember("Власник працює на ноутбуці", actor)
        session = runtime.control.create_session(actor.id)
        turn_id = str(uuid4())
        runtime.sessions.commit_turn(
            session,
            actor.id,
            turn_id,
            [
                {"role": "user", "content": "Тепер я працюю на десктопі."},
                {"role": "assistant", "content": "Прийнято."},
            ],
            tags={},
        )

        called = []
        monkeypatch.setattr(
            runtime.memory, "forget", lambda *a, **kw: called.append("forget") or True
        )
        monkeypatch.setattr(
            runtime.memory, "begin_purge", lambda *a, **kw: called.append("begin_purge")
        )
        monkeypatch.setattr(
            runtime.memory, "supersede", lambda *a, **kw: called.append("supersede") or True
        )
        monkeypatch.setattr(runtime.purge, "forget", lambda *a, **kw: called.append("purge_forget"))

        state["script"] = [
            {
                "content": json.dumps(
                    {
                        "candidates": [
                            {
                                "text": "Власник працює на десктопі",
                                "kind": "fact",
                                "turn_id": turn_id,
                            }
                        ]
                    },
                    ensure_ascii=False,
                )
            }
        ]
        outcome = await MemoryReviewer(runtime).review(actor)
        assert outcome["state"] == "recorded"
        assert called == []
        assert runtime.memory.is_live(old.id, actor)
        assert state["requests"][-1].get("tools", []) == []
    finally:
        runtime.close()


async def test_review_excludes_goal_and_tainted_turns_and_requires_consent(
    scripted_ollama, tmp_path
):
    from b12.memory_review import MemoryReviewer

    state, base = scripted_ollama
    server = await _start_http()
    async with server:
        port = server.sockets[0].getsockname()[1]
        runtime = open_runtime(
            base.model_copy(
                update={
                    "state_dir": tmp_path / "state",
                    "memory_review": True,
                    "network_allow": ("127.0.0.1",),
                }
            )
        )
        try:
            unconsented = runtime.control.create_actor(owner=False, consent=False)
            assert await MemoryReviewer(runtime).review(unconsented) == {
                "state": "skipped",
                "reason": "consent_required",
            }

            actor = runtime.control.create_actor(owner=True, consent=True)
            goal_session = runtime.control.create_session(actor.id)
            goal_task = runtime.control.create_task(goal_session)
            runtime.control.link_task_goal(goal_task, str(uuid4()), 1)
            goal_grant = runtime.control.issue_grant(
                actor.id, goal_session, owner_capabilities(runtime.settings), task_id=goal_task
            )
            state["script"] = [{"content": "Фонова ціль виконана."}]
            await runtime.agent.turn(
                goal_session, goal_grant, "Виконай фонову ціль.", task_id=goal_task, timeout_s=60
            )

            chat_session = runtime.control.create_session(actor.id)
            net_task = runtime.control.create_task(chat_session)
            net_grant = runtime.control.issue_grant(
                actor.id, chat_session, owner_capabilities(runtime.settings), task_id=net_task
            )
            state["script"] = [
                {"tool_calls": [("http_fetch", {"url": f"http://127.0.0.1:{port}/"})]},
                {"content": "Отримано з мережі."},
            ]
            await runtime.agent.turn(
                chat_session, net_grant, "Перевір сторінку.", task_id=net_task, timeout_s=60
            )

            requests_before = len(state["requests"])
            skipped = await MemoryReviewer(runtime).review(actor)
            assert skipped == {"state": "skipped", "reason": "no_turns"}
            assert len(state["requests"]) == requests_before
            assert runtime.control.get_meta(f"memory_review:{actor.id}") is not None

            # Subsequent interactive turn IS reviewed.
            ok_task = runtime.control.create_task(chat_session)
            ok_grant = runtime.control.issue_grant(
                actor.id, chat_session, owner_capabilities(runtime.settings), task_id=ok_task
            )
            state["script"] = [{"content": "Зрозуміло."}]
            ok_turn = await runtime.agent.turn(
                chat_session, ok_grant, "Запам'ятай: я використовую Neovim.", task_id=ok_task
            )
            state["script"] = [
                {
                    "content": json.dumps(
                        {
                            "candidates": [
                                {
                                    "text": "Власник використовує Neovim",
                                    "kind": "fact",
                                    "turn_id": ok_turn.turn_id,
                                }
                            ]
                        },
                        ensure_ascii=False,
                    )
                }
            ]
            recorded = await MemoryReviewer(runtime).review(actor)
            assert recorded["state"] == "recorded"
            assert [r.source_locator for r in runtime.memory.recent(actor)] == [
                f"turn:{ok_turn.turn_id}"
            ]
        finally:
            runtime.close()


async def test_review_caps_batch_at_6_turns_and_5_candidates(scripted_ollama, tmp_path):
    from b12.memory_review import MemoryReviewer

    state, base = scripted_ollama
    runtime = open_runtime(
        base.model_copy(
            update={"state_dir": tmp_path / "state", "memory_review": True, "output_tokens": 2048}
        )
    )
    try:
        actor = runtime.control.create_actor(owner=True, consent=True)
        session = runtime.control.create_session(actor.id)
        turn_ids = []
        for idx in range(7):
            tid = str(uuid4())
            turn_ids.append(tid)
            runtime.sessions.commit_turn(
                session,
                actor.id,
                tid,
                [
                    {"role": "user", "content": f"Факт номер {idx}"},
                    {"role": "assistant", "content": f"Зрозуміло {idx}"},
                ],
                tags={},
            )

        def reply_six_candidates(request):
            prompt_body = request["messages"][-1]["content"]
            for tid in turn_ids[:6]:
                assert tid in prompt_body
            assert turn_ids[6] not in prompt_body
            return {
                "content": json.dumps(
                    {
                        "candidates": [
                            {"text": f"Запис {i}", "kind": "fact", "turn_id": turn_ids[i]}
                            for i in range(6)
                        ]
                    },
                    ensure_ascii=False,
                )
            }

        state["script"] = [reply_six_candidates]
        first = await MemoryReviewer(runtime).review(actor)
        assert first["state"] == "recorded"
        assert first["count"] == 5
        assert len(runtime.memory.recent(actor)) == 5

        state["script"] = [
            {
                "content": json.dumps(
                    {
                        "candidates": [
                            {"text": "Сьомий запис", "kind": "decision", "turn_id": turn_ids[6]}
                        ]
                    },
                    ensure_ascii=False,
                )
            }
        ]
        second = await MemoryReviewer(runtime).review(actor)
        assert second["state"] == "recorded"
        assert second["count"] == 1
        assert len(runtime.memory.recent(actor)) == 6
    finally:
        runtime.close()


async def test_review_does_not_run_while_actor_is_busy(scripted_ollama, tmp_path):
    from b12.agent import _Active
    from b12.autonomy import Scheduler

    state, base = scripted_ollama
    off_runtime = open_runtime(
        base.model_copy(update={"state_dir": tmp_path / "off", "memory_review": False})
    )
    off_scheduler = Scheduler(off_runtime)
    try:
        off_actor = off_runtime.control.create_actor(owner=True, consent=True)
        off_sess = off_runtime.control.create_session(off_actor.id)
        off_runtime.sessions.commit_turn(
            off_sess,
            off_actor.id,
            str(uuid4()),
            [{"role": "user", "content": "Привіт"}, {"role": "assistant", "content": "Вітаю"}],
            tags={},
        )
        assert await off_scheduler.review_memory_idle() == []
        assert state["requests"] == []
    finally:
        off_scheduler.close()
        off_runtime.close()

    runtime = open_runtime(
        base.model_copy(update={"state_dir": tmp_path / "on", "memory_review": True})
    )
    scheduler = Scheduler(runtime)
    try:
        actor = runtime.control.create_actor(owner=True, consent=True)
        session = runtime.control.create_session(actor.id)
        turn_id = str(uuid4())
        runtime.sessions.commit_turn(
            session,
            actor.id,
            turn_id,
            [
                {"role": "user", "content": "Запам'ятай: улюблена мова Python."},
                {"role": "assistant", "content": "Добре."},
            ],
            tags={},
        )
        runtime.agent.active["active-user-turn"] = _Active(actor.id, asyncio.Event())
        busy_outcomes = await scheduler.review_memory_idle()
        assert len(busy_outcomes) == 1
        assert busy_outcomes[0]["state"] == "skipped"
        assert busy_outcomes[0]["reason"] == "actor_busy"
        assert state["requests"] == []
        del runtime.agent.active["active-user-turn"]

        runtime.attention.set_stopped(actor.id, True)
        stopped_outcomes = await scheduler.review_memory_idle()
        assert state["requests"] == []
        assert all(o["state"] == "skipped" for o in stopped_outcomes)
        runtime.attention.set_stopped(actor.id, False)

        state["script"] = [
            {
                "content": json.dumps(
                    {
                        "candidates": [
                            {
                                "text": "Улюблена мова власника — Python",
                                "kind": "preference",
                                "turn_id": turn_id,
                            }
                        ]
                    },
                    ensure_ascii=False,
                )
            }
        ]
        outcomes = await scheduler.review_memory_idle()
        assert len(outcomes) == 1
        assert outcomes[0]["state"] == "recorded"
        assert [r.text for r in runtime.memory.recent(actor)] == ["Улюблена мова власника — Python"]
    finally:
        scheduler.close()
        runtime.close()


async def test_clearing_session_forgets_reviewed_records(scripted_ollama, tmp_path):
    from b12.memory_review import MemoryReviewer

    state, base = scripted_ollama
    runtime = open_runtime(
        base.model_copy(update={"state_dir": tmp_path / "state", "memory_review": True})
    )
    try:
        actor = runtime.control.create_actor(owner=True, consent=True)
        sess1 = runtime.control.create_session(actor.id)
        sess2 = runtime.control.create_session(actor.id)
        t1, t2 = str(uuid4()), str(uuid4())
        runtime.sessions.commit_turn(
            sess1,
            actor.id,
            t1,
            [
                {"role": "user", "content": "Мій секретний код двері 8844."},
                {"role": "assistant", "content": "Зафіксувала."},
            ],
            tags={},
        )
        runtime.sessions.commit_turn(
            sess2,
            actor.id,
            t2,
            [
                {"role": "user", "content": "Я живу в Одесі."},
                {"role": "assistant", "content": "Зрозуміло."},
            ],
            tags={},
        )
        state["script"] = [
            {
                "content": json.dumps(
                    {
                        "candidates": [
                            {"text": "Код двері 8844", "kind": "fact", "turn_id": t1},
                            {"text": "Власник живе в Одесі", "kind": "fact", "turn_id": t2},
                        ]
                    },
                    ensure_ascii=False,
                )
            }
        ]
        outcome = await MemoryReviewer(runtime).review(actor)
        assert outcome["state"] == "recorded"
        assert outcome["count"] == 2

        cleared = runtime.sessions.clear_session(sess1, actor.id)
        assert cleared == [t1]
        remaining = runtime.memory.recent(actor)
        assert [r.text for r in remaining] == ["Власник живе в Одесі"]
        assert runtime.memory.search("8844", actor) == []
    finally:
        runtime.close()


async def test_scheduler_run_invokes_review_memory_idle_after_reflect_idle(
    scripted_ollama, tmp_path, monkeypatch
):
    from b12.autonomy import Scheduler

    state, base = scripted_ollama
    runtime = open_runtime(
        base.model_copy(
            update={
                "state_dir": tmp_path / "state",
                "memory_review": True,
                "scheduler_tick_s": 0.01,
            }
        )
    )
    scheduler = Scheduler(runtime)
    order: list[str] = []
    stop = asyncio.Event()

    async def fake_tick():
        order.append("tick")
        return []

    async def fake_reflect():
        order.append("reflect")
        return []

    original_review = scheduler.review_memory_idle

    async def spy_review():
        order.append("review")
        res = await original_review()
        stop.set()
        return res

    monkeypatch.setattr(scheduler, "tick", fake_tick)
    monkeypatch.setattr(scheduler, "reflect_idle", fake_reflect)
    monkeypatch.setattr(scheduler, "review_memory_idle", spy_review)
    try:
        actor = runtime.control.create_actor(owner=True, consent=True)
        session = runtime.control.create_session(actor.id)
        tid = str(uuid4())
        runtime.sessions.commit_turn(
            session,
            actor.id,
            tid,
            [
                {"role": "user", "content": "Запам'ятай: сервер у Києві."},
                {"role": "assistant", "content": "Добре."},
            ],
            tags={},
        )
        state["script"] = [
            {
                "content": json.dumps(
                    {"candidates": [{"text": "Сервер у Києві", "kind": "fact", "turn_id": tid}]},
                    ensure_ascii=False,
                )
            }
        ]
        await asyncio.wait_for(scheduler.run(stop), timeout=5)
        assert order == ["tick", "reflect", "review"]
        assert [r.text for r in runtime.memory.recent(actor)] == ["Сервер у Києві"]
    finally:
        scheduler.close()
        runtime.close()
