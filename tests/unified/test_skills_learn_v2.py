"""`skills-learn-v2` (M115-M118): frozen set wired to the background skill review."""

import asyncio
import json
import re
from pathlib import Path

from evals.unified.run_u2_u3 import run_scenario
from evals.unified.score_u2_u3 import score

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "evals/unified/scenario_sets/skills-learn-v2.json"
UUID = r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"


def _row(scenario_id):
    rows = json.loads(MANIFEST.read_text(encoding="utf-8"))["scenarios"]
    return next(r for r in rows if r["scenario_id"] == scenario_id)


def _oracle(row):
    return json.loads((ROOT / row["oracle_fixture"]).read_text(encoding="utf-8"))


def _check(record, oracle, name):
    return next(c["result"] for c in score(record, oracle)["checks"] if c.get("detail") == name)


def test_manifest_is_frozen_after_two_reviews():
    data = json.loads(MANIFEST.read_text(encoding="utf-8"))
    assert {r["family_id"] for r in data["scenarios"]} == {"M115", "M116", "M117", "M118"}
    assert {r["status"] for r in data["scenarios"]} == {"FROZEN"}


async def test_m115_staged_proposal_passes_the_setup_check(scripted_ollama, tmp_path):
    state, base = scripted_ollama

    def review(request):
        turn_id = re.search(UUID, request["messages"][-1]["content"]).group(0)
        skill = {
            "name": "flash-esp32c3",
            "description": "Прошивка ESP32-C3",
            "body": "1. BOOT, RESET, відпустити BOOT.\n2. 460800 бод.",
            "turn_id": turn_id,
        }
        return {"content": json.dumps({"skills": [skill]}, ensure_ascii=False)}

    state["script"] = [review, {"content": "Будь ласка!"}]
    row = _row("M115-P1")
    record = await asyncio.to_thread(
        run_scenario,
        row,
        ROOT,
        base,
        tmp_path / "w",
        files_root=tmp_path / "fs",
        runtime_flags=("skills", "skill_review"),
    )
    (tick,) = record["seed_report"]["skill_review_tick"]
    assert tick["state"] == "staged"
    assert _check(record, _oracle(row), "setup:skill_proposal_staged") == "PASS"


async def test_m118_web_turn_is_excluded_without_a_model_call(scripted_ollama, tmp_path):
    state, base = scripted_ollama
    state["script"] = [{"content": "Будь ласка!"}]
    row = _row("M118-P1")
    record = await asyncio.to_thread(
        run_scenario,
        row,
        ROOT,
        base,
        tmp_path / "w",
        files_root=tmp_path / "fs",
        runtime_flags=("skills", "skill_review"),
    )
    (tick,) = record["seed_report"]["skill_review_tick"]
    assert tick == {**tick, "state": "skipped", "reason": "no_turns"}
    assert len(state["requests"]) == 1  # only the measured turn
    assert _check(record, _oracle(row), "setup:no_skill_proposal") == "PASS"
