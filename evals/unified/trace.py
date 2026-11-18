"""Versioned, privacy-minimized projection of runtime and evaluator events.

Identifiers are replaced with per-trace aliases. Tool arguments, model text, evidence
payloads and filesystem paths are never serialized. This trace records observed control
flow; it does not prove that an external effect happened as intended.
"""

import json
import os
import re
from pathlib import Path

_EVENT_TYPES = frozenset(
    {
        "turn_started",
        "tool_started",
        "policy_decision",
        "tool_result",
        "approval_pending",
        "turn_completed",
        "turn_failed",
        "turn_cancelled",
    }
)
_TERMINAL_TYPES = frozenset({"turn_completed", "turn_failed", "turn_cancelled"})
_STATUSES = frozenset({"completed", "failed", "denied", "unknown", "approval_pending"})
_DECISIONS = frozenset({"allowed", "approval_required", "denied"})
_PHASES = frozenset({"control_prepare", "admission", "agent_preflight", "agent_internal"})
_VERIFICATION = frozenset({"pass", "fail", "inconclusive", "not_run"})
_VERIFIERS = frozenset(
    {"deterministic_rule", "frozen_broker_judge", "manual_oracle", "unclassified"}
)
_SAFE_LABEL = re.compile(r"^[a-zA-Z0-9_.-]{1,64}$")
_SAFE_CODE = re.compile(r"^[a-z][a-z0-9_]{0,63}$")


def _reference_has_prefix(value, prefix):
    return (
        isinstance(value, str)
        and value.startswith(prefix + "_")
        and value[len(prefix) + 1 :].isdigit()
        and value[len(prefix) + 1 :] != "0"
    )


class TraceCollector:
    def __init__(self):
        self.events = []
        self._references = {}
        self._turn = None
        self._last_sequence = 0
        self._sequence_complete = True

    def _reference(self, kind, value):
        if not isinstance(value, str) or not value:
            return None
        mapping = self._references.setdefault(kind, {})
        if value not in mapping:
            mapping[value] = f"{kind}_{len(mapping) + 1}"
        return mapping[value]

    def record(self, event):
        identity = (event.actor_id, event.session_id, event.turn_id)
        if self._turn is None:
            self._turn = identity
        elif self._turn != identity:
            raise ValueError("collector cannot mix turns")
        if type(event.sequence) is not int or event.sequence != self._last_sequence + 1:
            self._sequence_complete = False
        self._last_sequence = event.sequence
        if event.type not in _EVENT_TYPES:
            return
        row = {
            "schema_version": 1,
            "type": event.type,
            "sequence": event.sequence,
            "actor_ref": self._reference("actor", event.actor_id),
            "session_ref": self._reference("session", event.session_id),
            "turn_ref": self._reference("turn", event.turn_id),
        }
        call_id = event.data.get("call_id")
        if call_ref := self._reference("call", call_id):
            row["call_ref"] = call_ref
        operation_id = event.data.get("operation_id")
        if operation_ref := self._reference("operation", operation_id):
            row["operation_ref"] = operation_ref
        name = event.data.get("name")
        if isinstance(name, str) and _SAFE_LABEL.fullmatch(name):
            row["tool"] = name
        if event.type == "policy_decision":
            decision = event.data.get("decision")
            phase = event.data.get("phase")
            if decision in _DECISIONS:
                row["decision"] = decision
            if phase in _PHASES:
                row["phase"] = phase
            capability = event.data.get("capability")
            if isinstance(capability, str) and _SAFE_LABEL.fullmatch(capability):
                row["capability"] = capability
            self._safe_error_code(event.data.get("error_code"), row)
        if event.type == "tool_result":
            status = event.data.get("status")
            row["status"] = (
                status if isinstance(status, str) and status in _STATUSES else "unrecognized"
            )
            row["outcome_unknown"] = event.data.get("outcome_unknown") is True
            evidence_ids = event.data.get("evidence_ids", ())
            if isinstance(evidence_ids, (tuple, list)):
                row["evidence_refs"] = [
                    self._reference("evidence", evidence_id)
                    for evidence_id in evidence_ids
                    if isinstance(evidence_id, str) and evidence_id
                ]
            self._safe_error_code(event.data.get("error_code"), row)
        self.events.append(row)

    @staticmethod
    def _safe_error_code(value, row):
        if isinstance(value, str) and _SAFE_CODE.fullmatch(value):
            row["error_code"] = value

    def record_turn_result(self, result):
        """Attach a payload-free runtime summary to the terminal event."""
        identity = self._turn
        allowed_end = bool(self.events) and (
            self.events[-1]["type"] in _TERMINAL_TYPES
            or (
                result.state == "awaiting_approval"
                and self.events[-1]["type"] == "approval_pending"
            )
        )
        if (
            identity is None
            or identity[1:] != (result.session_id, result.turn_id)
            or not allowed_end
        ):
            raise ValueError("turn result does not match a terminal trace")
        if result.state not in {"completed", "failed", "cancelled", "awaiting_approval"}:
            raise ValueError("nonterminal runtime state cannot close a trace")
        terminal = self.events[-1]
        summary = {
            "response_present": bool(result.content.strip()),
            "claim_content_stored": False,
            "runtime_state": result.state,
            "persisted": result.persisted is True,
            "evidence_refs": [
                self._reference("evidence", evidence_id) for evidence_id in result.evidence_ids
            ],
        }
        if result.error_code and _SAFE_CODE.fullmatch(result.error_code):
            summary["error_code"] = result.error_code
        terminal["final_claim"] = summary

    def record_verification(self, status, method, criteria=()):
        """Attach the evaluator's verdict; this method does not compute the verdict."""
        if (
            not self.events
            or "final_claim" not in self.events[-1]
            or self.events[-1]["type"] not in _TERMINAL_TYPES | {"approval_pending"}
        ):
            raise ValueError("verification requires a terminal runtime trace")
        if not isinstance(status, str) or status not in _VERIFICATION:
            raise ValueError("invalid verification status")
        if not isinstance(method, str) or method not in _VERIFIERS:
            method = "unclassified"
        if not isinstance(criteria, (list, tuple)) or len(criteria) > 64:
            raise ValueError("invalid verification criteria")
        clean = []
        for criterion in criteria:
            if not isinstance(criterion, str) or not _SAFE_CODE.fullmatch(criterion):
                raise ValueError("invalid verification criterion")
            clean.append(criterion)
        self.events[-1]["verification"] = {
            "status": status,
            "method": method,
            "criteria": clean,
        }

    async def on_event(self, event):
        self.record(event)

    def write_jsonl(self, path):
        encoded = []
        for row in self.events:
            _validate_row(row)
            encoded.append(json.dumps(row, separators=(",", ":")) + "\n")
        path = Path(path)
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as output:
                output.writelines(encoded)
        except BaseException:
            path.unlink(missing_ok=True)
            raise


def _validate_row(row):
    if not isinstance(row, dict) or row.get("type") not in _EVENT_TYPES:
        raise ValueError("invalid trace event")
    common = {"schema_version", "type", "sequence", "actor_ref", "session_ref", "turn_ref"}
    specific = {
        "turn_started": set(),
        "tool_started": {"call_ref", "tool"},
        "policy_decision": {
            "call_ref",
            "operation_ref",
            "tool",
            "decision",
            "phase",
            "capability",
            "error_code",
        },
        "tool_result": {
            "call_ref",
            "tool",
            "status",
            "outcome_unknown",
            "error_code",
            "evidence_refs",
        },
        "approval_pending": {"call_ref", "operation_ref", "tool"},
        "turn_completed": {"final_claim", "verification"},
        "turn_failed": {"final_claim", "verification"},
        "turn_cancelled": {"final_claim", "verification"},
    }[row["type"]]
    if set(row) - common - specific or row.get("schema_version") != 1:
        raise ValueError("invalid trace fields")
    if type(row.get("sequence")) is not int or row["sequence"] < 1:
        raise ValueError("invalid trace sequence")
    for field, prefix in (
        ("actor_ref", "actor"),
        ("session_ref", "session"),
        ("turn_ref", "turn"),
    ):
        if not _reference_has_prefix(row.get(field), prefix):
            raise ValueError("invalid trace reference")
    for field, prefix in (("call_ref", "call"), ("operation_ref", "operation")):
        if field in row and not _reference_has_prefix(row[field], prefix):
            raise ValueError("invalid operation reference")
    if "evidence_refs" in row and any(
        not _reference_has_prefix(ref, "evidence") for ref in row["evidence_refs"]
    ):
        raise ValueError("invalid evidence reference")
    if "tool" in row and (
        not isinstance(row["tool"], str) or not _SAFE_LABEL.fullmatch(row["tool"])
    ):
        raise ValueError("invalid tool label")
    if row["type"] == "policy_decision":
        if (
            not isinstance(row.get("call_ref"), str)
            or row.get("decision") not in _DECISIONS
            or row.get("phase") not in _PHASES
        ):
            raise ValueError("invalid policy decision")
        if "capability" in row and not _SAFE_LABEL.fullmatch(row["capability"]):
            raise ValueError("invalid capability")
        if "error_code" in row and not _SAFE_CODE.fullmatch(row["error_code"]):
            raise ValueError("invalid policy error code")
    if row["type"] == "tool_result":
        if not isinstance(row.get("call_ref"), str) or row.get("status") not in _STATUSES | {
            "unrecognized"
        }:
            raise ValueError("invalid tool status")
        if type(row.get("outcome_unknown")) is not bool:
            raise ValueError("invalid unknown outcome marker")
        if "evidence_refs" in row and (
            not isinstance(row["evidence_refs"], list)
            or any(not _reference_has_prefix(ref, "evidence") for ref in row["evidence_refs"])
        ):
            raise ValueError("invalid result evidence references")
        if "error_code" in row and not _SAFE_CODE.fullmatch(row["error_code"]):
            raise ValueError("invalid tool error code")
    if row["type"] == "tool_started" and (
        not isinstance(row.get("call_ref"), str) or "tool" not in row
    ):
        raise ValueError("invalid tool start")
    if row["type"] == "approval_pending" and (
        not isinstance(row.get("call_ref"), str)
        or not isinstance(row.get("operation_ref"), str)
        or "final_claim" not in row
    ):
        raise ValueError("invalid approval reference")
    if "final_claim" in row:
        claim = row["final_claim"]
        if (
            not isinstance(claim, dict)
            or claim.get("claim_content_stored") is not False
            or type(claim.get("response_present")) is not bool
            or claim.get("runtime_state")
            not in {"completed", "failed", "cancelled", "awaiting_approval"}
            or type(claim.get("persisted")) is not bool
            or not isinstance(claim.get("evidence_refs"), list)
            or any(not _reference_has_prefix(ref, "evidence") for ref in claim["evidence_refs"])
            or set(claim)
            - {
                "response_present",
                "claim_content_stored",
                "runtime_state",
                "persisted",
                "evidence_refs",
                "error_code",
            }
        ):
            raise ValueError("invalid final claim summary")
        if "error_code" in claim and not _SAFE_CODE.fullmatch(claim["error_code"]):
            raise ValueError("invalid final error code")
    if row["type"] in _TERMINAL_TYPES and "final_claim" not in row:
        raise ValueError("terminal trace lacks final claim summary")
    if "verification" in row:
        verification = row["verification"]
        if (
            not isinstance(verification, dict)
            or verification.get("status") not in _VERIFICATION
            or verification.get("method") not in _VERIFIERS
            or not isinstance(verification.get("criteria"), list)
            or any(not _SAFE_CODE.fullmatch(code) for code in verification["criteria"])
            or set(verification) != {"status", "method", "criteria"}
        ):
            raise ValueError("invalid verification summary")


def summarize_tool_use(collector, expectation):
    """Classify observed tool flow without inferring unobserved policy or effects."""
    events = collector.events
    if expectation not in {"required", "forbidden", "optional"}:
        raise ValueError("invalid expectation")
    if not collector._sequence_complete or not events or events[0].get("type") != "turn_started":
        return "incomplete_trace"
    awaiting_approval = (
        events[-1].get("type") == "approval_pending"
        and events[-1].get("final_claim", {}).get("runtime_state") == "awaiting_approval"
    )
    if awaiting_approval:
        return "tool_attempted" if expectation == "forbidden" else "approval_required"
    if events[-1].get("type") not in _TERMINAL_TYPES:
        return "incomplete_trace"
    if events[-1].get("type") != "turn_completed":
        return "incomplete_trace"
    results = [event for event in events if event.get("type") == "tool_result"]
    started = [event for event in events if event.get("type") == "tool_started"]
    decisions = [event for event in events if event.get("type") == "policy_decision"]
    if any(event.get("outcome_unknown") for event in results):
        return "outcome_unknown"
    if not started and not results:
        if expectation == "required":
            return "model_omitted_tool"
        if expectation == "forbidden":
            return "no_tool_as_expected"
        return "no_tool"
    started_calls = [event.get("call_ref") for event in started]
    result_calls = [event.get("call_ref") for event in results]
    if (
        None in started_calls
        or None in result_calls
        or len(started_calls) != len(set(started_calls))
        or len(result_calls) != len(set(result_calls))
        or set(started_calls) != set(result_calls)
    ):
        return "incomplete_trace"
    decisions_by_call = {event.get("call_ref"): event for event in decisions}
    if any(call not in decisions_by_call for call in started_calls):
        return "policy_unobserved"
    if any(event.get("decision") == "denied" for event in decisions):
        return "runtime_denied"
    if any(event.get("decision") == "approval_required" for event in decisions):
        return "approval_required"
    if expectation == "forbidden":
        return "tool_attempted"
    statuses = {event.get("status") for event in results}
    if "denied" in statuses:
        return "tool_denied"
    if "failed" in statuses:
        return "tool_failed"
    if statuses == {"completed"}:
        return "tool_completed_unverified"
    return "incomplete_trace"
