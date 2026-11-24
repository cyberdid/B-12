"""Eval support for the background skill review: `skill_review_tick` setup key, the
`--skill-review` flag, judge-sheet facts and `setup:` evidence."""

import asyncio
import json
import re

from evals.unified.judge_sheet import _seed_facts
from evals.unified.score_u2_u3 import _evidence
from evals.unified.setup_adapter import build_runtime

UUID = r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"
SETUP = {
    "synthetic_clock": "2026-12-01T10:00:00+02:00",
    "speaking_actor": "synthetic-owner",
    "skill_review_tick": True,
    "synthetic_sessions": [
        {
            "alias": "s1",
            "turns": [
                {
                    "alias": "t1",
                    "messages": [
                        {
                            "role": "user",
                            "content": "Прошив ESP32-C3: BOOT, RESET, відпустити BOOT, 460800 бод.",
                        },
                        {"role": "assistant", "content": "Чудово."},
                    ],
                }
            ],
        }
    ],
}


def _review_reply(request):
    turn_id = re.search(UUID, request["messages"][-1]["content"]).group(0)
    skill = {
        "name": "flash-esp32c3",
        "description": "Прошивка ESP32-C3",
        "body": "1. BOOT, RESET, відпустити BOOT.\n2. 460800 бод.",
        "turn_id": turn_id,
    }
    return {"content": json.dumps({"skills": [skill]}, ensure_ascii=False)}


def _record(report):
    return {"tool_calls": [], "seed_report": report}


async def test_tick_stages_and_reports_the_proposal(scripted_ollama, tmp_path):
    state, base = scripted_ollama
    state["script"] = [_review_reply]
    report = await asyncio.to_thread(
        build_runtime, SETUP, tmp_path / "state", base, skill_review=True
    )
    (tick,) = report["skill_review_tick"]
    assert tick["state"] == "staged"
    (proposal,) = tick["proposals"]
    assert proposal["name"] == "flash-esp32c3" and proposal["action"] == "create"
    assert "460800" in proposal["content"]
    assert _evidence("setup:skill_proposal_staged", _record(report)) == "PASS"
    assert _evidence("setup:no_skill_proposal", _record(report)) == "FAIL"
    assert _seed_facts(_record(report))["skill_review_proposals"] == [proposal]


async def test_tick_without_the_flag_makes_no_model_call(scripted_ollama, tmp_path):
    state, base = scripted_ollama
    report = await asyncio.to_thread(
        build_runtime, SETUP, tmp_path / "state", base, skill_review=False
    )
    assert report["skill_review_tick"] == []
    assert state["requests"] == []
    # Nothing was measured with the flag off: neither check may pass.
    assert _evidence("setup:no_skill_proposal", _record(report)) == "NOT_SCORABLE"
    assert _evidence("setup:skill_proposal_staged", _record(report)) == "FAIL"
    assert _seed_facts(_record(report))["skill_review_proposals"] == []


def test_sets_without_the_tick_have_no_skill_facts():
    assert _seed_facts({"tool_calls": [], "seed_report": {}}) == {}


def test_runner_exposes_the_skill_review_flag():
    from evals.unified import run_u2_u3

    assert "skill_review" in run_u2_u3.RUNTIME_FLAGS
    source = open(run_u2_u3.__file__, encoding="utf-8").read()
    assert '"--skill-review"' in source


def test_no_proposal_passes_only_when_the_review_ran_and_found_nothing():
    def rec(*ticks):
        return {"tool_calls": [], "seed_report": {"skill_review_tick": list(ticks)}}

    ran = {"state": "skipped", "reason": "no_candidates"}
    excluded = {"state": "skipped", "reason": "no_turns"}
    timed_out = {"state": "failed", "reason": "deadline_exceeded"}
    garbage = {"state": "rejected", "reason": "invalid_output"}
    staged = {"state": "staged", "proposals": []}
    assert _evidence("setup:no_skill_proposal", rec(ran)) == "PASS"
    assert _evidence("setup:no_skill_proposal", rec(excluded)) == "PASS"
    assert _evidence("setup:no_skill_proposal", rec(timed_out)) == "NOT_SCORABLE"
    assert _evidence("setup:no_skill_proposal", rec(garbage)) == "NOT_SCORABLE"
    assert _evidence("setup:no_skill_proposal", rec(staged)) == "FAIL"
