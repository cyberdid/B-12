"""Standing gemma regression set and its report."""

import json
from pathlib import Path

from evals.unified import build_regression_set, regression_report

ROOT = Path(__file__).resolve().parents[2]


def test_set_is_built_from_frozen_rows_unchanged():
    built = build_regression_set.build()
    assert built["set_id"] == "regression-gemma-v1"
    assert {r["family_id"] for r in built["scenarios"]} == set(build_regression_set.FAMILIES)
    assert len(built["scenarios"]) == 2 * len(build_regression_set.FAMILIES)
    on_disk = json.loads(build_regression_set.OUT.read_text(encoding="utf-8"))
    assert on_disk == built  # the committed manifest is reproducible
    for row in built["scenarios"]:
        assert row["status"] == "FROZEN"
        assert (ROOT / row["oracle_fixture"]).exists()


def _write(directory, scenario_id, **fields):
    record = {
        "scenario_id": scenario_id,
        "status": "EXECUTED",
        "runtime_state": "completed",
        "error_code": None,
        "reply": "",
        "tool_calls": [],
        "evidence_ids": [],
        **fields,
    }
    path = Path(directory) / "r1" / f"{scenario_id}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record, ensure_ascii=False))


def test_report_flags_a_failed_turn_and_a_new_failure_against_the_baseline(tmp_path):
    manifest = build_regression_set.OUT
    base, run = tmp_path / "base", tmp_path / "run"
    call = {"name": "run_command", "arguments": {"command": "x"}, "status": "completed"}
    _write(base, "C58-P1", tool_calls=[call])
    _write(run, "C58-P1", tool_calls=[call] * 5)
    _write(base, "C39-P1")
    _write(run, "C39-P1", runtime_state="failed", error_code="context_mismatch")
    rows, regressions = regression_report.compare(manifest, run, base, ROOT)
    by_id = {r["scenario_id"]: r for r in rows}
    assert by_id["C39-P1"]["outcome"] == "RUN_FAILED:context_mismatch"
    assert by_id["C58-P1"]["repeats"] == 4
    assert {r["scenario_id"] for r in regressions} == {"C39-P1", "C58-P1"}


def test_report_without_baseline_flags_only_failures(tmp_path):
    _write(tmp_path / "run", "C39-P1", runtime_state="failed", error_code="context_mismatch")
    _write(tmp_path / "run", "C39-P2")
    rows, regressions = regression_report.compare(
        build_regression_set.OUT, tmp_path / "run", None, ROOT
    )
    assert [r["scenario_id"] for r in regressions] == ["C39-P1"]
    assert len(rows) == 2
