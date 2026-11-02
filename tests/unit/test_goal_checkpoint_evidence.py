from datetime import UTC, datetime, timedelta

from b12.goals import GoalStore


def test_goal_checkpoint_keeps_the_evidence_it_used(tmp_path):
    """Regression: a goal's checkpoint text survived forgetting the memory it was built from."""
    store = GoalStore(tmp_path / "goals")
    goal = store.create("actor-1", "session-1", "перевірити логи", "звіт")
    store.checkpoint(
        goal["id"],
        "actor-1",
        "Знайдено помилку у логах",
        datetime.now(UTC) + timedelta(hours=1),
        evidence_ids=("memory-42",),
    )
    store.purge_evidence("actor-1", ["memory-42"])
    assert store.get(goal["id"], "actor-1") is None


def test_a_goal_built_on_stale_evidence_is_paused_not_deleted(tmp_path):
    """A stale memory is still the owner's; its goals pause for review instead of vanishing."""
    store = GoalStore(tmp_path / "goals")
    goal = store.create("actor-1", "session-1", "перевірити факт", "звіт")
    store.checkpoint(
        goal["id"],
        "actor-1",
        "Факт перевірено",
        datetime.now(UTC) + timedelta(hours=1),
        evidence_ids=("memory-7",),
    )
    paused = store.pause_for_stale_evidence("actor-1", ["memory-7"])
    assert paused == [goal["id"]]
    current = store.get(goal["id"], "actor-1")
    assert current is not None
    assert current["status"] == "paused"
    assert current["status_reason"] == "evidence_stale"
