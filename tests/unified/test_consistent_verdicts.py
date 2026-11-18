"""Identical replies get one verdict across arms; owner adjudication wins."""

import json

from evals.unified.consistent_verdicts import canonical


def write_arm(directory, verdict, adjudicated_by=None):
    directory.mkdir()
    item = {
        "item_id": "C36-P1#x",
        "assistant_reply": "12",
        "assistant_tool_calls": [],
        "criteria": ["c"],
        "members": [["r1", "C36-P1"]],
    }
    (directory / "sheet.json").write_text(json.dumps([item]), encoding="utf-8")
    result = {"verdicts": {"C36-P1#x": verdict}, "final_verdicts": {"C36-P1#x": verdict}}
    if adjudicated_by:
        result["adjudicated"] = [{"item_id": "C36-P1#x", "verdict": verdict, "by": adjudicated_by}]
    (directory / "combined.json").write_text(json.dumps(result), encoding="utf-8")


def test_owner_adjudication_beats_later_unanimous_judges(tmp_path):
    write_arm(tmp_path / "a0", "SEMANTIC_PASS", adjudicated_by="owner yes")
    write_arm(tmp_path / "a1", "SEMANTIC_FAIL")
    best, _ = canonical({"A0": tmp_path / "a0", "A1": tmp_path / "a1"})
    [(verdict, arm, _strength)] = best.values()
    assert (verdict, arm) == ("SEMANTIC_PASS", "A0")


def test_without_adjudication_the_earliest_arm_wins(tmp_path):
    write_arm(tmp_path / "a0", "SEMANTIC_FAIL")
    write_arm(tmp_path / "a1", "SEMANTIC_PASS")
    best, _ = canonical({"A0": tmp_path / "a0", "A1": tmp_path / "a1"})
    assert next(iter(best.values()))[:2] == ("SEMANTIC_FAIL", "A0")
