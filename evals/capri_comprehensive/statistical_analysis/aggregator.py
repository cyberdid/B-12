"""Report Aggregator and CSV Scenario Matrix Generator.

Aggregates execution reports into:
1. The authoritative 15-column `CAPRI_SCENARIO_MATRIX.csv`.
2. Group-level statistical summaries with Wilson score confidence intervals.
3. Latency percentile distributions with non-parametric bootstrap confidence intervals.
4. Comprehensive Markdown evaluation summary tables.
"""

from __future__ import annotations

import csv
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np

from evals.capri_comprehensive.evaluators.schema import (
    ExecutionReport,
    ExecutionStatus,
    ScenarioDefinition,
)
from evals.capri_comprehensive.statistical_analysis.metrics import (
    calculate_binomial_summary,
    calculate_latency_summary,
    wilson_score_interval,
)

CSV_COLUMNS_15 = [
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


def derive_target_subsystem(scenario_id: str, group: str) -> str:
    """Map scenario group and ID to target Capri subsystem."""
    sid = scenario_id.upper()
    grp = group.upper()
    if sid.startswith("MEM") or "MEMORY" in grp:
        return "Autobiographical Memory"
    elif sid.startswith("LT") or "CONTINUITY" in grp:
        return "Long-Term Continuity"
    elif sid.startswith("CM") or "CROSS-MODEL" in grp:
        return "Cross-Model Invariance"
    elif sid.startswith("RE") or "REASONING" in grp:
        return "Complex Reasoning"
    elif sid.startswith("SEC") or "SECURITY" in grp:
        return "Security & Adversarial Sandboxing"
    elif sid.startswith("AUT") or "AUTONOMY" in grp:
        return "Autonomy & Initiative"
    elif sid.startswith("INT") or "INTERACTION" in grp:
        return "Human-AI Interaction"
    elif sid.startswith("VOI") or "VOICE" in grp:
        return "Voice & Real-Time"
    elif sid.startswith("REL") or "RELIABILITY" in grp:
        return "Reliability & Fault Tolerance"
    elif sid.startswith("ROB") or "ROBOTICS" in grp:
        return "Embodiment & Robotics"
    elif sid.startswith("JOURNEY") or "JOURNEY" in grp:
        return "Multi-Session Journeys"
    return "General Subsystem"


def derive_default_ablation_sensitivity(
    scenario_id: str, group: str, status: ExecutionStatus
) -> str:
    """Derive sensible baseline ablation sensitivity label for scenario."""
    if status in (ExecutionStatus.BLOCKED_HARDWARE, ExecutionStatus.BLOCKED_DELAY):
        return status.value
    sid = scenario_id.upper()
    grp = group.upper()
    if sid.startswith("MEM") or "MEMORY" in grp:
        return "A1_HIGH"
    elif sid.startswith("LT") or "CONTINUITY" in grp:
        return "A1_MODERATE"
    elif sid.startswith("CM") or "CROSS-MODEL" in grp:
        return "A5_INVARIANT"
    elif sid.startswith("RE") or "REASONING" in grp:
        return "A4_HIGH"
    elif sid.startswith("SEC") or "SECURITY" in grp:
        return "A3_CRITICAL"
    elif sid.startswith("AUT") or "AUTONOMY" in grp:
        return "A3_HIGH"
    elif sid.startswith("INT") or "INTERACTION" in grp:
        return "A5_LOW"
    elif sid.startswith("VOI") or "VOICE" in grp:
        return "A2_MODERATE"
    elif sid.startswith("REL") or "RELIABILITY" in grp:
        return "BASELINE"
    elif sid.startswith("ROB") or "ROBOTICS" in grp:
        return "BLOCKED_HARDWARE"
    elif sid.startswith("JOURNEY") or "JOURNEY" in grp:
        return "A1_HIGH"
    return "BASELINE"


class EvaluationAggregator:
    """Aggregates execution reports across scenarios and groups."""

    def __init__(self, reports: list[ExecutionReport] | None = None):
        self.reports: list[ExecutionReport] = reports or []

    def add_report(self, report: ExecutionReport) -> None:
        self.reports.append(report)

    def write_scenario_matrix_csv(
        self,
        output_path: str | Path,
        scenarios_map: dict[str, ScenarioDefinition] | None = None,
        ablation_sensitivities: dict[str, str] | None = None,
    ) -> Path:
        """Export all scenarios and reports to the mandatory 15-column CAPRI_SCENARIO_MATRIX.csv."""
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        sc_map = scenarios_map or {}
        ablation_map = ablation_sensitivities or {}

        with open(out, "w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS_15)
            writer.writeheader()

            for rep in sorted(self.reports, key=lambda r: r.scenario_id):
                sc = sc_map.get(rep.scenario_id)

                hypothesis = sc.research_hypothesis if sc else "Hypothesis verification"
                target_subsystem = derive_target_subsystem(rep.scenario_id, rep.group)

                # Confidence Interval (Wilson Score on turn success or scenario outcome)
                if rep.status in (ExecutionStatus.BLOCKED_HARDWARE, ExecutionStatus.BLOCKED_DELAY):
                    ci_low, ci_high = 0.0, 0.0
                elif rep.turn_results and len(rep.turn_results) > 0:
                    total_turns = len(rep.turn_results)
                    passed_turns = sum(1 for t in rep.turn_results if t.passed)
                    ci_low, ci_high = wilson_score_interval(
                        passed_turns, total_turns, confidence=0.95
                    )
                else:
                    ci_low, ci_high = (1.0, 1.0) if rep.raw_score >= 1.0 else (0.0, 0.0)

                # Latencies
                if rep.latencies_ms and len(rep.latencies_ms) > 0:
                    p50_lat = round(float(np.percentile(rep.latencies_ms, 50)), 2)
                    p95_lat = round(float(np.percentile(rep.latencies_ms, 95)), 2)
                else:
                    p50_lat = 0.0
                    p95_lat = 0.0

                # Ablation sensitivity
                if rep.scenario_id in ablation_map:
                    ablation_sens = ablation_map[rep.scenario_id]
                else:
                    ablation_sens = derive_default_ablation_sensitivity(
                        rep.scenario_id, rep.group, rep.status
                    )

                # Failure / Blocker reason
                if rep.status in (ExecutionStatus.BLOCKED_HARDWARE, ExecutionStatus.BLOCKED_DELAY):
                    fail_reason = rep.blocker_reason or f"Blocked prerequisite: {rep.status.value}"
                elif rep.status == ExecutionStatus.EXECUTED_FAIL:
                    fails = []
                    for t in rep.turn_results:
                        for a in t.failed_assertions:
                            if a.detail:
                                fails.append(a.detail)
                    fail_reason = "; ".join(fails)[:150] if fails else "Assertions failed"
                else:
                    fail_reason = "None"

                row = {
                    "Scenario_ID": rep.scenario_id,
                    "Group": rep.group,
                    "Name": rep.title,
                    "Taxonomy": rep.taxonomy.value
                    if hasattr(rep.taxonomy, "value")
                    else str(rep.taxonomy),
                    "Severity": rep.severity.value
                    if hasattr(rep.severity, "value")
                    else str(rep.severity),
                    "Target_Subsystem": target_subsystem,
                    "Hypothesis": hypothesis,
                    "Execution_Status": rep.status.value
                    if hasattr(rep.status, "value")
                    else str(rep.status),
                    "Raw_Score": rep.raw_score,
                    "CI_95_Low": round(ci_low, 4),
                    "CI_95_High": round(ci_high, 4),
                    "P50_Latency_ms": p50_lat,
                    "P95_Latency_ms": p95_lat,
                    "Ablation_Sensitivity": ablation_sens,
                    "Failure_Reason": fail_reason,
                }
                writer.writerow(row)

        return out

    def compute_group_statistics(self) -> dict[str, Any]:
        """Compute Wilson score intervals and latency summaries by group."""
        groups: dict[str, list[ExecutionReport]] = {}
        for rep in self.reports:
            groups.setdefault(rep.group, []).append(rep)

        stats: dict[str, Any] = {}
        for grp_name, grp_reports in groups.items():
            total = len(grp_reports)
            executed_passes = sum(
                1 for r in grp_reports if r.status == ExecutionStatus.EXECUTED_PASS
            )
            executed_fails = sum(
                1 for r in grp_reports if r.status == ExecutionStatus.EXECUTED_FAIL
            )
            blocked_hw = sum(1 for r in grp_reports if r.status == ExecutionStatus.BLOCKED_HARDWARE)
            blocked_delay = sum(1 for r in grp_reports if r.status == ExecutionStatus.BLOCKED_DELAY)

            runnable_count = executed_passes + executed_fails
            binom_summary = calculate_binomial_summary(
                successes=executed_passes,
                total=runnable_count if runnable_count > 0 else 0,
            )

            all_lats = []
            for r in grp_reports:
                all_lats.extend(r.latencies_ms)

            lat_summary = calculate_latency_summary(all_lats)

            stats[grp_name] = {
                "total": total,
                "executed_pass": executed_passes,
                "executed_fail": executed_fails,
                "blocked_hardware": blocked_hw,
                "blocked_delay": blocked_delay,
                "pass_rate_runnable": binom_summary["raw_rate"],
                "ci_95_low": binom_summary["ci_low"],
                "ci_95_high": binom_summary["ci_high"],
                "formatted_ci": binom_summary["formatted"],
                "latencies": lat_summary,
            }

        return stats

    def generate_markdown_summary(self, output_path: str | Path | None = None) -> str:
        """Generate a scientific Markdown summary report with tables and confidence intervals."""
        stats = self.compute_group_statistics()
        total_scenarios = len(self.reports)
        total_passes = sum(1 for r in self.reports if r.status == ExecutionStatus.EXECUTED_PASS)
        total_fails = sum(1 for r in self.reports if r.status == ExecutionStatus.EXECUTED_FAIL)
        total_blocked_hw = sum(
            1 for r in self.reports if r.status == ExecutionStatus.BLOCKED_HARDWARE
        )
        total_blocked_delay = sum(
            1 for r in self.reports if r.status == ExecutionStatus.BLOCKED_DELAY
        )

        runnable_total = total_passes + total_fails
        overall_binom = calculate_binomial_summary(
            total_passes, runnable_total if runnable_total > 0 else 0
        )

        lines = [
            "# Capri Comprehensive Evaluation: Statistical Summary",
            "",
            f"**Generated:** {datetime.now(UTC).isoformat()}  ",
            f"**Total Scenarios Evaluated:** {total_scenarios}  ",
            f"**Automated Pass Rate (Runnable):** {overall_binom['formatted']}  ",
            f"**Blocked Hardware:** {total_blocked_hw}  ",
            f"**Blocked Delay (Long-Term):** {total_blocked_delay}  ",
            "",
            "## 1. Group-by-Group Performance & Wilson 95% Confidence Intervals",
            "",
            (
                "| Group | Total | Pass | Fail | Blocked HW | Blocked Delay "
                "| Pass Rate (Wilson 95% CI) | P50 (ms) [95% CI] | P95 (ms) [95% CI] |"
            ),
            "|:---|---:|---:|---:|---:|---:|:---|:---|:---|",
        ]

        for grp_name, st in sorted(stats.items()):
            lats = st["latencies"]
            p50_str = (
                f"{lats['p50']:.1f} [{lats['p50_ci'][0]:.1f}, {lats['p50_ci'][1]:.1f}]"
                if lats["count"] > 0
                else "N/A"
            )
            p95_str = (
                f"{lats['p95']:.1f} [{lats['p95_ci'][0]:.1f}, {lats['p95_ci'][1]:.1f}]"
                if lats["count"] > 0
                else "N/A"
            )
            row_str = (
                f"| {grp_name} | {st['total']} | {st['executed_pass']} | {st['executed_fail']} | "
                f"{st['blocked_hardware']} | {st['blocked_delay']} | {st['formatted_ci']} | "
                f"{p50_str} | {p95_str} |"
            )
            lines.append(row_str)

        lines.extend(
            [
                "",
                "## 2. Four-Tier Scientific Taxonomy Breakdown",
                "",
                "| Taxonomy Category | Scenarios | Executed Pass | Executed Fail | Blocked |",
                "|:---|---:|---:|---:|---:|",
            ]
        )

        taxonomy_counts: dict[str, dict[str, int]] = {}
        for rep in self.reports:
            tax = rep.taxonomy.value if hasattr(rep.taxonomy, "value") else str(rep.taxonomy)
            entry = taxonomy_counts.setdefault(
                tax, {"total": 0, "pass": 0, "fail": 0, "blocked": 0}
            )
            entry["total"] += 1
            if rep.status == ExecutionStatus.EXECUTED_PASS:
                entry["pass"] += 1
            elif rep.status == ExecutionStatus.EXECUTED_FAIL:
                entry["fail"] += 1
            else:
                entry["blocked"] += 1

        for tax, counts in sorted(taxonomy_counts.items()):
            row_tax = (
                f"| `{tax}` | {counts['total']} | {counts['pass']} | "
                f"{counts['fail']} | {counts['blocked']} |"
            )
            lines.append(row_tax)

        content = "\n".join(lines) + "\n"
        if output_path:
            p = Path(output_path)
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(content, encoding="utf-8")

        return content
