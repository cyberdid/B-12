"""Empirical Stress Tests & Numerical Precision Harness for Milestone M4 Gate.

Validates:
1. Matrix CSV & Batch Summary bit-for-bit and float consistency across all 92 scenarios.
2. Zero duplicates, zero NaN/null values in required fields, and 15-column schema conformance.
3. Mathematical soundness:
   - CI bounds: 0.0 <= CI_95_Low <= CI_95_High <= 1.0
   - Wilson score intervals accurately enclose empirical turn success rates
   - Latency monotonicity: 0.0 <= P50_Latency_ms <= P95_Latency_ms
   - Blocked scenario invariant: Raw_Score == 0.0 and CI == [0.0, 0.0]
4. Top-level batch summary aggregation consistency with report item counts.
5. Cross-validation against ground-truth YAML scenario definitions.
"""

from __future__ import annotations

import csv
import json
import math
from pathlib import Path

import numpy as np
import pytest
import yaml

from evals.capri_comprehensive.evaluators.schema import ScenarioDefinition
from evals.capri_comprehensive.statistical_analysis.aggregator import (
    CSV_COLUMNS_15,
    derive_target_subsystem,
)
from evals.capri_comprehensive.statistical_analysis.metrics import wilson_score_interval

REPORTS_DIR = Path(__file__).parent.parent / "reports"
CSV_PATH = REPORTS_DIR / "CAPRI_SCENARIO_MATRIX.csv"
JSON_PATH = REPORTS_DIR / "batch_summary.json"
SCENARIOS_DIR = Path(__file__).parent.parent / "scenarios"


@pytest.fixture(scope="module")
def matrix_csv_data() -> tuple[list[str], list[dict[str, str]]]:
    """Load and parse CAPRI_SCENARIO_MATRIX.csv."""
    assert CSV_PATH.exists(), f"Missing matrix CSV at {CSV_PATH}"
    with open(CSV_PATH, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
        fieldnames = list(reader.fieldnames or [])
    return fieldnames, rows


@pytest.fixture(scope="module")
def batch_summary_data() -> dict:
    """Load and parse batch_summary.json."""
    assert JSON_PATH.exists(), f"Missing batch summary JSON at {JSON_PATH}"
    with open(JSON_PATH, encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture(scope="module")
def scenario_yamls() -> dict[str, ScenarioDefinition]:
    """Load all 92 scenario YAML definitions."""
    yaml_files = list(SCENARIOS_DIR.glob("**/*.yaml"))
    scenarios = {}
    for yf in yaml_files:
        with open(yf, encoding="utf-8") as f:
            data = yaml.safe_load(f)
            sc = ScenarioDefinition.model_validate(data)
            scenarios[sc.id] = sc
    return scenarios


class TestMatrixStructuralIntegrity:
    """Tests matrix structure, schema, completeness, and null-safety."""

    def test_schema_and_column_headers(self, matrix_csv_data):
        fieldnames, rows = matrix_csv_data
        assert fieldnames == CSV_COLUMNS_15
        assert len(fieldnames) == 15

    def test_scenario_counts_strictly_92(
        self, matrix_csv_data, batch_summary_data, scenario_yamls
    ):
        _, rows = matrix_csv_data
        reports = batch_summary_data.get("reports", [])
        assert len(rows) == 92, f"Expected 92 CSV rows, got {len(rows)}"
        assert len(reports) == 92, f"Expected 92 JSON reports, got {len(reports)}"
        assert len(scenario_yamls) == 92, f"Expected 92 YAML scenarios, got {len(scenario_yamls)}"
        assert batch_summary_data.get("total_scenarios") == 92

    def test_zero_duplicate_scenario_ids(self, matrix_csv_data, batch_summary_data):
        _, rows = matrix_csv_data
        csv_ids = [r["Scenario_ID"] for r in rows]
        json_ids = [r["scenario_id"] for r in batch_summary_data.get("reports", [])]

        dup_csv = len(csv_ids) - len(set(csv_ids))
        dup_json = len(json_ids) - len(set(json_ids))
        assert len(csv_ids) == len(set(csv_ids)), f"Duplicate IDs in CSV: {dup_csv}"
        assert len(json_ids) == len(set(json_ids)), f"Duplicate IDs in JSON: {dup_json}"
        assert set(csv_ids) == set(json_ids), "CSV and JSON scenario ID sets differ"

    def test_zero_nan_or_null_in_required_fields(self, matrix_csv_data):
        _, rows = matrix_csv_data
        for r in rows:
            sid = r["Scenario_ID"]
            for field in CSV_COLUMNS_15:
                val = r.get(field)
                assert val is not None, f"Null value in {sid} field {field}"
                assert val != "", f"Empty string in {sid} field {field}"
                assert val.strip().lower() not in (
                    "nan",
                    "null",
                ), f"NaN/null string in {sid} field {field}"


class TestMatrixNumericalAndStatisticalSoundness:
    """Tests mathematical soundness, confidence intervals, and latencies."""

    def test_confidence_interval_bounds(self, matrix_csv_data):
        _, rows = matrix_csv_data
        for r in rows:
            sid = r["Scenario_ID"]
            ci_low = float(r["CI_95_Low"])
            ci_high = float(r["CI_95_High"])
            assert 0.0 <= ci_low <= 1.0, f"[{sid}] CI_95_Low {ci_low} out of bounds [0, 1]"
            assert 0.0 <= ci_high <= 1.0, f"[{sid}] CI_95_High {ci_high} out of bounds [0, 1]"
            assert ci_low <= ci_high, (
                f"[{sid}] Inverted CI: CI_95_Low ({ci_low}) > CI_95_High ({ci_high})"
            )

    def test_latency_percentile_monotonicity_and_bounds(self, matrix_csv_data):
        _, rows = matrix_csv_data
        for r in rows:
            sid = r["Scenario_ID"]
            p50 = float(r["P50_Latency_ms"])
            p95 = float(r["P95_Latency_ms"])
            assert p50 >= 0.0, f"[{sid}] Negative P50 latency: {p50}"
            assert p95 >= 0.0, f"[{sid}] Negative P95 latency: {p95}"
            assert p50 <= p95 + 1e-4, f"[{sid}] Monotonicity violation: P50 ({p50}) > P95 ({p95})"

    def test_blocked_scenario_invariants(self, matrix_csv_data):
        _, rows = matrix_csv_data
        for r in rows:
            sid = r["Scenario_ID"]
            status = r["Execution_Status"]
            if "BLOCKED" in status:
                raw_score = float(r["Raw_Score"])
                ci_low = float(r["CI_95_Low"])
                ci_high = float(r["CI_95_High"])
                assert (
                    raw_score == 0.0
                ), f"[{sid}] Blocked scenario must have Raw_Score == 0.0, got {raw_score}"
                assert (
                    ci_low == 0.0
                ), f"[{sid}] Blocked scenario must have CI_95_Low == 0.0, got {ci_low}"
                assert (
                    ci_high == 0.0
                ), f"[{sid}] Blocked scenario must have CI_95_High == 0.0, got {ci_high}"
                assert (
                    r["Failure_Reason"] != "None"
                ), f"[{sid}] Blocked scenario must document blocker reason"

    def test_wilson_interval_consistency_with_empirical_turns(
        self, matrix_csv_data, batch_summary_data
    ):
        _, rows = matrix_csv_data
        json_reports = {r["scenario_id"]: r for r in batch_summary_data["reports"]}

        for r in rows:
            sid = r["Scenario_ID"]
            rep = json_reports[sid]
            status = r["Execution_Status"]
            ci_low = float(r["CI_95_Low"])
            ci_high = float(r["CI_95_High"])

            if "BLOCKED" in status:
                continue

            turns = rep.get("turn_results", [])
            if turns:
                total_turns = len(turns)
                passed_turns = sum(1 for t in turns if t["passed"])
                expected_low, expected_high = wilson_score_interval(
                    passed_turns, total_turns, 0.95
                )
                turn_rate = passed_turns / total_turns

                # Turn success rate must be enclosed within Wilson interval
                assert expected_low - 1e-4 <= turn_rate <= expected_high + 1e-4, (
                    f"[{sid}] Turn rate {turn_rate} not enclosed in "
                    f"Wilson [{expected_low}, {expected_high}]"
                )
                # Matrix CSV values must match Wilson calculations rounded to 4 decimals
                assert math.isclose(ci_low, round(expected_low, 4), abs_tol=1e-4)
                assert math.isclose(ci_high, round(expected_high, 4), abs_tol=1e-4)


class TestCrossArtifactConsistency:
    """Verifies bit-for-bit and float consistency across CSV, JSON, and YAML definitions."""

    def test_status_and_score_consistency(self, matrix_csv_data, batch_summary_data):
        _, rows = matrix_csv_data
        json_reports = {r["scenario_id"]: r for r in batch_summary_data["reports"]}

        for r in rows:
            sid = r["Scenario_ID"]
            rep = json_reports[sid]
            assert r["Execution_Status"] == rep["status"], f"[{sid}] Status mismatch"
            csv_score = float(r["Raw_Score"])
            json_score = float(rep["raw_score"])
            assert math.isclose(csv_score, json_score, abs_tol=1e-5), f"[{sid}] Raw_Score mismatch"

    def test_latency_percentile_exact_reproducibility(self, matrix_csv_data, batch_summary_data):
        _, rows = matrix_csv_data
        json_reports = {r["scenario_id"]: r for r in batch_summary_data["reports"]}

        for r in rows:
            sid = r["Scenario_ID"]
            rep = json_reports[sid]
            csv_p50 = float(r["P50_Latency_ms"])
            csv_p95 = float(r["P95_Latency_ms"])

            lats = rep.get("latencies_ms", [])
            if lats:
                exp_p50 = round(float(np.percentile(lats, 50)), 2)
                exp_p95 = round(float(np.percentile(lats, 95)), 2)
            else:
                exp_p50 = 0.0
                exp_p95 = 0.0

            assert math.isclose(
                csv_p50, exp_p50, abs_tol=1e-2
            ), f"[{sid}] P50 latency mismatch: {csv_p50} vs {exp_p50}"
            assert math.isclose(
                csv_p95, exp_p95, abs_tol=1e-2
            ), f"[{sid}] P95 latency mismatch: {csv_p95} vs {exp_p95}"

    def test_metadata_alignment_with_yaml_specifications(self, matrix_csv_data, scenario_yamls):
        _, rows = matrix_csv_data
        for r in rows:
            sid = r["Scenario_ID"]
            sc = scenario_yamls[sid]

            assert r["Name"] == sc.title, f"[{sid}] Name mismatch"
            assert r["Taxonomy"] == sc.taxonomy.value, f"[{sid}] Taxonomy mismatch"
            assert r["Severity"] == sc.severity.value, f"[{sid}] Severity mismatch"
            assert r["Hypothesis"] == sc.research_hypothesis, f"[{sid}] Hypothesis mismatch"
            assert r["Target_Subsystem"] == derive_target_subsystem(
                sid, sc.group
            ), f"[{sid}] Subsystem mismatch"

    def test_top_level_summary_aggregation_integrity(self, matrix_csv_data, batch_summary_data):
        _, rows = matrix_csv_data
        reports = batch_summary_data["reports"]

        count_pass = sum(1 for r in reports if r["status"] == "EXECUTED_PASS")
        count_fail = sum(1 for r in reports if r["status"] == "EXECUTED_FAIL")
        count_hw = sum(1 for r in reports if r["status"] == "BLOCKED_HARDWARE")
        count_delay = sum(1 for r in reports if r["status"] == "BLOCKED_DELAY")

        # Перевіряємо узгодженість зведення з власними записами, а не фіксовані числа:
        # цифри змінюються з кожним повним прогоном і мають бути виведені з артефактів.
        assert batch_summary_data["total_scenarios"] == 92
        assert batch_summary_data["passed"] == count_pass
        assert batch_summary_data["failed"] == count_fail
        assert batch_summary_data["blocked_hardware"] == count_hw
        assert batch_summary_data["blocked_delay"] == count_delay
        assert count_pass + count_fail + count_hw + count_delay == 92


def test_runner_zero_facade_strings_integrity() -> None:
    """Verify that runner.py contains zero hardcoded turn responses or mock echo strings."""
    runner_path = Path(__file__).parent.parent / "runners" / "runner.py"
    content = runner_path.read_text(encoding="utf-8")
    forbidden_facade_strings = [
        "RETRY_SUCCESS TRANSACTION_COMMITTED",
        "MODEL_UNAVAILABLE CONNECTION_REFUSED",
        "BACKOFF_ENFORCED: interval scaled exponentially.",
        "ALL_MUTATIONS_SERIALIZED cleanly.",
        "STATE_HASH_MATCH: 100%",
        "SIGTERM_HANDLED_CLEANLY: WAL flushed.",
        "RESUMING_STEP: 3",
        "_dispatch_deterministic_turn",
    ]
    for s in forbidden_facade_strings:
        assert (
            s not in content
        ), f"Integrity violation: forbidden facade string '{s}' found in runner.py"


def test_ablation_a4_tools_token_differentiation_integrity() -> None:
    """Verify that A4_TOOLS ablation outputs genuinely differentiated prompt token counts."""
    ablation_file = (
        Path(__file__).parent.parent / "artifacts" / "ablations" / "RE-01_A4_TOOLS.json"
    )
    assert ablation_file.exists(), f"Missing ablation artifact at {ablation_file}"
    with open(ablation_file, encoding="utf-8") as f:
        data = json.load(f)
    results = data["results"]
    tokens = [results[c]["tokens_prompt"] for c in ["FULL", "STRICT", "MINIMAL"]]
    assert len(set(tokens)) == 3, (
        f"A4_TOOLS prompt tokens must be distinct across conditions, got {tokens}"
    )
    assert tokens[0] > tokens[1] > tokens[2], (
        f"A4_TOOLS prompt tokens must strictly decrease FULL > STRICT > MINIMAL: {tokens}"
    )


def test_ablation_a3_gating_token_differentiation_integrity() -> None:
    """Verify that A3_GATING ablation outputs genuinely differentiated prompt token counts."""
    ablation_file = (
        Path(__file__).parent.parent / "artifacts" / "ablations" / "SEC-01_A3_GATING.json"
    )
    assert ablation_file.exists(), f"Missing ablation artifact at {ablation_file}"
    with open(ablation_file, encoding="utf-8") as f:
        data = json.load(f)
    results = data["results"]
    tokens = [results[c]["tokens_prompt"] for c in ["DETERMINISTIC", "PROMPT_ONLY"]]
    assert len(set(tokens)) == 2, f"A3_GATING prompt tokens must be distinct, got {tokens}"
    assert tokens[0] > tokens[1], (
        f"DETERMINISTIC should have longer system policy prompt: {tokens}"
    )
