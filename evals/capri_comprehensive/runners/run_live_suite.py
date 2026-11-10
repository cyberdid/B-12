"""Run the live component checks and merge their reports into the suite outputs.

Each live handler (see live_components.py) produces one ExecutionReport in the same
format the scenario runner writes. The reports replace the earlier harness-limited
entries for the same scenario IDs in artifacts/, batch_summary.json and the matrix.

Usage (from the repository root):
    uv run python -m evals.capri_comprehensive.runners.run_live_suite
"""

from __future__ import annotations

import json
import time
from datetime import UTC, datetime
from pathlib import Path

from evals.capri_comprehensive.evaluators.schema import (
    AssertionOutcome,
    ExecutionReport,
    ExecutionStatus,
    ScenarioDefinition,
    TurnExecutionResult,
)
from evals.capri_comprehensive.runners.live_components import HANDLERS, run_live
from evals.capri_comprehensive.statistical_analysis.aggregator import EvaluationAggregator

ROOT = Path(__file__).resolve().parents[1]
SCENARIOS = ROOT / "scenarios"
ARTIFACTS = ROOT / "artifacts"
REPORTS = ROOT / "reports"


def _scenario(sid: str) -> ScenarioDefinition:
    return ScenarioDefinition.from_yaml_file(next(SCENARIOS.glob(f"*/{sid}.yaml")))


def _to_report(sc: ScenarioDefinition, started: str, result) -> ExecutionReport:
    passed = result.passed
    assertions = [
        AssertionOutcome(
            rule_type="live_measurement",
            passed=e.passed,
            detail=f"{e.name}: {e.detail}",
            expected=True,
            actual=e.passed,
            turn=0,
        )
        for e in result.evidence
    ]
    turn = TurnExecutionResult(
        turn_index=0,
        prompt=f"live component check {sc.id}",
        response_content=result.response,
        tool_calls=[],
        ttft_ms=0.0,
        total_duration_ms=0.0,
        passed=passed,
        passed_assertions=[a for a in assertions if a.passed],
        failed_assertions=[a for a in assertions if not a.passed],
    )
    return ExecutionReport(
        scenario_id=sc.id,
        group=sc.group,
        title=sc.title,
        taxonomy=sc.taxonomy,
        severity=sc.severity,
        execution_mode=sc.execution_mode,
        status=ExecutionStatus.EXECUTED_PASS if passed else ExecutionStatus.EXECUTED_FAIL,
        all_passed=passed,
        turn_results=[turn],
        latencies_ms=[],
        ttft_ms_list=[],
        started_at=started,
        completed_at=datetime.now(UTC).isoformat(),
        raw_score=1.0 if passed else 0.0,
    )


def main() -> None:
    batch = json.loads((REPORTS / "batch_summary.json").read_text(encoding="utf-8"))
    by_id = {r["scenario_id"]: r for r in batch["reports"]}
    scenarios: dict[str, ScenarioDefinition] = {}
    new_reports: dict[str, ExecutionReport] = {}
    for sid in HANDLERS:
        sc = _scenario(sid)
        scenarios[sid] = sc
        started = datetime.now(UTC).isoformat()
        t0 = time.monotonic()
        result = run_live(sid)
        report = _to_report(sc, started, result)
        new_reports[sid] = report
        out = ARTIFACTS / sid
        out.mkdir(parents=True, exist_ok=True)
        (out / "execution_report.json").write_text(
            report.model_dump_json(indent=2), encoding="utf-8"
        )
        verdict = "PASS" if report.all_passed else "FAIL"
        print(f"{sid} {verdict} ({time.monotonic() - t0:.1f}s)", flush=True)

    for sid, report in new_reports.items():
        by_id[sid] = json.loads(report.model_dump_json())
    batch["reports"] = [by_id[k] for k in sorted(by_id)]
    counts = {}
    for r in batch["reports"]:
        counts[r["status"]] = counts.get(r["status"], 0) + 1
    batch["passed"] = counts.get("EXECUTED_PASS", 0)
    batch["failed"] = counts.get("EXECUTED_FAIL", 0)
    batch["blocked_hardware"] = counts.get("BLOCKED_HARDWARE", 0)
    batch["blocked_delay"] = counts.get("BLOCKED_DELAY", 0)
    (REPORTS / "batch_summary.json").write_text(
        json.dumps(batch, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    all_reports = [ExecutionReport(**r) for r in batch["reports"]]
    all_scenarios = {}
    for path in SCENARIOS.glob("*/*.yaml"):
        sc = ScenarioDefinition.from_yaml_file(path)
        all_scenarios[sc.id] = sc
    agg = EvaluationAggregator(all_reports)
    agg.write_scenario_matrix_csv(REPORTS / "CAPRI_SCENARIO_MATRIX.csv", scenarios_map=all_scenarios)
    agg.generate_markdown_summary(REPORTS / "STATISTICAL_SUMMARY.md")
    print("counts:", counts, flush=True)


if __name__ == "__main__":
    main()
