"""Blinded annotation sheet: stable failures x configurations (first run of each).

Writes sheet.json (what judges see: no model, configuration or reviewer label) and key.json
(item -> scenario, configuration) kept apart. Seeded shuffle, so the sheet is reproducible.
"""
import json
import random
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
REPO = ROOT.parents[1]
REP = REPO / "evals/capri_comprehensive/reports/repeats"
data = json.loads((ROOT / "artifacts/data.json").read_text())
ids = data["stable_fail_all_three"]
runs = {
    "A": REP / "run1/batch_summary.json",
    "B": REP / "deployed-26b/run1/batch_summary_deployed-26b.json",
    "C": REP / "deployed-31b/run1/batch_summary_deployed-31b.json",
}
scen = {}
for p in (REPO / "evals/capri_comprehensive/scenarios").glob("*/*.yaml"):
    d = yaml.safe_load(p.read_text(encoding="utf-8"))
    scen[d["id"]] = d


def expectations(d):
    out = []
    for t in d["interactions"]:
        exp = [{k: v for k, v in b.items() if k != "description"} for b in t.get("expected_behaviors", [])]
        forb = [{k: v for k, v in b.items() if k != "description"} for b in t.get("forbidden_behaviors", [])]
        out.append({"turn": t["turn"], "speaker": "owner" if "owner" in t.get("actor_id", "") else "other",
                    "input": t["input"], "expected": exp, "forbidden": forb})
    return out


items = []
for cfg, path in runs.items():
    reports = {r["scenario_id"]: r for r in json.loads(path.read_text(encoding="utf-8"))["reports"]}
    for sid in ids:
        r, d = reports[sid], scen[sid]
        items.append({
            "_scenario": sid, "_config": cfg,
            "title": d.get("title"), "hypothesis": d.get("research_hypothesis"),
            "turns": expectations(d),
            "assistant_replies": [{"turn": t["turn_index"], "reply": t["response_content"][:2500],
                                   "tools_called": [c["name"] for c in t.get("tool_calls", [])]}
                                  for t in r["turn_results"]],
            "automatic_check_failures": [a["detail"][:300] for t in r["turn_results"]
                                         for a in t["failed_assertions"]],
        })
random.Random(20261115).shuffle(items)
sheet, key = [], {}
for n, it in enumerate(items, 1):
    item_id = f"item-{n:02d}"
    key[item_id] = {"scenario": it.pop("_scenario"), "config": it.pop("_config")}
    sheet.append({"item_id": item_id, **it})
out = Path(__file__).resolve().parent
(out / "sheet.json").write_text(json.dumps(sheet, ensure_ascii=False, indent=1), encoding="utf-8")
(out / "key.json").write_text(json.dumps(key, ensure_ascii=False, indent=1), encoding="utf-8")
print(len(sheet), "items")
