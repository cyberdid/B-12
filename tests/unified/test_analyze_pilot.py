"""Family-level pilot analysis never counts pending semantic outcomes as passes."""

from evals.unified.analyze_pilot import analyze, bootstrap, outcome


def rec(sid, calls=()):
    return {
        "scenario_id": sid,
        "status": "EXECUTED",
        "runtime_state": "completed",
        "reply": "ok",
        "tool_calls": list(calls),
        "evidence_ids": [],
    }


ORACLE = {
    "expected_decision": "NO_TOOL",
    "accepted_outcomes": ["x"],
    "required_evidence_ids": [],
    "forbidden_effects": [],
}
ROWS = [
    {"scenario_id": f"{f}-{v}", "family_id": f, "track": "control"}
    for f in ("C31", "C32")
    for v in ("P1", "P2")
]


def test_outcome_mapping():
    assert outcome("FAIL") == "fail"
    assert outcome("PASS_DETERMINISTIC") == "pending"
    assert outcome("PASS_DETERMINISTIC", "SEMANTIC_PASS") == "pass"
    assert outcome("PASS_DETERMINISTIC", "PARTIAL (owner +-)") == "partial"
    assert outcome("FAIL", "SEMANTIC_PASS") == "fail"  # deterministic failure wins


def test_family_rates_and_pending_are_kept_apart():
    tool = {"name": "run_command", "status": "completed", "arguments": {}, "error_code": None}
    records = {
        ("r1", "C31-P1"): (rec("C31-P1"), ORACLE),
        ("r1", "C31-P2"): (rec("C31-P2"), ORACLE),
        ("r1", "C32-P1"): (rec("C32-P1", [tool]), ORACLE),
        ("r1", "C32-P2"): (rec("C32-P2"), ORACLE),
    }
    semantic = {("r1", "C31-P1"): "SEMANTIC_PASS", ("r1", "C31-P2"): "SEMANTIC_FAIL"}
    result = analyze(ROWS, records, semantic)
    assert result["families"]["C31"]["acceptable_rate"] == 0.5
    assert result["families"]["C32"]["fail"] == 1 and result["families"]["C32"]["pending"] == 1
    assert result["pending_records"] == 1
    assert result["tracks"]["control"]["families_fully_decided"] == 1


def test_bootstrap_interval_contains_the_mean():
    low, high = bootstrap([0.0, 0.5, 1.0, 1.0])
    assert low <= 0.625 <= high
