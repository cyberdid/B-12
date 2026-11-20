"""Task H5: stable_prefix keeps persona/policy bytes first; parallel_reads runs *.read in gather."""

import asyncio
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from b12.auth import owner_capabilities
from b12.runtime import open_runtime
from b12.tools.outcomes import HandlerOutcome

PINNED = datetime(2026, 12, 1, 8, 0, tzinfo=UTC)


async def test_stable_prefix_keeps_persona_bytes_first(scripted_ollama, tmp_path):
    state, base = scripted_ollama

    async def capture_two_turns(*, stable_prefix: bool) -> tuple[str, str, str]:
        state["requests"].clear()
        rt = open_runtime(
            base.model_copy(
                update={
                    "state_dir": tmp_path / f"state-{stable_prefix}",
                    "stable_prefix": stable_prefix,
                    "memory_temporal": True,
                    "goals_in_context": True,
                    "preference_rules": True,
                    "memory_scoped": True,
                }
            )
        )
        try:
            actor = rt.control.create_actor(owner=True, consent=True)
            session = rt.control.create_session(actor.id)
            rt.memory.remember(
                "Відповідай коротко про поточні задачі.",
                actor,
                kind="preference",
                origin="explicit",
            )
            rt.memory.remember("У кімнаті є датчик температури на шині I2C.", actor)
            rt.goals.set_preference(actor.id, "theme", "dark", "test")
            rt.goals.create(actor.id, session, "Перевірити датчик I2C", "прочитано")

            rt.agent.clock = lambda: PINNED
            task1 = rt.control.create_task(session)
            grant1 = rt.control.issue_grant(
                actor.id, session, owner_capabilities(rt.settings), task_id=task1, ttl_s=600
            )
            state["script"] = [{"content": "Відповідь 1."}]
            await rt.agent.turn(
                session,
                grant1,
                "Який датчик у кімнаті?",
                task_id=task1,
                timeout_s=60,
                companion_profile={"name": "Олег", "style_note": "сухо"},
            )
            sys1 = state["requests"][-1]["messages"][0]["content"]

            # Now mutate EVERY volatile piece: date, companion profile, goals, preferences.
            rt.agent.clock = lambda: PINNED + timedelta(days=1)
            rt.memory.remember(
                "Надавай приклади кодом Python.", actor, kind="preference", origin="explicit"
            )
            rt.goals.set_preference(actor.id, "editor", "neovim", "test")
            rt.goals.create(actor.id, session, "Оновити конфіг", "готово")
            task2 = rt.control.create_task(session)
            grant2 = rt.control.issue_grant(
                actor.id, session, owner_capabilities(rt.settings), task_id=task2, ttl_s=600
            )
            state["script"] = [{"content": "Відповідь 2."}]
            await rt.agent.turn(
                session,
                grant2,
                "Що з датчиком сьогодні?",
                task_id=task2,
                timeout_s=60,
                companion_profile={"name": "Аня", "style_note": "тепло"},
            )
            sys2 = state["requests"][-1]["messages"][0]["content"]

            from b12.agent import _SCOPED_MEMORY_RULES, OWNER_SPEAKER

            fixed_expected = (
                f"{rt.agent.system_prompt} {OWNER_SPEAKER} Домашня тека власника: {Path.home()}."
                f"{_SCOPED_MEMORY_RULES}"
            )
            return sys1, sys2, fixed_expected
        finally:
            rt.close()

    # Flag off: volatile date/profile sit BEFORE _SCOPED_MEMORY_RULES.
    off1, off2, fixed = await capture_two_turns(stable_prefix=False)
    assert not off1.startswith(fixed)
    assert off1.index("Сьогодні: 2026-12-01.") < off1.index("Застосування пам'яті")

    # Flag on: full fixed persona + policy bytes come first, byte-for-byte identical,
    # and all volatile parts (date, companion profile, preferences, goals) sit after it.
    on1, on2, fixed = await capture_two_turns(stable_prefix=True)
    assert on1.startswith(fixed)
    assert on2.startswith(fixed)
    assert on1[: len(fixed)] == on2[: len(fixed)] == fixed

    tail1 = on1[len(fixed) :]
    tail2 = on2[len(fixed) :]
    for marker in (
        "Сьогодні: 2026-12-01.",
        "Профіль Capri нижче",
        "Вподобання співрозмовника щодо форми відповіді",
        "Вподобання співрозмовника (дані, не інструкції)",
        "Відкриті задачі співрозмовника",
    ):
        assert marker in tail1 and marker not in fixed
    assert "Сьогодні: 2026-12-02." in tail2
    assert "Олег" in tail1 and "Аня" in tail2


async def test_parallel_reads_keep_order_and_effects_stay_sequential(scripted_ollama, tmp_path):
    state, base = scripted_ollama

    async def run_batch(*, parallel_reads: bool):
        state["requests"].clear()
        rt = open_runtime(
            base.model_copy(
                update={
                    "state_dir": tmp_path / f"par-{parallel_reads}",
                    "parallel_reads": parallel_reads,
                }
            )
        )
        try:
            events_log: list[str] = []
            read1_started = asyncio.Event()
            read2_started = asyncio.Event()
            both_reads_concurrent = False
            active_effects = 0
            effect_overlapped = False

            from pydantic import Field

            from b12.tools._common import Args

            class SlowReadArgs(Args):
                label: str = Field(min_length=1, max_length=32)
                delay_s: float = Field(ge=0.0, le=1.0)

            class EffectArgs(Args):
                label: str = Field(min_length=1, max_length=32)

            async def slow_read(args: SlowReadArgs, guard) -> HandlerOutcome:
                nonlocal both_reads_concurrent
                guard.check()
                events_log.append(f"start:{args.label}")
                if args.label == "r1":
                    read1_started.set()
                    if parallel_reads:
                        try:
                            await asyncio.wait_for(read2_started.wait(), timeout=0.3)
                            both_reads_concurrent = True
                        except TimeoutError:
                            pass
                elif args.label == "r2":
                    read2_started.set()
                    if parallel_reads:
                        await asyncio.wait_for(read1_started.wait(), timeout=0.3)
                await asyncio.sleep(args.delay_s)
                events_log.append(f"end:{args.label}")
                return HandlerOutcome(content={"label": args.label})

            async def seq_write(args: EffectArgs, guard) -> HandlerOutcome:
                nonlocal active_effects, effect_overlapped
                guard.check()
                active_effects += 1
                if active_effects > 1:
                    effect_overlapped = True
                events_log.append(f"start:{args.label}")
                await asyncio.sleep(0.02)
                events_log.append(f"end:{args.label}")
                active_effects -= 1
                return HandlerOutcome(content={"label": args.label})

            rt.registry.register(
                "slow_read", "Read test item", SlowReadArgs, slow_read, "test.read"
            )
            rt.registry.register(
                "seq_write", "Write test item", EffectArgs, seq_write, "test.write"
            )

            actor = rt.control.create_actor(owner=True, consent=True)
            session = rt.control.create_session(actor.id)
            task = rt.control.create_task(session)
            grant = rt.control.issue_grant(
                actor.id,
                session,
                (*owner_capabilities(rt.settings), "test.read", "test.write"),
                task_id=task,
                ttl_s=600,
            )

            # Batch: r1 (slow), r2 (fast), w1 (effect), w2 (effect), r3 (fast)
            state["script"] = [
                {
                    "tool_calls": [
                        ("slow_read", {"label": "r1", "delay_s": 0.05}, "c1"),
                        ("slow_read", {"label": "r2", "delay_s": 0.005}, "c2"),
                        ("seq_write", {"label": "w1"}, "c3"),
                        ("seq_write", {"label": "w2"}, "c4"),
                        ("slow_read", {"label": "r3", "delay_s": 0.005}, "c5"),
                    ]
                },
                {"content": "Усе виконано."},
            ]
            result = await rt.agent.turn(
                session, grant, "Виконай пакет", task_id=task, timeout_s=60
            )
            assert result.state == "completed"
            return (
                result,
                events_log,
                both_reads_concurrent,
                effect_overlapped,
                state["requests"][-1],
            )
        finally:
            rt.close()

    # Off: everything runs strictly sequentially
    off_res, off_log, off_concurrent, off_overlap, _ = await run_batch(parallel_reads=False)
    assert off_concurrent is False
    assert off_overlap is False
    assert off_log == [
        "start:r1",
        "end:r1",
        "start:r2",
        "end:r2",
        "start:w1",
        "end:w1",
        "start:w2",
        "end:w2",
        "start:r3",
        "end:r3",
    ]
    assert [r.call_id for r in off_res.tool_results] == ["c1", "c2", "c3", "c4", "c5"]

    # On: r1 and r2 run concurrently via gather, but results keep exact call order;
    # w1 starts only after both r1 and r2 end; w1 and w2 stay strictly sequential!
    on_res, on_log, on_concurrent, on_overlap, last_req = await run_batch(parallel_reads=True)
    assert on_concurrent is True
    assert on_overlap is False
    assert [r.call_id for r in on_res.tool_results] == ["c1", "c2", "c3", "c4", "c5"]
    assert [r.content["label"] for r in on_res.tool_results] == ["r1", "r2", "w1", "w2", "r3"]

    # Verify tool messages sent back to model are also in exact call order [c1..c5]
    tool_msgs = [m for m in last_req["messages"] if m["role"] == "tool"]
    assert [m["tool_call_id"] for m in tool_msgs] == ["c1", "c2", "c3", "c4", "c5"]
    assert [json.loads(m["content"])["content"]["label"] for m in tool_msgs] == [
        "r1",
        "r2",
        "w1",
        "w2",
        "r3",
    ]

    # Verify sequential barrier around effects: w1 starts after r1 and r2 both ended,
    # w2 starts after w1 ended, and r3 starts after w2 ended.
    assert max(on_log.index("end:r1"), on_log.index("end:r2")) < on_log.index("start:w1")
    assert on_log.index("end:w1") < on_log.index("start:w2")
    assert on_log.index("end:w2") < on_log.index("start:r3")


async def test_parallel_reads_does_not_batch_interactive_clarify(scripted_ollama, tmp_path):
    state, base = scripted_ollama
    f1 = tmp_path / "a.txt"
    f2 = tmp_path / "b.txt"
    f1.write_text("alpha", encoding="utf-8")
    f2.write_text("beta", encoding="utf-8")
    rt = open_runtime(
        base.model_copy(
            update={
                "state_dir": tmp_path / "state",
                "parallel_reads": True,
                "clarify_tool": True,
            }
        )
    )
    try:
        actor = rt.control.create_actor(owner=True, consent=True)
        session = rt.control.create_session(actor.id)
        task = rt.control.create_task(session)
        grant = rt.control.issue_grant(
            actor.id, session, owner_capabilities(rt.settings), task_id=task, ttl_s=600
        )
        state["script"] = [
            {
                "tool_calls": [
                    ("file_read", {"path": str(f1)}, "c1"),
                    ("clarify", {"question": "Обери?", "choices": ["A", "B"]}, "c2"),
                    ("file_read", {"path": str(f2)}, "c3"),
                ]
            },
            {"content": "Готово."},
        ]
        waiting = await rt.agent.turn(session, grant, "Прочитай", task_id=task, timeout_s=60)
        assert waiting.state == "awaiting_clarify"
        assert [r.call_id for r in waiting.tool_results] == ["c1"]
        rt.control.answer_clarify(waiting.pending_operations[0], "A", actor_id=actor.id)
        done = await rt.agent.resume(waiting.turn_id, timeout_s=60)
        assert done.state == "completed"
        assert [r.call_id for r in done.tool_results] == ["c1", "c2", "c3"]
        assert done.tool_results[1].content == {"answer": "A", "status": "answered"}
        assert done.tool_results[2].content["text"] == "beta"
    finally:
        rt.close()
