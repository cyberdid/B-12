"""The U2/U3 runner drives a real agent turn on seeded synthetic state (scripted model)."""

import asyncio
import json
from pathlib import Path

from evals.unified.run_u2_u3 import run_scenario

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "evals/unified/scenario_sets/u2-u3-draft-v4.json"


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
    assert json.loads(json.dumps(record)) == record  # plain JSON, no read-only mappings
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
    assert 'ROOT_ARGS+=(--ro-bind "$top" "$top")' in script
    assert "ENTRY=(-m evals.unified.run_u2_u3)" in script


async def test_declared_tools_narrow_the_grant_at_capability_level(scripted_ollama, tmp_path):
    state, base = scripted_ollama
    state["script"] = [{"content": "Даних про датчик руху немає."}]

    record = await asyncio.to_thread(
        run_scenario, row("C05-P1"), ROOT, base, tmp_path / "work", files_root=tmp_path / "fs"
    )

    policy = record["tool_policy"]
    assert policy["applied"] is True and policy["level"] == "capability"
    assert set(policy["granted_capabilities"]) == {"filesystem.read", "memory.read"}
    offered = {t["function"]["name"] for t in state["requests"][0].get("tools", [])}
    assert "run_command" not in offered and "file_write" not in offered
    assert {"file_read", "memory_search"} <= offered


def test_style_arms_change_only_the_declared_sentence():
    import pytest

    from evals.unified.run_u2_u3 import A0_SENTENCE, A1_SENTENCE, E1_INSTRUCTION, apply_arm

    base = f"Персона. {A0_SENTENCE} Інше правило."
    assert apply_arm(base, "A0") == base
    assert apply_arm(base, "A1") == f"Персона. {A1_SENTENCE} Інше правило."
    assert apply_arm(base, "E1") == f"{base} {E1_INSTRUCTION}"
    with pytest.raises(ValueError):
        apply_arm("no baseline sentence", "A1")
    with pytest.raises(ValueError):
        apply_arm(base, "E2")


def test_real_runtime_prompt_contains_the_a0_sentence_once():
    from b12.agent import SYSTEM_PROMPT
    from evals.unified.run_u2_u3 import A0_SENTENCE

    assert SYSTEM_PROMPT.count(A0_SENTENCE) == 1


async def test_record_carries_the_arm_and_prompt_hash(scripted_ollama, tmp_path):
    state, base = scripted_ollama
    state["script"] = [{"content": "Привіт!"}]
    record = await asyncio.to_thread(
        run_scenario,
        row("C01-P1"),
        ROOT,
        base,
        tmp_path / "w",
        files_root=tmp_path / "fs",
        arm="A1",
    )
    assert record["u2_arm"] == "A1"
    assert "1–3" in state["requests"][0]["messages"][0]["content"]


def test_broad_claim_pattern_covers_what_the_runtime_default_misses():
    from b12.agent import _ACTION_CLAIM
    from evals.unified.run_u2_u3 import BROAD_ACTION_CLAIM

    for text in ("Я прочитав настанову: розділ 4.2.", "Я прочитав інструкцію `/sandbox/m50`."):
        assert not _ACTION_CLAIM.search(text)
        assert BROAD_ACTION_CLAIM.search(text)
    assert not BROAD_ACTION_CLAIM.search("Я ще не прочитав файл, зараз перевірю інструментом.")
    assert not BROAD_ACTION_CLAIM.search("Привіт! Чим допомогти?")


async def test_arm_d_makes_the_runtime_re_ask_after_a_claimed_read(scripted_ollama, tmp_path):
    state, base = scripted_ollama
    target = tmp_path / "fs" / "sandbox/c06/notes/project-codename.txt"
    script = [
        {"content": "Я прочитав настанову: кодова назва ЖОВТЕНЬ-1."},
        {"tool_calls": [("file_read", {"path": str(target)})]},
        {"content": "Кодова назва: ЛИСТОПАД-7."},
    ]
    state["script"] = list(script)
    baseline = await asyncio.to_thread(
        run_scenario, row("C06-P1"), ROOT, base, tmp_path / "a", files_root=tmp_path / "fs"
    )
    assert baseline["reply"].startswith("Я прочитав настанову")  # default pattern misses it
    state["script"] = list(script)
    record = await asyncio.to_thread(
        run_scenario,
        row("C06-P1"),
        ROOT,
        base,
        tmp_path / "d",
        files_root=tmp_path / "fs2",
        arm="D",
    )
    assert record["reply"] == "Кодова назва: ЛИСТОПАД-7."
    assert [c["name"] for c in record["tool_calls"]] == ["file_read"]
    from b12.agent import _ACTION_CLAIM
    from evals.unified.run_u2_u3 import BROAD_ACTION_CLAIM

    assert _ACTION_CLAIM is not BROAD_ACTION_CLAIM  # restored after the run


async def test_memory_temporal_arm_seeds_metadata_and_pins_the_scenario_clock(
    scripted_ollama, tmp_path
):
    state, base = scripted_ollama
    state["script"] = [{"content": "2 жовтня."}]
    record = await asyncio.to_thread(
        run_scenario,
        row("M04-P1"),
        ROOT,
        base,
        tmp_path / "w",
        files_root=tmp_path / "fs",
        memory_temporal=True,
    )
    assert record["memory_temporal"] is True
    assert "event_time" not in record["seed_report"]["dropped_fields"].get("m04-r1", [])
    request = json.dumps(state["requests"][0], ensure_ascii=False)
    assert "подія 2026-10-02" in request
    assert "Сьогодні: 2026-12-01." in request


async def test_synthetic_environment_is_stubbed_for_the_run(scripted_ollama, tmp_path):
    state, base = scripted_ollama
    state["script"] = [
        {"tool_calls": [("run_command", {"command": "free -h", "cwd": "/"})]},
        {"content": "Доступно 12.4 ГіБ."},
    ]
    record = await asyncio.to_thread(
        run_scenario, row("C11-P1"), ROOT, base, tmp_path / "w", files_root=tmp_path / "fs"
    )
    assert set(record["environment_stub"]) == {"system_info", "run_command"}
    tool_message = next(m for m in state["requests"][1]["messages"] if m["role"] == "tool")
    assert "12.4Gi" in tool_message["content"]


def test_narrow_pattern_catches_document_claims_but_not_recalled_facts():
    from evals.unified.run_u2_u3 import NARROW_ACTION_CLAIM as N

    assert N.search("Я прочитав інструкцію `/sandbox/m50/bike-v2.md`.")
    assert N.search("Я перевірив файл `/sandbox/m50/bike-v2.md` і знайшов розділ 2.1.")
    assert N.search("Я прочитав настанову: розділ 4.2.")
    assert not N.search("Згідно з інформацією, яку я знайшов, процес виглядає так.")
    assert not N.search("Я перевірив пам'ять і бачу запис від 30 листопада.")
    assert not N.search("Я ще не прочитав файл, зараз перевірю.")
