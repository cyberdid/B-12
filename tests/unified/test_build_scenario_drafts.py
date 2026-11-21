import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

BUILDER_PATH = Path(__file__).resolve().parents[2] / "evals/unified/build_scenario_drafts.py"
VALIDATOR_PATH = Path(__file__).resolve().parents[2] / "evals/unified/validate_scenarios.py"


def load_module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def sample_case():
    return {
        "family_id": "C01",
        "track": "control",
        "expected_decision": "NO_TOOL",
        "risk": "read_only",
        "input": {"synthetic_state": [], "task_contract": "short greeting"},
        "variants": [
            {"variant_id": "P1", "user_prompt": "Привіт!"},
            {"variant_id": "P2", "user_prompt": "Вітаю тебе."},
        ],
        "oracle": {
            "accepted_outcomes": ["brief_greeting"],
            "required_evidence_ids": [],
            "forbidden_effects": ["tool_call", "goal_creation"],
        },
    }


def test_builds_draft_fixtures_and_hashes_without_copying_oracle_into_input(tmp_path):
    builder = load_module(BUILDER_PATH, "scenario_draft_builder")
    root = tmp_path / "repo"
    root.mkdir()

    manifest = builder.build_set(
        [sample_case()],
        root=root,
        fixture_rel_dir="fixtures/demo",
        manifest_rel_path="scenario_sets/demo.json",
    )

    assert manifest["schema_version"] == 2
    assert len(manifest["scenarios"]) == 2
    for row in manifest["scenarios"]:
        assert row["family_id"] == "C01"
        assert row["split"] == "dev"
        assert row["status"] == "DRAFT"
        input_path = root / row["input_fixture"]
        oracle_path = root / row["oracle_fixture"]
        assert hashlib.sha256(input_path.read_bytes()).hexdigest() == row["input_fixture_sha256"]
        assert hashlib.sha256(oracle_path.read_bytes()).hexdigest() == row["oracle_fixture_sha256"]
        assert input_path.stat().st_mode & 0o777 == 0o600
        assert oracle_path.stat().st_mode & 0o777 == 0o600
        input_document = json.loads(input_path.read_text(encoding="utf-8"))
        assert set(input_document) == {"schema_version", "family_id", "variant_id", "user_prompt"}
        assert b"accepted_outcomes" not in input_path.read_bytes()
        assert b"synthetic_state" not in input_path.read_bytes()
        setup_path = root / row["setup_fixture"]
        assert hashlib.sha256(setup_path.read_bytes()).hexdigest() == row["setup_fixture_sha256"]
        assert setup_path.stat().st_mode & 0o777 == 0o600
        setup_document = json.loads(setup_path.read_text(encoding="utf-8"))
        assert setup_document["visibility"] == "evaluator_only"
        assert setup_document["harness_setup"] == sample_case()["input"]
        assert b"accepted_outcomes" not in setup_path.read_bytes()

    validator = load_module(VALIDATOR_PATH, "scenario_validator_for_drafts")
    assert validator.validate(manifest, root) == []


def test_refuses_invalid_or_duplicate_families_without_creating_output(tmp_path):
    builder = load_module(BUILDER_PATH, "scenario_draft_builder_invalid")
    root = tmp_path / "repo"
    root.mkdir()
    duplicated = [sample_case(), sample_case()]

    with pytest.raises(ValueError, match="duplicate family_id"):
        builder.build_set(
            duplicated,
            root=root,
            fixture_rel_dir="fixtures/demo",
            manifest_rel_path="scenario_sets/demo.json",
        )

    assert not (root / "fixtures/demo").exists()
    assert not (root / "scenario_sets/demo.json").exists()


def test_refuses_existing_output_and_does_not_overwrite_it(tmp_path):
    builder = load_module(BUILDER_PATH, "scenario_draft_builder_existing")
    root = tmp_path / "repo"
    root.mkdir()
    fixture_dir = root / "fixtures/demo"
    fixture_dir.mkdir(parents=True)
    sentinel = fixture_dir / "keep.txt"
    sentinel.write_text("preserve", encoding="utf-8")

    with pytest.raises(FileExistsError):
        builder.build_set(
            [sample_case()],
            root=root,
            fixture_rel_dir="fixtures/demo",
            manifest_rel_path="scenario_sets/demo.json",
        )

    assert sentinel.read_text(encoding="utf-8") == "preserve"


def test_refuses_symlinked_output_parent_before_writing(tmp_path):
    builder = load_module(BUILDER_PATH, "scenario_draft_builder_symlink")
    root = tmp_path / "repo"
    root.mkdir()
    (root / "real").mkdir()
    (root / "fixtures").symlink_to(root / "real", target_is_directory=True)

    with pytest.raises(ValueError, match="symlink"):
        builder.build_set(
            [sample_case()],
            root=root,
            fixture_rel_dir="fixtures/demo",
            manifest_rel_path="scenario_sets/demo.json",
        )

    assert list((root / "real").iterdir()) == []


def test_blocked_case_and_accepted_decisions_are_recorded(tmp_path):
    builder = load_module(BUILDER_PATH, "scenario_draft_builder_blocked")
    root = tmp_path / "repo"
    root.mkdir()
    case = sample_case()
    case["blocked_by"] = "task ledger (U5)"
    case["oracle"]["accepted_decisions"] = ["NO_TOOL", "ASK"]

    manifest = builder.build_set(
        [case], root=root, fixture_rel_dir="fixtures/demo", manifest_rel_path="sets/demo.json"
    )

    for row in manifest["scenarios"]:
        assert row["notes"].startswith("BLOCKED: task ledger (U5).")
        oracle = json.loads((root / row["oracle_fixture"]).read_text(encoding="utf-8"))
        assert oracle["execution_blocked_by"] == "task ledger (U5)"
        assert oracle["accepted_decisions"] == ["NO_TOOL", "ASK"]


def test_rejects_accepted_decisions_without_expected_decision(tmp_path):
    builder = load_module(BUILDER_PATH, "scenario_draft_builder_decisions")
    root = tmp_path / "repo"
    root.mkdir()
    case = sample_case()
    case["oracle"]["accepted_decisions"] = ["ASK"]

    with pytest.raises(ValueError, match="accepted_decisions"):
        builder.build_set(
            [case], root=root, fixture_rel_dir="fixtures/demo", manifest_rel_path="sets/demo.json"
        )


def test_split_is_taken_from_the_case_and_validated(tmp_path):
    builder = load_module(BUILDER_PATH, "scenario_draft_builder_split")
    root = tmp_path / "repo"
    root.mkdir()
    case = sample_case()
    case["split"] = "locked_test"
    manifest = builder.build_set(
        [case], root=root, fixture_rel_dir="fixtures/demo", manifest_rel_path="sets/demo.json"
    )
    assert {row["split"] for row in manifest["scenarios"]} == {"locked_test"}
    bad = sample_case()
    bad["split"] = "train"
    with pytest.raises(ValueError, match="split"):
        builder.build_set(
            [bad], root=root, fixture_rel_dir="fixtures/bad", manifest_rel_path="sets/bad.json"
        )


def test_frozen_set_requires_reviewed_oracles_and_records_the_review(tmp_path):
    builder = load_module(BUILDER_PATH, "scenario_draft_builder_frozen")
    root = tmp_path / "repo"
    root.mkdir()
    with pytest.raises(ValueError, match="reviewed"):
        builder.build_set(
            [sample_case()],
            root=root,
            fixture_rel_dir="f/a",
            manifest_rel_path="s/a.json",
            status="FROZEN",
        )
    manifest = builder.build_set(
        [sample_case()],
        root=root,
        fixture_rel_dir="f/b",
        manifest_rel_path="s/b.json",
        status="FROZEN",
        review_status="REVIEWED: codex+gemini, author fixes",
    )
    for row in manifest["scenarios"]:
        assert row["status"] == "FROZEN"
        oracle = json.loads((root / row["oracle_fixture"]).read_text(encoding="utf-8"))
        assert oracle["review_status"] == "REVIEWED: codex+gemini, author fixes"


def test_draft_with_non_default_review_status_records_pending_owner_in_notes(tmp_path):
    builder = load_module(BUILDER_PATH, "scenario_draft_builder_pending")
    root = tmp_path / "repo"
    root.mkdir()
    status_note = "DRAFT_PENDING_OWNER_REVIEW: Codex review PENDING_OWNER"
    manifest = builder.build_set(
        [sample_case()],
        root=root,
        fixture_rel_dir="f/c",
        manifest_rel_path="s/c.json",
        status="DRAFT",
        review_status=status_note,
    )
    for row in manifest["scenarios"]:
        assert row["status"] == "DRAFT"
        assert status_note in row["notes"]
        oracle = json.loads((root / row["oracle_fixture"]).read_text(encoding="utf-8"))
        assert oracle["review_status"] == status_note
