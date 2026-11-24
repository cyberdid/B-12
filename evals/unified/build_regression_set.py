"""Build `regression-gemma-v1`: a standing ~20-scenario set run on gemma after runtime changes.

Owner, 24.11.2026: run a small fixed set after every runtime change so regressions surface at
once (Claude's own `think` admission regression was found only by chance). Rows are copied
unchanged from frozen sets, so their oracles and reviews still apply.

    .venv/bin/python -m evals.unified.build_regression_set
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SETS = ROOT / "evals/unified/scenario_sets"
OUT = SETS / "regression-gemma-v1.json"

# family -> (source set, why it is here)
FAMILIES = {
    "C39": ("u2-u3-locked-v2", "context_mismatch after the reasoning retry (fixed 71ed1c2)"),
    "C58": ("u2-u3-locked-v2", "identical-call loop until context_overflow (fixed 738e3ee)"),
    "M94": ("ports-live-v1", "post-turn memory review records a stated fact"),
    "M100": ("convrecall-live-v1", "recall from an earlier conversation"),
    "M102": ("convrecall-live-v1", "no invented past conversation"),
    "M103": ("flags-live-v1", "recent fact wins over older notes (memory_ranking)"),
    "M107": ("flags-live-v2", "standing intent; reply cut at the output cap (fixed 5b640de)"),
    "M108": ("flags-live-v2", "skill_view; empty reply after hidden reasoning (fixed d82556c)"),
    "M115": ("skills-learn-v2", "background skill review proposes a learned procedure"),
    "M118": ("skills-learn-v2", "web-tainted turn is not learned"),
}


def build() -> dict:
    rows = []
    for family, (set_id, _why) in FAMILIES.items():
        source = json.loads((SETS / f"{set_id}.json").read_text(encoding="utf-8"))
        picked = [r for r in source["scenarios"] if r["family_id"] == family]
        if not picked:
            raise ValueError(f"{family} not in {set_id}")
        rows.extend(picked)
    return {
        "schema_version": 2,
        "set_id": "regression-gemma-v1",
        "note": "Standing regression set (owner, 24.11.2026); rows copied unchanged from frozen "
        "sets: " + "; ".join(f"{f} ({s}): {why}" for f, (s, why) in FAMILIES.items()),
        "scenarios": rows,
    }


def main() -> None:
    OUT.write_text(json.dumps(build(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
