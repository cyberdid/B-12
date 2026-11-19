import json

from evals.unified.analyze_u5_metrics import analyze_arm, compare_metrics


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")


def make_arm(root, arm, labels, *, criterion="uses_expired_rule"):
    records = root / arm / "records"
    judge = root / arm / "judge"
    sheet = []
    criterion_results = {}
    for scenario, label in labels.items():
        item_id = f"{scenario}#hash"
        sheet.append(
            {
                "item_id": item_id,
                "members": [["r1", scenario]],
                "criteria": [criterion],
                "criterion_polarity": {criterion: "prohibited"},
            }
        )
        criterion_results[item_id] = {
            criterion: {"label": label, "votes": {"j1": label, "j2": label}}
        }
        write_json(
            records / "r1" / f"{scenario}.json",
            {"scenario_id": scenario, "status": "EXECUTED", "runtime_state": "completed"},
        )
    write_json(judge / "sheet.json", sheet)
    write_json(judge / "combined.json", {"criterion_results": criterion_results})
    return records, judge


def test_u5_metrics_use_tagged_criterion_labels_and_pair_by_family(tmp_path):
    root = tmp_path / "repo"
    for scenario in ("M61-P1", "M61-P2"):
        write_json(
            root / f"{scenario}.oracle.json",
            {
                "forbidden_effects": ["uses_expired_rule"],
                "metric_tags": {"stale_use": ["uses_expired_rule"]},
            },
        )
    manifest = {
        "scenarios": [
            {
                "scenario_id": scenario,
                "family_id": "M61",
                "oracle_fixture": f"{scenario}.oracle.json",
            }
            for scenario in ("M61-P1", "M61-P2")
        ]
    }
    manifest_path = root / "manifest.json"
    write_json(manifest_path, manifest)
    b0_records, b0_judge = make_arm(
        tmp_path, "B0", {"M61-P1": "met", "M61-P2": "not_met"}
    )
    u5_records, u5_judge = make_arm(
        tmp_path, "U5", {"M61-P1": "not_met", "M61-P2": "not_met"}
    )

    b0 = analyze_arm(manifest_path, b0_records, b0_judge, root)
    u5 = analyze_arm(manifest_path, u5_records, u5_judge, root)
    compared = compare_metrics(b0, u5, baseline_name="B0", arm_name="U5", draws=100)

    # `met` means the prohibited effect was avoided; `not_met` means it occurred.
    assert b0["metrics"]["stale_use"]["mean_family_event_rate"] == 0.5
    assert u5["metrics"]["stale_use"]["mean_family_event_rate"] == 1.0
    assert compared["stale_use"]["mean_delta"] == 0.5
    assert compared["stale_use"]["cluster_bootstrap_95ci"] == [0.5, 0.5]


def test_unresolved_criterion_is_reported_and_excludes_incomplete_family(tmp_path):
    root = tmp_path / "repo"
    scenario = "M64-P1"
    write_json(
        root / f"{scenario}.oracle.json",
        {
            "forbidden_effects": ["revives_revoked_rule"],
            "metric_tags": {"stale_use": ["revives_revoked_rule"]},
        },
    )
    manifest_path = root / "manifest.json"
    write_json(
        manifest_path,
        {
            "scenarios": [
                {
                    "scenario_id": scenario,
                    "family_id": "M64",
                    "oracle_fixture": f"{scenario}.oracle.json",
                }
            ]
        },
    )
    records, judge = make_arm(
        tmp_path, "U5", {scenario: None}, criterion="revives_revoked_rule"
    )
    result = analyze_arm(manifest_path, records, judge, root)

    metric = result["metrics"]["stale_use"]
    assert metric["unknown_observations"] == 1
    assert metric["complete_families"] == 0
    assert metric["mean_family_event_rate"] is None


def test_missing_expected_repeat_is_counted_as_unknown(tmp_path):
    root = tmp_path / "repo"
    scenario = "M64-P1"
    write_json(
        root / f"{scenario}.oracle.json",
        {
            "forbidden_effects": ["revives_revoked_rule"],
            "metric_tags": {"stale_use": ["revives_revoked_rule"]},
        },
    )
    manifest_path = root / "manifest.json"
    write_json(
        manifest_path,
        {
            "scenarios": [
                {
                    "scenario_id": scenario,
                    "family_id": "M64",
                    "oracle_fixture": f"{scenario}.oracle.json",
                }
            ]
        },
    )
    records, judge = make_arm(
        tmp_path, "U5", {scenario: "not_met"}, criterion="revives_revoked_rule"
    )
    result = analyze_arm(manifest_path, records, judge, root, expected_repeats=2)

    metric = result["metrics"]["stale_use"]
    assert result["expected_repeats"] == ["r1", "r2"]
    assert result["observed_repeats"] == ["r1"]
    assert metric["occurred_observations"] == 1
    assert metric["unknown_observations"] == 1
    assert metric["complete_families"] == 0


def test_metric_tag_requires_prohibited_criterion_polarity(tmp_path):
    root = tmp_path / "repo"
    scenario = "M64-P1"
    criterion = "revives_revoked_rule"
    write_json(
        root / f"{scenario}.oracle.json",
        {
            "forbidden_effects": [criterion],
            "metric_tags": {"stale_use": [criterion]},
        },
    )
    manifest_path = root / "manifest.json"
    write_json(
        manifest_path,
        {
            "scenarios": [
                {
                    "scenario_id": scenario,
                    "family_id": "M64",
                    "oracle_fixture": f"{scenario}.oracle.json",
                }
            ]
        },
    )
    records, judge = make_arm(tmp_path, "U5", {scenario: "met"}, criterion=criterion)
    sheet_path = judge / "sheet.json"
    sheet = json.loads(sheet_path.read_text(encoding="utf-8"))
    sheet[0]["criterion_polarity"][criterion] = "required"
    write_json(sheet_path, sheet)

    import pytest

    with pytest.raises(ValueError, match="must be prohibited"):
        analyze_arm(manifest_path, records, judge, root)
