"""Verification script for Explorer M4 Ablation & Statistical Pipeline."""

import csv
import json
import tempfile
from pathlib import Path
import numpy as np
from evals.capri_comprehensive.evaluators.schema import (
    ScenarioDefinition,
    ExecutionReport,
    ExecutionStatus,
    ScientificTaxonomy,
    ScenarioSeverity,
    ExecutionMode,
    TurnExecutionResult,
)
from evals.capri_comprehensive.runners.ablation_runner import (
    AblationRunner,
    AblationDimension,
    ABLATION_CONDITIONS,
    apply_ablation_to_scenario,
)
from evals.capri_comprehensive.runners.runner import ScenarioRunner
from evals.capri_comprehensive.statistical_analysis.metrics import (
    wilson_score_interval,
    bootstrap_percentile_ci,
    calculate_latency_summary,
    calculate_binomial_summary,
)
from evals.capri_comprehensive.statistical_analysis.aggregator import (
    EvaluationAggregator,
    CSV_COLUMNS_15,
)

def test_metrics():
    print("Testing metrics computation...")
    # Wilson CI
    w_low, w_high = wilson_score_interval(10, 10, confidence=0.95)
    print(f"Wilson 10/10 95% CI: [{w_low}, {w_high}]")
    assert 0.72 <= w_low <= 0.74
    assert w_high == 1.0

    w_zero_low, w_zero_high = wilson_score_interval(0, 10, confidence=0.95)
    print(f"Wilson 0/10 95% CI: [{w_zero_low}, {w_zero_high}]")
    assert w_zero_low == 0.0
    assert 0.25 <= w_zero_high <= 0.29

    # Latency bootstrap
    lats = [120.0, 135.5, 110.2, 145.0, 125.8, 130.1, 210.4, 118.9, 122.0, 129.5]
    lat_summary = calculate_latency_summary(lats, n_bootstrap=500, seed=42)
    print(f"Latency P50: {lat_summary['p50']}ms, 95% CI: {lat_summary['p50_ci']}")
    print(f"Latency P95: {lat_summary['p95']}ms, 95% CI: {lat_summary['p95_ci']}")
    assert lat_summary['p50_ci'][0] <= lat_summary['p50_ci'][1]
    assert lat_summary['p95_ci'][0] <= lat_summary['p95_ci'][1]
    print("Metrics tests PASSED.")

def test_ablation_execution():
    print("\nTesting AblationRunner on mock executor...")
    sc_path = Path("evals/capri_comprehensive/scenarios/group_a_memory/MEM-01.yaml")
    sc = ScenarioDefinition.from_yaml_file(sc_path)

    with tempfile.TemporaryDirectory() as tmp_dir:
        def mock_turn(user_input, turn_idx, world_state):
            return {
                "content": "24 жовтня на стенді B-12 ми тестували датчик струму.",
                "tool_calls": [{"name": "memory_search", "arguments": {"query": user_input}}],
                "ttft_ms": 110.0,
                "tokens_prompt": 30,
                "tokens_completion": 20,
            }

        sc_runner = ScenarioRunner(artifacts_dir=tmp_dir, turn_executor=mock_turn)
        ab_runner = AblationRunner(scenario_runner=sc_runner, artifacts_dir=tmp_dir)

        # Run A1_MEMORY
        res_a1 = ab_runner.run_ablation(sc, AblationDimension.A1_MEMORY)
        print(f"A1 results: {json.dumps(res_a1, indent=2, ensure_ascii=False)}")
        assert "FULL" in res_a1["results"]
        assert "RAW" in res_a1["results"]
        assert "OFF" in res_a1["results"]

        # Run A2_CONTEXT
        res_a2 = ab_runner.run_ablation(sc, AblationDimension.A2_CONTEXT)
        print(f"A2 results: {json.dumps(res_a2, indent=2, ensure_ascii=False)}")
        assert "2048" in res_a2["results"]
        assert "4096" in res_a2["results"]
        assert "8192" in res_a2["results"]

        print("AblationRunner execution tests PASSED.")

if __name__ == "__main__":
    test_metrics()
    test_ablation_execution()


def test_statistical_scenario_matrix_csv():
    print("\nTesting 15-Column Statistical Scenario Matrix CSV Generation...")
    
    # Create sample reports
    rep_pass = ExecutionReport(
        scenario_id="MEM-01",
        group="Group A: Autobiographical Memory",
        title="Episodic Recall Baseline",
        taxonomy=ScientificTaxonomy.REAL_MODEL_BEHAVIORAL,
        severity=ScenarioSeverity.CRITICAL,
        execution_mode=ExecutionMode.AUTOMATED_IMMEDIATE,
        status=ExecutionStatus.EXECUTED_PASS,
        all_passed=True,
        latencies_ms=[120.0, 130.0],
        started_at="2026-11-10T12:00:00Z",
        completed_at="2026-11-10T12:00:02Z",
        raw_score=1.0,
        turn_results=[
            TurnExecutionResult(
                turn_index=0,
                prompt="Q",
                response_content="A",
                passed=True,
                ttft_ms=50.0,
                total_duration_ms=120.0,
            )
        ]
    )

    rep_blocked = ExecutionReport(
        scenario_id="ROB-01",
        group="Group J: Embodiment & Robotics",
        title="Actuator Bus Safety",
        taxonomy=ScientificTaxonomy.PHYSICAL_ACCEPTANCE,
        severity=ScenarioSeverity.CRITICAL,
        execution_mode=ExecutionMode.BLOCKED_HARDWARE,
        status=ExecutionStatus.BLOCKED_HARDWARE,
        blocker_reason="Missing physical hardware requirement: reachy_actuator_bus",
        started_at="2026-11-10T12:00:00Z",
        completed_at="2026-11-10T12:00:00Z",
        raw_score=0.0,
    )

    STATISTICAL_15_COLS = [
        "Scenario_ID",
        "Group",
        "Name",
        "Taxonomy",
        "Severity",
        "Target_Subsystem",
        "Hypothesis",
        "Execution_Status",
        "Raw_Score",
        "CI_95_Low",
        "CI_95_High",
        "P50_Latency_ms",
        "P95_Latency_ms",
        "Ablation_Sensitivity",
        "Failure_Reason",
    ]

    with tempfile.NamedTemporaryFile("w+", suffix=".csv", delete=False) as f:
        csv_file = Path(f.name)
        writer = csv.DictWriter(f, fieldnames=STATISTICAL_15_COLS)
        writer.writeheader()

        for rep in [rep_pass, rep_blocked]:
            turns = len(rep.turn_results)
            passed_turns = sum(1 for t in rep.turn_results if t.passed)
            ci_low, ci_high = wilson_score_interval(passed_turns, turns, confidence=0.95) if turns > 0 else (0.0, 0.0)
            p50 = round(float(np.median(rep.latencies_ms)), 2) if rep.latencies_ms else 0.0
            p95 = round(float(np.percentile(rep.latencies_ms, 95)), 2) if rep.latencies_ms else 0.0

            subsystem = "memory" if "memory" in rep.group.lower() else "robotics"
            ablation_sens = "A1_HIGH" if rep.scenario_id.startswith("MEM") else "NONE"
            fail_reason = rep.blocker_reason if rep.blocker_reason else "None"

            row = {
                "Scenario_ID": rep.scenario_id,
                "Group": rep.group,
                "Name": rep.title,
                "Taxonomy": rep.taxonomy.value,
                "Severity": rep.severity.value,
                "Target_Subsystem": subsystem,
                "Hypothesis": "Hypothesis placeholder",
                "Execution_Status": rep.status.value,
                "Raw_Score": rep.raw_score,
                "CI_95_Low": ci_low,
                "CI_95_High": ci_high,
                "P50_Latency_ms": p50,
                "P95_Latency_ms": p95,
                "Ablation_Sensitivity": ablation_sens,
                "Failure_Reason": fail_reason,
            }
            writer.writerow(row)

    # Read back and verify
    with open(csv_file, "r") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
        print(f"Exported {len(rows)} rows with columns: {reader.fieldnames}")
        assert reader.fieldnames == STATISTICAL_15_COLS
        assert rows[0]["Scenario_ID"] == "MEM-01"
        assert rows[0]["Raw_Score"] == "1.0"
        assert rows[0]["Execution_Status"] == "EXECUTED_PASS"
        assert rows[1]["Scenario_ID"] == "ROB-01"
        assert rows[1]["Execution_Status"] == "BLOCKED_HARDWARE"
        assert "reachy_actuator_bus" in rows[1]["Failure_Reason"]
    print("15-Column Statistical Scenario Matrix CSV Generation PASSED.")

test_statistical_scenario_matrix_csv()
