"""ADR-018 end to end: background proposals pass the five-way gate (scripted model)."""

from datetime import UTC, datetime, timedelta

import pytest

CAPS = ("filesystem.read", "filesystem.write", "time.read", "process.execute")


class Clock:
    def __init__(self):
        real = datetime.now(UTC)
        start = real.replace(hour=10, minute=0, second=0, microsecond=0)
        while start < real + timedelta(hours=1):
            start += timedelta(days=1)
        self.now = start

    def __call__(self):
        return self.now


@pytest.fixture
def rig(scripted_ollama, tmp_path, request):
    from b12.autonomy import Scheduler
    from b12.runtime import open_runtime

    state, base = scripted_ollama
    gate = getattr(request, "param", True)
    settings = base.model_copy(update={"state_dir": tmp_path / "state", "initiative_gate": gate})
    runtime = open_runtime(settings)
    clock = Clock()
    runtime.attention.clock = clock
    scheduler = Scheduler(runtime, clock=clock)
    actor = runtime.control.create_actor(owner=True, consent=True)
    session = runtime.control.create_session(actor.id)
    goal = runtime.goals.create(
        actor.id,
        session,
        "Стежити за звітами",
        "звіт є",
        allowed_tools=CAPS,
        review_interval_s=60,
        budget_turns=10,
    )
    yield state, runtime, scheduler, actor, goal, clock, tmp_path
    scheduler.close()
    runtime.close()


def _write(state, path, text="Записав звіт."):
    state["script"] = [
        {"tool_calls": [("file_write", {"path": str(path), "text": "звіт\n"})]},
        {"content": text},
    ]


async def test_a_review_with_nothing_new_is_not_spoken(rig):
    state, runtime, scheduler, actor, goal, clock, tmp = rig
    state["script"] = [{"content": "Нічого нового."}]
    [outcome] = await scheduler.tick()
    assert outcome["initiative_decision"] == "drop" and outcome["initiative_reason"] == "not_novel"
    assert outcome["delivered"] is False


async def test_a_review_with_an_effect_is_delivered_and_its_repeat_is_dropped(rig):
    state, runtime, scheduler, actor, goal, clock, tmp = rig
    _write(state, tmp / "r1.txt")
    [first] = await scheduler.tick()
    assert first["initiative_decision"] == "deliver" and first["delivered"] is True
    clock.now += timedelta(hours=2)
    _write(state, tmp / "r2.txt")
    [second] = await scheduler.tick()
    assert (second["initiative_decision"], second["initiative_reason"]) == ("drop", "duplicate")


async def test_a_review_waiting_for_approval_needs_the_owner(rig):
    state, runtime, scheduler, actor, goal, clock, tmp = rig
    state["script"] = [
        {
            "tool_calls": [
                (
                    "shell_exec",
                    {
                        "executable": "/usr/bin/touch",
                        "argv": [str(tmp / "m")],
                        "cwd": str(tmp),
                        "declared_effects": ["create m"],
                    },
                )
            ]
        },
        {"content": "Чекаю дозволу."},
    ]
    [outcome] = await scheduler.tick()
    assert outcome["initiative_decision"] == "needs_owner" and outcome["delivered"] is False


async def test_quiet_hours_defer_and_the_proposal_is_delivered_when_they_end(rig):
    state, runtime, scheduler, actor, goal, clock, tmp = rig
    clock.now = clock.now.replace(hour=22)  # 00:00 in Kyiv: quiet hours
    _write(state, tmp / "night.txt")
    [outcome] = await scheduler.tick()
    assert outcome["initiative_decision"] == "defer" and outcome["delivered"] is False
    clock.now += timedelta(hours=9)  # 09:00 Kyiv
    state["script"] = []
    settled = [o for o in await scheduler.tick() if "decision" in o]
    assert settled == [{"proposal_id": outcome["proposal_id"], "decision": "deliver"}]
    [stored] = [p for p in runtime.goals.proposals(actor.id) if p["id"] == outcome["proposal_id"]]
    assert stored["delivered"] and stored["decision"] == "deliver"


async def test_quiet_mode_keeps_the_proposal_in_the_inbox(rig):
    state, runtime, scheduler, actor, goal, clock, tmp = rig
    runtime.attention.set_quiet(actor.id, True)
    _write(state, tmp / "q.txt")
    [outcome] = await scheduler.tick()
    assert outcome["initiative_decision"] == "inbox" and outcome["delivered"] is False
    assert runtime.goals.get(goal["id"], actor.id)["consumed_turns"] == 1  # work went on


async def test_a_muted_goal_stays_silent(rig):
    state, runtime, scheduler, actor, goal, clock, tmp = rig
    runtime.goals.set_muted(goal["id"], actor.id, True)
    _write(state, tmp / "m.txt")
    [outcome] = await scheduler.tick()
    assert (outcome["initiative_decision"], outcome["initiative_reason"]) == ("drop", "goal_muted")


@pytest.mark.parametrize("rig", [False], indirect=True)
async def test_without_the_gate_every_review_is_delivered(rig):
    state, runtime, scheduler, actor, goal, clock, tmp = rig
    state["script"] = [{"content": "Нічого нового."}]
    [outcome] = await scheduler.tick()
    assert outcome["delivered"] is True and "initiative_decision" not in outcome
