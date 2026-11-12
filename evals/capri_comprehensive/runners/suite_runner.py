"""Batch Suite Runner for Capri Comprehensive Evaluation.

Executes multiple scenario files across Groups A–K:
- Supports sequential and parallel execution (using isolated disposable sandboxes).
- Discovers scenarios by group, taxonomy, or path glob.
- Provides real-time console progress.
- Outputs structured JSON batch reports and standard JUnit XML for CI/CD integration.
"""

from __future__ import annotations

import argparse
import json
import logging
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime
from pathlib import Path

from evals.capri_comprehensive.evaluators.schema import (
    ExecutionMode,
    ExecutionReport,
    ExecutionStatus,
    ScenarioDefinition,
    ScenarioSeverity,
    ScientificTaxonomy,
)
from evals.capri_comprehensive.runners.runner import ScenarioRunner

logger = logging.getLogger("evals.suite_runner")


class SuiteRunner:
    """Orchestrates batch execution of Capri evaluation scenarios."""

    def __init__(
        self,
        scenarios_dir: str | Path | None = None,
        artifacts_dir: str | Path | None = None,
        reports_dir: str | Path | None = None,
        scenario_runner: ScenarioRunner | None = None,
    ):
        base_dir = Path(__file__).resolve().parent.parent
        self.scenarios_dir = Path(scenarios_dir) if scenarios_dir else base_dir / "scenarios"
        self.artifacts_dir = Path(artifacts_dir) if artifacts_dir else base_dir / "artifacts"
        self.reports_dir = Path(reports_dir) if reports_dir else base_dir / "reports"
        self.scenario_runner = scenario_runner or ScenarioRunner(artifacts_dir=self.artifacts_dir)

    def discover_scenarios(
        self,
        group_filter: list[str] | None = None,
        taxonomy_filter: list[str] | None = None,
    ) -> list[Path]:
        """Discover scenario YAML files matching filter criteria."""
        if not self.scenarios_dir.exists():
            return []

        all_yamls = sorted(self.scenarios_dir.glob("**/*.yaml")) + sorted(
            self.scenarios_dir.glob("**/*.yml")
        )
        matching: list[Path] = []

        for p in all_yamls:
            if group_filter:
                rel_parts = p.relative_to(self.scenarios_dir).parts
                if not any(g.lower() in [part.lower() for part in rel_parts] for g in group_filter):
                    continue

            if taxonomy_filter:
                try:
                    sc = ScenarioDefinition.from_yaml_file(p)
                    if sc.taxonomy.value not in taxonomy_filter:
                        continue
                except Exception:
                    continue

            matching.append(p)

        return matching

    def run_suite(
        self,
        scenario_paths: list[Path] | None = None,
        parallel: bool = False,
        max_workers: int = 4,
    ) -> list[ExecutionReport]:
        """Execute a batch of scenarios and collect reports."""
        paths = scenario_paths if scenario_paths is not None else self.discover_scenarios()
        reports: list[ExecutionReport] = []
        total = len(paths)

        print("============================================================")
        print(f"Capri Comprehensive Evaluation Suite: {total} Scenarios")
        print(f"Parallel: {parallel} (Workers: {max_workers if parallel else 1})")
        print(f"Started at: {datetime.now(UTC).isoformat()}")
        print("============================================================")

        if not paths:
            print("No scenarios found to execute.")
            return []

        if parallel and max_workers > 1:
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                future_to_path = {executor.submit(self._run_single, p): p for p in paths}
                for i, future in enumerate(as_completed(future_to_path), 1):
                    p = future_to_path[future]
                    try:
                        rep = future.result()
                        reports.append(rep)
                        self._print_progress(i, total, rep)
                    except Exception as e:
                        logger.error("Error executing %s: %s", p, e)
        else:
            for i, p in enumerate(paths, 1):
                rep = self._run_single(p)
                reports.append(rep)
                self._print_progress(i, total, rep)

        # Sort reports by scenario_id
        reports.sort(key=lambda r: r.scenario_id)
        return reports

    def _run_single(self, path: Path) -> ExecutionReport:
        try:
            return self.scenario_runner.run(path)
        except Exception as e:
            logger.error("Unhandled error running scenario %s: %s", path, e, exc_info=True)
            return ExecutionReport(
                scenario_id=path.stem,
                group="Unknown",
                title=f"Execution Failure: {path.name}",
                taxonomy=ScientificTaxonomy.DETERMINISTIC_SOFTWARE,
                severity=ScenarioSeverity.HIGH,
                execution_mode=ExecutionMode.AUTOMATED_IMMEDIATE,
                status=ExecutionStatus.EXECUTED_FAIL,
                all_passed=False,
                blocker_reason=f"Unhandled exception during execution: {e}",
                started_at=datetime.now(UTC).isoformat(),
                completed_at=datetime.now(UTC).isoformat(),
                raw_score=0.0,
            )

    def _print_progress(self, index: int, total: int, rep: ExecutionReport) -> None:
        status_color = {
            ExecutionStatus.EXECUTED_PASS: "\033[92mPASS\033[0m",
            ExecutionStatus.EXECUTED_FAIL: "\033[91mFAIL\033[0m",
            ExecutionStatus.BLOCKED_HARDWARE: "\033[93mBLOCKED_HARDWARE\033[0m",
            ExecutionStatus.BLOCKED_DELAY: "\033[94mBLOCKED_DELAY\033[0m",
        }.get(rep.status, rep.status.value)

        duration = sum(rep.latencies_ms)
        title_clip = rep.title[:35]
        print(
            f"[{index}/{total}] {rep.scenario_id:<10} | {status_color:<26} | "
            f"{duration:6.1f}ms | {title_clip}"
        )

    def generate_junit_xml(self, reports: list[ExecutionReport], output_path: str | Path) -> Path:
        """Generate JUnit-compatible XML test report."""
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)

        total_tests = len(reports)
        total_failures = sum(1 for r in reports if r.status == ExecutionStatus.EXECUTED_FAIL)
        total_skipped = sum(
            1
            for r in reports
            if r.status
            in (
                ExecutionStatus.BLOCKED_HARDWARE,
                ExecutionStatus.BLOCKED_DELAY,
                ExecutionStatus.SKIPPED,
            )
        )
        total_time = sum(sum(r.latencies_ms) for r in reports) / 1000.0

        testsuite = ET.Element(
            "testsuite",
            name="capri_comprehensive_suite",
            tests=str(total_tests),
            failures=str(total_failures),
            skipped=str(total_skipped),
            time=f"{total_time:.3f}",
            timestamp=datetime.now(UTC).isoformat(),
        )

        for rep in reports:
            case_time = sum(rep.latencies_ms) / 1000.0
            testcase = ET.SubElement(
                testsuite,
                "testcase",
                classname=rep.group,
                name=f"{rep.scenario_id}: {rep.title}",
                time=f"{case_time:.3f}",
            )

            if rep.status == ExecutionStatus.EXECUTED_FAIL:
                failure = ET.SubElement(testcase, "failure", message="Scenario assertions failed")
                fail_details = []
                for turn in rep.turn_results:
                    for f in turn.failed_assertions:
                        fail_details.append(f"Turn {turn.turn_index}: {f.rule_type} - {f.detail}")
                failure.text = "\n".join(fail_details)

            elif rep.status in (
                ExecutionStatus.BLOCKED_HARDWARE,
                ExecutionStatus.BLOCKED_DELAY,
                ExecutionStatus.SKIPPED,
            ):
                skipped = ET.SubElement(
                    testcase, "skipped", message=rep.blocker_reason or rep.status.value
                )
                skipped.text = rep.blocker_reason or ""

        tree = ET.ElementTree(testsuite)
        tree.write(out, encoding="utf-8", xml_declaration=True)
        return out

    def generate_json_summary(
        self, reports: list[ExecutionReport], output_path: str | Path
    ) -> Path:
        """Generate structured JSON summary of suite execution."""
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)

        summary_data = {
            "timestamp": datetime.now(UTC).isoformat(),
            "total_scenarios": len(reports),
            "passed": sum(1 for r in reports if r.status == ExecutionStatus.EXECUTED_PASS),
            "failed": sum(1 for r in reports if r.status == ExecutionStatus.EXECUTED_FAIL),
            "blocked_hardware": sum(
                1 for r in reports if r.status == ExecutionStatus.BLOCKED_HARDWARE
            ),
            "blocked_delay": sum(1 for r in reports if r.status == ExecutionStatus.BLOCKED_DELAY),
            "reports": [r.model_dump(mode="json") for r in reports],
        }

        with open(out, "w", encoding="utf-8") as f:
            json.dump(summary_data, f, indent=2, ensure_ascii=False)
        return out


def main() -> None:
    parser = argparse.ArgumentParser(description="Capri Comprehensive Evaluation Suite Runner")
    parser.add_argument(
        "--group", "-g", action="append", help="Filter scenarios by group directory"
    )
    parser.add_argument("--parallel", action="store_true", help="Run scenarios in parallel")
    parser.add_argument("--workers", type=int, default=4, help="Number of worker threads")
    parser.add_argument("--junit", default=None, help="Output path for JUnit XML")
    parser.add_argument("--json", default=None, help="Output path for JSON summary")
    parser.add_argument(
        "--scenarios-dir", default=None, help="Directory containing scenario YAML files"
    )
    args = parser.parse_args()

    suite = SuiteRunner(scenarios_dir=args.scenarios_dir)
    paths = suite.discover_scenarios(group_filter=args.group)
    reports = suite.run_suite(paths, parallel=args.parallel, max_workers=args.workers)

    if args.junit:
        suite.generate_junit_xml(reports, args.junit)
    if args.json:
        suite.generate_json_summary(reports, args.json)


if __name__ == "__main__":
    main()
