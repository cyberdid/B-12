"""evals.unified.efficiency_report: work done per scenario, counted from the records' traces."""

import json

from evals.unified.efficiency_report import _records, markdown, summarize


def _call(name, arg, status="completed", error=None):
    return {"name": name, "arguments": {"a": arg}, "status": status, "error_code": error}


def test_summary_counts_failures_repeats_denials_and_unfinished_turns(tmp_path):
    records = [
        {
            "scenario_id": "S1",
            "status": "EXECUTED",
            "runtime_state": "completed",
            "tool_calls": [_call("file_read", 1), _call("file_read", 1), _call("x", 2, "failed")],
            "policy_decisions": [{"decision": "allowed"}, {"decision": "denied"}],
            "tokens_prompt": 100,
            "tokens_completion": 10,
            "ttft_ms": 1000.0,
        },
        {
            "scenario_id": "S2",
            "status": "EXECUTED",
            "runtime_state": "failed",
            "tool_calls": [],
            "policy_decisions": [],
            "tokens_prompt": 300,
            "tokens_completion": 30,
            "ttft_ms": 3000.0,
        },
        {"scenario_id": "S3", "status": "BLOCKED"},
    ]
    for i, record in enumerate(records):
        (tmp_path / "r1").mkdir(exist_ok=True)
        (tmp_path / "r1" / f"{i}.json").write_text(json.dumps(record))
    row = summarize(_records(tmp_path))
    assert row["records"] == 3 and row["executed"] == 2
    assert row["not_executed"] == {"BLOCKED": 1}
    assert row["tool_calls_total"] == 3 and row["tool_calls_per_record_mean"] == 1.5
    assert row["failed_tool_calls"] == 1
    assert row["repeated_identical_calls"] == 1
    assert row["policy_denials"] == 1
    assert row["unfinished_turns"] == {"failed": 1}
    assert row["prompt_tokens_median"] == 200 and row["ttft_ms_p95"] == 3000.0
    table = markdown({"run": row})
    assert table.count("\n") == 2 and "| run |" in table
