"""Eval corpus invariants, deterministic scoring and runner over scripted transport."""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "evals"))


def corpus():
    return [
        json.loads(line)
        for path in sorted((ROOT / "evals" / "cases").glob("*.jsonl"))
        for line in path.read_text().splitlines()
    ]


def test_corpus_size_categories_and_check_types():
    from scoring import evaluate

    cases = corpus()
    assert len(cases) >= 100 and len({c["id"] for c in cases}) == len(cases)
    assert sum(1 for c in cases if c.get("multi_step")) >= 30
    assert {c["category"] for c in cases} >= {
        "ua",
        "en",
        "tools",
        "memory",
        "behavior",
        "adversarial",
    }
    assert any(len(c["turns"]) >= 50 for c in cases)
    world = {"memories": [], "memory_count": 0, "control_before": 1, "control_after": 1}
    turns = [{"content": "", "state": "completed", "calls": []}] * 60
    for case in cases:
        assert case["checks"], case["id"]
        for check in case["checks"]:
            evaluate(check, turns, world)  # every check type is known


def test_scoring_is_strict_and_turn_scoped(tmp_path):
    from scoring import evaluate, substitute

    turns = [
        {"content": "Відповідь: 391", "state": "completed", "calls": [{"name": "file_read"}]},
        {"content": "Hello world", "state": "awaiting_approval", "calls": []},
    ]
    world = {
        "memories": ["кава без цукру"],
        "memory_count": 1,
        "control_before": 1,
        "control_after": 2,
    }
    assert evaluate({"type": "contains", "value": "391", "turn": 0}, turns, world)[0]
    assert not evaluate({"type": "contains", "value": "391"}, turns, world)[0]
    assert evaluate({"type": "tool_called", "name": "file_read"}, turns, world)[0]
    assert not evaluate({"type": "tool_called", "name": "file_read", "turn": 1}, turns, world)[0]
    assert evaluate({"type": "script", "value": "latin"}, turns, world)[0]
    assert evaluate({"type": "state", "value": "awaiting_approval"}, turns, world)[0]
    assert evaluate({"type": "memory_contains", "value": "цукр"}, turns, world)[0]
    assert not evaluate({"type": "control_unchanged"}, turns, world)[0]
    path = tmp_path / "f.txt"
    path.write_text("точно\n")
    assert evaluate({"type": "file_equals", "path": str(path), "value": "точно"}, turns, world)[0]
    assert substitute({"a": ["{sandbox}/x"]}, {"sandbox": "/s", "cpu_count": 1, "year": 1}) == {
        "a": ["/s/x"]
    }


async def test_run_case_records_real_effects_and_failures(scripted_ollama, tmp_path):
    from runner import run_case

    state, settings = scripted_ollama
    case = {
        "id": "probe",
        "category": "tools",
        "turns": ["Створи файл"],
        "checks": [
            {"type": "file_equals", "path": "{sandbox}/out.txt", "value": "ok"},
            {"type": "contains", "value": "ЗАПИСАНО"},
        ],
    }
    sandbox_file = tmp_path / "work" / "probe-0-32768" / "sandbox" / "out.txt"
    state["script"] = [
        {"tool_calls": [("file_write", {"path": str(sandbox_file), "text": "ok"})]},
        {"content": "Не те слово"},
    ]
    row = await run_case(case, 0, settings, tmp_path / "work")
    assert [c["passed"] for c in row["checks"]] == [True, False]
    assert not row["passed"] and row["turns"][0]["calls"][0]["name"] == "file_write"
    assert row["turns"][0]["model_metrics"][0]["prompt_eval_count"] > 0
    assert (tmp_path / "work" / "probe-0-32768").exists()  # failed runs are kept
