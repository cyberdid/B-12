"""The U2/U3 runner drives a real agent turn on seeded synthetic state (scripted model)."""

import asyncio
import json
from pathlib import Path

from evals.unified.run_u2_u3 import run_scenario

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "evals/unified/scenario_sets/u2-u3-draft-v3.json"


def row(scenario_id):
    rows = json.loads(MANIFEST.read_text(encoding="utf-8"))["scenarios"]
    return next(r for r in rows if r["scenario_id"] == scenario_id)


async def test_tool_call_arguments_and_reply_are_recorded(scripted_ollama, tmp_path):
    state, base = scripted_ollama
    files = tmp_path / "fs"
    target = files / "sandbox/c06/notes/project-codename.txt"
    state["script"] = [
        {"tool_calls": [("file_read", {"path": str(target)})]},
        {"content": "Кодова назва: ЛИСТОПАД-7."},
    ]

    record = await asyncio.to_thread(
        run_scenario, row("C06-P1"), ROOT, base, tmp_path / "work", files_root=files
    )

    assert record["status"] == "EXECUTED"
    assert record["reply"] == "Кодова назва: ЛИСТОПАД-7."
    assert record["tool_calls"][0]["name"] == "file_read"
    assert record["tool_calls"][0]["arguments"] == {"path": str(target)}
    assert record["tool_calls"][0]["status"] == "completed"
    assert "Яка кодова назва" in state["requests"][0]["messages"][-1]["content"]
    assert "accepted_outcomes" not in json.dumps(state["requests"][0], ensure_ascii=False)


async def test_seeded_memory_evidence_maps_back_to_declared_ids(scripted_ollama, tmp_path):
    state, base = scripted_ollama
    state["script"] = [{"content": "24 В."}]

    record = await asyncio.to_thread(
        run_scenario, row("M08-P1"), ROOT, base, tmp_path / "work", files_root=tmp_path / "fs"
    )

    setup = json.loads((ROOT / row("M08-P1")["setup_fixture"]).read_text(encoding="utf-8"))
    declared = {m["alias"]: m["memory_id"] for m in setup["harness_setup"]["synthetic_memory"]}
    assert declared["m08-r2"] in record["evidence_ids"]
    assert declared["m08-r1"] not in record["evidence_ids"]  # superseded, not live
    assert record["seed_report"]["applied_relations"] == [{"supersedes": "m08-r1", "by": "m08-r2"}]


async def test_guest_turn_does_not_receive_owner_private_memory(scripted_ollama, tmp_path):
    state, base = scripted_ollama
    state["script"] = [{"content": "Не можу про це розповісти."}]

    record = await asyncio.to_thread(
        run_scenario, row("M26-P1"), ROOT, base, tmp_path / "work", files_root=tmp_path / "fs"
    )

    assert record["evidence_ids"] == []
    assert "лікаря" not in json.dumps(state["requests"][0], ensure_ascii=False)


def test_blocked_scenario_is_recorded_without_running(tmp_path):
    record = run_scenario(row("C24-P1"), ROOT, None, tmp_path / "work", files_root=tmp_path)
    assert record["status"] == "BLOCKED"
    assert "U6" in record["reason"]
    assert not (tmp_path / "work").exists()


def test_cli_refuses_to_run_outside_the_sandbox(tmp_path, monkeypatch):
    import pytest

    from evals.unified.run_u2_u3 import main

    monkeypatch.delenv("B12_EVAL_SANDBOX", raising=False)
    with pytest.raises(SystemExit) as stop:
        main([str(MANIFEST), "C06-P1", str(tmp_path / "out")])
    assert stop.value.code == 2
    assert not (tmp_path / "out").exists()


def test_sandbox_script_offers_the_unified_entry_with_fresh_mounts():
    script = (ROOT / "evals/capri_comprehensive/runners/sandboxed_suite.sh").read_text()
    assert "unified-u2u3)" in script
    assert "EXTRA+=(--tmpfs /sandbox --tmpfs /actors)" in script
    assert "ENTRY=(-m evals.unified.run_u2_u3)" in script
