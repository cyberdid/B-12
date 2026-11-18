"""Judge label combination repairs ids and applies family-level adjudication."""

import pytest

from evals.unified.combine_judges import finalize

SHEET = [
    {"item_id": "C39-P1#aaa", "criteria": ["c1", "c2"], "members": [["r1", "C39-P1"]]},
    {"item_id": "M41-P1#bbb", "criteria": ["c1"], "members": [["r1", "M41-P1"]]},
]


def labels(**overrides):
    base = [
        {"item_id": "C39-P1#aaa", "criterion": "c1", "label": "met"},
        {"item_id": "C39-P1#aaa", "criterion": "c2", "label": "met"},
        {"item_id": "M41-P1#bbb", "criterion": "c1", "label": "not_met"},
    ]
    for index, change in overrides.items():
        base[int(index[1:])] = {**base[int(index[1:])], **change}
    return base


def test_wrong_hash_suffix_is_mapped_and_recorded():
    result = finalize(
        SHEET,
        {"a": labels(i0={"item_id": "C39-P1#zzz"}, i1={"item_id": "C39-P1#zzz"}), "b": labels()},
    )
    assert result["item_id_corrections"] == {"a": [("C39-P1#zzz", "C39-P1#aaa")]}
    assert result["final_verdicts"] == {
        "C39-P1#aaa": "SEMANTIC_PASS",
        "M41-P1#bbb": "SEMANTIC_FAIL",
    }


def test_adjudication_sets_every_item_with_a_dispute():
    disputed = {"a": labels(), "b": labels(i1={"label": "not_met"})}
    with pytest.raises(ValueError, match="no adjudication"):
        finalize(SHEET, disputed, adjudication={})
    result = finalize(SHEET, disputed, adjudication={"C39": ["PARTIAL (owner +-)", "precedent"]})
    assert result["final_verdicts"]["C39-P1#aaa"] == "PARTIAL (owner +-)"
    assert result["adjudicated"][0]["before"] == "NEEDS_OWNER"


def test_item_id_key_overrides_the_family():
    disputed = {"a": labels(), "b": labels(i1={"label": "not_met"})}
    result = finalize(
        SHEET,
        disputed,
        adjudication={
            "C39": ["SEMANTIC_PASS", "family"],
            "C39-P1#aaa": ["SEMANTIC_FAIL (-)", "item"],
        },
    )
    assert result["final_verdicts"]["C39-P1#aaa"] == "SEMANTIC_FAIL (-)"
