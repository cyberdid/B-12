"""Build a blind semantic-judge sheet for U2/U3 records and combine the judges' labels.

The sheet holds, per executed scenario: the user prompt, the evaluator-only synthetic
facts the answer must rest on, what the assistant observably did (tool calls with
arguments and status, evidence count) and its reply, plus the prose items left by the
deterministic scorer (`semantic_pending`). It carries no model name, no deterministic
verdict and no author verdict. Each judge labels every item `met`, `not_met` or
`unclear`. `combine` keeps unanimous labels and lists disagreements for the owner.
"""

import json
from pathlib import Path

from evals.unified.score_u2_u3 import score

LABELS = {"met", "not_met", "unclear"}


def _facts(setup):
    facts = {}
    if setup.get("synthetic_files"):
        facts["files"] = setup["synthetic_files"]
    if setup.get("synthetic_memory"):
        facts["memory"] = [
            {k: v for k, v in row.items() if k not in {"memory_id", "derived_from", "supersedes"}}
            for row in setup["synthetic_memory"][:20]
        ]
    for key in (
        "synthetic_goals",
        "synthetic_environment",
        "missing_files",
        "control_policy",
        "speaking_actor",
        "synthetic_clock",
    ):
        if setup.get(key) is not None:
            facts[key] = setup[key]
    return facts


def build(manifest, records_dir, root):
    rows = {r["scenario_id"]: r for r in json.loads(Path(manifest).read_text())["scenarios"]}
    sheet = []
    for path in sorted(Path(records_dir).glob("*.json")):
        record = json.loads(path.read_text(encoding="utf-8"))
        row = rows[record["scenario_id"]]
        oracle = json.loads((Path(root) / row["oracle_fixture"]).read_text(encoding="utf-8"))
        result = score(record, oracle)
        if result["verdict"] in {"BLOCKED", "RUN_FAILED"} or not result["semantic_pending"]:
            continue
        setup = json.loads((Path(root) / row["setup_fixture"]).read_text(encoding="utf-8"))
        prompt = json.loads((Path(root) / row["input_fixture"]).read_text(encoding="utf-8"))
        sheet.append(
            {
                "item_id": record["scenario_id"],
                "user_prompt": prompt["user_prompt"],
                "synthetic_facts": _facts(setup["harness_setup"]),
                "assistant_tool_calls": [
                    {"name": c["name"], "arguments": c.get("arguments"), "status": c["status"]}
                    for c in record["tool_calls"]
                ],
                "memory_evidence_offered_by_runtime": len(record.get("evidence_ids", [])),
                "assistant_reply": record["reply"],
                "criteria": result["semantic_pending"],
            }
        )
    return sheet


def combine(sheet, labels_by_judge):
    """labels_by_judge: {judge: [{"item_id", "criterion", "label", "reason"}]}."""
    table = {}
    for judge, labels in labels_by_judge.items():
        for item in labels:
            if item["label"] not in LABELS:
                raise ValueError(f"{judge}: bad label {item['label']!r}")
            table.setdefault((item["item_id"], item["criterion"]), {})[judge] = item["label"]
    expected = {(s["item_id"], c) for s in sheet for c in s["criteria"]}
    missing = expected - set(table)
    if missing:
        raise ValueError(f"unlabelled criteria: {sorted(missing)[:5]}")
    agreed, disputed = {}, []
    for key in sorted(expected):
        votes = table[key]
        if len(votes) == len(labels_by_judge) and len(set(votes.values())) == 1:
            agreed[key] = next(iter(votes.values()))
        else:
            disputed.append({"item_id": key[0], "criterion": key[1], "votes": votes})
    per_item = {}
    for (item, _), label in agreed.items():
        per_item.setdefault(item, set()).add(label)
    for entry in disputed:
        per_item.setdefault(entry["item_id"], set()).add("disputed")
    verdicts = {
        item: (
            "SEMANTIC_FAIL"
            if "not_met" in found
            else "NEEDS_OWNER"
            if found & {"disputed", "unclear"}
            else "SEMANTIC_PASS"
        )
        for item, found in per_item.items()
    }
    return {"agreed": len(agreed), "disputed": disputed, "verdicts": verdicts}


def main(argv=None):
    import argparse

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("manifest", type=Path)
    parser.add_argument("records", type=Path)
    parser.add_argument("out", type=Path)
    args = parser.parse_args(argv)
    sheet = build(args.manifest, args.records, Path.cwd())
    args.out.write_text(json.dumps(sheet, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"{len(sheet)} items, {sum(len(s['criteria']) for s in sheet)} criteria")


if __name__ == "__main__":
    main()


def build_pilot(manifest, out_dir, root, *, track=None):
    """Sheet for a multi-repeat pilot: identical records are judged once.

    Records of the same scenario whose reply and tool calls are byte-identical across
    repeats become one item; `members` lists every (repeat, scenario_id) it stands for.
    """
    import hashlib

    rows = {r["scenario_id"]: r for r in json.loads(Path(manifest).read_text())["scenarios"]}
    groups = {}
    for path in sorted(Path(out_dir).glob("r*/*.json")):
        record = json.loads(path.read_text(encoding="utf-8"))
        row = rows[record["scenario_id"]]
        if track and row["track"] != track:
            continue
        key = json.dumps(
            [record["scenario_id"], record.get("reply"), record.get("tool_calls")],
            ensure_ascii=False,
            sort_keys=True,
        )
        digest = hashlib.sha256(key.encode()).hexdigest()[:10]
        groups.setdefault((record["scenario_id"], digest), {"path": path, "members": []})
        groups[(record["scenario_id"], digest)]["members"].append(
            [path.parent.name, record["scenario_id"]]
        )
    sheet = []
    for (sid, digest), group in sorted(groups.items()):
        record = json.loads(group["path"].read_text(encoding="utf-8"))
        row = rows[sid]
        oracle = json.loads((Path(root) / row["oracle_fixture"]).read_text(encoding="utf-8"))
        result = score(record, oracle)
        if result["verdict"] in {"BLOCKED", "RUN_FAILED", "FAIL"} or not result["semantic_pending"]:
            continue  # deterministic FAIL already decides; nothing semantic to judge
        setup = json.loads((Path(root) / row["setup_fixture"]).read_text(encoding="utf-8"))
        prompt = json.loads((Path(root) / row["input_fixture"]).read_text(encoding="utf-8"))
        sheet.append(
            {
                "item_id": f"{sid}#{digest}",
                "members": group["members"],
                "user_prompt": prompt["user_prompt"],
                "synthetic_facts": _facts(setup["harness_setup"]),
                "assistant_tool_calls": [
                    {"name": c["name"], "arguments": c.get("arguments"), "status": c["status"]}
                    for c in record["tool_calls"]
                ],
                "memory_evidence_offered_by_runtime": len(record.get("evidence_ids", [])),
                "assistant_reply": record["reply"],
                "criteria": result["semantic_pending"],
            }
        )
    return sheet


def expand(sheet, verdicts):
    """Map item verdicts back to {"<repeat>/<scenario_id>": verdict} for analyze_pilot."""
    out = {}
    for item in sheet:
        verdict = verdicts.get(item["item_id"])
        if verdict is None:
            continue
        for repeat, sid in item["members"]:
            out[f"{repeat}/{sid}"] = verdict
    return out
