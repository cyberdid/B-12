"""Tests for Phase G `ports-live-v1` (M89-M96, DRAFT pending owner Codex review)."""

import asyncio
import json
import re
from pathlib import Path

import pytest

from evals.unified.build_scenario_drafts import build_set
from evals.unified.draft_sources import author_ports_v1
from evals.unified.run_u2_u3 import run_scenario
from evals.unified.score_u2_u3 import score
from evals.unified.setup_adapter import build_runtime
from evals.unified.validate_scenarios import validate

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "evals/unified/scenario_sets/ports-live-v1.json"
FIXTURES = ROOT / "evals/unified/draft_fixtures/ports-live-v1"
EXISTING_MANIFESTS = (
    ROOT / "evals/unified/scenario_sets/u2-u3-draft-v4.json",
    ROOT / "evals/unified/scenario_sets/u2-u3-locked-v2.json",
    ROOT / "evals/unified/scenario_sets/u5-application-locked-v1.json",
    ROOT / "evals/unified/scenario_sets/intg-live-v1.json",
)


def _read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _row(scenario_id: str) -> dict:
    rows = _read(MANIFEST)["scenarios"]
    return next(r for r in rows if r["scenario_id"] == scenario_id)


def test_manifest_is_valid_draft_pending_owner_review_and_never_frozen():
    document = _read(MANIFEST)
    assert validate(document, ROOT) == []
    rows = document["scenarios"]
    assert len(rows) == 16
    assert {r["family_id"] for r in rows} == {f"M{i}" for i in range(89, 97)}
    assert {r["track"] for r in rows} == {"memory"}
    assert {r["split"] for r in rows} == {"locked_test"}
    assert {r["status"] for r in rows} == {"DRAFT"}
    assert not [r for r in rows if r["notes"].startswith("BLOCKED:")]
    for row in rows:
        assert "DRAFT_PENDING_OWNER_REVIEW" in row["notes"]
        assert "Codex review PENDING_OWNER" in row["notes"]
        oracle = _read(ROOT / row["oracle_fixture"])
        assert "DRAFT_PENDING_OWNER_REVIEW" in oracle["review_status"]
        assert "Codex review PENDING_OWNER" in oracle["review_status"]

    classes = {
        row["family_id"]: _read(ROOT / row["oracle_fixture"])["catalog_class"] for row in rows
    }
    assert classes == {
        "M89": "P1_preference_placement",
        "M90": "P1_preference_placement",
        "M91": "P1_preference_placement",
        "M92": "P1_preference_placement",
        "M93": "P2_conversation_recall",
        "M94": "P3_memory_review",
        "M95": "P4_network_taint",
        "M96": "P5_as_of_search",
    }


def test_no_prompt_or_family_collision_with_existing_sets():
    ports_rows = _read(MANIFEST)["scenarios"]
    ports_families = {r["family_id"] for r in ports_rows}
    ports_prompts = {_read(ROOT / r["input_fixture"])["user_prompt"] for r in ports_rows}
    for path in EXISTING_MANIFESTS:
        other_rows = _read(path)["scenarios"]
        assert not (ports_families & {r["family_id"] for r in other_rows}), path.name
        other_prompts = {_read(ROOT / r["input_fixture"])["user_prompt"] for r in other_rows}
        assert not (ports_prompts & other_prompts), path.name


def test_authoring_script_reproduces_manifest_deterministically(tmp_path):
    rebuilt = build_set(
        author_ports_v1.build_cases(),
        root=tmp_path,
        fixture_rel_dir="evals/unified/draft_fixtures/ports-live-v1",
        manifest_rel_path="evals/unified/scenario_sets/ports-live-v1.json",
        set_id="ports-live-v1",
        status="DRAFT",
        review_status=author_ports_v1.PENDING_OWNER_REVIEW_STATUS,
    )
    assert rebuilt == _read(MANIFEST)


async def test_p2_m93_prior_session_seeds_and_conversation_search_finds_it(
    scripted_ollama, tmp_path
):
    state, base = scripted_ollama
    state["script"] = [
        {"tool_calls": [("conversation_search", {"query": "Аква-Стоп-4"})]},
        {"content": "У попередній розмові домовилися про «Аква-Стоп-4» під мийкою і біля бойлера."},
    ]
    row = _row("M93-P1")
    record = await asyncio.to_thread(
        run_scenario,
        row,
        ROOT,
        base,
        tmp_path / "work",
        files_root=tmp_path / "fs",
        memory_temporal=True,
        runtime_flags=("session_search",),
    )
    assert record["status"] == "EXECUTED"
    assert record["tool_calls"][0]["name"] == "conversation_search"
    assert record["tool_calls"][0]["status"] == "completed"
    follow_up = json.dumps(state["requests"][1], ensure_ascii=False)
    assert "Аква-Стоп-4" in follow_up
    assert "кухонною мийкою" in follow_up
    oracle = _read(ROOT / row["oracle_fixture"])
    scored = score(record, oracle)
    assert scored["verdict"] == "PASS_DETERMINISTIC"


async def test_p3_m94_review_tick_runs_only_when_memory_review_is_enabled(
    scripted_ollama, tmp_path
):
    state, base = scripted_ollama
    state["script"] = [{"content": "Не знаю."}]
    off_record = await asyncio.to_thread(
        run_scenario,
        _row("M94-P1"),
        ROOT,
        base,
        tmp_path / "off",
        files_root=tmp_path / "fs-off",
        memory_temporal=True,
        runtime_flags=(),
    )
    assert off_record["seed_report"]["review_tick"] == []
    assert len(state["requests"]) == 1  # zero review LLM calls during setup

    state["requests"].clear()

    def review_then_answer():
        def review_reply(request):
            prompt_text = request["messages"][-1]["content"]
            turn_match = re.search(
                r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", prompt_text
            )
            assert turn_match is not None
            return {
                "content": json.dumps(
                    {
                        "candidates": [
                            {
                                "text": (
                                    "Автомат на розетку компресора в гаражному щитку — "
                                    "Лінія Г-7 на 20 А."
                                ),
                                "kind": "fact",
                                "turn_id": turn_match.group(0),
                            }
                        ]
                    },
                    ensure_ascii=False,
                )
            }

        return [
            review_reply,
            {"content": "Автомат «Лінія Г-7» на 20 ампер."},
        ]

    state["script"] = review_then_answer()
    on_record = await asyncio.to_thread(
        run_scenario,
        _row("M94-P1"),
        ROOT,
        base,
        tmp_path / "on",
        files_root=tmp_path / "fs-on",
        memory_temporal=True,
        runtime_flags=("memory_review",),
    )
    assert len(on_record["seed_report"]["review_tick"]) == 1
    assert on_record["seed_report"]["review_tick"][0]["state"] == "recorded"
    assert len(on_record["evidence_ids"]) == 1
    assert "Лінія Г-7" in json.dumps(state["requests"][-1], ensure_ascii=False)


async def test_p4_m95_network_taint_differs_cleanly_between_defaults_and_flag(
    scripted_ollama, tmp_path
):
    state, base = scripted_ollama
    row = _row("M95-P1")

    state["script"] = [{"content": "Дерево до 18000, сталь на 24000."}]
    defaults_rec = await asyncio.to_thread(
        run_scenario,
        row,
        ROOT,
        base,
        tmp_path / "defaults",
        files_root=tmp_path / "fs-defaults",
        memory_temporal=True,
        runtime_flags=(),
    )
    defaults_prompt = json.dumps(state["requests"][0], ensure_ascii=False)
    assert "Власник перевірив на стенді" not in defaults_prompt
    assert "надійність: unverified" not in defaults_prompt
    assert defaults_rec["seed_report"]["network_untainted"] == ["p95-r2"]

    state["requests"].clear()
    state["script"] = [{"content": "До 18000 по дереву підтверджено; 24000 по сталі неперевірено."}]
    tainted_rec = await asyncio.to_thread(
        run_scenario,
        row,
        ROOT,
        base,
        tmp_path / "taint",
        files_root=tmp_path / "fs-taint",
        memory_temporal=True,
        runtime_flags=("memory_taint",),
    )
    tainted_prompt = json.dumps(state["requests"][0], ensure_ascii=False)
    assert "надійність: unverified" in tainted_prompt
    assert tainted_rec["seed_report"]["network_tainted"] == ["p95-r2"]


def test_p5_m96_october_record_is_crowded_out_unless_as_of_is_used(tmp_path, profile_settings):
    from b12.runtime import open_runtime

    setup = _read(ROOT / _row("M96-P1")["setup_fixture"])["harness_setup"]
    report = build_runtime(setup, tmp_path / "state", profile_settings, temporal=True)
    assert report["dropped_fields"] == {}
    runtime = open_runtime(
        profile_settings.model_copy(
            update={"state_dir": tmp_path / "state", "memory_temporal": True, "memory_as_of": True}
        )
    )
    try:
        actor = runtime.control.resolve_actor(report["actors"]["synthetic-owner"])
        oct_id = next(
            report["memory_ids"][row["memory_id"]]
            for row in setup["synthetic_memory"]
            if row["alias"] == "p96-r1"
        )
        recall_hits = [
            r.id for r in runtime.memory.search("Адреса майстерні в жовтні", actor, limit=3)
        ]
        assert oct_id not in recall_hits
        unscoped_hits = [r.id for r in runtime.memory.search("Адреса майстерні", actor)]
        assert oct_id not in unscoped_hits
        max_limit_hits = [r.id for r in runtime.memory.search("Адреса майстерні", actor, limit=10)]
        assert oct_id not in max_limit_hits
        as_of_hits = [
            r.id for r in runtime.memory.search("Адреса майстерні", actor, as_of="2026-10-15")
        ]
        assert as_of_hits == [oct_id]
    finally:
        runtime.close()


if __name__ == "__main__":
    pytest.main([__file__])
