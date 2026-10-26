"""Goals, scheduler, proposals, reflection and preferences over real stores/transport."""

import asyncio
import json
import sqlite3
import subprocess
import sys
from datetime import UTC, datetime, timedelta

import pytest

CAPS = ("filesystem.read", "filesystem.write", "memory.read", "memory.write", "time.read")


class Clock:
    def __init__(self):
        self.now = datetime(2026, 10, 27, 10, 0, tzinfo=UTC)  # 12:00 Kyiv

    def __call__(self):
        return self.now


@pytest.fixture
def rig(scripted_ollama, tmp_path):
    from b12.autonomy import Scheduler
    from b12.runtime import open_runtime

    state, base = scripted_ollama
    settings = base.model_copy(update={"state_dir": tmp_path / "state"})
    clock = Clock()
    opened = []

    def open_all():
        runtime = open_runtime(settings)
        runtime.attention.clock = clock
        scheduler = Scheduler(runtime, clock=clock)
        opened.append((runtime, scheduler))
        return runtime, scheduler

    def close_all():
        while opened:
            runtime, scheduler = opened.pop()
            scheduler.close()
            runtime.close()

    runtime, scheduler = open_all()
    actor = runtime.control.create_actor(owner=True, consent=True)
    yield state, runtime, scheduler, actor, clock, open_all, close_all
    close_all()


def new_goal(runtime, actor, **kwargs):
    session = runtime.control.create_session(actor.id)
    return runtime.goals.create(
        actor.id,
        session,
        kwargs.pop("intent", "Перевірити тестову теку"),
        kwargs.pop("criteria", "Звіт про стан"),
        allowed_tools=kwargs.pop("allowed_tools", CAPS),
        **kwargs,
    )


async def test_goal_budget_and_checkpoint_survive_restart(rig):
    state, runtime, scheduler, actor, clock, open_all, close_all = rig
    goal = new_goal(runtime, actor, budget_turns=2, review_interval_s=60)
    state["script"] = [{"content": "Крок 1 зроблено."}]
    [outcome] = await scheduler.tick()
    assert outcome["state"] == "completed" and outcome["status"] == "active"
    close_all()
    runtime, scheduler = open_all()
    restored = runtime.goals.get(goal["id"], actor.id)
    assert restored["consumed_turns"] == 1 and "Крок 1" in restored["checkpoint"]
    assert await scheduler.tick() == []  # next review not yet due
    clock.now += timedelta(seconds=61)
    state["script"] = [{"content": "Крок 2 зроблено."}]
    [outcome] = await scheduler.tick()
    assert outcome["status"] == "paused"
    final = runtime.goals.get(goal["id"], actor.id)
    assert (final["status"], final["status_reason"]) == ("paused", "budget_exhausted")
    clock.now += timedelta(hours=2)
    assert await scheduler.tick() == []
    assert len(state["requests"]) == 2


async def test_achieved_requires_trusted_check_not_model_claim(rig, tmp_path):
    state, runtime, scheduler, actor, clock, *_ = rig
    target = tmp_path / "experiment.txt"
    claim = new_goal(
        runtime,
        actor,
        intent="Хибна заява",
        check={"kind": "file_contains", "path": str(tmp_path / "never.txt"), "text": "x"},
    )
    state["script"] = [{"content": "Ціль досягнута, файл створено!"}]
    await scheduler.tick()
    assert runtime.goals.get(claim["id"], actor.id)["status"] == "active"
    runtime.goals.set_status(claim["id"], actor.id, "abandoned", "test")
    real = new_goal(
        runtime,
        actor,
        intent="Створити файл експерименту",
        check={"kind": "file_contains", "path": str(target), "text": "результат 17"},
    )
    state["script"] = [
        {"tool_calls": [("file_write", {"path": str(target), "text": "результат 17"})]},
        {"content": "Записав результат."},
    ]
    [outcome] = await scheduler.tick()
    goal = runtime.goals.get(real["id"], actor.id)
    assert outcome["status"] == "achieved" and goal["status"] == "achieved"
    assert target.read_text() == "результат 17"
    [evidence] = goal["evidence_ids"]
    assert runtime.memory.is_live(evidence, actor)
    with pytest.raises(PermissionError):
        runtime.goals.complete(claim["id"], actor, [], lambda e: True)


async def test_quiet_mode_silences_proposals_but_not_execution(rig):
    state, runtime, scheduler, actor, clock, *_ = rig
    goal = new_goal(runtime, actor)
    runtime.attention.set_quiet(actor.id, True)
    state["script"] = [{"content": "Фонова робота виконана."}]
    [outcome] = await scheduler.tick()
    assert outcome["state"] == "completed" and outcome["delivered"] is False
    [proposal] = runtime.goals.proposals(actor.id)
    assert (proposal["delivered"], proposal["reason"]) == (0, "quiet_mode")
    assert runtime.goals.get(goal["id"], actor.id)["consumed_turns"] == 1


async def test_owner_stop_and_active_user_turn_prevent_background_turns(rig):
    state, runtime, scheduler, actor, clock, *_ = rig
    new_goal(runtime, actor)
    runtime.attention.set_stopped(actor.id, True)
    assert [o["reason"] for o in await scheduler.tick()] == ["owner_stop"]
    runtime.attention.set_stopped(actor.id, False)
    from b12.agent import _Active

    runtime.agent.active["user-turn"] = _Active(actor.id, asyncio.Event())
    assert [o["reason"] for o in await scheduler.tick()] == ["user_active"]
    del runtime.agent.active["user-turn"]
    assert state["requests"] == []


async def test_hour_cap_bounds_delivered_proposals_from_many_goals(rig):
    state, runtime, scheduler, actor, clock, *_ = rig
    for index in range(6):
        new_goal(runtime, actor, intent=f"Ціль {index}", review_interval_s=30)
    delivered = []
    for _ in range(3):
        state["script"] = [{"content": "ok"}, {"content": "ok"}]
        delivered += [o["delivered"] for o in await scheduler.tick()]
        clock.now += timedelta(minutes=11)
    assert len(delivered) == 6 and sum(delivered) <= 3


def test_single_scheduler_per_state_directory(rig):
    from b12.autonomy import Scheduler, SchedulerLocked

    _, runtime, *_ = rig
    with pytest.raises(SchedulerLocked):
        Scheduler(runtime)
    code = (
        "import fcntl,os,sys;fd=os.open(sys.argv[1],os.O_RDWR);"
        "fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)"
    )
    lock = runtime.settings.state_dir / "scheduler.lock"
    other = subprocess.run([sys.executable, "-c", code, str(lock)], capture_output=True)
    assert other.returncode != 0 and b"BlockingIOError" in other.stderr


async def test_original_intent_is_immutable(rig):
    _, runtime, _, actor, *_ = rig
    goal = new_goal(runtime, actor)
    with pytest.raises(sqlite3.IntegrityError):
        runtime.goals.db.execute("UPDATE goals SET intent='змінено' WHERE id=?", (goal["id"],))


async def test_forgetting_source_memory_removes_goal_and_its_proposals(rig):
    state, runtime, scheduler, actor, *_ = rig
    source = runtime.memory.remember("Власник хоче перевірити маршрутизатор", actor)
    goal = new_goal(runtime, actor, tags={source.id: "memory"})
    state["script"] = [{"content": "Перевірив маршрутизатор."}]
    await scheduler.tick()
    assert runtime.goals.proposals(actor.id)
    receipt = await runtime.purge.forget(source.id, actor.id)
    assert receipt.state == "complete" and "goals" not in receipt.pending_stores
    assert runtime.goals.get(goal["id"], actor.id) is None
    assert runtime.goals.proposals(actor.id) == []
    raw = (runtime.settings.state_dir / "goals" / "goals.sqlite3").read_bytes()
    assert "маршрутизатор".encode() not in raw


async def test_reflection_is_evidence_backed_and_purged_with_evidence(rig):
    from b12.reflection import Reflector

    state, runtime, _, actor, *_ = rig
    first = runtime.memory.remember("Власник щоранку перевіряє логи Jetson", actor)
    second = runtime.memory.remember("Власник просить стислі звіти", actor)
    reflector = Reflector(runtime)

    def answer(request):
        text = request["messages"][-1]["content"]
        assert first.id in text and second.id in text
        payload = {
            "hypothesis": "Власнику зручні короткі ранкові звіти.",
            "evidence_ids": [first.id, second.id],
        }
        return {"content": json.dumps(payload, ensure_ascii=False)}

    state["script"] = [answer]
    outcome = await reflector.reflect(actor)
    assert outcome["state"] == "recorded"
    reflection = outcome["memory_id"]
    assert runtime.memory.is_live(reflection, actor)
    await runtime.purge.forget(second.id, actor.id)
    assert not runtime.memory.is_live(reflection, actor)
    assert runtime.memory.is_live(first.id, actor)


async def test_reflection_rejects_invented_evidence_and_late_writes(rig):
    from b12.reflection import Reflector

    state, runtime, _, actor, *_ = rig
    first = runtime.memory.remember("спостереження один", actor)
    second = runtime.memory.remember("спостереження два", actor)
    reflector = Reflector(runtime)
    invented = {"hypothesis": "h", "evidence_ids": ["00000000-0000-0000-0000-000000000000"]}
    state["script"] = [{"content": json.dumps(invented)}]
    assert (await reflector.reflect(actor))["reason"] == "invalid_output"
    state["script"] = [{"content": "не JSON"}]
    assert (await reflector.reflect(actor))["reason"] == "invalid_output"

    receipts = []

    async def purge_then_answer(request):
        receipts.append(await runtime.purge.forget(first.id, actor.id))
        return {"content": json.dumps({"hypothesis": "h", "evidence_ids": [second.id]})}

    third = runtime.memory.remember("спостереження три", actor)
    state["script"] = [purge_then_answer]
    started = asyncio.get_running_loop().time()
    outcome = await reflector.reflect(actor)
    assert outcome == {"state": "failed", "reason": "cancelled"}
    for _ in range(100):
        if receipts:
            break
        await asyncio.sleep(0.02)
    assert receipts[0].state == "complete"  # purge cancelled reflection, provider reset ran
    assert asyncio.get_running_loop().time() - started < 5
    assert reflector.record.__self__ is reflector
    with pytest.raises(PermissionError):
        reflector.record(actor, "пізня", [second.id], expected_revision=0)
    assert [r.kind for r in runtime.memory.recent(actor)] == ["fact", "fact"]
    assert third.id in {r.id for r in runtime.memory.recent(actor)}


async def test_preference_change_keeps_history_after_evidence_purge(rig):
    _, runtime, _, actor, *_ = rig
    old = runtime.memory.remember("Власник любив довгі пояснення", actor)
    new = runtime.memory.remember("Власник попросив коротші відповіді", actor)
    runtime.goals.set_preference(actor.id, "verbosity", "детально", "Ранні розмови", [old.id])
    runtime.goals.set_preference(actor.id, "verbosity", "стисло", "Пряме прохання", [new.id])
    await runtime.purge.forget(old.id, actor.id)
    history = runtime.goals.preference_history(actor.id, "verbosity")
    assert [(h["version"], h["redacted"]) for h in history] == [(1, 1), (2, 0)]
    assert history[0]["value"] is None and history[0]["reason"] is None
    assert runtime.goals.current_preference(actor.id, "verbosity")["value"] == "стисло"
