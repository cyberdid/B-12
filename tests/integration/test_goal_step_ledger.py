"""ADR-017 crash-injection suite: a goal's side effect survives a crash without being repeated.

A scripted model asks for the same effect again after every restart (the worst case: the
checkpoint did not record that the effect happened). The synthetic world is a file whose
lines count the effects. Exit: no duplicated effect, no false completion, no blind retry of
an unknown outcome.
"""

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from pydantic import BaseModel, ConfigDict, Field

from b12.tools.outcomes import HandlerOutcome

CAPS = ("filesystem.read", "filesystem.write", "time.read")


class Crash(BaseException):
    """A process stop at a chosen point: not an Exception, so nothing in the runtime catches it."""


class AppendArgs(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    path: str = Field(max_length=512)
    text: str = Field(max_length=200)


def _install(runtime, world: Path):
    async def append_line(args, guard):
        guard.check()
        with open(args.path, "a", encoding="utf-8") as handle:
            handle.write(args.text + "\n")
        return HandlerOutcome(content={"appended": True})

    def verify_append(raw, context):
        path = Path(raw["path"])
        return path.is_file() and raw["text"] + "\n" in path.read_text(encoding="utf-8")

    registry = runtime.agent.registry
    registry.register(
        "append_line",
        "Append one line to a file.",
        AppendArgs,
        append_line,
        "filesystem.write",
        verify=verify_append,
    )
    registry.register(
        "append_blind",
        "Append one line (no trusted check).",
        AppendArgs,
        append_line,
        "filesystem.write",
    )


_CLOCK_REF: list = []


class Clock:
    """A pinned clock: the test must not depend on the wall-clock time of day."""

    def __init__(self):
        self.now = datetime(2026, 11, 21, 10, 0, tzinfo=UTC)
        _CLOCK_REF[:] = [self]

    def __call__(self):
        return self.now


@pytest.fixture(autouse=True)
def _pin_goal_clock(monkeypatch):
    """GoalStore stamps goals and proposals with real time; pin them to the test clock."""
    from b12 import goals as goals_module

    _CLOCK_REF.clear()

    def now():
        if _CLOCK_REF:
            return _CLOCK_REF[0].now.isoformat()
        return datetime(2026, 11, 21, 10, 0, tzinfo=UTC).isoformat()

    monkeypatch.setattr(goals_module, "_now", now)


@pytest.fixture
def rig(scripted_ollama, tmp_path, request):
    from b12.autonomy import Scheduler
    from b12.runtime import open_runtime

    state, base = scripted_ollama
    ledger = getattr(request, "param", True)
    settings = base.model_copy(update={"state_dir": tmp_path / "state", "task_ledger": ledger})
    clock = Clock()
    world = tmp_path / "world.txt"
    opened = []

    def open_all():
        runtime = open_runtime(settings)
        runtime.attention.clock = clock
        _install(runtime, world)
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
    goal = runtime.goals.create(
        actor.id,
        session,
        "Дописати рядок у журнал",
        "рядок є",
        allowed_tools=CAPS,
        review_interval_s=60,
        budget_turns=10,
    )
    yield state, world, goal, actor, clock, open_all, close_all
    close_all()


def _script(state, tool, world, text="запис-1"):
    state["script"] = [
        {"tool_calls": [(tool, {"path": str(world), "text": text})]},
        {"content": "Дописав рядок."},
    ]


def _lines(world):
    return world.read_text(encoding="utf-8").splitlines() if world.exists() else []


async def _crash_once(monkeypatch, target, name, scheduler):
    real = getattr(target, name)
    fired = {"done": False}

    def crashing(*args, **kwargs):
        if not fired["done"]:
            fired["done"] = True
            raise Crash(name)
        return real(*args, **kwargs)

    monkeypatch.setattr(target, name, crashing)
    with pytest.raises(Crash):
        await scheduler.tick()
    monkeypatch.setattr(target, name, real)


async def _restart_and_tick(state, tool, world, clock, open_all, close_all):
    close_all()
    runtime, scheduler = open_all()
    clock.now += timedelta(seconds=61)
    _script(state, tool, world)
    outcomes = await scheduler.tick()
    return runtime, outcomes


async def test_crash_after_effect_before_finish_verified_tool_is_not_repeated(rig, monkeypatch):
    from b12.control import ControlStore

    state, world, goal, actor, clock, open_all, close_all = rig
    close_all()
    runtime, scheduler = open_all()
    _script(state, "append_line", world)
    await _crash_once(monkeypatch, ControlStore, "finish", scheduler)
    assert _lines(world) == ["запис-1"]
    runtime, [outcome] = await _restart_and_tick(
        state, "append_line", world, clock, open_all, close_all
    )
    assert _lines(world) == ["запис-1"]  # reconciled by the trusted check, not repeated
    tool_message = next(m for m in state["requests"][-1]["messages"] if m["role"] == "tool")
    assert "already_done" in tool_message["content"]


async def test_crash_after_effect_unverifiable_tool_pauses_for_the_owner(rig, monkeypatch):
    from b12.control import ControlStore

    state, world, goal, actor, clock, open_all, close_all = rig
    close_all()
    runtime, scheduler = open_all()
    _script(state, "append_blind", world)
    await _crash_once(monkeypatch, ControlStore, "finish", scheduler)
    runtime, [outcome] = await _restart_and_tick(
        state, "append_blind", world, clock, open_all, close_all
    )
    assert _lines(world) == ["запис-1"]  # unknown is never blind-retried
    stored = runtime.goals.get(goal["id"], actor.id)
    assert (stored["status"], stored["status_reason"]) == ("paused", "unknown_outcome_needs_owner")
    assert stored["status"] != "achieved"


async def test_crash_before_the_effect_lets_a_verified_tool_run_once(rig, monkeypatch):

    state, world, goal, actor, clock, open_all, close_all = rig
    close_all()
    runtime, scheduler = open_all()
    _script(state, "append_line", world)
    tool = runtime.agent.registry._tools["append_line"]

    async def crash_before(args, guard):
        raise Crash("before effect")

    runtime.agent.registry._tools["append_line"] = tool.__class__(
        **{**tool.__dict__, "handler": crash_before}
    )
    with pytest.raises(Crash):
        await scheduler.tick()
    assert _lines(world) == []
    runtime, _ = await _restart_and_tick(state, "append_line", world, clock, open_all, close_all)
    assert _lines(world) == ["запис-1"]  # verified absent -> exactly one effect


async def test_crash_after_finish_before_checkpoint_is_not_repeated(rig, monkeypatch):
    from b12.goals import GoalStore

    state, world, goal, actor, clock, open_all, close_all = rig
    close_all()
    runtime, scheduler = open_all()
    _script(state, "append_blind", world)
    await _crash_once(monkeypatch, GoalStore, "checkpoint", scheduler)
    runtime, [outcome] = await _restart_and_tick(
        state, "append_blind", world, clock, open_all, close_all
    )
    assert _lines(world) == ["запис-1"]  # completed earlier: the ledger answers, no handler run
    assert runtime.goals.get(goal["id"], actor.id)["status"] == "active"


async def test_owner_cancel_during_effect_is_unknown_and_not_retried(rig, monkeypatch):
    from b12.control import ControlStore

    state, world, goal, actor, clock, open_all, close_all = rig
    close_all()
    runtime, scheduler = open_all()
    _script(state, "append_blind", world)
    real_finish = ControlStore.finish

    def cancel_then_finish(self, operation_id, state_, code=None):
        turn = self.db.execute(
            "SELECT turn_id FROM operations WHERE id=?", (operation_id,)
        ).fetchone()[0]
        self.cancel_turn(turn)
        return real_finish(self, operation_id, state_, code)

    monkeypatch.setattr(ControlStore, "finish", cancel_then_finish)
    await scheduler.tick()
    monkeypatch.setattr(ControlStore, "finish", real_finish)
    runtime, _ = await _restart_and_tick(state, "append_blind", world, clock, open_all, close_all)
    assert _lines(world) == ["запис-1"]
    stored = runtime.goals.get(goal["id"], actor.id)
    assert stored["status_reason"] == "unknown_outcome_needs_owner"


async def test_owner_replan_allows_the_same_effect_again(rig, monkeypatch):
    state, world, goal, actor, clock, open_all, close_all = rig
    close_all()
    runtime, scheduler = open_all()
    _script(state, "append_line", world)
    await scheduler.tick()
    assert _lines(world) == ["запис-1"]
    runtime.goals.set_status(goal["id"], actor.id, "abandoned", "owner")
    runtime.goals.set_status(goal["id"], actor.id, "active", "owner_replan", reopen=True)
    assert runtime.goals.get(goal["id"], actor.id)["plan_revision"] == 2
    runtime, _ = await _restart_and_tick(state, "append_line", world, clock, open_all, close_all)
    assert _lines(world) == ["запис-1", "запис-1"]  # deliberate repeat after an owner replan


@pytest.mark.parametrize("rig", [False], indirect=True)
async def test_without_the_ledger_a_crash_duplicates_the_effect(rig, monkeypatch):
    """Documents the gap ADR-017 closes (flag off = previous behaviour)."""
    from b12.control import ControlStore

    state, world, goal, actor, clock, open_all, close_all = rig
    close_all()
    runtime, scheduler = open_all()
    _script(state, "append_blind", world)
    await _crash_once(monkeypatch, ControlStore, "finish", scheduler)
    await _restart_and_tick(state, "append_blind", world, clock, open_all, close_all)
    assert _lines(world) == ["запис-1", "запис-1"]
