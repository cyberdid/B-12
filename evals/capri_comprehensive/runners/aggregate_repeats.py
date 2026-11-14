"""Aggregate repeated suite runs: per-scenario pass counts and run-to-run variance.

Reads reports/repeats[/<variant>]/runK/batch_summary*.json written by repeat_suite.sh and
prints a Markdown summary (also written to REPEATS_SUMMARY[_<VARIANT>].md beside them).

Usage: python -m evals.capri_comprehensive.runners.aggregate_repeats [variant]
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

REPORTS = Path(__file__).resolve().parents[1] / "reports"


def wilson(passed: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if not n:
        return 0.0, 0.0
    p = passed / n
    centre = (p + z * z / (2 * n)) / (1 + z * z / n)
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return centre - half, centre + half


def load(variant: str) -> tuple[Path, list[dict[str, str]]]:
    base = REPORTS / "repeats" / variant if variant else REPORTS / "repeats"
    runs = []
    for run_dir in sorted(base.glob("run*")):
        batch = next(run_dir.glob("batch_summary*.json"), None)
        if batch is None:
            continue
        reports = json.loads(batch.read_text(encoding="utf-8"))["reports"]
        runs.append({r["scenario_id"]: r["status"].removeprefix("EXECUTED_") for r in reports})
    return base, runs


def summarize(variant: str = "") -> str:
    base, runs = load(variant)
    if not runs:
        raise SystemExit(f"no runs under {base}")
    ids = sorted(set().union(*runs))
    runnable = [i for i in ids if all(r.get(i) in ("PASS", "FAIL") for r in runs)]
    counts = {i: sum(r[i] == "PASS" for r in runs) for i in runnable}
    n = len(runs)
    per_run = [sum(r[i] == "PASS" for i in runnable) for r in runs]
    stable_pass = [i for i in runnable if counts[i] == n]
    stable_fail = [i for i in runnable if counts[i] == 0]
    flaky = [i for i in runnable if 0 < counts[i] < n]
    total = sum(per_run)
    cases = n * len(runnable)
    lo, hi = wilson(total, cases)
    mean = total / n
    sd = math.sqrt(sum((x - mean) ** 2 for x in per_run) / (n - 1)) if n > 1 else 0.0
    lines = [
        f"# Repeated runs{f' — {variant}' if variant else ''}",
        "",
        f"- Runs: {n}; runnable scenarios per run: {len(runnable)}",
        f"- Passed per run: {', '.join(map(str, per_run))} (mean {mean:.1f}, SD {sd:.1f})",
        f"- Pooled pass rate: {total}/{cases} = {100 * total / cases:.1f}% "
        f"(Wilson 95% CI {100 * lo:.1f}–{100 * hi:.1f}%; runs are not independent samples "
        "of scenarios, so this interval understates scenario-level uncertainty)",
        f"- Stable pass ({n}/{n}): {len(stable_pass)}; stable fail (0/{n}): {len(stable_fail)}; "
        f"flaky: {len(flaky)}",
        "",
        "## Flaky scenarios",
        "",
        "| Scenario | Passed |",
        "|:---|---:|",
        *[f"| {i} | {counts[i]}/{n} |" for i in flaky],
        "",
        f"## Stable fail (0/{n})",
        "",
        ", ".join(stable_fail) or "—",
        "",
    ]
    text = "\n".join(lines)
    name = f"REPEATS_SUMMARY{f'_{variant.upper()}' if variant else ''}.md"
    (base / name).write_text(text, encoding="utf-8")
    return text


if __name__ == "__main__":
    print(summarize(sys.argv[1] if len(sys.argv) > 1 else ""))
