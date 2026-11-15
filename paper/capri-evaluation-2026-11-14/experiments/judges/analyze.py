"""Agreement between the reviewer (Claude) and two blinded LLM judges (Codex, Antigravity).

Inputs: labels_claude.json (fixed before any judge output was read), labels_codex_pass{1,2}.json,
labels_agy_pass{1,2}.json, key.json. Output: agreement.json and disputed.md (items for the
owner to review). Pass 1 of each judge is its primary label; pass 2 (reversed order) measures
self-consistency.
"""
import json
from collections import Counter
from itertools import combinations
from pathlib import Path

HERE = Path(__file__).resolve().parent
LABELS = ("genuine_defect", "correct_in_substance", "scenario_mismatch")


def load(name):
    rows = json.loads((HERE / name).read_text())
    out = {r["item_id"]: r["label"] for r in rows}
    assert set(out.values()) <= set(LABELS), name
    return out


def cohen(a, b, items):
    po = sum(a[i] == b[i] for i in items) / len(items)
    pe = sum((sum(a[i] == c for i in items) / len(items)) * (sum(b[i] == c for i in items) / len(items))
             for c in LABELS)
    return round((po - pe) / (1 - pe), 3) if pe < 1 else 1.0


def fleiss(raters, items):
    n, k = len(raters), len(LABELS)
    p_j = [sum(r[i] == c for r in raters for i in items) / (n * len(items)) for c in LABELS]
    p_i = [(sum(sum(r[i] == c for r in raters) ** 2 for c in LABELS) - n) / (n * (n - 1)) for i in items]
    pbar, pe = sum(p_i) / len(items), sum(p ** 2 for p in p_j)
    return round((pbar - pe) / (1 - pe), 3)


key = json.loads((HERE / "key.json").read_text())
items = sorted(key)
claude = load("labels_claude.json")
judges = {name: [load(f"labels_{name}_pass{p}.json") for p in (1, 2)] for name in ("codex", "agy")}
for name, (p1, p2) in judges.items():
    assert set(p1) == set(p2) == set(items), name
primary = {"claude": claude, "codex": judges["codex"][0], "agy": judges["agy"][0]}

report = {
    "items": len(items),
    "label_counts": {k: dict(Counter(v.values())) for k, v in primary.items()},
    "self_consistency": {n: {"agreement": round(sum(p[0][i] == p[1][i] for i in items) / len(items), 3),
                             "kappa": cohen(p[0], p[1], items)} for n, p in judges.items()},
    "pairwise_kappa": {f"{a}-{b}": cohen(primary[a], primary[b], items) for a, b in combinations(primary, 2)},
    "pairwise_agreement": {f"{a}-{b}": round(sum(primary[a][i] == primary[b][i] for i in items) / len(items), 3)
                           for a, b in combinations(primary, 2)},
    "fleiss_kappa": fleiss(list(primary.values()), items),
}
majority, disputed = {}, []
for i in items:
    votes = Counter(r[i] for r in primary.values())
    label, count = votes.most_common(1)[0]
    majority[i] = label if count >= 2 else "no_majority"
    if count < 3:
        disputed.append(i)
by_scenario = {}
for i in items:
    by_scenario.setdefault(key[i]["scenario"], []).append(majority[i])
report["majority_counts"] = dict(Counter(majority.values()))
report["unanimous"] = len(items) - len(disputed)
report["scenario_majority"] = {s: dict(Counter(v)) for s, v in sorted(by_scenario.items())}
(HERE / "agreement.json").write_text(json.dumps(report, indent=1) + "\n")

sheet = {x["item_id"]: x for x in json.loads((HERE / "sheet.json").read_text())}
reasons = {n: {r["item_id"]: r.get("reason", "") for r in json.loads((HERE / f"labels_{n}_pass1.json").read_text())}
           for n in ("codex", "agy")}
lines = ["# Disputed items (judges and reviewer disagree)", "",
         "Fill `owner` with genuine_defect / correct_in_substance / scenario_mismatch.", ""]
for i in disputed:
    x = sheet[i]
    lines += [f"## {i} — {key[i]['scenario']} ({x['title']})", "",
              f"- claude: {claude[i]}",
              f"- codex: {primary['codex'][i]} — {reasons['codex'].get(i, '')}",
              f"- agy: {primary['agy'][i]} — {reasons['agy'].get(i, '')}",
              f"- automatic failures: {'; '.join(x['automatic_check_failures'])[:600]}", ""]
    for t, r in zip(x["turns"], x["assistant_replies"]):
        lines += [f"  **Turn {t['turn']} ({t['speaker']}):** {t['input']}", "",
                  f"  > tools: {r['tools_called']}  ", f"  > {r['reply'][:1200].replace(chr(10), ' ')}", ""]
    lines += ["- **owner:** ", ""]
if not (HERE / "disputed.md").exists():  # never overwrite the owner's annotated copy
    (HERE / "disputed.md").write_text("\n".join(lines))

# Owner adjudication of the disputed items (marks: yes/+ normal; +- minor defect; - major).
owner_file = HERE / "labels_owner.json"
if owner_file.exists():
    owner = {r["item_id"]: r for r in json.loads(owner_file.read_text())}
    assert set(owner) == set(disputed), "owner must label exactly the disputed items"
    final = {i: (owner[i]["label"] if i in owner else majority[i]) for i in items}
    report["owner_adjudicated"] = len(owner)
    report["owner_marks"] = dict(Counter(r["owner_mark"] for r in owner.values()))
    report["agreement_with_owner_on_disputed"] = {
        n: f"{sum(primary[n][i] == owner[i]['label'] for i in owner)}/{len(owner)}" for n in primary}
    report["final_counts"] = dict(Counter(final.values()))
    by = {}
    for i in items:
        by.setdefault(key[i]["scenario"], []).append(final[i])
    report["final_by_scenario"] = {s: dict(Counter(v)) for s, v in sorted(by.items())}
    (HERE / "agreement.json").write_text(json.dumps(report, indent=1) + "\n")
print(json.dumps(report, indent=1))
print(len(disputed), "disputed items")
