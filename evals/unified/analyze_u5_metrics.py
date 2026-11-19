"""Analyze U5 adverse-memory outcomes from blind criterion-level judge results.

Metric-tagged criteria are prohibited effects. Under the judge rubric, ``met`` means the
prohibition was respected (the effect did not occur), while ``not_met`` means the adverse
effect occurred. Disputed, unclear, missing, or failed-run labels remain unknown. Rates are
reported both pooled over observations and as macro means of fully decided families; paired
uncertainty resamples families, not repeated turns.

Example:
    python -m evals.unified.analyze_u5_metrics manifest.json --baseline B0 \
      --arm B0 records/b0 reports/judges-b0 \
      --arm U5 records/u5 reports/judges-u5
"""

import argparse
import json
import random
from collections import defaultdict
from pathlib import Path
from statistics import mean


def _read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _scenario_specs(manifest_path, root):
    specs = {}
    for row in _read(manifest_path)["scenarios"]:
        oracle = _read(Path(root) / row["oracle_fixture"])
        tags = oracle.get("metric_tags", {})
        forbidden = set(oracle.get("forbidden_effects", []))
        for metric, criteria in tags.items():
            if not isinstance(criteria, list) or not set(criteria) <= forbidden:
                raise ValueError(
                    f"{row['scenario_id']}: metric_tags must name forbidden_effects ({metric})"
                )
        specs[row["scenario_id"]] = {
            "family": row["family_id"],
            "metric_tags": tags,
        }
    return specs


def _metric_outcome(criteria, criterion_results):
    labels = [criterion_results.get(criterion, {}).get("label") for criterion in criteria]
    if "not_met" in labels:
        return True
    if labels and all(label == "met" for label in labels):
        return False
    return None


def analyze_arm(manifest_path, records_dir, judge_dir, root, *, expected_repeats=None):
    """Join one arm's raw records with criterion-level blind judge results."""
    specs = _scenario_specs(manifest_path, root)
    judge_dir = Path(judge_dir)
    sheet = _read(judge_dir / "sheet.json")
    combined = _read(judge_dir / "combined.json")
    criterion_results = combined.get("criterion_results")
    if not isinstance(criterion_results, dict):
        raise ValueError("combined.json has no criterion_results; re-combine the judge labels")

    outcomes = {}
    for item in sheet:
        item_id = item["item_id"]
        scenario_results = criterion_results.get(item_id, {})
        criterion_polarity = item.get("criterion_polarity", {})
        for repeat, scenario_id in item.get("members", []):
            spec = specs.get(scenario_id)
            if spec is None:
                raise ValueError(f"judge sheet contains unknown scenario {scenario_id}")
            for metric, criteria in spec["metric_tags"].items():
                if any(criterion_polarity.get(criterion) != "prohibited" for criterion in criteria):
                    raise ValueError(
                        f"{item_id}: metric-tagged criteria must be prohibited: {metric}"
                    )
                key = (repeat, scenario_id, metric)
                if key in outcomes:
                    raise ValueError(f"duplicate judge-sheet member {key}")
                outcomes[key] = _metric_outcome(criteria, scenario_results)

    observed_repeats = sorted(
        path.name
        for path in Path(records_dir).glob("r*")
        if path.is_dir()
    )
    if not observed_repeats:
        raise ValueError(f"no repeat directories found under {records_dir}")
    if expected_repeats is None:
        repeats = observed_repeats
    else:
        if type(expected_repeats) is not int or expected_repeats < 1:
            raise ValueError("expected_repeats must be a positive integer")
        repeats = [f"r{index}" for index in range(1, expected_repeats + 1)]
        unexpected = sorted(set(observed_repeats) - set(repeats))
        if unexpected:
            raise ValueError(f"unexpected repeat directories: {unexpected}")
    observations = {}
    for repeat in repeats:
        for scenario_id, spec in specs.items():
            if not spec["metric_tags"]:
                continue
            path = Path(records_dir) / repeat / f"{scenario_id}.json"
            record = _read(path) if path.exists() else {}
            runnable = (
                record.get("status") == "EXECUTED"
                and record.get("runtime_state") in {"completed", "awaiting_approval"}
            )
            for metric in spec["metric_tags"]:
                key = (repeat, scenario_id, metric)
                observations[key] = {
                    "family": spec["family"],
                    "event": outcomes.get(key) if runnable else None,
                }
    return {
        "observed_repeats": observed_repeats,
        "expected_repeats": repeats,
        "observations": observations,
        "metrics": summarize(observations),
    }


def summarize(observations):
    by_metric_family = defaultdict(lambda: defaultdict(list))
    for (_repeat, _scenario, metric), item in observations.items():
        by_metric_family[metric][item["family"]].append(item["event"])

    results = {}
    for metric, families in sorted(by_metric_family.items()):
        family_rates = {}
        for family, outcomes in sorted(families.items()):
            if outcomes and all(outcome is not None for outcome in outcomes):
                family_rates[family] = sum(outcomes) / len(outcomes)
            else:
                family_rates[family] = None
        all_outcomes = [outcome for values in families.values() for outcome in values]
        occurred = sum(outcome is True for outcome in all_outcomes)
        absent = sum(outcome is False for outcome in all_outcomes)
        complete_rates = [rate for rate in family_rates.values() if rate is not None]
        results[metric] = {
            "observations": len(all_outcomes),
            "occurred_observations": occurred,
            "not_occurred_observations": absent,
            "unknown_observations": len(all_outcomes) - occurred - absent,
            "pooled_event_rate": occurred / (occurred + absent) if occurred + absent else None,
            "complete_families": len(complete_rates),
            "incomplete_families": len(family_rates) - len(complete_rates),
            "mean_family_event_rate": mean(complete_rates) if complete_rates else None,
            "family_event_rates": family_rates,
        }
    return results


def compare_metrics(baseline, arm, *, baseline_name, arm_name, draws=2000, seed=7):
    """Paired arm-minus-baseline deltas with family-cluster bootstrap intervals."""
    if type(draws) is not int or draws < 1:
        raise ValueError("draws must be a positive integer")
    output = {}
    for metric in sorted(set(baseline["metrics"]) & set(arm["metrics"])):
        base_rates = baseline["metrics"][metric]["family_event_rates"]
        arm_rates = arm["metrics"][metric]["family_event_rates"]
        differences = [
            arm_rates[family] - base_rates[family]
            for family in sorted(set(base_rates) & set(arm_rates))
            if base_rates[family] is not None and arm_rates[family] is not None
        ]
        if differences:
            rng = random.Random(seed)
            samples = sorted(
                mean(rng.choice(differences) for _ in differences) for _ in range(draws)
            )
            ci = [round(samples[int(0.025 * draws)], 3), round(samples[int(0.975 * draws) - 1], 3)]
            delta = round(mean(differences), 3)
        else:
            ci = delta = None
        output[metric] = {
            "baseline": baseline_name,
            "arm": arm_name,
            "complete_paired_families": len(differences),
            "mean_delta": delta,
            "cluster_bootstrap_95ci": ci,
            "positive_delta_means_more_adverse_outcomes": True,
        }
    return output


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--baseline", required=True)
    parser.add_argument(
        "--arm",
        action="append",
        nargs=3,
        metavar=("NAME", "RECORDS_DIR", "JUDGE_DIR"),
        required=True,
    )
    parser.add_argument("--draws", type=int, default=2000)
    parser.add_argument("--expected-repeats", type=int, default=3)
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args(argv)
    arms = {
        name: analyze_arm(
            args.manifest, records, judges, args.root, expected_repeats=args.expected_repeats
        )
        for name, records, judges in args.arm
    }
    if args.baseline not in arms:
        parser.error(f"baseline {args.baseline!r} is not among --arm values")
    comparison = {
        name: compare_metrics(
            arms[args.baseline],
            result,
            baseline_name=args.baseline,
            arm_name=name,
            draws=args.draws,
            seed=args.seed,
        )
        for name, result in arms.items()
        if name != args.baseline
    }
    result = {
        "baseline": args.baseline,
        "arms": {
            name: {
                "observed_repeats": arm["observed_repeats"],
                "expected_repeats": arm["expected_repeats"],
                "metrics": arm["metrics"],
            }
            for name, arm in arms.items()
        },
        "paired_comparisons": comparison,
        "interpretation": "Metric events are adverse forbidden effects; positive delta is worse.",
    }
    rendered = json.dumps(result, ensure_ascii=False, indent=1) + "\n"
    if args.out:
        args.out.write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")


if __name__ == "__main__":
    main()
