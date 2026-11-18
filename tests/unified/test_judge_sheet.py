"""Judge sheets stay blind; combined labels never pass a disputed or unmet criterion."""

import json
from pathlib import Path

import pytest

from evals.unified.judge_sheet import build, combine

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "evals/unified/scenario_sets/u2-u3-draft-v4.json"


def write_record(directory, scenario_id, reply, calls=()):
    directory.mkdir(parents=True, exist_ok=True)
    record = {
        "scenario_id": scenario_id,
        "status": "EXECUTED",
        "runtime_state": "completed",
        "model": "secret-model-name",
        "reply": reply,
        "tool_calls": list(calls),
        "evidence_ids": [],
    }
    (directory / f"{scenario_id}.json").write_text(json.dumps(record), encoding="utf-8")


def test_sheet_has_criteria_facts_and_no_model_or_verdicts(tmp_path):
    write_record(tmp_path / "rec", "M04-P1", "Першого запуску не пам'ятаю.")
    sheet = build(MANIFEST, tmp_path / "rec", ROOT)
    assert [s["item_id"] for s in sheet] == ["M04-P1"]
    text = json.dumps(sheet, ensure_ascii=False)
    assert "secret-model-name" not in text
    assert "verdict" not in text and "PASS" not in text
    assert "event_date_2026_10_02_not_recorded_date" in sheet[0]["criteria"]
    assert sheet[0]["synthetic_facts"]["memory"][0]["event_time"] == "2026-10-02"


def test_combine_needs_unanimity_and_flags_disputes():
    sheet = [{"item_id": "A", "criteria": ["c1", "c2"]}, {"item_id": "B", "criteria": ["c1"]}]
    labels = {
        "j1": [
            {"item_id": "A", "criterion": "c1", "label": "met"},
            {"item_id": "A", "criterion": "c2", "label": "met"},
            {"item_id": "B", "criterion": "c1", "label": "not_met"},
        ],
        "j2": [
            {"item_id": "A", "criterion": "c1", "label": "met"},
            {"item_id": "A", "criterion": "c2", "label": "not_met"},
            {"item_id": "B", "criterion": "c1", "label": "not_met"},
        ],
    }
    result = combine(sheet, labels)
    assert result["verdicts"] == {"A": "NEEDS_OWNER", "B": "SEMANTIC_FAIL"}
    assert result["disputed"] == [
        {"item_id": "A", "criterion": "c2", "votes": {"j1": "met", "j2": "not_met"}}
    ]


def test_combine_rejects_missing_or_invalid_labels():
    sheet = [{"item_id": "A", "criteria": ["c1"]}]
    with pytest.raises(ValueError, match="unlabelled"):
        combine(sheet, {"j1": []})
    with pytest.raises(ValueError, match="bad label"):
        combine(sheet, {"j1": [{"item_id": "A", "criterion": "c1", "label": "yes"}]})


def test_pilot_sheet_groups_identical_repeats_and_expands_verdicts(tmp_path):
    from evals.unified.judge_sheet import build_pilot, expand

    for repeat, reply in (
        ("r1", "Усе добре, дякую."),
        ("r2", "Усе добре, дякую."),
        ("r3", "Усе гаразд, а в тебе?"),
    ):
        write_record(tmp_path / "out" / repeat, "C02-P1", reply)
    sheet = build_pilot(MANIFEST, tmp_path / "out", ROOT)
    members = sorted(len(item["members"]) for item in sheet)
    assert members == [1, 2]
    verdicts = {item["item_id"]: "SEMANTIC_FAIL" for item in sheet}
    expanded = expand(sheet, verdicts)
    assert set(expanded) == {"r1/C02-P1", "r2/C02-P1", "r3/C02-P1"}
