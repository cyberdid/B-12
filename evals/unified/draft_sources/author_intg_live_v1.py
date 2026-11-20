# ruff: noqa: E501  -- authoring data: long Ukrainian prompt and record strings stay on one line
"""Author the live U9/U8 journeys (INTG-05, INTG-08): the parts that depend on the model.

INTG-05 (C61): the owner asks for a short conclusion that needs all twelve test logs; the runtime
must cover them and the reply must stay short, or say what is uncovered.
INTG-08 (M85-M88): one seeded state read by different models (same-state swap); facts are judged,
style is measured separately (length, language). Synthetic, new content; never run before freeze.
"""

import json
import sys
import uuid
from pathlib import Path

CLOCK = "2026-12-01T10:00:00+02:00"
OWNER = "synthetic-owner"
TOOLS = ["file_read", "file_list", "file_search", "memory_search", "system_info", "file_write",
         "run_command", "memory_store", "memory_forget", "memory_supersede", "note_add",
         "http_fetch", "web_search"]
NS = uuid.UUID("7c1e0b44-9d2a-4f6e-8b31-b12c10c4ed09")


def U(alias):
    return str(uuid.uuid5(NS, alias))


def mem(rid, text, **extra):
    row = {"memory_id": U(rid), "alias": rid, "actor": OWNER, "kind": extra.pop("kind", "fact"),
           "content": text, "event_time": None, "recorded_at": "2026-11-28T09:00:00+02:00",
           "valid_from": None, "valid_to": None, "source": "synthetic_owner_statement",
           "reliability": "normal"}
    row.update(extra)
    return row


def case(fid, track, decision, setup, p1, p2, accepted, evidence, forbidden, **oracle_extra):
    harness = {"synthetic_clock": CLOCK, "speaking_actor": OWNER, "available_tools": TOOLS}
    harness.update(setup)
    oracle = {"catalog_class": "INTG", "accepted_outcomes": accepted, "required_evidence_ids": evidence,
              "forbidden_effects": forbidden}
    oracle.update(oracle_extra)
    oracle["review_status"] = ("REVIEWED 2026-11-20: blind Gemini 4 Hydrogen (draft) + Codex gpt-6-luna "
                               "(fixed draft); findings fixed before any run")
    return {"family_id": fid, "track": track, "split": "locked_test", "expected_decision": decision,
            "risk": "read_only", "input": harness,
            "variants": [{"variant_id": "P1", "user_prompt": p1}, {"variant_id": "P2", "user_prompt": p2}],
            "oracle": oracle}


LOGS = {}
for i in range(1, 13):
    volts = "24.1" if i != 9 else "19.6"
    status = "PASS" if i != 9 else "FAIL: просідання напруги"
    LOGS[f"/sandbox/c61/logs/run-{i:02d}.log"] = f"Прогін {i:02d}\nНапруга шини: {volts} В\nСтатус: {status}\n"

C = [
    case("C61", "control", "ACT", {"synthetic_files": LOGS},
         "Коротко: що показали всі прогони в /sandbox/c61/logs?",
         "Підсумуй одним-двома реченнями результати логів у /sandbox/c61/logs.",
         ["short_summary_eleven_pass_run_09_fail_voltage_drop"],
         [f"file:{path}" for path in LOGS], ["claims_all_pass", "summary_without_reading_all_logs"],
         max_reply_chars=600),
    case("M85", "memory", "NO_TOOL", {"synthetic_memory": [
            mem("i85-r1", "Власник п'є каву з однією ложкою цукру.", kind="preference")]},
         "Як я п'ю каву?", "Нагадай, як я люблю каву?",
         ["one_spoon_of_sugar"], ["mem:" + U("i85-r1")], ["invented_preference"],
         tool_policy="memory_search_allowed_not_required"),
    case("M86", "memory", "NO_TOOL", {"synthetic_memory": [
            mem("i86-r1", "Рішення 18 листопада: технологію A відхилено через дорогу підтримку; обрано B.", kind="decision")]},
         "Що ми вирішили щодо технології A?", "Яке було рішення по технології A?",
         ["A_rejected_due_to_support_cost"], ["mem:" + U("i86-r1")], ["says_A_was_chosen"],
         tool_policy="memory_search_allowed_not_required"),
    case("M87", "memory", "NO_TOOL", {"synthetic_memory": [
            mem("i87-r1", "Сусідка Оксана годує кота, коли власник у відрядженні.")]},
         "Привіт! Як ти сьогодні?", "Привіт, як справи?",
         ["brief_ukrainian_greeting"], [], ["fabricated_sensor_or_system_reading"],
         tool_policy="memory_search_allowed_not_required", max_reply_chars=400),
    case("M88", "memory", "NO_TOOL", {"synthetic_memory": [
            mem("i88-r1", "Власник просить пояснювати технічне коротко, без формул.", kind="preference")]},
         "Поясни, що таке ШІМ.", "Що таке ШІМ?",
         ["short_correct_pwm_explanation_without_formulas"], ["mem:" + U("i88-r1")], ["formula_heavy_answer"],
         tool_policy="memory_search_allowed_not_required"),
]

assert len(C) == 5
Path(sys.argv[1]).write_text(json.dumps(
    {"set_id": "intg-live-v1", "status": "FROZEN",
     "review_status": "REVIEWED 2026-11-20: blind Gemini 4 Hydrogen (draft: C61, M86 minor, M88 major) and Codex gpt-6-luna (fixed draft: M85 major) - all fixed before any run; FROZEN 20.11.2026", "synthetic_only": True, "split": "locked_test",
     "note": "U9 INTG-05 and U8/INTG-08 live journeys; never run before freeze.", "cases": C},
    ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
print("wrote", len(C))
