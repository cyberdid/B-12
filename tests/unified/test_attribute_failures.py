"""Failures are split into model vs framework classes on the same frozen set."""

from pathlib import Path

from evals.unified.attribute_failures import attribute, info_absent

ROOT = Path(__file__).resolve().parents[2]


def analysis(rates):
    return {
        "families": {
            f: {"track": "memory" if f.startswith("M") else "control", "acceptable_rate": r}
            for f, r in rates.items()
        }
    }


def test_classes():
    result = attribute(
        {
            "bolt": analysis({"C1": 0.0, "C2": 0.0, "C3": 1.0, "C4": 1.0}),
            "haiku": analysis({"C1": 1.0, "C2": 0.0, "C3": 1.0, "C4": 0.0}),
            "luna": analysis({"C1": 0.5, "C2": 0.17, "C3": 1.0, "C4": 0.0}),
        },
        "bolt",
    )
    classes = {r["family"]: r["class"] for r in result["families"]}
    assert classes == {
        "C1": "model",
        "C2": "framework_or_scenario",
        "C3": "all_pass",
        "C4": "reference_only_pass",
    }


def test_info_absent_tags_families_whose_required_record_loses_metadata():
    tagged = info_absent(ROOT / "evals/unified/scenario_sets/u2-u3-locked-v2.json", ROOT)
    assert "event_time" in tagged["M35"]  # event date exists only as metadata
    assert "valid_to" in tagged["M45"]  # validity interval is not stored
    assert "C41" not in tagged
