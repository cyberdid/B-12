"""Verify baseline manifest shape and important provenance constraints."""

import hashlib
import json
from copy import deepcopy
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def manifest():
    path = ROOT / "reports/unified/baseline/environment-2026-11-18.json"
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.fixture
def validator():
    schema = json.loads((ROOT / "evals/unified/manifest.schema.json").read_text())
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def test_baseline_manifest_is_valid(validator, manifest):
    assert list(validator.iter_errors(manifest)) == []


@pytest.mark.parametrize(
    "change",
    [
        lambda m: m.pop("commit"),
        lambda m: m.update(commit="invented"),
        lambda m: m.update(status="SUCCESS"),
        lambda m: m["configuration"].update(context_tokens=-1),
        lambda m: m["model"].update(profile_sha256="invalid"),
    ],
)
def test_invalid_provenance_rejected(validator, manifest, change):
    invalid = deepcopy(manifest)
    change(invalid)
    assert list(validator.iter_errors(invalid))


def test_completed_run_cannot_be_reproducibility_ready_with_unknown_parameters(manifest):
    import importlib.util

    path = ROOT / "evals/unified/validate_manifest.py"
    assert path.exists(), "manifest readiness validator missing"
    spec = importlib.util.spec_from_file_location("manifest_validator", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    manifest["status"] = "COMPLETED"
    missing = module.readiness_issues(manifest, ROOT)
    assert "model.digest" in missing
    assert "configuration.context_tokens" in missing
    assert "raw_results" in missing


def test_noncompleted_run_never_claims_readiness(manifest):
    import importlib.util

    path = ROOT / "evals/unified/validate_manifest.py"
    assert path.exists(), "manifest readiness validator missing"
    spec = importlib.util.spec_from_file_location("manifest_validator", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert "status" in module.readiness_issues(manifest, ROOT)


def test_ready_run_requires_existing_safe_artifact_path(manifest, tmp_path):
    import importlib.util

    path = ROOT / "evals/unified/validate_manifest.py"
    spec = importlib.util.spec_from_file_location("manifest_validator", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    manifest["status"] = "COMPLETED"
    manifest["scenario_set_sha256"] = "a" * 64
    manifest["environment"] = {
        "host": "host-1",
        "os": "linux",
        "python": "3.12",
        "cpu": "cpu",
        "gpu": "none",
        "vram_bytes": 0,
        "ram_bytes": 123,
        "power_mode": "unknown-not-recorded",
    }
    manifest["model"] = {
        "name": "test",
        "digest": "test-digest",
        "quantization": "q4",
        "runtime_version": "test",
        "profile_sha256": "b" * 64,
        "tokenizer_sha256": "c" * 64,
        "chat_template_sha256": "d" * 64,
    }
    manifest["configuration"] = {
        "context_tokens": 8192,
        "output_tokens": 512,
        "cache_state": "cold",
        "repeats": 1,
        "snapshot_sha256": "e" * 64,
    }
    manifest["raw_results"] = [
        {"path": "results.json", "sha256": hashlib.sha256(b"{}").hexdigest()}
    ]
    assert "raw_results.invalid_path" in module.readiness_issues(manifest, tmp_path)
    (tmp_path / "results.json").write_text("{}")
    assert module.readiness_issues(manifest, tmp_path) == []
    (tmp_path / "results.json").write_text("tampered")
    assert "raw_results.hash_mismatch" in module.readiness_issues(manifest, tmp_path)
    manifest["raw_results"] = [{"path": "../escape", "sha256": "f" * 64}]
    assert "raw_results.invalid_path" in module.readiness_issues(manifest, tmp_path)


def _completed_software_suite_manifest(tmp_path):
    artifact = tmp_path / "pytest.log"
    artifact.write_text("894 passed, 3 skipped, 0 failed\n")
    digest = hashlib.sha256(artifact.read_bytes()).hexdigest()
    return {
        "schema_version": 2,
        "run_id": "pytest-full-2026-11-18",
        "run_type": "software_suite",
        "status": "COMPLETED",
        "commit": "36d557d83ce2f44f694cea5d19939031c630a471",
        "dirty": True,
        "scenario_set_sha256": None,
        "environment": {
            "host": None,
            "os": "Linux-test",
            "python": "3.12.3",
            "cpu": "CPU-test",
            "gpu": "not_applicable",
            "vram_bytes": 0,
            "ram_bytes": 1024,
            "power_mode": "unknown-not-recorded",
        },
        "model": {
            "name": None,
            "digest": None,
            "quantization": None,
            "runtime_version": None,
            "profile_sha256": None,
            "tokenizer_sha256": None,
            "chat_template_sha256": None,
        },
        "configuration": {
            "context_tokens": None,
            "output_tokens": None,
            "cache_state": "not_applicable",
            "repeats": 1,
            "snapshot_sha256": "a" * 64,
        },
        "suite": {
            "name": "B-12 full pytest suite",
            "command": "B12_DOCKER_TEST=1 .venv/bin/pytest -q",
            "test_roots": ["tests"],
            "source_snapshot_sha256": "a" * 64,
            "passed": 894,
            "skipped": 3,
            "failed": 0,
            "duration_seconds": 156.55,
        },
        "raw_results": [{"path": "pytest.log", "sha256": digest}],
    }


def test_v2_completed_software_suite_is_ready_without_model(tmp_path):
    import importlib.util

    path = ROOT / "evals/unified/validate_manifest.py"
    spec = importlib.util.spec_from_file_location("manifest_validator", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    manifest = _completed_software_suite_manifest(tmp_path)

    assert module.readiness_issues(manifest, tmp_path) == []


def test_v2_model_evaluation_requires_model_and_scenario_provenance(tmp_path):
    import importlib.util

    path = ROOT / "evals/unified/validate_manifest.py"
    spec = importlib.util.spec_from_file_location("manifest_validator", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    manifest = _completed_software_suite_manifest(tmp_path)
    manifest["run_type"] = "model_evaluation"

    issues = module.readiness_issues(manifest, tmp_path)
    assert issues
    assert all(issue.startswith("schema:") for issue in issues)


def test_ready_manifest_rejects_symlinked_result_even_inside_root(tmp_path):
    import importlib.util

    path = ROOT / "evals/unified/validate_manifest.py"
    spec = importlib.util.spec_from_file_location("manifest_validator", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    manifest = _completed_software_suite_manifest(tmp_path)
    actual = tmp_path / "actual.log"
    actual.write_text("894 passed, 3 skipped, 0 failed\n")
    (tmp_path / "pytest.log").unlink()
    (tmp_path / "pytest.log").symlink_to(actual.name)

    assert "raw_results.invalid_path" in module.readiness_issues(manifest, tmp_path)
