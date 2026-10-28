from uuid import uuid4

import pytest
from pydantic import ValidationError

from b12.contracts import Actor, MemoryRecord, ModelReply, ToolCall, ToolResult


@pytest.mark.parametrize("actor_id", ["", " \t", "x" * 129, "guest\nadmin", "guest\x7f"])
def test_actor_rejects_invalid_identity(actor_id):
    with pytest.raises(ValidationError):
        Actor(id=actor_id)


@pytest.mark.parametrize("field", ["owner", "consent"])
@pytest.mark.parametrize("value", ["true", "false", 1, 0, None])
def test_text_or_numbers_cannot_become_control_grants(field, value):
    with pytest.raises(ValidationError):
        Actor(id="guest", **{field: value})


def test_actor_is_frozen_and_forbids_untrusted_fields():
    actor = Actor(id="owner", owner=True, consent=True)
    with pytest.raises(ValidationError):
        actor.consent = False
    with pytest.raises(ValidationError):
        Actor(id="guest", approved=True)
    assert actor.model_dump() == {
        "schema_version": 1,
        "id": "owner",
        "owner": True,
        "consent": True,
    }


def memory_data(**changes):
    return {
        "id": str(uuid4()),
        "owner_id": "owner",
        "kind": "fact",
        "text": "Пам’ять",
        "source": "event-17",
        "created_at": "2026-10-24T18:00:00+00:00",
        **changes,
    }


@pytest.mark.parametrize(
    "changes",
    [
        {"id": "not-a-uuid"},
        {"evidence_ids": ("not-a-uuid",)},
        {"owner_id": " "},
        {"source": ""},
        {"kind": " "},
        {"text": " "},
        {"created_at": "2026-10-24T18:00:00"},
        {"created_at": "yesterday"},
        {"created_at": "2026-10-24T18:00:00+03:00"},
        {"created_at": "2026-10-24T18:00:00+0000"},
    ],
)
def test_memory_rejects_invalid_provenance(changes):
    with pytest.raises(ValidationError):
        MemoryRecord(**memory_data(**changes))


def test_memory_json_roundtrip_preserves_provenance():
    record = MemoryRecord(**memory_data(evidence_ids=(str(uuid4()),)))
    assert MemoryRecord.model_validate_json(record.model_dump_json()) == record


def test_memory_accepts_zulu_utc_timestamp():
    record = MemoryRecord(**memory_data(created_at="2026-10-24T18:00:00Z"))
    assert record.created_at == "2026-10-24T18:00:00Z"


@pytest.mark.parametrize("call_id", ["call_ollama_0", "a2f:opaque-17"])
def test_tool_identifiers_accept_opaque_model_ids(call_id):
    call = ToolCall(id=call_id, name="memory.search", arguments={"query": "ехо"})
    result = ToolResult(call_id=call.id, name=call.name, status="ok", content={"hits": []})
    assert result.call_id == call.id


@pytest.mark.parametrize("call_id", ["", " ", "call\n0", "x" * 129])
def test_tool_identifiers_reject_invalid_ids(call_id):
    with pytest.raises(ValidationError):
        ToolCall(id=call_id, name="time", arguments={})


@pytest.mark.parametrize("field", ["turn_id", "task_id"])
def test_tool_call_origin_is_an_application_uuid(field):
    origin_id = str(uuid4())
    call = ToolCall(id="model-call", name="time", arguments={}, **{field: origin_id})
    assert getattr(call, field) == origin_id
    with pytest.raises(ValidationError):
        ToolCall(id="model-call", name="time", arguments={}, **{field: "arbitrary"})


def test_uncertain_tool_effects_survive_serialization():
    result = ToolResult(
        call_id="a",
        name="shell_exec",
        status="error",
        content={},
        side_effects=({"path": "/tmp/output", "state": "possibly_written"},),
        outcome_unknown=True,
    )
    restored = ToolResult.model_validate_json(result.model_dump_json())
    assert restored.outcome_unknown is True
    assert restored.side_effects == ({"path": "/tmp/output", "state": "possibly_written"},)


def test_unsupported_contract_schema_version_is_rejected():
    with pytest.raises(ValidationError):
        ModelReply(schema_version=2)
    assert ModelReply().model_dump()["schema_version"] == 1


@pytest.mark.parametrize("duration", [-1, float("nan"), float("inf")])
def test_tool_result_duration_is_finite_and_nonnegative(duration):
    with pytest.raises(ValidationError):
        ToolResult(call_id="a", name="time", status="ok", content={}, duration_ms=duration)


@pytest.mark.parametrize("arguments", [{"value": object()}, {"value": float("nan")}, {1: "v"}])
def test_tool_arguments_are_json_values(arguments):
    with pytest.raises(ValidationError):
        ToolCall(id="a", name="time", arguments=arguments)


def test_reply_mutable_defaults_are_independent():
    first, second = ModelReply(), ModelReply()
    first.metrics["prompt_tokens"] = 10
    assert second.metrics == {}
    assert first.tool_calls == second.tool_calls == ()


def test_models_do_not_share_caller_payloads():
    payload = {"hits": []}
    first = ToolResult(call_id="a", name="search", status="ok", content=payload)
    second = ToolResult(call_id="b", name="search", status="ok", content=payload)
    first.content["other"] = 1
    assert "other" not in second.content
