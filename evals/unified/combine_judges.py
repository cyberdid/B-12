"""Combine blind judge labels for one run, apply adjudication, write the semantic verdicts.

    python -m evals.unified.combine_judges <sheet.json> <out_dir> \
        --labels codex=a.json[,b.json] --labels agy=c.json[,d.json] [--adjudication adj.json]

Label files may be raw judge outputs ({"labels": [...]}, or an agy result with
"structured_output") or saved label files. A judge sometimes copies an item id with the wrong
hash suffix; such a label is mapped to the only unlabelled item with the same scenario and
criterion, and every correction is recorded. Without --adjudication the disputes are printed
for a human. The adjudication file maps a family (e.g. "C39") to [verdict, reason]; the
verdict replaces every item of that family that has a disputed criterion (the adjudicator
judges the whole reply). A full item id as key overrides its family for that item.
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
        if not candidates and all(
            label["criterion"] in labelled[item]
            for item in criteria
            if item.startswith(prefix) and label["criterion"] in criteria[item]
        ):
            # A phantom id (the judge invented it) next to the real, already labelled item:
            # dropped and recorded, never mapped (gemma A0 judging, 20.11.2026).
            fixes.add((label["item_id"], "dropped_phantom"))
            label["item_id"] = None
            continue
        if len(candidates) != 1:
            raise ValueError(f"cannot map {label['item_id']}: {candidates}")
        fixes.add((label["item_id"], candidates[0]))
        label["item_id"] = candidates[0]
    labels[:] = [label for label in labels if label["item_id"] is not None]
    return sorted(fixes)


def finalize(
    sheet, labels_by_judge, adjudication=None, criterion_adjudication=None, adjudicator="owner"
):
    corrections = {judge: repair_ids(sheet, labels) for judge, labels in labels_by_judge.items()}
    result = combine(sheet, labels_by_judge)
    result["item_id_corrections"] = {k: v for k, v in corrections.items() if v}
    final = dict(result["verdicts"])
    if adjudication is not None:
        adjudicated = []
        for item in sorted({d["item_id"] for d in result["disputed"]}):
            family = item.split("-", 1)[0]  # M97-P1#hash -> M97; also M100-P1#hash -> M100
            key = item if item in adjudication else family
            if key not in adjudication:
                raise ValueError(f"no adjudication for disputed family {family}")
            verdict, reason = adjudication[key]
            adjudicated.append(
                {"item_id": item, "before": final[item], "verdict": verdict, "by": reason}
            )
            final[item] = verdict
        result["adjudicated"] = adjudicated
    if criterion_adjudication is not None:
        valid_labels = {"met", "not_met", "unclear"}
        if not isinstance(criterion_adjudication, dict):
            raise ValueError("criterion adjudication must be a JSON object")
        used = set()
        for item_id, criteria in result["criterion_results"].items():
            scenario_id = item_id.split("#", 1)[0]
            family_id = scenario_id.split("-", 1)[0]
            for key in (family_id, scenario_id, item_id):
                selected = criterion_adjudication.get(key)
                if selected is None:
                    continue
                if not isinstance(selected, dict):
                    raise ValueError(f"criterion adjudication for {key} must be an object")
                for criterion, label in selected.items():
                    if criterion not in criteria:
                        continue
                    if label not in valid_labels:
                        raise ValueError(
                            f"bad criterion adjudication label for {key}/{criterion}: {label!r}"
                        )
                    criteria[criterion]["label"] = label
                    criteria[criterion]["adjudicated_by"] = adjudicator
                    used.add((key, criterion))
        requested = {
            (key, criterion)
            for key, criteria in criterion_adjudication.items()
            for criterion in criteria
        }
        if requested - used:
            raise ValueError(
                f"unknown criterion adjudication entries: {sorted(requested - used)[:5]}"
            )
        result["criterion_adjudication"] = criterion_adjudication
    result["final_verdicts"] = final
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("sheet", type=Path)
    parser.add_argument("out_dir", type=Path)
    parser.add_argument("--labels", action="append", required=True, help="judge=path[,path]")
    parser.add_argument("--adjudication", type=Path)
    parser.add_argument(
        "--criterion-adjudication",
        type=Path,
        help="JSON mapping family/scenario/item IDs to criterion labels (met/not_met/unclear)",
    )
    parser.add_argument(
        "--adjudicator",
        default="owner",
        help="who decided criterion labels: owner, or claude_delegated under owner rules",
    )
    parser.add_argument(
        "--stale-sheet",
        type=Path,
        help="sheet the labels were made from; labels of its items that are no longer in the "
        "current sheet (records re-run since) are dropped, never re-mapped",
    )
    args = parser.parse_args(argv)
    sheet = json.loads(args.sheet.read_text(encoding="utf-8"))
    labels = {}
    for spec in args.labels:
        judge, paths = spec.split("=", 1)
        labels[judge] = [x for path in paths.split(",") for x in load_labels(path)]
        if args.stale_sheet:
            old = {x["item_id"] for x in json.loads(args.stale_sheet.read_text(encoding="utf-8"))}
            gone = old - {s["item_id"] for s in sheet}
            labels[judge] = [x for x in labels[judge] if x["item_id"] not in gone]
    adjudication = (
        json.loads(args.adjudication.read_text(encoding="utf-8")) if args.adjudication else None
    )
    criterion_adjudication = (
        json.loads(args.criterion_adjudication.read_text(encoding="utf-8"))
        if args.criterion_adjudication
        else None
    )
    disputes_only = adjudication is None
    try:
        result = finalize(
            sheet, labels, adjudication, criterion_adjudication, adjudicator=args.adjudicator
        )
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
