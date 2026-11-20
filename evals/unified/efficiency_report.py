"""Efficiency of a run from its own records: how much work the runtime did per scenario.

    python -m evals.unified.efficiency_report <run_dir> [<run_dir> ...] [--json out.json]

Quality reports say whether an answer was right; this one says what it cost. Per run (all
repeats pooled): records, tool calls per record, failed tool calls, policy denials, repeated
identical calls inside one record, unfinished turns (runtime_state other than completed),
prompt/completion tokens and TTFT (median and P95). Everything comes from the trace fields the
runner already writes, never from the model's own report. Idea from Hermes Agent's toolperf
A/B harness ("scoring from traces, not self-report").
"""

from __future__ import annotations

import argparse
import json
import statistics
from collections import Counter
from pathlib import Path


def _pct(values: list[float], q: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, round(q * (len(ordered) - 1))))
    return ordered[index]


def _median(values: list[float]) -> float | None:
    return statistics.median(values) if values else None


def _records(run_dir: Path) -> list[dict]:
    out = []
    for path in sorted(run_dir.glob("r*/*.json")) or sorted(run_dir.glob("*.json")):
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if isinstance(record, dict) and "scenario_id" in record:
            out.append(record)
    return out


def summarize(records: list[dict]) -> dict:
    executed = [r for r in records if r.get("status") == "EXECUTED"]
    calls_per = [len(r.get("tool_calls") or []) for r in executed]
    failed = repeated = denied = 0
    for record in executed:
        calls = record.get("tool_calls") or []
        failed += sum(
            1 for c in calls if c.get("status") not in (None, "completed") or c.get("error_code")
        )
        keys = Counter(
            json.dumps([c.get("name"), c.get("arguments")], sort_keys=True, ensure_ascii=False)
            for c in calls
        )
        repeated += sum(n - 1 for n in keys.values() if n > 1)
        denied += sum(
            1 for d in record.get("policy_decisions") or [] if d.get("decision") == "denied"
        )
    unfinished = Counter(
        r.get("runtime_state") for r in executed if r.get("runtime_state") != "completed"
    )
    prompt = [r["tokens_prompt"] for r in executed if isinstance(r.get("tokens_prompt"), int)]
    completion = [
        r["tokens_completion"] for r in executed if isinstance(r.get("tokens_completion"), int)
    ]
    ttft = [r["ttft_ms"] for r in executed if isinstance(r.get("ttft_ms"), (int, float))]
    total_calls = sum(calls_per)
    return {
        "records": len(records),
        "executed": len(executed),
        "not_executed": dict(Counter(r.get("status") for r in records if r not in executed)),
        "tool_calls_total": total_calls,
        "tool_calls_per_record_mean": round(total_calls / len(executed), 3) if executed else None,
        "records_with_tool_calls": sum(1 for n in calls_per if n),
        "failed_tool_calls": failed,
        "repeated_identical_calls": repeated,
        "policy_denials": denied,
        "unfinished_turns": dict(unfinished),
        "prompt_tokens_median": _median(prompt),
        "prompt_tokens_p95": _pct(prompt, 0.95),
        "completion_tokens_median": _median(completion),
        "completion_tokens_p95": _pct(completion, 0.95),
        "ttft_ms_median": _median(ttft),
        "ttft_ms_p95": _pct(ttft, 0.95),
    }


def _fmt(value) -> str:
    if value is None:
        return "—"
    if isinstance(value, float):
        return f"{value:.1f}" if value >= 10 else f"{value:.2f}"
    if isinstance(value, dict):
        return ", ".join(f"{k}={v}" for k, v in sorted(value.items(), key=str)) or "0"
    return str(value)


COLUMNS = (
    ("executed", "записів"),
    ("tool_calls_per_record_mean", "викликів/запис"),
    ("failed_tool_calls", "невдалі виклики"),
    ("repeated_identical_calls", "повтори"),
    ("policy_denials", "відмови політики"),
    ("unfinished_turns", "незавершені ходи"),
    ("prompt_tokens_median", "prompt tok P50"),
    ("completion_tokens_median", "completion tok P50"),
    ("ttft_ms_median", "TTFT P50, мс"),
    ("ttft_ms_p95", "TTFT P95, мс"),
)


def markdown(rows: dict[str, dict]) -> str:
    head = "| Прогін | " + " | ".join(label for _, label in COLUMNS) + " |"
    sep = "|---" * (len(COLUMNS) + 1) + "|"
    body = [
        f"| {name} | " + " | ".join(_fmt(row[key]) for key, _ in COLUMNS) + " |"
        for name, row in rows.items()
    ]
    return "\n".join([head, sep, *body])


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("runs", nargs="+", type=Path)
    parser.add_argument("--json", type=Path)
    args = parser.parse_args(argv)
    rows = {run.name: summarize(_records(run)) for run in args.runs}
    print(markdown(rows))
    if args.json:
        args.json.write_text(json.dumps(rows, ensure_ascii=False, indent=1) + "\n", "utf-8")


if __name__ == "__main__":
    main()
