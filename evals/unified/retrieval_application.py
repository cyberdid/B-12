"""U3 exit: retrieval and application measured separately on the memory track.

Retrieval holds when every `mem:` id the oracle requires is among the record's evidence ids
(the memory records the runtime put in front of the model). Application is the final verdict
(aligned semantic verdict, or the deterministic FAIL) of the records where retrieval held. A
record whose oracle requires no memory id counts only towards application (abstention and
privacy families).

    python -m evals.unified.retrieval_application <manifest> <verdicts_dir> name=<run_dir> ...
"""

import json
import sys
from collections import Counter
from pathlib import Path

from evals.unified.analyze_pilot import HARNESS_INVALID, load, outcome
from evals.unified.score_u2_u3 import score


def measure(rows, records, semantic):
    family = {r["scenario_id"]: (r["family_id"], r["track"]) for r in rows}
    tally = Counter()
    for (repeat, sid), (record, oracle) in records.items():
        fam, track = family[sid]
        if track != "memory" or fam in HARNESS_INVALID:
            continue
        needed = [
            i.split(":", 1)[1] for i in oracle["required_evidence_ids"] if i.startswith("mem:")
        ]
        result = outcome(score(record, oracle)["verdict"], semantic.get((repeat, sid)))
        if not needed:
            tally["no_retrieval_needed"] += 1
            tally[f"no_retrieval_needed_{result}"] += 1
            continue
        tally["retrieval_needed"] += 1
        if all(i in record.get("evidence_ids", []) for i in needed):
            tally["retrieved"] += 1
            tally[f"retrieved_{result}"] += 1
        else:
            tally[f"missed_{result}"] += 1
    need, got = tally["retrieval_needed"], tally["retrieved"]
    return {
        "retrieval_rate": round(got / need, 3) if need else None,
        "application_rate_given_retrieval": round(tally["retrieved_pass"] / got, 3)
        if got
        else None,
        "application_partial_given_retrieval": round(tally["retrieved_partial"] / got, 3)
        if got
        else None,
        "no_retrieval_families_pass_rate": round(
            tally["no_retrieval_needed_pass"] / tally["no_retrieval_needed"], 3
        )
        if tally["no_retrieval_needed"]
        else None,
        "counts": dict(sorted(tally.items())),
    }


def main(argv=None):
    argv = argv if argv is not None else sys.argv[1:]
    manifest, verdicts = argv[0], Path(argv[1])
    out = {}
    for arg in argv[2:]:
        name, run_dir = arg.split("=", 1)
        rows, records = load(manifest, run_dir, Path.cwd())
        raw = json.loads((verdicts / f"semantic_{name}.json").read_text(encoding="utf-8"))
        out[name] = measure(rows, records, {tuple(k.split("/", 1)): v for k, v in raw.items()})
        m = out[name]
        print(
            f"{name:6} retrieval {m['retrieval_rate']} | application|retrieved "
            f"{m['application_rate_given_retrieval']}"
            f" (+partial {m['application_partial_given_retrieval']})"
            f" | no-retrieval families {m['no_retrieval_families_pass_rate']}"
        )
    (verdicts / "retrieval_application.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    main()
