"""Integration tests for ADR-022 owner schedules through Scheduler and InitiativeGate."""

import json
import sqlite3
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

CAPS = ("filesystem.read", "filesystem.write", "time.read", "memory.read")


class Clock:
    def __init__(self, start: datetime | None = None):
        if start is not None:
            self.now = start
        else:
            real = datetime.now(UTC)
            cand = real.replace(hour=10, minute=0, second=0, microsecond=0)
            while cand < real + timedelta(hours=2):
                cand += timedelta(days=1)
            self.now = cand

    def __call__(self):
        return self.now


@pytest.fixture
def rig(scripted_ollama, tmp_path, request):
    from b12.autonomy import Scheduler
    from b12.runtime import open_runtime

    state, base = scripted_ollama
    enabled = getattr(request, "param", True)
    settings = base.model_copy(
        update={
            "state_dir": tmp_path / "state",
            "schedules": enabled,
            "initiative_gate": True,
            "task_ledger": True,
        }
    )
    clock = Clock()
    opened = []

    def open_all():
        runtime = open_runtime(settings)
        runtime.attention.clock = clock
        runtime.schedules.clock = clock
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
    session = runtime.control.create_session(actor.id)
    yield state, runtime, scheduler, actor, session, clock, open_all, close_all, tmp_path
    close_all()


async def test_occurrence_runs_once_across_restart(rig, monkeypatch):
    from b12.schedules import ScheduleStore

    state, runtime, scheduler, actor, session, clock, open_all, close_all, _ = rig
    due_at = clock.now + timedelta(minutes=5)
    sched = runtime.schedules.add(
        actor.id,
        session,
        {"kind": "once", "at": due_at.isoformat()},
        "Ранкове нагадування",
        tz="Europe/Kyiv",
        allowed_tools=CAPS,
        now=clock.now,
    )
    occ = sched["next_run"]
    assert runtime.schedules.claim(sched["id"], occ) is True

    # Simulate crash/restart before finish(): same occurrence must never be claimed or run again.
    close_all()
    runtime, scheduler = open_all()
    assert runtime.schedules.claim(sched["id"], occ) is False
    runs = runtime.schedules.runs(sched["id"])
    assert len(runs) == 1 and runs[0]["outcome"] == "unknown"

    clock.now = due_at + timedelta(minutes=1)
    assert await scheduler.tick() == []
    assert state["requests"] == []

    # Also test full Scheduler crash mid-turn (after claim, before finish): restart does not rerun.
    daily_due = clock.now + timedelta(minutes=10)
    local_due = daily_due.astimezone(ZoneInfo("Europe/Kyiv"))
    daily = runtime.schedules.add(
        actor.id,
        session,
        {"kind": "daily", "time": local_due.strftime("%H:%M"), "weekdays": [local_due.weekday()]},
        "Щоденний звіт",
        tz="Europe/Kyiv",
        allowed_tools=CAPS,
        now=clock.now,
    )
    clock.now = daily_due + timedelta(seconds=10)

    class Crash(BaseException):
        pass

    real_finish = ScheduleStore.finish

    def crash_on_finish(self, *args, **kwargs):
        raise Crash("simulated crash before finish")

    monkeypatch.setattr(ScheduleStore, "finish", crash_on_finish)
    state["script"] = [{"content": "Звіт 1"}]
    with pytest.raises(Crash):
        await scheduler.tick()
    monkeypatch.setattr(ScheduleStore, "finish", real_finish)
    assert len(state["requests"]) == 1

    close_all()
    runtime, scheduler = open_all()
    assert await scheduler.tick() == []
    assert len(state["requests"]) == 1  # never re-run on restart
    daily_runs = runtime.schedules.runs(daily["id"])
    assert len(daily_runs) == 1 and daily_runs[0]["outcome"] == "unknown"


async def test_quiet_hours_defer_not_speak(rig):
    state, runtime, scheduler, actor, session, clock, *_ = rig
    kyiv = ZoneInfo("Europe/Kyiv")
    # Set clock to 01:00 Europe/Kyiv (inside default quiet hours 23:00-08:00).
    local = clock.now.astimezone(kyiv).replace(hour=0, minute=55, second=0, microsecond=0)
    if local <= clock.now.astimezone(kyiv):
        local += timedelta(days=1)
    clock.now = local.astimezone(UTC)
    fire_at = local + timedelta(minutes=5)  # 01:00 Kyiv

    sched = runtime.schedules.add(
        actor.id,
        session,
        {"kind": "once", "at": fire_at.isoformat()},
        "Нічна перевірка бекапів",
        tz="Europe/Kyiv",
        allowed_tools=CAPS,
        now=clock.now,
    )
    clock.now = fire_at.astimezone(UTC) + timedelta(seconds=5)
    state["script"] = [{"content": "Бекапи в порядку."}]
    [outcome] = await scheduler.tick()
    assert outcome["schedule_id"] == sched["id"]
    assert outcome["initiative_decision"] == "defer"
    assert outcome["initiative_reason"] == "quiet_hours"
    assert outcome["delivered"] is False

    # Proposals hold the deferred item with goal_id = f"schedule:{id}".
    [proposal] = runtime.goals.proposals(actor.id)
    assert proposal["goal_id"] == f"schedule:{sched['id']}"
    assert proposal["decision"] == "defer" and proposal["delivered"] == 0

    # Once quiet hours end (09:00 Kyiv), tick() delivers the deferred proposal.
    clock.now = (local.replace(hour=9, minute=0)).astimezone(UTC)
    settled = [o for o in await scheduler.tick() if "decision" in o]
    assert settled == [{"proposal_id": outcome["proposal_id"], "decision": "deliver"}]
    [stored] = runtime.goals.proposals(actor.id)
    assert stored["delivered"] == 1 and stored["decision"] == "deliver"


async def test_silent_reply_is_dropped(rig):
    state, runtime, scheduler, actor, session, clock, *_ = rig
    due_at = clock.now + timedelta(minutes=5)
    sched = runtime.schedules.add(
        actor.id,
        session,
        {"kind": "once", "at": due_at.isoformat()},
        "Перевір логи і мовчи, якщо чисто",
        tz="Europe/Kyiv",
        allowed_tools=CAPS,
        now=clock.now,
    )
    clock.now = due_at + timedelta(seconds=5)
    state["script"] = [{"content": "[SILENT]"}]
    [outcome] = await scheduler.tick()
    assert outcome["schedule_id"] == sched["id"]
    assert outcome["initiative_decision"] == "drop"
    assert outcome["initiative_reason"] == "silent"
    assert outcome["delivered"] is False
    [proposal] = runtime.goals.proposals(actor.id)
    assert proposal["delivered"] == 0 and proposal["decision"] == "drop"


async def test_transport_failure_reruns_after_5_minutes(rig, monkeypatch):
    from b12.model_errors import ModelError

    state, runtime, scheduler, actor, session, clock, *_ = rig
    due_at = clock.now + timedelta(minutes=5)
    sched = runtime.schedules.add(
        actor.id,
        session,
        {"kind": "once", "at": due_at.isoformat()},
        "Надіслати зведення",
        tz="Europe/Kyiv",
        allowed_tools=CAPS,
        now=clock.now,
    )
    clock.now = due_at + timedelta(seconds=5)

    original_chat = runtime.agent.model.chat
    attempts = {"count": 0}

    async def flaky_chat(request, **kwargs):
        attempts["count"] += 1
        if attempts["count"] == 1:
            raise ModelError("transport_error", "ollama down")
        return await original_chat(request, **kwargs)

    monkeypatch.setattr(runtime.agent.model, "chat", flaky_chat)
    [first] = await scheduler.tick()
    assert first["schedule_id"] == sched["id"]
    assert first["state"] == "failed"
    assert first["error_code"] == "transport_error"
    assert first["retry_scheduled"] is True
    assert state["requests"] == []

    # Before 5 minutes pass: does not re-run.
    clock.now += timedelta(minutes=4)
    assert await scheduler.tick() == []
    assert attempts["count"] == 1

    # At +5 minutes: re-runs and succeeds.
    clock.now += timedelta(minutes=1)
    state["script"] = [{"content": "Зведення після відновлення Ollama."}]
    [second] = await scheduler.tick()
    assert attempts["count"] == 2
    assert second["schedule_id"] == sched["id"]
    assert second["state"] == "completed"
    assert second["delivered"] is True


async def test_transport_backoff_15_and_30_minutes_and_no_retry_after_model_call(rig, monkeypatch):
    from b12.model_errors import ModelError

    state, runtime, scheduler, actor, session, clock, *_ = rig
    due_at = clock.now + timedelta(minutes=5)
    sched = runtime.schedules.add(
        actor.id,
        session,
        {"kind": "once", "at": due_at.isoformat()},
        "Звіт",
        tz="Europe/Kyiv",
        allowed_tools=CAPS,
        now=clock.now,
    )
    clock.now = due_at + timedelta(seconds=5)

    async def always_down(request, **kwargs):
        raise ModelError("transport_timeout", "timeout")

    monkeypatch.setattr(runtime.agent.model, "chat", always_down)
    await scheduler.tick()  # attempt 1 -> +5m
    clock.now += timedelta(minutes=5)
    await scheduler.tick()  # retry 1 -> +15m
    clock.now += timedelta(minutes=14)
    assert await scheduler.tick() == []
    clock.now += timedelta(minutes=1)
    await scheduler.tick()  # retry 2 -> +30m
    clock.now += timedelta(minutes=29)
    assert await scheduler.tick() == []
    # Retry 3 exhausted -> paused.
    clock.now += timedelta(minutes=1)
    [fourth] = await scheduler.tick()
    assert fourth["retry_scheduled"] is False
    assert runtime.schedules.get(sched["id"], actor.id)["status"] == "paused"


async def test_no_retry_after_model_call_and_failure_streak_pauses(rig, monkeypatch):
    from b12.model_errors import ModelError

    state, runtime, scheduler, actor, session, clock, *_ = rig
    due_at = clock.now + timedelta(minutes=5)
    target = runtime.settings.state_dir.parent / "effect.txt"
    sched = runtime.schedules.add(
        actor.id,
        session,
        {"kind": "interval", "minutes": 60},
        "Запиши файл",
        tz="Europe/Kyiv",
        allowed_tools=CAPS,
        now=due_at - timedelta(minutes=60),
    )
    clock.now = due_at + timedelta(seconds=5)

    # Round 1 executes a tool; round 2 fails with transport_error -> model already ran, no retry.
    original_chat = runtime.agent.model.chat
    calls = {"n": 0}

    async def fail_after_tool(request, **kwargs):
        calls["n"] += 1
        if calls["n"] == 2:
            raise ModelError("transport_error", "mid-turn drop")
        return await original_chat(request, **kwargs)

    state["script"] = [{"tool_calls": [("file_write", {"path": str(target), "text": "x"})]}]
    monkeypatch.setattr(runtime.agent.model, "chat", fail_after_tool)
    [first] = await scheduler.tick()
    assert first["state"] == "failed"
    assert "retry_scheduled" not in first
    assert runtime.schedules.get(sched["id"], actor.id)["retry_at"] is None
    assert runtime.schedules.get(sched["id"], actor.id)["failure_streak"] == 1

    # 2 more failures -> failure_streak reaches 3 -> schedule paused.
    async def provider_err(request, **kwargs):
        raise ModelError("provider_error", "bad response")

    monkeypatch.setattr(runtime.agent.model, "chat", provider_err)
    clock.now += timedelta(minutes=60)
    [second] = await scheduler.tick()
    assert second["status"] == "active"
    clock.now += timedelta(minutes=60)
    [third] = await scheduler.tick()
    assert third["status"] == "paused"
    assert runtime.schedules.get(sched["id"], actor.id)["failure_streak"] == 3


async def test_owner_stop_and_missed_catchup_and_no_schedule_tools(rig):
    state, runtime, scheduler, actor, session, clock, *_ = rig
    # Schedule old enough to be missed (> 2h catchup window for daily).
    old_at = clock.now - timedelta(hours=3)
    kyiv_old = old_at.astimezone(ZoneInfo("Europe/Kyiv"))
    missed_sched = runtime.schedules.add(
        actor.id,
        session,
        {"kind": "daily", "time": kyiv_old.strftime("%H:%M"), "weekdays": [kyiv_old.weekday()]},
        "Давно пропущене",
        tz="Europe/Kyiv",
        allowed_tools=CAPS,
        now=old_at - timedelta(minutes=5),
    )
    [missed_out] = await scheduler.tick()
    assert missed_out["schedule_id"] == missed_sched["id"]
    assert missed_out["state"] == "missed"
    assert state["requests"] == []
    assert runtime.schedules.runs(missed_sched["id"])[0]["outcome"] == "missed"

    # Active schedule with owner stop: skipped without running model.
    due_at = clock.now + timedelta(minutes=5)
    active_sched = runtime.schedules.add(
        actor.id,
        session,
        {"kind": "once", "at": due_at.isoformat()},
        "Під owner stop",
        tz="Europe/Kyiv",
        allowed_tools=CAPS,
        now=clock.now,
    )
    clock.now = due_at + timedelta(seconds=10)
    runtime.attention.set_stopped(actor.id, True)
    [stopped] = await scheduler.tick()
    assert stopped["state"] == "skipped" and stopped["reason"] == "owner_stop"
    assert state["requests"] == []

    # Lift owner stop: now runs, and offered tools never contain any schedule management tool.
    runtime.attention.set_stopped(actor.id, False)
    state["script"] = [{"content": "Виконано."}]
    [ran] = await scheduler.tick()
    assert ran["state"] == "completed" and ran["delivered"] is True
    offered_names = {t["function"]["name"] for t in state["requests"][-1].get("tools", [])}
    assert not any("schedule" in name for name in offered_names)
    assert runtime.schedules.get(active_sched["id"], actor.id)["status"] == "completed"


@pytest.mark.parametrize("rig", [False], indirect=True)
async def test_schedules_flag_off_ignores_due_schedules(rig):
    state, runtime, scheduler, actor, session, clock, *_ = rig
    due_at = clock.now + timedelta(minutes=1)
    runtime.schedules.add(
        actor.id,
        session,
        {"kind": "once", "at": due_at.isoformat()},
        "Не повинно запуститись",
        tz="Europe/Kyiv",
        allowed_tools=CAPS,
        now=clock.now,
    )
    clock.now = due_at + timedelta(minutes=1)
    assert await scheduler.tick() == []
    assert state["requests"] == []


async def test_cli_schedule_commands(scripted_ollama, tmp_path, monkeypatch, capsys):
    import asyncio

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
            main, ["schedule", "add", "Ранковий звіт", "--time", "08:00", "--weekdays", "0,1,2,3,4"]
        )
        == 0
    )
    created = json.loads(capsys.readouterr().out)
    assert created["spec"] == {"kind": "daily", "time": "08:00", "weekdays": [0, 1, 2, 3, 4]}

    assert await asyncio.to_thread(main, ["schedule", "list"]) == 0
    listed = json.loads(capsys.readouterr().out)
    assert [s["id"] for s in listed] == [created["id"]]

    assert await asyncio.to_thread(main, ["schedule", "pause", created["id"]]) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "paused"

    assert await asyncio.to_thread(main, ["schedule", "resume", created["id"]]) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "active"

    assert await asyncio.to_thread(main, ["schedule", "remove", created["id"]]) == 0
    assert json.loads(capsys.readouterr().out) == {"removed": created["id"]}
    assert await asyncio.to_thread(main, ["schedule", "list"]) == 0
    assert json.loads(capsys.readouterr().out) == []

    # Verify goals.sqlite3 holds the schedules table cleanly.
    db = sqlite3.connect(tmp_path / "state" / "goals" / "goals.sqlite3")
    tables = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    db.close()
    assert {"schedules", "schedule_runs"} <= tables
