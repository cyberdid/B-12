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
