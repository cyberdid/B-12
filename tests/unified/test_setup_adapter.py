"""Evaluator-side setup fixtures seed a disposable synthetic runtime (no model)."""

import importlib.util
import json
from pathlib import Path

import pytest

from b12.runtime import open_runtime

ROOT = Path(__file__).resolve().parents[2]
PATH = ROOT / "evals/unified/setup_adapter.py"
FIXTURES = ROOT / "evals/unified/draft_fixtures/u2-u3-v4"
MANIFEST = ROOT / "evals/unified/scenario_sets/u2-u3-draft-v4.json"
U5_V3_MANIFEST = ROOT / "evals/unified/scenario_sets/u5-application-v3.json"


@pytest.fixture
def adapter():
    assert PATH.exists(), "setup adapter implementation missing"
    spec = importlib.util.spec_from_file_location("setup_adapter", PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def setup_of(family, variant="p1"):
    path = FIXTURES / family.lower() / f"{family.lower()}-{variant}.setup.json"
    return json.loads(path.read_text(encoding="utf-8"))["harness_setup"]


def declared(setup, alias, key="synthetic_memory", id_key="memory_id"):
    return next(row[id_key] for row in setup[key] if row["alias"] == alias)


def reopen(settings, state):
    return open_runtime(settings.model_copy(update={"state_dir": state, "host_access": "none"}))


def test_materializes_sandbox_files_and_dirs_privately(adapter, tmp_path):
    root = tmp_path / "fs"
    paths = adapter.materialize_files(setup_of("C22"), root)
    assert (root / "sandbox/c22/in/m1.txt").read_text(encoding="utf-8") == "4.98\n"
    assert (root / "sandbox/c22/out").is_dir()
    assert paths["/sandbox/c22/in/m2.txt"] == root / "sandbox/c22/in/m2.txt"
    assert (root / "sandbox/c22/in/m1.txt").stat().st_mode & 0o777 == 0o600
    assert not (root / "sandbox/c23").exists()


@pytest.mark.parametrize(
    "bad", ["/etc/passwd", "/sandbox/../etc/x", "sandbox/rel.txt", "/sandbox//x", "/sandbox/a/./b"]
)
def test_rejects_paths_outside_synthetic_roots(adapter, tmp_path, bad):
    with pytest.raises(ValueError):
        adapter.materialize_files({"synthetic_files": {bad: "x"}}, tmp_path / "fs")
    assert not (tmp_path / "fs" / "etc").exists()


def test_refuses_to_reuse_an_existing_filesystem_root(adapter, tmp_path):
    root = tmp_path / "fs"
    root.mkdir()
    with pytest.raises(FileExistsError):
        adapter.materialize_files(setup_of("C06"), root)


def test_achieved_goal_links_seeded_evidence_and_reports_dropped_clocks(
    adapter, tmp_path, profile_settings
):
    setup = setup_of("M22")
    report = adapter.build_runtime(setup, tmp_path / "state", profile_settings)
    actual_evidence = report["memory_ids"][declared(setup, "m22-e1")]
    actual_goal = report["goal_ids"][declared(setup, "m22-g1", "synthetic_goals", "goal_id")]
    assert "event_time" in report["dropped_fields"]["m22-e1"]
    runtime = reopen(profile_settings, tmp_path / "state")
    try:
        actor = runtime.control.resolve_actor(report["actors"]["synthetic-owner"])
        goal = runtime.goals.get(actual_goal, actor.id)
        assert goal["status"] == "achieved"
        assert goal["evidence_ids"] == [actual_evidence]
        assert runtime.memory.is_live(actual_evidence, actor)
    finally:
        runtime.close()


def test_superseded_record_is_stale_and_replacement_is_live(adapter, tmp_path, profile_settings):
    setup = setup_of("M08")
    report = adapter.build_runtime(setup, tmp_path / "state", profile_settings)
    runtime = reopen(profile_settings, tmp_path / "state")
    try:
        actor = runtime.control.resolve_actor(report["actors"]["synthetic-owner"])
        old = report["memory_ids"][declared(setup, "m08-r1")]
        new = report["memory_ids"][declared(setup, "m08-r2")]
        assert not runtime.memory.is_live(old, actor)
        assert runtime.memory.is_live(new, actor)
        assert report["applied_relations"] == [{"supersedes": "m08-r1", "by": "m08-r2"}]
    finally:
        runtime.close()


def test_other_actor_memory_stays_in_owner_namespace(adapter, tmp_path, profile_settings):
    setup = setup_of("M26")
    report = adapter.build_runtime(setup, tmp_path / "state", profile_settings)
    assert report["speaking_actor"] == "synthetic-guest-b"
    runtime = reopen(profile_settings, tmp_path / "state")
    try:
        owner = runtime.control.resolve_actor(report["actors"]["synthetic-owner"])
        guest = runtime.control.resolve_actor(report["actors"]["synthetic-guest-b"])
        assert owner.owner and not guest.owner
        assert runtime.memory.search("лікаря", owner)
        assert runtime.memory.search("лікаря", guest) == []
    finally:
        runtime.close()


def test_goal_statuses_follow_goalstore(adapter, tmp_path, profile_settings):
    setup = setup_of("M21")
    report = adapter.build_runtime(setup, tmp_path / "state", profile_settings)
    runtime = reopen(profile_settings, tmp_path / "state")
    try:
        actor = report["actors"]["synthetic-owner"]
        statuses = {
            alias: runtime.goals.get(
                report["goal_ids"][declared(setup, alias, "synthetic_goals", "goal_id")], actor
            )["status"]
            for alias in ("m21-g1", "m21-g2")
        }
        assert statuses == {"m21-g1": "abandoned", "m21-g2": "active"}
    finally:
        runtime.close()


def test_every_unblocked_current_setup_seeds_without_error(adapter, tmp_path, profile_settings):
    rows = json.loads(MANIFEST.read_text(encoding="utf-8"))["scenarios"]
    seeded = 0
    for row in rows:
        if row["notes"].startswith("BLOCKED:") or not row["scenario_id"].endswith("P1"):
            continue
        setup = json.loads((ROOT / row["setup_fixture"]).read_text(encoding="utf-8"))
        base = tmp_path / row["scenario_id"]
        report = adapter.build_runtime(
            setup["harness_setup"], base / "state", profile_settings, files_root=base / "fs"
        )
        assert set(report["memory_ids"]) == {
            item["memory_id"] for item in setup["harness_setup"].get("synthetic_memory", [])
        }
        seeded += 1
    assert seeded == 53


def test_recorded_at_becomes_created_at_and_event_time_is_dropped(
    adapter, tmp_path, profile_settings
):
    setup = setup_of("M04")
    report = adapter.build_runtime(setup, tmp_path / "state", profile_settings)
    assert report["dropped_fields"]["m04-r1"] == ["event_time", "reliability"]
    runtime = reopen(profile_settings, tmp_path / "state")
    try:
        actor = runtime.control.resolve_actor(report["actors"]["synthetic-owner"])
        record = runtime.memory.get(report["memory_ids"][declared(setup, "m04-r1")], actor)
        assert record.created_at == "2026-11-28T10:00:00+00:00"
    finally:
        runtime.close()


def u5_setup_of(scenario_id):
    rows = json.loads(U5_V3_MANIFEST.read_text(encoding="utf-8"))["scenarios"]
    row = next(item for item in rows if item["scenario_id"] == scenario_id)
    return json.loads((ROOT / row["setup_fixture"]).read_text(encoding="utf-8"))["harness_setup"]


def test_scoped_temporal_seed_preserves_scope_and_document_provenance(
    adapter, tmp_path, profile_settings
):
    setup = u5_setup_of("M61-P1")
    report = adapter.build_runtime(
        setup, tmp_path / "state", profile_settings, temporal=True, scoped=True
    )
    assert report["dropped_fields"] == {}

    runtime = reopen(
        profile_settings.model_copy(update={"memory_temporal": True, "memory_scoped": True}),
        tmp_path / "state",
    )
    try:
        actor = runtime.control.resolve_actor(report["actors"]["synthetic-owner"])
        record = runtime.memory.get(report["memory_ids"][declared(setup, "u61-p1")], actor)
        assert record.applies_when == "коли власник працює в нічну зміну"
        assert record.origin == "explicit"
    finally:
        runtime.close()

    manual_setup = u5_setup_of("M68-P1")
    manual_report = adapter.build_runtime(
        manual_setup, tmp_path / "manual-state", profile_settings, temporal=True, scoped=True
    )
    runtime = reopen(
        profile_settings.model_copy(update={"memory_temporal": True, "memory_scoped": True}),
        tmp_path / "manual-state",
    )
    try:
        actor = runtime.control.resolve_actor(manual_report["actors"]["synthetic-owner"])
        manual_id = manual_report["memory_ids"][declared(manual_setup, "u68-r1")]
        record = runtime.memory.get(manual_id, actor)
        assert record.reliability == "high"
        assert record.source_locator == "manual p.4"
        assert record.temporal_source == "document"
    finally:
        runtime.close()


def test_revoked_fixture_memory_is_retired_during_seed(adapter, tmp_path, profile_settings):
    setup = u5_setup_of("M64-P1")
    report = adapter.build_runtime(
        setup, tmp_path / "state", profile_settings, temporal=True, scoped=True
    )
    assert report["revoked_memories"] == ["u64-p1"]
    runtime = reopen(profile_settings, tmp_path / "state")
    try:
        actor = runtime.control.resolve_actor(report["actors"]["synthetic-owner"])
        record = runtime.memory.get(report["memory_ids"][declared(setup, "u64-p1")], actor)
        assert record.status == "stale"
        assert record.status_reason == "revoked"
        assert not runtime.memory.is_live(record.id, actor)
    finally:
        runtime.close()


def test_u5_replacement_can_make_completed_goal_evidence_stale(
    adapter, tmp_path, profile_settings
):
    setup = u5_setup_of("M76-P1")
    report = adapter.build_runtime(
        setup, tmp_path / "state", profile_settings, temporal=True, scoped=True
    )
    runtime = reopen(profile_settings, tmp_path / "state")
    try:
        actor = runtime.control.resolve_actor(report["actors"]["synthetic-owner"])
        goal_id = report["goal_ids"][declared(setup, "u76-g1", "synthetic_goals", "goal_id")]
        goal = runtime.goals.get(goal_id, actor.id)
        old_evidence = report["memory_ids"][declared(setup, "u76-e1")]
        new_evidence = report["memory_ids"][declared(setup, "u76-e2")]
        assert goal["status"] == "achieved"
        assert goal["evidence_ids"] == [old_evidence]
        assert not runtime.memory.is_live(old_evidence, actor)
        assert runtime.memory.is_live(new_evidence, actor)
    finally:
        runtime.close()


def test_every_u5_v3_p1_setup_seeds_without_dropped_memory_fields(
    adapter, tmp_path, profile_settings
):
    rows = json.loads(U5_V3_MANIFEST.read_text(encoding="utf-8"))["scenarios"]
    seeded = 0
    for row in rows:
        if not row["scenario_id"].endswith("P1"):
            continue
        setup = json.loads((ROOT / row["setup_fixture"]).read_text(encoding="utf-8"))[
            "harness_setup"
        ]
        report = adapter.build_runtime(
            setup,
            tmp_path / row["scenario_id"],
            profile_settings,
            temporal=True,
            scoped=True,
        )
        assert report["dropped_fields"] == {}, row["scenario_id"]
        expected_relations = {
            (memory["alias"], next(
                item["alias"]
                for item in setup.get("synthetic_memory", [])
                if item["memory_id"] == memory["supersedes"]
            ))
            for memory in setup.get("synthetic_memory", [])
            if memory.get("supersedes")
        }
        actual_relations = {
            (item["by"], item["supersedes"]) for item in report["applied_relations"]
        }
        assert actual_relations == expected_relations, row["scenario_id"]
        seeded += 1
    assert seeded == 24
