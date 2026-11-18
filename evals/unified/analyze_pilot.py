"""Family-level analysis of a U2/U3 pilot run (U2 protocol: the family is the unit).

Per record the verdict is: the deterministic scorer's FAIL, or — when semantic judging has
been combined — the final semantic verdict; otherwise PASS_DETERMINISTIC counts as
`pending`. Per family the acceptable rate is the share of its records (variants × repeats)
judged acceptable; the track rate is the mean over families with a cluster bootstrap 95%
interval (families resampled). Pending records are reported, never counted as passes.
"""

import json
import random
from collections import defaultdict
from pathlib import Path
from statistics import mean

from evals.unified.score_u2_u3 import score

ACCEPT = {"PASS", "SEMANTIC_PASS"}


def outcome(deterministic, semantic=None):
    if deterministic in {"FAIL", "RUN_FAILED"}:
        return "fail"
    if deterministic == "BLOCKED":
        return "blocked"
    if semantic is None:
        return "pending"
    if semantic in ACCEPT:
        return "pass"
    if semantic.startswith("PARTIAL"):
        return "partial"
    if semantic.startswith("SEMANTIC_FAIL") or semantic == "FAIL":
        return "fail"
    return "pending"


def bootstrap(values, *, draws=2000, seed=7):
    rng = random.Random(seed)
    if not values:
        return None
    stats = sorted(mean(rng.choice(values) for _ in values) for _ in range(draws))
    return [round(stats[int(0.025 * draws)], 3), round(stats[int(0.975 * draws) - 1], 3)]


# Families whose setup needs a synthetic environment (disk, uptime, local services) that the
# harness does not stub yet: tool output is the real sandbox, so the oracle is unreachable for
# every model. Excluded from rates until the environment stub exists (found 18.11.2026).
HARNESS_INVALID = {"C51", "C52", "C53", "C54", "C11", "C12"}


def analyze(rows, records, semantic=None, exclude=HARNESS_INVALID):
    """rows: manifest scenarios; records: {(repeat, scenario_id): (record, oracle)}."""
    semantic = semantic or {}
    family_of = {r["scenario_id"]: (r["family_id"], r["track"]) for r in rows}
    per_family = defaultdict(lambda: defaultdict(int))
    for (repeat, sid), (record, oracle) in records.items():
        if family_of[sid][0] in exclude:
            continue
        verdict = score(record, oracle)["verdict"]
        result = outcome(verdict, semantic.get((repeat, sid)))
        per_family[family_of[sid]][result] += 1
    tracks = defaultdict(list)
    families = {}
    for (family, track), counts in sorted(per_family.items()):
        decided = counts["pass"] + counts["fail"] + counts["partial"]
        rate = counts["pass"] / decided if decided else None
        tally = {k: counts[k] for k in ("pass", "partial", "fail", "pending", "blocked")}
        families[family] = {"track": track, **tally, "acceptable_rate": rate}
        if rate is not None and counts["pending"] == 0:
            tracks[track].append(rate)
    summary = {
        track: {
            "families_fully_decided": len(rates),
            "mean_family_acceptable_rate": round(mean(rates), 3) if rates else None,
            "cluster_bootstrap_95ci": bootstrap(rates),
        }
        for track, rates in sorted(tracks.items())
    }
    pending = sum(f["pending"] for f in families.values())
    return {
        "families": families,
        "tracks": summary,
        "pending_records": pending,
        "excluded_families": sorted(exclude & {f for f, _ in family_of.values()}),
    }


def load(manifest, out_dir, root):
    rows = json.loads(Path(manifest).read_text(encoding="utf-8"))["scenarios"]
    by_id = {r["scenario_id"]: r for r in rows}
    records = {}
    for path in sorted(Path(out_dir).glob("r*/*.json")):
        record = json.loads(path.read_text(encoding="utf-8"))
        row = by_id[record["scenario_id"]]
        oracle = json.loads((Path(root) / row["oracle_fixture"]).read_text(encoding="utf-8"))
        records[(path.parent.name, record["scenario_id"])] = (record, oracle)
    return rows, records


def main(argv=None):
    import argparse

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("manifest", type=Path)
    parser.add_argument("out_dir", type=Path)
    parser.add_argument("--semantic", type=Path, help="JSON {repeat/scenario_id: verdict}")
    args = parser.parse_args(argv)
    rows, records = load(args.manifest, args.out_dir, Path.cwd())
    semantic = {}
    if args.semantic:
        raw = json.loads(args.semantic.read_text(encoding="utf-8"))
        semantic = {tuple(k.split("/", 1)): v for k, v in raw.items()}
    print(json.dumps(analyze(rows, records, semantic), ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
