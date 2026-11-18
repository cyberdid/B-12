"""One verdict per identical reply across arms (found 18.11.2026: 9 of 112 identical replies
judged in several arms got different verdicts, e.g. C36 "12" passed in A0 and failed later).

An identical reply is the same scenario, reply text and tool calls. Its canonical verdict comes
from the strongest source among all arms: the owner's adjudication, then Claude's delegated
adjudication, then unanimous judges; ties keep the earliest arm in the given order. Each arm's
semantic map is rewritten with the canonical verdicts; changes are reported.

    python -m evals.unified.consistent_verdicts <out_dir> name=<judge_dir> [name=<judge_dir> ...]
"""

import json
import sys
from pathlib import Path

SHEETS = ("sheet.json", "sheet_control.json", "sheet_memory.json")


def _source(arm_result, item_id):
    for entry in arm_result.get("adjudicated", []):
        if entry["item_id"] == item_id:
            return 2 if str(entry.get("by", "")).startswith("owner") else 1
    return 0


def _sheet(directory):
    items = []
    for name in SHEETS:
        path = Path(directory) / name
        if path.exists():
            items += json.loads(path.read_text(encoding="utf-8"))
    return items


def _key(item):
    return (
        item["item_id"].split("#")[0],
        item["assistant_reply"],
        json.dumps(item["assistant_tool_calls"], sort_keys=True, ensure_ascii=False),
    )


def canonical(arms):
    """arms: ordered {name: judge_dir}. Returns ({key: (verdict, arm, strength)}, loaded)."""
    best, loaded = {}, {}
    for order, (name, directory) in enumerate(arms.items()):
        result = json.loads((Path(directory) / "combined.json").read_text(encoding="utf-8"))
        final = result.get("final_verdicts") or result["verdicts"]
        sheet = _sheet(directory)
        loaded[name] = (sheet, final)
        for item in sheet:
            verdict = final.get(item["item_id"])
            if verdict is None or verdict == "NEEDS_OWNER":
                continue
            strength = (_source(result, item["item_id"]), -order)
            key = _key(item)
            if key not in best or strength > best[key][2]:
                best[key] = (verdict, name, strength)
    return best, loaded


def main(argv=None):
    argv = argv if argv is not None else sys.argv[1:]
    out_dir = Path(argv[0])
    arms = dict(arg.split("=", 1) for arg in argv[1:])
    best, loaded = canonical(arms)
    out_dir.mkdir(parents=True, exist_ok=True)
    changes = []
    for name, (sheet, final) in loaded.items():
        semantic = {}
        for item in sheet:
            verdict = final.get(item["item_id"])
            canon = best.get(_key(item))
            if canon and canon[0] != verdict:
                changes.append(
                    {
                        "arm": name,
                        "item_id": item["item_id"],
                        "was": verdict,
                        "now": canon[0],
                        "from_arm": canon[1],
                    }
                )
                verdict = canon[0]
            if verdict is None:
                continue
            for repeat, scenario in item["members"]:
                semantic[f"{repeat}/{scenario}"] = verdict
        (out_dir / f"semantic_{name}.json").write_text(
            json.dumps(semantic, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
        )
    (out_dir / "changes.json").write_text(
        json.dumps(changes, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
    )
    print(f"{len(changes)} verdicts aligned across {len(loaded)} arms")


if __name__ == "__main__":
    main()
