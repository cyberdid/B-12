import importlib.util
import json
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator

from b12.agent import TurnEvent

PATH = Path(__file__).resolve().parents[2] / "evals/unified/trace.py"


class TraceTests(unittest.TestCase):
    def test_privacy_and_call_linkage(self):
        self.assertTrue(PATH.exists(), "trace collector missing")
        spec = importlib.util.spec_from_file_location("unified_trace", PATH)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        trace = mod.TraceCollector()
        for event in [
            TurnEvent(
                "tool_started",
                "secret-session",
                "secret-turn",
                "secret-actor",
                1,
                {"call_id": "private-id", "name": "file_read", "arguments": {"path": "/secret"}},
            ),
            TurnEvent(
                "text_delta",
                "secret-session",
                "secret-turn",
                "secret-actor",
                2,
                {"text": "private text"},
            ),
            TurnEvent(
                "tool_result",
                "secret-session",
                "secret-turn",
                "secret-actor",
                3,
                {
                    "call_id": "private-id",
                    "name": "file_read",
                    "status": "completed",
                    "outcome_unknown": False,
                },
            ),
        ]:
            trace.record(event)
        self.assertEqual(len(trace.events), 2)
        self.assertEqual(trace.events[0]["call_ref"], trace.events[1]["call_ref"])
        self.assertNotIn("secret", repr(trace.events))
        self.assertNotIn("private", repr(trace.events))
        self.assertEqual(trace.events[1]["status"], "completed")

    def test_unknown_status_is_not_serialized(self):
        self.assertTrue(PATH.exists(), "trace collector missing")
        spec = importlib.util.spec_from_file_location("unified_trace", PATH)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        trace = mod.TraceCollector()
        trace.record(
            TurnEvent("tool_result", "s", "t", "a", 1, {"call_id": "x", "status": "secret"})
        )
        self.assertNotIn("secret", repr(trace.events))

    def test_cannot_mix_turns_in_one_collector(self):
        self.assertTrue(PATH.exists(), "trace collector missing")
        spec = importlib.util.spec_from_file_location("unified_trace", PATH)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        trace = mod.TraceCollector()
        trace.record(TurnEvent("turn_started", "s", "turn1", "a", 1, {}))
        with self.assertRaises(ValueError):
            trace.record(TurnEvent("turn_started", "s", "turn2", "a", 1, {}))

    def test_jsonl_export_rejects_existing_file_and_private_extra_fields(self):
        import tempfile

        self.assertTrue(PATH.exists())
        spec = importlib.util.spec_from_file_location("unified_trace", PATH)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        trace = mod.TraceCollector()
        trace.record(TurnEvent("turn_started", "s", "t", "a", 1, {}))
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "trace.jsonl"
            trace.write_jsonl(path)
            self.assertIn("turn_started", path.read_text())
            with self.assertRaises(FileExistsError):
                trace.write_jsonl(path)
            trace.events[0]["secret"] = "PRIVATE"
            with self.assertRaises(ValueError):
                trace.write_jsonl(Path(tmp) / "unsafe.jsonl")
            self.assertFalse((Path(tmp) / "unsafe.jsonl").exists())

    def test_tool_use_summary_uses_task_expectation_and_reports_uncertainty(self):
        spec = importlib.util.spec_from_file_location("unified_trace", PATH)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        trace = mod.TraceCollector()
        trace.record(TurnEvent("turn_started", "s", "t", "a", 1, {}))
        trace.record(TurnEvent("turn_completed", "s", "t", "a", 2, {}))
        self.assertEqual(mod.summarize_tool_use(trace, "required"), "model_omitted_tool")
        self.assertEqual(mod.summarize_tool_use(trace, "forbidden"), "no_tool_as_expected")
        trace = mod.TraceCollector()
        for seq, typ, data in [
            (1, "turn_started", {}),
            (2, "tool_started", {"call_id": "one"}),
            (3, "tool_result", {"call_id": "one", "status": "failed", "outcome_unknown": True}),
            (4, "turn_completed", {}),
        ]:
            trace.record(TurnEvent(typ, "s", "t", "a", seq, data))
        self.assertEqual(mod.summarize_tool_use(trace, "required"), "outcome_unknown")

    def test_dropped_event_prevents_omission_claim(self):
        spec = importlib.util.spec_from_file_location("unified_trace", PATH)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        trace = mod.TraceCollector()
        trace.record(TurnEvent("turn_started", "s", "t", "a", 1, {}))
        trace.record(TurnEvent("turn_completed", "s", "t", "a", 3, {}))
        self.assertEqual(mod.summarize_tool_use(trace, "required"), "incomplete_trace")

    def test_pending_call_prevents_success_claim(self):
        spec = importlib.util.spec_from_file_location("unified_trace", PATH)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        trace = mod.TraceCollector()
        for sequence, kind, payload in [
            (1, "turn_started", {}),
            (2, "tool_started", {"call_id": "one"}),
            (3, "tool_result", {"call_id": "one", "status": "completed"}),
            (4, "tool_started", {"call_id": "two"}),
            (5, "turn_completed", {}),
        ]:
            trace.record(TurnEvent(kind, "s", "t", "a", sequence, payload))
        self.assertEqual(mod.summarize_tool_use(trace, "required"), "incomplete_trace")

    def test_versioned_trace_keeps_only_pseudonymous_context_and_policy_outcomes(self):
        from types import SimpleNamespace

        spec = importlib.util.spec_from_file_location("unified_trace", PATH)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        trace = mod.TraceCollector()
        for event in [
            TurnEvent("turn_started", "private-session", "private-turn", "private-actor", 1, {}),
            TurnEvent(
                "tool_started",
                "private-session",
                "private-turn",
                "private-actor",
                2,
                {"call_id": "private-call", "name": "file_read", "arguments": {"path": "/secret"}},
            ),
            TurnEvent(
                "policy_decision",
                "private-session",
                "private-turn",
                "private-actor",
                3,
                {
                    "call_id": "private-call",
                    "operation_id": "private-operation",
                    "decision": "allowed",
                    "phase": "control_prepare",
                    "capability": "filesystem.read",
                },
            ),
            TurnEvent(
                "tool_result",
                "private-session",
                "private-turn",
                "private-actor",
                4,
                {"call_id": "private-call", "name": "file_read", "status": "completed"},
            ),
            TurnEvent("turn_completed", "private-session", "private-turn", "private-actor", 5, {}),
        ]:
            trace.record(event)
        trace.record_turn_result(
            SimpleNamespace(
                actor_id="private-actor",
                session_id="private-session",
                turn_id="private-turn",
                state="completed",
                content="PRIVATE_FINAL_41",
                error_code=None,
                persisted=True,
                evidence_ids=("private-evidence",),
            )
        )
        trace.record_verification("pass", "deterministic_rule", ["evidence_present"])

        assert trace.events[1]["tool"] == "file_read"
        assert trace.events[2]["decision"] == "allowed"
        assert trace.events[2]["call_ref"] == trace.events[1]["call_ref"]
        assert trace.events[2]["operation_ref"] == "operation_1"
        assert trace.events[-1]["final_claim"]["response_present"] is True
        assert trace.events[-1]["final_claim"]["evidence_refs"] == ["evidence_1"]
        assert trace.events[-1]["verification"]["status"] == "pass"
        assert "private-actor" not in repr(trace.events)
        assert "private-operation" not in repr(trace.events)
        assert "private-evidence" not in repr(trace.events)
        assert "PRIVATE_FINAL_41" not in repr(trace.events)
        schema = json.loads((PATH.parent / "trace.schema.json").read_text(encoding="utf-8"))
        validator = Draft202012Validator(schema)
        assert all(not list(validator.iter_errors(row)) for row in trace.events)

    def test_policy_missing_is_not_silently_called_allowed(self):
        spec = importlib.util.spec_from_file_location("unified_trace", PATH)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        trace = mod.TraceCollector()
        for sequence, kind, data in [
            (1, "turn_started", {}),
            (2, "tool_started", {"call_id": "one", "name": "file_read"}),
            (3, "tool_result", {"call_id": "one", "status": "completed"}),
            (4, "turn_completed", {}),
        ]:
            trace.record(TurnEvent(kind, "s", "t", "a", sequence, data))
        self.assertEqual(mod.summarize_tool_use(trace, "required"), "policy_unobserved")

    def test_approval_wait_is_a_valid_nonterminal_control_outcome(self):
        from types import SimpleNamespace

        spec = importlib.util.spec_from_file_location("unified_trace", PATH)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        trace = mod.TraceCollector()
        for sequence, kind, data in [
            (1, "turn_started", {}),
            (2, "tool_started", {"call_id": "call-a", "name": "sudo_exec"}),
            (
                3,
                "policy_decision",
                {
                    "call_id": "call-a",
                    "operation_id": "operation-a",
                    "decision": "approval_required",
                    "phase": "control_prepare",
                    "capability": "process.sudo",
                },
            ),
            (
                4,
                "approval_pending",
                {"call_id": "call-a", "operation_id": "operation-a", "name": "sudo_exec"},
            ),
        ]:
            trace.record(TurnEvent(kind, "s", "t", "a", sequence, data))
        trace.record_turn_result(
            SimpleNamespace(
                session_id="s",
                turn_id="t",
                state="awaiting_approval",
                content="",
                error_code=None,
                persisted=False,
                evidence_ids=(),
            )
        )

        assert trace.events[-1]["final_claim"]["runtime_state"] == "awaiting_approval"
        assert mod.summarize_tool_use(trace, "required") == "approval_required"
        assert mod.summarize_tool_use(trace, "forbidden") == "tool_attempted"
        schema = json.loads((PATH.parent / "trace.schema.json").read_text(encoding="utf-8"))
        validator = Draft202012Validator(schema)
        assert all(not list(validator.iter_errors(row)) for row in trace.events)
