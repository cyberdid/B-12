"""Multi-store synthetic runtime snapshots keep the same actor and state."""

import importlib.util
from pathlib import Path

import pytest

from b12.runtime import open_runtime

PATH = Path(__file__).resolve().parents[2] / "evals/unified/runtime_snapshot.py"


@pytest.fixture
def snapshot_module():
    assert PATH.exists(), "runtime snapshot implementation missing"
    spec = importlib.util.spec_from_file_location("runtime_snapshot", PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_clones_keep_actor_memory_and_goal(snapshot_module, tmp_path, profile_settings):
    snap = snapshot_module.SyntheticRuntimeSnapshot.create(tmp_path / "source", profile_settings)
    clone_a = tmp_path / "a"
    clone_b = tmp_path / "b"
    assert snap.clone(clone_a) == snap.hashes
    assert snap.clone(clone_b) == snap.hashes
    runtime = open_runtime(
        profile_settings.model_copy(update={"state_dir": clone_a, "host_access": "none"})
    )
    try:
        actor = runtime.control.resolve_actor(snap.actor_id)
        assert len(runtime.memory.search("synthetic", actor)) == 1
        assert len(runtime.goals.for_actor(actor.id)) == 1
        assert runtime.goals.current_preferences(actor.id)["language"] == "uk"
    finally:
        runtime.close()


def test_changed_snapshot_and_existing_destination_are_rejected(
    snapshot_module, tmp_path, profile_settings
):
    snap = snapshot_module.SyntheticRuntimeSnapshot.create(tmp_path / "source", profile_settings)
    existing = tmp_path / "exists"
    existing.mkdir()
    with pytest.raises(FileExistsError):
        snap.clone(existing)
    selected = snap.path / next(iter(snap.hashes))
    selected.write_bytes(b"tampered")
    with pytest.raises(ValueError):
        snap.clone(tmp_path / "clone")
    assert not (tmp_path / "clone").exists()


def test_added_file_and_symlink_in_snapshot_are_rejected(
    snapshot_module, tmp_path, profile_settings
):
    snap = snapshot_module.SyntheticRuntimeSnapshot.create(tmp_path / "source", profile_settings)
    extra = snap.path / "extra"
    extra.write_text("changed")
    with pytest.raises(ValueError):
        snap.clone(tmp_path / "clone1")
    extra.unlink()
    extra.symlink_to("/etc/passwd")
    with pytest.raises(ValueError):
        snap.clone(tmp_path / "clone2")
    assert not (tmp_path / "clone1").exists()
    assert not (tmp_path / "clone2").exists()


def test_mutation_of_one_clone_does_not_affect_other(snapshot_module, tmp_path, profile_settings):
    snap = snapshot_module.SyntheticRuntimeSnapshot.create(tmp_path / "source", profile_settings)
    first, second = tmp_path / "a", tmp_path / "b"
    snap.clone(first)
    snap.clone(second)
    settings_a = profile_settings.model_copy(update={"state_dir": first, "host_access": "none"})
    runtime_a = open_runtime(settings_a)
    try:
        actor = runtime_a.control.resolve_actor(snap.actor_id)
        goal = runtime_a.goals.for_actor(actor.id)[0]
        runtime_a.goals.set_status(goal["id"], actor.id, "paused", "synthetic change")
        runtime_a.goals.set_preference(actor.id, "synthetic_preference", "changed", "test")
    finally:
        runtime_a.close()
    runtime_b = open_runtime(
        profile_settings.model_copy(update={"state_dir": second, "host_access": "none"})
    )
    try:
        assert runtime_b.goals.for_actor(snap.actor_id)[0]["status"] == "active"
        assert "synthetic_preference" not in runtime_b.goals.current_preferences(snap.actor_id)
    finally:
        runtime_b.close()
