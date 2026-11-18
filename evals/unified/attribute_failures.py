"""Separate model failures from framework failures on one frozen set (owner, 18.11.2026).

Input: one `analyze_pilot` result per model, all run in the same runtime on the same set.
A family "passes" for a model when its acceptable rate is at least 0.5. Per family:

- `model`: the reference model (Bolt) fails and at least one other model passes — the runtime
  gave enough to succeed, so the failure belongs to the model;
- `framework_or_scenario`: every model fails — look at the runtime, the scenario or the oracle;
- `all_pass`: every model passes;
- `reference_only_pass`: the reference passes and every other model fails.

Independently, a family is tagged `info_absent` when a required memory record carried clock or
validity metadata that the runtime does not store (the adapter's dropped fields): no model can
use information that never reaches its context.
"""

import json
from collections import Counter
from pathlib import Path

DROPPED_MATTERS = {"event_time", "valid_from", "valid_to", "reliability", "source_locator"}


def info_absent(manifest, root):
    """Families whose required memory evidence has metadata the runtime drops."""
    tagged = {}
    for row in json.loads(Path(manifest).read_text(encoding="utf-8"))["scenarios"]:
        setup = json.loads((Path(root) / row["setup_fixture"]).read_text(encoding="utf-8"))
        oracle = json.loads((Path(root) / row["oracle_fixture"]).read_text(encoding="utf-8"))
        required = {
            e.split(":", 1)[1] for e in oracle["required_evidence_ids"] if e.startswith("mem:")
        }
        for record in setup["harness_setup"].get("synthetic_memory", []):
            if record["memory_id"] not in required:
                continue
            lost = sorted(k for k in DROPPED_MATTERS if record.get(k))
            if lost:
                tagged.setdefault(row["family_id"], set()).update(lost)
    return {family: sorted(fields) for family, fields in tagged.items()}


def attribute(analyses, reference, absent=None, threshold=0.5):
    """analyses: {model: analyze_pilot result}; reference: the local model's name."""
    absent = absent or {}
    families = sorted(set.intersection(*(set(a["families"]) for a in analyses.values())))
    rows = []
    for family in families:
        rates = {m: a["families"][family]["acceptable_rate"] for m, a in analyses.items()}
        passed = {m: r is not None and r >= threshold for m, r in rates.items()}
        others = [m for m in analyses if m != reference]
        if all(passed.values()):
            cls = "all_pass"
        elif not any(passed.values()):
            cls = "framework_or_scenario"
        elif not passed[reference] and any(passed[m] for m in others):
            cls = "model"
        elif passed[reference] and not any(passed[m] for m in others):
            cls = "reference_only_pass"
        else:
            cls = "mixed"
        rows.append(
            {
                "family": family,
                "track": analyses[reference]["families"][family]["track"],
                "class": cls,
                "rates": rates,
                "info_absent": absent.get(family, []),
            }
        )
    summary = Counter((r["track"], r["class"]) for r in rows)
    return {
        "reference": reference,
        "threshold": threshold,
        "families": rows,
        "summary": {f"{t}/{c}": n for (t, c), n in sorted(summary.items())},
    }


def main(argv=None):
    import argparse

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--reference", required=True)
    parser.add_argument("--model", action="append", required=True, help="name=analysis.json")
    args = parser.parse_args(argv)
    analyses = {}
    for item in args.model:
        name, path = item.split("=", 1)
        analyses[name] = json.loads(Path(path).read_text(encoding="utf-8"))
    result = attribute(analyses, args.reference, info_absent(args.manifest, Path.cwd()))
    print(json.dumps(result, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
