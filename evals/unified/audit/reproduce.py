"""U10 independent reproduction of the headline numbers, written separately from
analyze_pilot/compare_arms: reads raw records, the frozen oracles and each run's own
combined.json (final verdicts, no cross-arm alignment), and recomputes the family-level
acceptable rates and paired differences with a plain percentile bootstrap.

    python -m evals.unified.audit.reproduce
"""

import json
import random
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from evals.unified.score_u2_u3 import score  # noqa: E402

ART = Path("evals/capri_comprehensive/artifacts")
REP = Path("reports/unified")
INVALID = {"C51", "C52", "C53", "C54", "C11", "C12"}
INFRA = {"http_error", "transport_error", "transport_timeout"}


def verdicts(judge_dir):
    combined = json.loads((judge_dir / "combined.json").read_text())
    final = combined.get("final_verdicts") or combined["verdicts"]
    out = {}
    for name in ("sheet.json", "sheet_control.json", "sheet_memory.json"):
        path = judge_dir / name
        if path.exists():
            for item in json.loads(path.read_text()):
                for repeat, sid in item["members"]:
                    out[(repeat, sid)] = final.get(item["item_id"])
    return out


def family_rates(manifest, run, judge_dir):
    rows = {r["scenario_id"]: r for r in json.loads(Path(manifest).read_text())["scenarios"]}
    sem = verdicts(judge_dir)
    fam = defaultdict(lambda: [0, 0])
    issues = defaultdict(int)
    for path in sorted((ART / run).glob("r*/*.json")):
        rec = json.loads(path.read_text())
        row = rows[rec["scenario_id"]]
        if row["family_id"] in INVALID:
            continue
        if rec.get("error_code") in INFRA:
            issues["infra_record"] += 1
            continue
        oracle = json.loads(Path(row["oracle_fixture"]).read_text())
        det = score(rec, oracle)["verdict"]
        if det in ("FAIL", "RUN_FAILED"):
            ok = False
        else:
            v = sem.get((path.parent.name, rec["scenario_id"]))
            if v is None and det == "PASS_DETERMINISTIC":
                issues["unjudged_pass"] += 1
                continue
            ok = v in ("SEMANTIC_PASS", "PASS")
        key = (row["family_id"], row["track"])
        fam[key][0] += ok
        fam[key][1] += 1
    rates = {k: a / n for k, (a, n) in fam.items() if n}
    return rates, dict(issues)


def mean_ci(values, draws=2000, seed=11):
    rng = random.Random(seed)
    m = sum(values) / len(values)
    boots = sorted(sum(rng.choice(values) for _ in values) / len(values) for _ in range(draws))
    return round(m, 3), [
        round(boots[int(0.025 * draws)], 3),
        round(boots[int(0.975 * draws) - 1], 3),
    ]


def compare(manifest, base, arm):
    b, bi = family_rates(manifest, *base)
    a, ai = family_rates(manifest, *arm)
    out = {"issues": {"base": bi, "arm": ai}}
    for track in ("control", "memory"):
        keys = [k for k in b if k[1] == track and k in a]
        if not keys:
            continue
        out[track] = {
            "base": round(sum(b[k] for k in keys) / len(keys), 3),
            "arm": round(sum(a[k] for k in keys) / len(keys), 3),
            "diff": mean_ci([a[k] - b[k] for k in keys]),
            "families": len(keys),
        }
    return out


LOCKED = "evals/unified/scenario_sets/u2-u3-locked-v2.json"
U5SET = "evals/unified/scenario_sets/u5-application-locked-v1.json"
CASES = {
    "U4 on Bolt (A0 -> U4)": (
        LOCKED,
        ("unified-locked-pilot-2026-11-18", REP / "semantic-judge-locked-pilot-2026-11-18"),
        ("unified-locked-u4-temporal-2026-11-18", REP / "semantic-judge-U4-2026-11-18/v2"),
    ),
    "F on Bolt (A0 -> F)": (
        LOCKED,
        ("unified-locked-pilot-2026-11-18", REP / "semantic-judge-locked-pilot-2026-11-18"),
        ("unified-locked-framework-F-2026-11-18", REP / "semantic-judge-F/v2"),
    ),
    "drift (A0 -> A0b)": (
        LOCKED,
        ("unified-locked-pilot-2026-11-18", REP / "semantic-judge-locked-pilot-2026-11-18"),
        ("unified-locked-A0b-2026-11-18", REP / "semantic-judge-A0b"),
    ),
    "U4 on gemma (GA0 -> GDEF)": (
        LOCKED,
        ("unified-locked-gemma-colab-A0-2026-11-19", REP / "semantic-judge-gemma-A0"),
        ("unified-locked-gemma-colab-defaults-2026-11-19", REP / "semantic-judge-gemma-defaults"),
    ),
    "U5 on U5 set (B0 -> U5)": (
        U5SET,
        ("unified-u5-application-locked-v1-B0-2026-11-19", REP / "semantic-judge-u5-b0"),
        ("unified-u5-application-locked-v1-U5-2026-11-19", REP / "semantic-judge-u5-u5"),
    ),
}

if __name__ == "__main__":
    result = {name: compare(*spec) for name, spec in CASES.items()}
    Path("reports/unified/audit").mkdir(parents=True, exist_ok=True)
    Path("reports/unified/audit/reproduction-2026-11-20.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=1) + "\n"
    )
    for name, r in result.items():
        line = name
        for t in ("control", "memory"):
            if t in r:
                line += f" | {t} {r[t]['base']} -> {r[t]['arm']} diff {r[t]['diff'][0]:+} {r[t]['diff'][1]} n={r[t]['families']}"
        print(line, "| issues", r["issues"])
