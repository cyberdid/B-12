"""Runtime integration with a scripted local model; no real inference."""

import importlib.util
from pathlib import Path

from b12.runtime import open_runtime


def collector():
    path = Path(__file__).resolve().parents[2] / "evals/unified/trace.py"
    spec = importlib.util.spec_from_file_location("unified_trace_runtime", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.TraceCollector()


async def test_trace_captures_real_loop_without_payloads(scripted_ollama, tmp_path):
    state, settings = scripted_ollama
    runtime = open_runtime(settings.model_copy(update={"state_dir": tmp_path / "state"}))
    try:
        actor = runtime.control.create_actor(owner=True, consent=True)
        session = runtime.control.create_session(actor.id)
        task = runtime.control.create_task(session)
        grant = runtime.control.issue_grant(actor.id, session, ("filesystem.read",), task_id=task)
        target = tmp_path / "secret-name.txt"
        target.write_text("PRIVATE_PAYLOAD_741")
        state["script"] = [
            {"tool_calls": [("file_read", {"path": str(target)})]},
            {"content": "The file was read."},
        ]
        trace = collector()
        result = await runtime.agent.turn(
            session, grant, "Read this file.", task_id=task, on_event=trace.on_event
        )
        assert result.state == "completed"
        trace.record_turn_result(result)
        trace.record_verification("pass", "deterministic_rule", ["file_read_completed"])
        assert [row["type"] for row in trace.events] == [
            "turn_started",
            "tool_started",
            "policy_decision",
            "tool_result",
            "turn_completed",
        ]
        assert trace.events[1]["call_ref"] == trace.events[2]["call_ref"]
        assert trace.events[2]["decision"] == "allowed"
        assert trace.events[3]["status"] == "completed"
        assert trace.events[-1]["verification"]["status"] == "pass"
        assert "PRIVATE_PAYLOAD_741" not in repr(trace.events)
        assert str(target) not in repr(trace.events)
        assert actor.id not in repr(trace.events)
    finally:
        runtime.close()


async def test_file_effect_is_verified_independently_of_model_text(scripted_ollama, tmp_path):
    import hashlib

    state, settings = scripted_ollama
    runtime = open_runtime(settings.model_copy(update={"state_dir": tmp_path / "state"}))
    try:
        actor = runtime.control.create_actor(owner=True, consent=True)
        session = runtime.control.create_session(actor.id)
        task = runtime.control.create_task(session)
        grant = runtime.control.issue_grant(
            actor.id, session, ("filesystem.write",), task_id=task, full_execution=True
        )
        target = tmp_path / "output.txt"
        state["script"] = [
            {"tool_calls": [("file_write", {"path": str(target), "text": "synthetic result"})]},
            {"content": "Done."},
        ]
        result = await runtime.agent.turn(session, grant, "Write the file.", task_id=task)
        assert result.state == "completed"
        path = Path(__file__).resolve().parents[2] / "evals/unified/file_verifier.py"
        spec = importlib.util.spec_from_file_location("unified_file_verifier", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        expected = hashlib.sha256(b"synthetic result").hexdigest()
        assert module.verify_file(tmp_path, "output.txt", expected) == "verified"
        target.write_text("changed")
        assert module.verify_file(tmp_path, "output.txt", expected) == "mismatch"
    finally:
        runtime.close()


async def test_trace_links_retrieved_memory_to_final_claim_without_storing_payload(
    scripted_ollama, tmp_path
):
    state, settings = scripted_ollama
    runtime = open_runtime(settings.model_copy(update={"state_dir": tmp_path / "state"}))
    try:
        actor = runtime.control.create_actor(owner=True, consent=True)
        session = runtime.control.create_session(actor.id)
        task = runtime.control.create_task(session)
        grant = runtime.control.issue_grant(actor.id, session, ("memory.read",), task_id=task)
        record = runtime.memory.remember(
            "synthetic evidence marker: prefers jasmine tea", actor, source="test fixture"
        )
        state["script"] = [
            {"tool_calls": [("memory_search", {"query": "synthetic evidence marker"})]},
            {"content": "The stored preference is jasmine tea."},
        ]
        trace = collector()
        result = await runtime.agent.turn(
            session, grant, "What preference was stored?", task_id=task, on_event=trace.on_event
        )
        assert result.state == "completed"
        trace.record_turn_result(result)
        tool_result = next(row for row in trace.events if row["type"] == "tool_result")
        assert tool_result["evidence_refs"] == ["evidence_1"]
        assert trace.events[-1]["final_claim"]["evidence_refs"] == ["evidence_1"]
        assert record.id not in repr(trace.events)
        assert "jasmine tea" not in repr(trace.events)
    finally:
        runtime.close()
