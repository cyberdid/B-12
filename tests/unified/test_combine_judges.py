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
    assert result["criterion_results"]["C39-P1#aaa"]["c2"]["label"] is None


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


def test_criterion_adjudication_resolves_only_the_named_effect():
    disputed = {"a": labels(), "b": labels(i1={"label": "not_met"})}
    result = finalize(
        SHEET,
        disputed,
        adjudication={"C39": ["SEMANTIC_PASS", "whole-response precedent"]},
        criterion_adjudication={"C39": {"c2": "met"}},
    )
    assert result["criterion_results"]["C39-P1#aaa"]["c2"] == {
        "label": "met",
        "votes": {"a": "met", "b": "not_met"},
        "adjudicated_by": "owner",
    }


def test_criterion_adjudication_validates_labels():
    with pytest.raises(ValueError, match="bad criterion adjudication"):
        finalize(
            SHEET[:1],
            {"a": labels()[:2], "b": labels()[:2]},
            criterion_adjudication={"C39": {"c1": "yes"}},
        )


def test_stale_labels_of_rerun_items_are_dropped_not_remapped(tmp_path):
    import json

    from evals.unified.combine_judges import main

    old_sheet = [
        {
            "item_id": "C39-P1#old",
            "criteria": ["c1"],
            "members": [["r1", "C39-P1"]],
            "user_prompt": "p",
            "assistant_reply": "old",
        }
    ]
    new_sheet = [
        {
            "item_id": "C39-P1#new",
            "criteria": ["c1"],
            "members": [["r1", "C39-P1"]],
            "user_prompt": "p",
            "assistant_reply": "new",
        }
    ]
    (tmp_path / "old.json").write_text(json.dumps(old_sheet))
    (tmp_path / "new.json").write_text(json.dumps(new_sheet))
    stale = {"labels": [{"item_id": "C39-P1#old", "criterion": "c1", "label": "met"}]}
    fresh = {"labels": [{"item_id": "C39-P1#new", "criterion": "c1", "label": "not_met"}]}
    for name, data in (("a_old", stale), ("a_new", fresh), ("b_old", stale), ("b_new", fresh)):
        (tmp_path / f"{name}.json").write_text(json.dumps(data))
    main(
        [
            str(tmp_path / "new.json"),
            str(tmp_path / "out"),
            "--labels",
            f"a={tmp_path / 'a_old.json'},{tmp_path / 'a_new.json'}",
            "--labels",
            f"b={tmp_path / 'b_old.json'},{tmp_path / 'b_new.json'}",
            "--stale-sheet",
            str(tmp_path / "old.json"),
        ]
    )
    result = json.loads((tmp_path / "out/combined.json").read_text())
    assert result["final_verdicts"] == {"C39-P1#new": "SEMANTIC_FAIL"}


def test_a_phantom_item_id_next_to_the_labelled_real_item_is_dropped():
    from evals.unified.combine_judges import repair_ids

    sheet = [{"item_id": "M36-P2#real", "criteria": ["c1"]}]
    labels = [
        {"item_id": "M36-P2#real", "criterion": "c1", "label": "met"},
        {"item_id": "M36-P2#phantom", "criterion": "c1", "label": "not_met"},
    ]
    fixes = repair_ids(sheet, labels)
    assert fixes == [("M36-P2#phantom", "dropped_phantom")]
    assert labels == [{"item_id": "M36-P2#real", "criterion": "c1", "label": "met"}]
