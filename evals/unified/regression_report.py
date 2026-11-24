"""Deterministic report of a regression run, optionally against a baseline run.

    .venv/bin/python -m evals.unified.regression_report <run_dir> [--baseline <run_dir>]

A scenario regresses when its turn failed, its deterministic verdict is FAIL, or it repeats
identical tool calls more than the baseline did. Semantic criteria need judges and are not
read here. Exit code 1 when anything regressed.
"""

from __future__ import annotations

import argparse
import collections
import json
import sys
from pathlib import Path

from evals.unified.score_u2_u3 import score

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "evals/unified/scenario_sets/regression-gemma-v1.json"


def _records(run_dir: Path) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = collections.defaultdict(list)
    for path in sorted(Path(run_dir).glob("r*/*.json")):
        record = json.loads(path.read_text(encoding="utf-8"))
        out[record["scenario_id"]].append(record)
    return out


def _repeats(record: dict) -> int:
    keys = collections.Counter(
        json.dumps([c.get("name"), c.get("arguments")], sort_keys=True, ensure_ascii=False)
        for c in record.get("tool_calls") or []
    )
    return sum(n - 1 for n in keys.values() if n > 1)


def _outcome(record: dict, oracle: dict) -> str:
    if record.get("runtime_state") not in ("completed", "awaiting_approval"):
        return f"RUN_FAILED:{record.get('error_code')}"
    return score(record, oracle)["verdict"]


def summarize(run_dir: Path, rows: dict, root: Path) -> dict[str, dict]:
    result = {}
    for scenario_id, records in _records(run_dir).items():
        row = rows.get(scenario_id)
        if row is None:
            continue
        oracle = json.loads((root / row["oracle_fixture"]).read_text(encoding="utf-8"))
        outcomes = [_outcome(r, oracle) for r in records]
        bad = [o for o in outcomes if o.startswith("RUN_FAILED") or o == "FAIL"]
        result[scenario_id] = {
            "scenario_id": scenario_id,
            "outcome": bad[0] if bad else outcomes[0],
            "repeats": max(_repeats(r) for r in records),
            "failed": bool(bad),
        }
    return result


def run_gpu(run_dir: Path) -> str | None:
    """The Colab GPU the orchestrator recorded for a run (pilot.log `gpu=` line)."""
    try:
        lines = (Path(run_dir) / "pilot.log").read_text(encoding="utf-8").splitlines()
    except OSError:
        return None
    found = [line.split("gpu=", 1)[1].split()[0] for line in lines if "gpu=" in line]
    return found[-1] if found else None


def compare(manifest: Path, run_dir: Path, baseline: Path | None, root: Path = ROOT):
    rows = {r["scenario_id"]: r for r in json.loads(Path(manifest).read_text())["scenarios"]}
    now = summarize(run_dir, rows, root)
    before = summarize(baseline, rows, root) if baseline else {}
    regressions = []
    for scenario_id, item in sorted(now.items()):
        old = before.get(scenario_id)
        if item["failed"] and not (old and old["failed"]):
            regressions.append(item)
        elif old and item["repeats"] > old["repeats"]:
            regressions.append(item)
    return [now[k] for k in sorted(now)], regressions


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("run_dir", type=Path)
    parser.add_argument("--baseline", type=Path, default=None)
    parser.add_argument("--manifest", type=Path, default=MANIFEST)
    args = parser.parse_args(argv)
    rows, regressions = compare(args.manifest, args.run_dir, args.baseline)
    if args.baseline is not None:
        now_gpu, base_gpu = run_gpu(args.run_dir), run_gpu(args.baseline)
        if now_gpu != base_gpu:
            print(
                f"WARNING: GPU differs (run {now_gpu}, baseline {base_gpu}); gemma's output can "
                "change with the GPU — compare runs on the same GPU"
            )
    flagged = {r["scenario_id"] for r in regressions}
    for row in rows:
        mark = "REGRESSION" if row["scenario_id"] in flagged else "ok"
        print(f"{row['scenario_id']:10} {row['outcome']:28} repeats={row['repeats']:<3} {mark}")
    print(f"{len(rows)} scenarios, {len(regressions)} regressions")
    return 1 if regressions else 0


if __name__ == "__main__":
    sys.exit(main())
