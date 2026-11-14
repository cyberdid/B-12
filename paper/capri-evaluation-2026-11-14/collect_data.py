"""Collect every number used in the manuscript from repository artifacts (no inference).

Writes artifacts/data.json. Each block names its source files; the manuscript and figures
read only this file, so a reader can trace any reported number back to raw data.
"""
from __future__ import annotations

import itertools
import json
import math
import statistics
import subprocess
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[1]
EVAL = REPO / "evals/capri_comprehensive"
REP = EVAL / "reports/repeats"
OUT = ROOT / "artifacts"


def statuses(path: Path) -> dict[str, str]:
    reports = json.loads(path.read_text(encoding="utf-8"))["reports"]
    return {r["scenario_id"]: r["status"].removeprefix("EXECUTED_") for r in reports}


def statuses_at(commit: str, rel: str) -> dict[str, str]:
    text = subprocess.check_output(["git", "-C", str(REPO), "show", f"{commit}:{rel}"], text=True)
    return {r["scenario_id"]: r["status"].removeprefix("EXECUTED_") for r in json.loads(text)["reports"]}


def wilson(k: int, n: int, z: float = 1.96) -> list[float]:
    p = k / n
    c = (p + z * z / (2 * n)) / (1 + z * z / n)
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return [round(100 * (c - h), 1), round(100 * (c + h), 1)]


def sign_test(b: int, w: int) -> float:
    n = b + w
    if not n:
        return 1.0
    tail = sum(math.comb(n, k) for k in range(0, min(b, w) + 1)) / 2**n
    return round(min(1.0, 2 * tail), 3)


def summarize(runs: list[dict[str, str]], ids: list[str]) -> dict:
    per_run = [sum(r[i] == "PASS" for i in ids) for r in runs]
    counts = {i: sum(r[i] == "PASS" for r in runs) for i in ids}
    n = len(runs)
    total = sum(per_run)
    return {
        "per_run": per_run,
        "mean": round(statistics.mean(per_run), 2),
        "sd": round(statistics.stdev(per_run), 2) if n > 1 else 0.0,
        "pooled_percent": round(100 * total / (n * len(ids)), 1),
        "pooled_wilson95": wilson(total, n * len(ids)),
        "stable_pass": sum(c == n for c in counts.values()),
        "stable_fail": sum(c == 0 for c in counts.values()),
        "flaky": sorted(i for i, c in counts.items() if 0 < c < n),
        "pairwise_discordance": [
            sum(a[i] != b[i] for i in ids) for a, b in itertools.combinations(runs, 2)
        ],
        "stable_fail_ids": sorted(i for i, c in counts.items() if c == 0),
        "counts": counts,
    }


def main() -> None:
    OUT.mkdir(exist_ok=True)
    data: dict = {}

    # Suite composition (scenario YAML files).
    scen = [yaml.safe_load(p.read_text(encoding="utf-8")) for p in (EVAL / "scenarios").glob("*/*.yaml")]
    models = {}
    for s in scen:
        m = s["pre_conditions"]["runtime_settings"].get("model")
        models[m] = models.get(m, 0) + 1
    data["suite"] = {
        "scenarios": len(scen),
        "by_model": models,
        "blocked_hardware": sum(s.get("execution_mode") == "blocked_hardware" for s in scen),
        "groups": len({s["group"] for s in scen}),
        "source": "evals/capri_comprehensive/scenarios/*/*.yaml",
    }

    # Repeated runs. Main configuration: Bolt (pinned) + gemma4:12b (swappable), lexical recall.
    main_runs = [statuses(REP / f"run{i}/batch_summary.json") for i in (1, 2, 3)]
    ids = sorted(i for i in main_runs[0] if all(r[i] in ("PASS", "FAIL") for r in main_runs))
    data["runnable"] = len(ids)
    variants = {
        "bolt": main_runs,
        "gemma4-26b": [statuses(REP / f"deployed-26b/run{i}/batch_summary_deployed-26b.json") for i in (1, 2, 3)],
        "gemma4-31b": [statuses(REP / f"deployed-31b/run{i}/batch_summary_deployed-31b.json") for i in (1, 2, 3)],
        "bolt-evidence-after-user": [statuses(REP / f"run{i}/batch_summary.json") for i in (4, 5, 6)],
    }
    data["repeats"] = {k: summarize(v, ids) for k, v in variants.items()}

    # Model-dependent subset: scenarios a deployed variant reruns on its own model.
    import sys
    sys.path.insert(0, str(REPO))
    from evals.capri_comprehensive.runners.live_components import DEPLOYED_HANDLERS
    from evals.capri_comprehensive.runners.run_runtime_suite import runtime_scenarios
    model_dep = sorted({s.id for s in runtime_scenarios()} | set(DEPLOYED_HANDLERS))
    model_dep = [i for i in model_dep if i in ids]
    data["model_dependent"] = {
        "n": len(model_dep),
        "per_config": {k: summarize(v, model_dep)["per_run"] for k, v in variants.items()},
    }
    sf = [set(data["repeats"][k]["stable_fail_ids"]) for k in ("bolt", "gemma4-26b", "gemma4-31b")]
    data["stable_fail_all_three"] = sorted(set.intersection(*sf))

    # Single-run comparison of 13.11 (commit 5a639f9): 12b local semantic, 26b/31b via tunnel.
    single = {
        "bolt": "evals/capri_comprehensive/reports/batch_summary.json",
        "gemma4-12b": "evals/capri_comprehensive/reports/batch_summary_deployed.json",
        "gemma4-26b": "evals/capri_comprehensive/reports/batch_summary_deployed-26b.json",
        "gemma4-31b": "evals/capri_comprehensive/reports/batch_summary_deployed-31b.json",
    }
    data["single_run_2026_11_13"] = {
        k: sum(v == "PASS" for i, v in statuses_at("5a639f9", p).items() if i in ids)
        for k, p in single.items()
    }

    # Paired comparison: Evidence after user (runs 4-6) vs before (runs 1-3).
    before, after = data["repeats"]["bolt"]["counts"], data["repeats"]["bolt-evidence-after-user"]["counts"]
    better = sorted(i for i in ids if after[i] > before[i])
    worse = sorted(i for i in ids if after[i] < before[i])
    data["evidence_paired"] = {
        "better": {i: [before[i], after[i]] for i in better},
        "worse": {i: [before[i], after[i]] for i in worse},
        "sign_test_p": sign_test(len(better), len(worse)),
    }

    # Prompt-cache bench (Bolt, 3 sessions x 7 turns; turn 0 excluded as warm-up).
    bench = EVAL / "reports/experiments/evidence-after-user-2026-11-14"
    cache = {}
    for label in ("baseline", "after"):
        rows = json.loads((bench / f"{label}.json").read_text())["rows"]
        warm = [r for r in rows if r["turn"] > 0]
        med = lambda key: round(statistics.median(r[key] for r in warm), 3)  # noqa: E731
        by_turn = {}
        for r in rows:
            by_turn.setdefault(r["turn"], []).append(r)
        cache[label] = {
            "n_warm": len(warm),
            "ttft_median": med("ttft"), "ttft_max": round(max(r["ttft"] for r in warm), 3),
            "prompt_median": med("prompt"), "cached_median": med("cached"),
            "prefill_median": med("prefill_s"),
            "ttft_by_turn": [round(statistics.median(x["ttft"] for x in by_turn[t]), 3) for t in sorted(by_turn)],
            "cached_by_turn": [statistics.median(x["cached"] for x in by_turn[t]) for t in sorted(by_turn)],
            "prompt_by_turn": [statistics.median(x["prompt"] for x in by_turn[t]) for t in sorted(by_turn)],
        }
    data["prompt_cache"] = cache

    # Brevity A/B (experiments/brevity_ab.py).
    rows = json.loads((ROOT / "experiments/brevity_ab_rows.json").read_text(encoding="utf-8"))
    casual = ["INT-01", "INT-02", "INT-03", "INT-05", "INT-06", "INT-07", "INT-08", "VOI-01", "VOI-03", "LT-08"]
    work = ["INT-04", "RE-01", "RE-04", "RE-07", "AUT-02", "MEM-01", "MEM-07"]
    ab = {}
    for arm in ("control", "treatment"):
        r = [x for x in rows if x["arm"] == arm]
        first = [x for x in r if x["turn"] == 0]
        cas = [x["chars"] for x in r if x["scenario"] in casual]
        wk = [x for x in first if x["scenario"] in work]
        passed = {(x["repeat"], x["scenario"]): x["passed_scenario"] for x in first}
        ab[arm] = {
            "casual_chars_median": statistics.median(cas), "casual_chars_mean": round(statistics.mean(cas)),
            "work_turns_with_tool": sum(x["tool_calls"] > 0 for x in wk), "work_turns": len(wk),
            "scenario_passes": sum(passed.values()), "scenario_runs": len(passed),
            "low_cyrillic_replies": sum(x["cyrillic_share"] < 0.5 for x in r),
        }
    per_scen = {}
    for s in casual + work:
        per_scen[s] = {
            arm: {
                "passes": sum(x["passed_scenario"] for x in rows if x["arm"] == arm and x["scenario"] == s and x["turn"] == 0),
                "tools": [x["tool_calls"] for x in rows if x["arm"] == arm and x["scenario"] == s and x["turn"] == 0],
                "chars_median": statistics.median(x["chars"] for x in rows if x["arm"] == arm and x["scenario"] == s and x["turn"] == 0),
            } for arm in ("control", "treatment")
        }
    ab["per_scenario"] = per_scen
    ab["casual"], ab["work"] = casual, work
    ab["repeats"] = max(x["repeat"] for x in rows) + 1
    data["brevity_ab"] = ab

    (OUT / "data.json").write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(json.dumps({k: data[k] for k in ("suite", "runnable", "model_dependent", "single_run_2026_11_13",
                                           "stable_fail_all_three")}, ensure_ascii=False, indent=1))
    for k, v in data["repeats"].items():
        print(k, v["per_run"], v["mean"], v["pooled_percent"], v["pooled_wilson95"], v["stable_pass"],
              v["stable_fail"], len(v["flaky"]), v["pairwise_discordance"])
    print(data["evidence_paired"])
    print({k: {kk: vv for kk, vv in v.items() if "by_turn" not in kk} for k, v in cache.items()})
    print({k: v for k, v in ab.items() if k in ("control", "treatment")})


if __name__ == "__main__":
    main()
