"""Run model scenarios through the real B-12 runtime and merge them into the suite.

The original suite answered model scenarios with a raw Ollama call (see
`runtime_executor.py`). This entry point reruns them with `RuntimeTurnExecutor`, so
Capri's actor isolation, consent, persona, recall and tool registry are what is measured.

Host tools touch the real filesystem, so run it only through `runners/sandboxed_suite.sh`,
which refuses to start outside the bubblewrap sandbox.

Usage (from the repository root):
    evals/capri_comprehensive/runners/sandboxed_suite.sh [SCENARIO_ID ...]
    B12_EVAL_VARIANT=deployed evals/capri_comprehensive/runners/sandboxed_suite.sh
The deployed variant (gemma4:12b with semantic recall) writes artifacts/deployed/ and the
*_DEPLOYED report files instead of the main matrix.
"""

from __future__ import annotations

import os
import sys
import tempfile
import time
from pathlib import Path

from evals.capri_comprehensive.evaluators.schema import ExecutionMode, ScenarioDefinition
from evals.capri_comprehensive.runners.live_components import HANDLERS
from evals.capri_comprehensive.runners.run_live_suite import (
    ARTIFACTS,
    SCENARIOS,
    merge_into_suite,
)
from evals.capri_comprehensive.runners.runner import ScenarioRunner
from evals.capri_comprehensive.runners.runtime_executor import RuntimeTurnExecutor

SANDBOX_MARKER = "B12_EVAL_SANDBOX"
VARIANT = os.environ.get("B12_EVAL_VARIANT", "")  # "", "deployed" or "deployed-<model>"


def runtime_scenarios() -> list[ScenarioDefinition]:
    """Scenarios answered by a model and not measured by a live component handler."""
    found = []
    for path in sorted(SCENARIOS.glob("*/*.yaml")):
        sc = ScenarioDefinition.from_yaml_file(path)
        if sc.id in HANDLERS or sc.pre_conditions.runtime_settings.model == "none":
            continue
        if sc.execution_mode in (ExecutionMode.BLOCKED_HARDWARE, ExecutionMode.BLOCKED_DELAY):
            continue
        found.append(sc)
    return found


def main(ids: list[str]) -> None:
    if os.environ.get(SANDBOX_MARKER) != "1":
        raise SystemExit("refusing to run host tools outside the sandbox: use sandboxed_suite.sh")
    chosen = runtime_scenarios()
    if ids:
        known = {sc.id for sc in chosen}
        unknown = [i for i in ids if i not in known]
        if unknown:
            raise SystemExit(f"not a runtime scenario: {unknown}")
        chosen = [sc for sc in chosen if sc.id in ids]
    base = Path(tempfile.mkdtemp(prefix="b12-runtime-suite-"))
    artifacts = ARTIFACTS / VARIANT if VARIANT else ARTIFACTS
    runner = ScenarioRunner(
        artifacts_dir=artifacts, turn_executor=RuntimeTurnExecutor(base, variant=VARIANT)
    )
    reports = {}
    for i, sc in enumerate(chosen, 1):
        t0 = time.monotonic()
        report = runner.run(sc)
        reports[sc.id] = report
        verdict = "PASS" if report.all_passed else "FAIL"
        print(f"[{i}/{len(chosen)}] {sc.id} {verdict} ({time.monotonic() - t0:.1f}s)", flush=True)
    merge_into_suite(reports, VARIANT)


if __name__ == "__main__":
    main(sys.argv[1:])
