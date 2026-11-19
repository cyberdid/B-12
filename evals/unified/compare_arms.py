"""Paired family-level comparison of arms against a baseline, on aligned verdicts.

    python -m evals.unified.compare_arms <verdicts_dir> <manifest> <baseline> name=<run_dir> ...

<verdicts_dir> holds semantic_<name>.json from consistent_verdicts. Per arm: the family
acceptable rates (analyze_pilot), then the mean paired difference arm − baseline over families
decided in both, with a cluster bootstrap 95% interval (families resampled). Writes
analysis_<name>.json and comparison.json into <verdicts_dir>.
"""

import json
import random
import sys
from pathlib import Path
from statistics import mean

from evals.unified.analyze_pilot import analyze, load


def paired(base, arm, *, draws=2000, seed=7):
    out = {}
    for track in ("control", "memory"):
        diffs = [
            arm[f]["acceptable_rate"] - base[f]["acceptable_rate"]
            for f in base
            if f in arm
            and base[f]["track"] == track
            and base[f]["acceptable_rate"] is not None
            and arm[f]["acceptable_rate"] is not None
            and base[f]["pending"] == 0
            and arm[f]["pending"] == 0
        ]
        if not diffs:
            continue
        rng = random.Random(seed)
        stats = sorted(mean(rng.choice(diffs) for _ in diffs) for _ in range(draws))
        out[track] = {
            "families": len(diffs),
            "mean_diff": round(mean(diffs), 3),
            "cluster_bootstrap_95ci": [
                round(stats[int(0.025 * draws)], 3),
                round(stats[int(0.975 * draws) - 1], 3),
            ],
        }
    return out


def main(argv=None):
    argv = argv if argv is not None else sys.argv[1:]
    out_dir, manifest, baseline = Path(argv[0]), argv[1], argv[2]
    runs = dict(arg.split("=", 1) for arg in argv[3:])
    analyses = {}
    for name, run_dir in runs.items():
        rows, records = load(manifest, run_dir, Path.cwd())
        raw = json.loads((out_dir / f"semantic_{name}.json").read_text(encoding="utf-8"))
        semantic = {tuple(k.split("/", 1)): v for k, v in raw.items()}
        analyses[name] = analyze(rows, records, semantic)
        (out_dir / f"analysis_{name}.json").write_text(
            json.dumps(analyses[name], ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
        )
    base = analyses[baseline]["families"]
    comparison = {
        name: {
            "tracks": a["tracks"],
            "pending_records": a["pending_records"],
            "vs_" + baseline: paired(base, a["families"]) if name != baseline else None,
        }
        for name, a in analyses.items()
    }
    (out_dir / "comparison.json").write_text(
        json.dumps(comparison, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
    )
    for name, c in comparison.items():
        t = c["tracks"]
        line = f"{name:6} control {t.get('control', {}).get('mean_family_acceptable_rate')}"
        line += f" memory {t.get('memory', {}).get('mean_family_acceptable_rate')}"
        line += f" pending {c['pending_records']}"
        for track, d in (c["vs_" + baseline] or {}).items():
            line += f" | {track} {d['mean_diff']:+.3f} {d['cluster_bootstrap_95ci']}"
        print(line)


if __name__ == "__main__":
    main()
