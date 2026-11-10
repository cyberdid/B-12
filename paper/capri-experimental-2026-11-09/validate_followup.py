"""Validate the bundled follow-up evidence, without inference or private artifacts."""
from collections import Counter
from pathlib import Path
import json

ROOT = Path(__file__).resolve().parent
EXP = ROOT / "experiments/gemma12b-stage-2026-11-09"
summary = json.loads((EXP / "stage-summary.json").read_text())
budget = json.loads((EXP / "budget-results.json").read_text())
assert len(budget) == 12
for arm, expected_chars, assertion_passes in (
    ("current", 11344, 0), ("head", 10598, 0),
    ("removed", 9886, 3), ("neutral", 11344, 0),
):
    rows = [row for row in budget if row["arm"] == arm]
    assert len(rows) == 3
    assert all(row["last_request"]["total_message_chars"] == expected_chars for row in rows)
    assert sum(row["pytest_exit_code"] == 0 for row in rows) == assertion_passes
    assert summary["budget"][arm]["last_message_chars"] == expected_chars
for repeat in range(1, 4):
    current = json.loads((EXP / f"current-{repeat}.json").read_text())
    for arm in ("head", "removed", "neutral"):
        candidate = json.loads((EXP / f"{arm}-{repeat}.json").read_text())
        assert len(candidate["requests"]) == len(current["requests"]) == 37
        for actual, baseline in zip(candidate["requests"], current["requests"]):
            assert {k: v for k, v in actual["message_chars_by_role"].items() if k != "system"} == {
                k: v for k, v in baseline["message_chars_by_role"].items() if k != "system"
            }
    neutral = json.loads((EXP / f"neutral-{repeat}.json").read_text())
    assert neutral["prefix_chars"] == current["prefix_chars"] == 1458
    assert neutral["prefix_utf8_bytes"] == current["prefix_utf8_bytes"] == 2617
    assert max(row["synthetic_tokens_with_tools"] for row in current["requests"]) == 32014
assert 32014 + 8 + 512 <= 32768

calibration = json.loads((EXP / "gemma-calibration-results.json").read_text())
assert len(calibration) == 8
assert all(row["status"] == "returned" and row["exact_prompt_count"] for row in calibration)
assert all(row["input_tokens"] == row["metrics"]["prompt_eval_count"] for row in calibration)
assert Counter(row["case"] for row in calibration) == {"ua": 2, "emoji": 2, "schema": 2, "tool-history": 2}

pilot = json.loads((EXP / "gemma-pilot-results.json").read_text())
assert len(pilot) == 12 and all(row["passed"] for row in pilot)
assert all(all(check["passed"] for check in row["checks"]) for row in pilot)
assert sum(len(row["turns"]) for row in pilot) == 16
assert Counter(row["num_ctx"] for row in pilot) == {4096: 6, 8192: 6}
assert Counter(row["case"] for row in pilot) == {
    "ua-fact-0": 4, "tool-write-read-0": 4, "memory-store-recall-0": 4,
}
for filename in ("gemma-calibration-cleanup.json", "gemma-pilot-cleanup.json"):
    assert json.loads((EXP / filename).read_text())["unload_acknowledged"]
print("Verified: four-arm CPU ablation; 8 exact Gemma counts; 12 selected case passes; cleanup acknowledgements.")
