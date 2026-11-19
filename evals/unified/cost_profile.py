"""Latency/cost profile per arm (U2 deliverable): TTFT P50/P95, completion tokens, tool calls
and reply length per record, over the runnable non-harness-invalid families.

    python -m evals.unified.cost_profile <out_json> name=<run_dir> ...
"""

import json
import sys
from pathlib import Path
from statistics import mean, quantiles

from evals.unified.analyze_pilot import HARNESS_INVALID


def _p(values, q):
    values = sorted(v for v in values if v is not None)
    if len(values) < 2:
        return values[0] if values else None
    return round(quantiles(values, n=100, method="inclusive")[q - 1], 1)


def profile(run_dir):
    rows = []
    for path in sorted(Path(run_dir).glob("r*/*.json")):
        record = json.loads(path.read_text(encoding="utf-8"))
        if record.get("status") != "EXECUTED" or record["family_id"] in HARNESS_INVALID:
            continue
        rows.append(record)
    return {
        "records": len(rows),
        "ttft_ms_p50": _p([r.get("ttft_ms") for r in rows], 50),
        "ttft_ms_p95": _p([r.get("ttft_ms") for r in rows], 95),
        "completion_tokens_mean": round(mean(r.get("tokens_completion", 0) for r in rows), 1),
        "tool_calls_mean": round(mean(len(r["tool_calls"]) for r in rows), 2),
        "reply_chars_p50": _p([len(r["reply"]) for r in rows], 50),
        "reply_chars_p95": _p([len(r["reply"]) for r in rows], 95),
    }


def main(argv=None):
    argv = argv if argv is not None else sys.argv[1:]
    out = {name: profile(d) for name, d in (a.split("=", 1) for a in argv[1:])}
    Path(argv[0]).write_text(json.dumps(out, indent=1) + "\n", encoding="utf-8")
    for name, p in out.items():
        print(name, p)


if __name__ == "__main__":
    main()
