"""Combine blind judge labels for one run, apply adjudication, write the semantic verdicts.

    python -m evals.unified.combine_judges <sheet.json> <out_dir> \
        --labels codex=a.json[,b.json] --labels agy=c.json[,d.json] [--adjudication adj.json]

Label files may be raw judge outputs ({"labels": [...]}, or an agy result with
"structured_output") or saved label files. A judge sometimes copies an item id with the wrong
hash suffix; such a label is mapped to the only unlabelled item with the same scenario and
criterion, and every correction is recorded. Without --adjudication the disputes are printed
for a human. The adjudication file maps a family (e.g. "C39") to [verdict, reason]; the
verdict replaces every item of that family that has a disputed criterion (the adjudicator
judges the whole reply).
"""

import argparse
import collections
import json
from pathlib import Path

from evals.unified.judge_sheet import combine, expand


def load_labels(path):
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if isinstance(data.get("structured_output"), dict):
        data = data["structured_output"]
    return data["labels"]


def repair_ids(sheet, labels):
    criteria = {s["item_id"]: set(s["criteria"]) for s in sheet}
    labelled = collections.defaultdict(set)
    for label in labels:
        if label["item_id"] in criteria:
            labelled[label["item_id"]].add(label["criterion"])
    unlabelled = [item for item in criteria if not labelled[item]]
    fixes = set()
    for label in labels:
        if label["item_id"] in criteria:
            continue
        prefix = label["item_id"].split("#")[0] + "#"
        candidates = [
            item
            for item in unlabelled
            if item.startswith(prefix) and label["criterion"] in criteria[item]
        ]
        if len(candidates) != 1:
            raise ValueError(f"cannot map {label['item_id']}: {candidates}")
        fixes.add((label["item_id"], candidates[0]))
        label["item_id"] = candidates[0]
    return sorted(fixes)


def finalize(sheet, labels_by_judge, adjudication=None):
    corrections = {judge: repair_ids(sheet, labels) for judge, labels in labels_by_judge.items()}
    result = combine(sheet, labels_by_judge)
    result["item_id_corrections"] = {k: v for k, v in corrections.items() if v}
    final = dict(result["verdicts"])
    if adjudication is not None:
        adjudicated = []
        for item in sorted({d["item_id"] for d in result["disputed"]}):
            family = item[:3]
            if family not in adjudication:
                raise ValueError(f"no adjudication for disputed family {family}")
            verdict, reason = adjudication[family]
            adjudicated.append(
                {"item_id": item, "before": final[item], "verdict": verdict, "by": reason}
            )
            final[item] = verdict
        result["adjudicated"] = adjudicated
    result["final_verdicts"] = final
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("sheet", type=Path)
    parser.add_argument("out_dir", type=Path)
    parser.add_argument("--labels", action="append", required=True, help="judge=path[,path]")
    parser.add_argument("--adjudication", type=Path)
    args = parser.parse_args(argv)
    sheet = json.loads(args.sheet.read_text(encoding="utf-8"))
    labels = {}
    for spec in args.labels:
        judge, paths = spec.split("=", 1)
        labels[judge] = [x for path in paths.split(",") for x in load_labels(path)]
    adjudication = (
        json.loads(args.adjudication.read_text(encoding="utf-8")) if args.adjudication else None
    )
    disputes_only = adjudication is None
    try:
        result = finalize(sheet, labels, adjudication)
    except ValueError as exc:
        parser.exit(2, f"{exc}\n")
    args.out_dir.mkdir(parents=True, exist_ok=True)
    for judge, items in labels.items():
        (args.out_dir / f"labels_{judge}.json").write_text(
            json.dumps({"judge": judge, "labels": items}, ensure_ascii=False, indent=1) + "\n",
            encoding="utf-8",
        )
    (args.out_dir / "combined.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
    )
    if not disputes_only:
        semantic = expand(sheet, result["final_verdicts"])
        (args.out_dir / "semantic.json").write_text(
            json.dumps(semantic, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
        )
    counts = collections.Counter(result["final_verdicts"].values())
    print(f"agreed {result['agreed']}, disputed {len(result['disputed'])}, verdicts {dict(counts)}")
    by_id = {s["item_id"]: s for s in sheet}
    for dispute in result["disputed"]:
        item = by_id[dispute["item_id"]]
        print(
            f"- {dispute['item_id']} [{dispute['criterion']}] {dispute['votes']} | "
            f"{item['user_prompt'][:80]} | {item['assistant_reply'][:160]!r}"
        )


if __name__ == "__main__":
    main()
