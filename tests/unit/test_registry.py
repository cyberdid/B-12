"""Real temporary effects exercise validation, dispatch and result association."""

import asyncio
import json
import time
from dataclasses import replace
from pathlib import Path
from uuid import uuid4

import pytest
from pydantic import BaseModel, ConfigDict, Field

from b12.contracts import Actor, ToolCall
from b12.tools.outcomes import HandlerOutcome


class WriteArgs(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    path: str = Field(min_length=1, pattern=r"^/[^\x00]+$")
    number: int


@pytest.fixture
def rig(tmp_path):
    from b12.control import ControlStore
    from b12.tools.registry import ToolRegistry

    store = ControlStore(tmp_path / "control")
    actor = store.create_actor(owner=True, consent=True)
    session = store.create_session(actor.id)
    grant = store.issue_grant(actor.id, session, ("host.write",))
    context = store.begin_turn(session, grant, deadline=time.monotonic() + 5)
    registry = ToolRegistry(store, timeout_s=1)

    async def write(args, effect):
        effect.check()
        Path(args.path).write_text(str(args.number))
        return HandlerOutcome(content={"written": True})

    registry.register("write", "Записати число", WriteArgs, write, "host.write")
    yield store, registry, context, tmp_path / "effect"
    store.close()


def call(path, **changes):
    return ToolCall(
        id=changes.pop("id", "call-1"),
        name=changes.pop("name", "write"),
        arguments={"path": str(path), "number": 7, **changes},
    )


async def test_authorized_real_effect_and_exact_result(rig):
    _, registry, context, path = rig
    result = await registry.execute(call(path), context)
    assert (result.call_id, result.name, result.status) == ("call-1", "write", "completed")
    assert path.read_text() == "7"
    assert not result.outcome_unknown


@pytest.mark.parametrize(
    "changes",
    [{"number": "7"}, {"number": True}, {"path": "relative"}, {"approved": True}, {"extra": 1}],
)
async def test_invalid_args_never_reach_handler(rig, changes):
    _, registry, context, path = rig
    request = call(path)
    request.arguments.update(changes)
    result = await registry.execute(request, context)
    assert result.error_code == "invalid_arguments"
    assert not path.exists()


async def test_unknown_tool_is_structured(rig):
    _, registry, context, path = rig
    result = await registry.execute(call(path, name="absent"), context)
    assert result.error_code == "unknown_tool"
    assert result.call_id == "call-1"
    assert not path.exists()


def test_schemas_fresh_stable_and_only_current_authority(rig):
    store, registry, context, _ = rig
    schemas = registry.schemas(context)
    assert schemas[0]["function"]["parameters"]["additionalProperties"] is False
    schemas[0]["function"]["name"] = "corrupt"
    assert registry.schemas(context)[0]["function"]["name"] == "write"
    store.set_consent(context.actor_id, False)
    assert registry.schemas(context) == []


async def test_actor_or_forged_context_is_not_authority(rig):
    _, registry, context, path = rig
    actor = Actor(id=context.actor_id, owner=True, consent=True)
    result = await registry.execute(call(path), actor)
    assert result.error_code == "invalid_context"
    forged = replace(context, credential="fabricated")
    assert (await registry.execute(call(path), forged)).error_code == "invalid_context"
    assert not path.exists()


async def test_origin_must_match_server_context(rig):
    _, registry, context, path = rig
    request = call(path).model_copy(update={"turn_id": str(uuid4())})
    assert (await registry.execute(request, context)).error_code == "origin_mismatch"
    assert not path.exists()


async def test_completed_call_cannot_run_twice(rig):
    _, registry, context, path = rig
    await registry.execute(call(path), context)
    path.unlink()
    result = await registry.execute(call(path), context)
    assert result.error_code == "replay_blocked"
    assert not path.exists()


async def test_handler_failure_is_unknown_and_does_not_leak(rig):
    _, registry, context, path = rig

    async def fail(args, effect):
        effect.check()
        Path(args.path).write_text("once")
        raise RuntimeError("private-output-path")

    registry.register("fail", "Помилка", WriteArgs, fail, "host.write")
    result = await registry.execute(call(path, name="fail"), context)
    assert result.status == "unknown" and result.outcome_unknown
    assert "private-output-path" not in result.model_dump_json()
    assert path.read_text() == "once"


@pytest.mark.parametrize("mode", ["timeout", "cancel", "task_cancel"])
async def test_uncertain_effect_is_persisted_and_never_replayed(rig, mode):
    store, registry, context, path = rig
    entered = asyncio.Event()

    async def slow(args, effect):
        effect.check()
        Path(args.path).write_text("once")
        entered.set()
        await asyncio.Event().wait()

    registry.register("slow", "Повільно", WriteArgs, slow, "host.write")
    registry.timeout_s = 0.03
    task = asyncio.create_task(registry.execute(call(path, name="slow"), context))
    await entered.wait()
    if mode == "cancel":
        context.cancel.set()
    elif mode == "task_cancel":
        task.cancel()
    if mode == "task_cancel":
        with pytest.raises(asyncio.CancelledError):
            await task
    else:
        result = await task
        assert result.outcome_unknown and result.status == "unknown"
    store_path = store.path
    store.close()
    from b12.control import ControlStore
    from b12.tools.registry import ToolRegistry

    restarted = ControlStore(store_path)
    recovered = ToolRegistry(restarted)
    recovered.register("slow", "Повільно", WriteArgs, slow, "host.write")
    resumed = restarted.resume_turn(context.turn_id, deadline=time.monotonic() + 5)
    path.unlink()
    result = await recovered.execute(call(path, name="slow"), resumed)
    assert result.error_code == "replay_blocked" and result.outcome_unknown
    assert not path.exists()
    assert restarted.audit_events()[-1]["state"] == "unknown"
    restarted.close()


async def test_blocking_async_handler_cannot_claim_late_success(rig):
    _, registry, context, path = rig
    registry.timeout_s = 0.01

    async def late(args, effect):
        time.sleep(0.02)  # Contract violation; return must still fail closed.
        effect.check()
        path.write_text("late")
        return HandlerOutcome()

    registry.register("late", "Пізній handler", WriteArgs, late, "host.write")
    result = await registry.execute(call(path, name="late"), context)
    assert result.status == "unknown" and result.outcome_unknown
    assert not path.exists()


@pytest.mark.parametrize("kind", ["sync", "lax", "extras", "nested", "optional", "union"])
def test_registration_rejects_unsafe_contract(rig, kind):
    _, registry, _, _ = rig

    class Lax(BaseModel):
        model_config = ConfigDict(extra="forbid")
        number: int

    class Extras(BaseModel):
        model_config = ConfigDict(strict=True)
        number: int

    class Child(BaseModel):
        number: int

    class Nested(BaseModel):
        model_config = ConfigDict(strict=True, extra="forbid")
        child: Child

    async def handler(args, effect):
        return HandlerOutcome()

    class Optional(BaseModel):
        # anyOf renders differently in Ollama vs the pinned template (+6 tokens observed).
        model_config = ConfigDict(strict=True, extra="forbid")
        number: int | None = None

    class Union(BaseModel):
        model_config = ConfigDict(strict=True, extra="forbid")
        value: int | str

    model = {
        "lax": Lax,
        "extras": Extras,
        "nested": Nested,
        "optional": Optional,
        "union": Union,
    }.get(kind, WriteArgs)
    selected = (lambda args, effect: {}) if kind == "sync" else handler
    with pytest.raises(ValueError):
        registry.register("unsafe", "Unsafe", model, selected, "host.write")


async def test_same_call_concurrent_dispatch_never_duplicates_effect(rig):
    _, registry, context, path = rig
    entered = asyncio.Event()
    finish = asyncio.Event()

    async def handler(args, guard):
        guard.check()
        path.write_text("once")
        entered.set()
        await finish.wait()
        return HandlerOutcome()

    registry.register("concurrent", "Один виклик", WriteArgs, handler, "host.write")
    request = call(path, name="concurrent")
    first = asyncio.create_task(registry.execute(request, context))
    await entered.wait()
    second = await registry.execute(request, context)
    assert second.error_code == "replay_blocked" and second.outcome_unknown
    finish.set()
    assert (await first).status == "completed"
    assert path.read_text() == "once"


async def test_handler_control_error_cannot_put_payload_in_audit(rig):
    store, registry, context, path = rig
    from b12.control import ControlError

    async def handler(args, guard):
        raise ControlError("private-user-text-/private/path")

    registry.register("unsafe_error", "Помилка", WriteArgs, handler, "host.write")
    result = await registry.execute(call(path, name="unsafe_error"), context)
    assert "private-user-text" not in result.model_dump_json()
    assert "private-user-text" not in str(store.audit_events())


async def test_destructive_catalog_risk_requires_exact_approval(rig):
    store, registry, context, path = rig

    async def handler(args, guard):
        guard.check()
        path.write_text("approved")
        return HandlerOutcome()

    registry.register(
        "destructive", "Контрольований effect", WriteArgs, handler, "host.write", risk="destructive"
    )
    request = call(path, name="destructive")
    pending = await registry.execute(request, context)
    assert pending.status == "approval_pending" and not path.exists()
    store.decide_approval(pending.content["operation_id"], True)
    assert (await registry.execute(request, context)).status == "completed"
    assert path.read_text() == "approved"


def outcome_types():
    import importlib.util

    assert importlib.util.find_spec("b12.tools.outcomes"), "typed handler outcomes missing"
    from b12.tools.outcomes import HandlerOutcome, SideEffect

    return HandlerOutcome, SideEffect


async def test_real_effect_and_truncation_propagate_to_typed_result(rig):
    store, registry, context, path = rig
    Outcome, Effect = outcome_types()
    evidence = str(uuid4())

    async def handler(args, guard):
        guard.check()
        path.write_text("effect")
        return Outcome(
            content={"preview": "effect"},
            truncated=True,
            side_effects=(Effect(kind="file_write", state="completed", evidence_ids=(evidence,)),),
        )

    registry.register("outcome", "Effect", WriteArgs, handler, "host.write")
    result = await registry.execute(call(path, name="outcome"), context)
    assert path.read_text() == "effect" and result.status == "completed"
    assert result.truncated and not result.outcome_unknown
    assert result.side_effects[0]["kind"] == "file_write"
    assert result.side_effects[0]["evidence_ids"] == [evidence]
    assert result.side_effects[0]["operation_id"] == store.audit_events()[-1]["operation_id"]
    assert (result.call_id, result.name) == ("call-1", "outcome")


async def test_unknown_outcome_preserves_bounded_evidence_and_blocks_replay(rig):
    store, registry, context, path = rig
    Outcome, Effect = outcome_types()

    async def handler(args, guard):
        guard.check()
        path.write_text("partial")
        return Outcome(
            status="unknown",
            error_code="cleanup_failed",
            truncated=True,
            content={"stdout": "bounded", "cleanup": "unconfirmed"},
            side_effects=(Effect(kind="file_write", state="possible"),),
        )

    registry.register("uncertain", "Effect", WriteArgs, handler, "host.write")
    request = call(path, name="uncertain")
    result = await registry.execute(request, context)
    assert result.status == "unknown" and result.outcome_unknown and result.truncated
    assert result.content == {"stdout": "bounded", "cleanup": "unconfirmed"}
    assert result.side_effects[0]["state"] == "possible"
    assert result.error_code == "cleanup_failed"
    assert store.audit_events()[-1]["state"] == "unknown"
    assert "bounded" not in str(store.audit_events())
    path.unlink()
    assert (await registry.execute(request, context)).error_code == "replay_blocked"
    assert not path.exists()


async def test_failed_outcome_certifies_no_effect_and_persists_failure(rig):
    store, registry, context, path = rig
    Outcome, _ = outcome_types()

    async def handler(args, guard):
        return Outcome(
            status="failed", error_code="permission_denied", content={"reason": "denied"}
        )

    registry.register("clean_fail", "Failure", WriteArgs, handler, "host.write")
    result = await registry.execute(call(path, name="clean_fail"), context)
    assert result.status == "failed" and result.error_code == "permission_denied"
    assert not result.outcome_unknown and not result.side_effects and not path.exists()
    assert store.audit_events()[-1]["state"] == "failed"


@pytest.mark.parametrize(
    "attack",
    [
        "ids",
        "status",
        "control",
        "nested",
        "oversized",
        "nonfinite",
        "failed_effect",
        "completed_possible",
        "error_code",
        "cyclic",
    ],
)
async def test_malformed_handler_outcome_cannot_spoof_or_succeed(rig, attack):
    store, registry, context, path = rig
    Outcome, Effect = outcome_types()

    async def handler(args, guard):
        outcome = Outcome(content={"ok": True})
        if attack == "ids":
            return {"call_id": "spoof", "name": "spoof", "status": "completed", "content": {}}
        if attack == "status":
            outcome = outcome.model_copy(update={"status": "approval_pending"})
        elif attack == "control":
            outcome.__dict__["grant_id"] = "spoof"
        elif attack == "nested":
            effect = Effect(kind="file_write", state="completed")
            effect.__dict__["actor_id"] = "spoof"
            outcome = outcome.model_copy(update={"side_effects": (effect,)})
        elif attack == "oversized":
            outcome = outcome.model_copy(update={"content": {"text": "ї" * 40000}})
        elif attack == "nonfinite":
            outcome = outcome.model_copy(update={"content": {"value": float("nan")}})
        elif attack == "failed_effect":
            outcome = outcome.model_copy(
                update={
                    "status": "failed",
                    "error_code": "handler_failed",
                    "side_effects": (Effect(kind="file_write", state="completed"),),
                }
            )
        elif attack == "completed_possible":
            outcome = outcome.model_copy(
                update={"side_effects": (Effect(kind="file_write", state="possible"),)}
            )
        elif attack == "error_code":
            outcome = outcome.model_copy(update={"status": "unknown", "error_code": "private-text"})
        elif attack == "cyclic":
            cyclic = {}
            cyclic["self"] = cyclic
            outcome = outcome.model_copy(update={"content": cyclic})
        return outcome

    registry.register("malformed", "Malformed", WriteArgs, handler, "host.write")
    result = await registry.execute(call(path, name="malformed"), context)
    assert (result.call_id, result.name) == ("call-1", "malformed")
    assert result.status == "unknown" and result.outcome_unknown
    assert result.error_code == "invalid_handler_outcome"
    assert store.audit_events()[-1]["state"] == "unknown"
    assert not path.exists()


@pytest.mark.parametrize("interruption", ["timeout", "cancel"])
async def test_interrupted_cleanup_preserves_bounded_handler_evidence(rig, interruption):
    store, registry, context, path = rig
    Outcome, Effect = outcome_types()
    entered = asyncio.Event()
    registry.timeout_s = 0.03

    async def handler(args, guard):
        guard.check()
        path.write_text("started")
        entered.set()
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            return Outcome(
                status="unknown",
                error_code="cleanup_failed",
                truncated=True,
                content={"stdout": "partial-output", "cleanup": "unconfirmed"},
                side_effects=(Effect(kind="file_write", state="possible"),),
            )

    registry.register("cleanup", "Cleanup", WriteArgs, handler, "host.write")
    task = asyncio.create_task(registry.execute(call(path, name="cleanup"), context))
    await entered.wait()
    if interruption == "cancel":
        context.cancel.set()
    result = await task
    assert result.status == "unknown" and result.outcome_unknown and result.truncated
    assert result.content == {"stdout": "partial-output", "cleanup": "unconfirmed"}
    assert result.side_effects[0]["state"] == "possible"
    assert result.error_code == ("cancelled" if interruption == "cancel" else "deadline_exceeded")
    assert store.audit_events()[-1]["state"] == "unknown"
    assert "partial-output" not in str(store.audit_events())


async def test_invalid_arguments_name_fields_without_echoing_values(rig):
    _, registry, context, path = rig
    secret = "PRIVATE-VALUE-not-to-echo"
    request = ToolCall(
        id="bad-args",
        name="write",
        arguments={"path": str(path), "number": secret, "surplus": secret},
    )
    result = await registry.execute(request, context)
    assert (result.status, result.error_code) == ("denied", "invalid_arguments")
    fields = {(item["field"], item["error"]) for item in result.content["invalid_fields"]}
    assert ("number", "int_type") in fields and ("surplus", "extra_forbidden") in fields
    assert secret not in json.dumps(result.model_dump()) and not path.exists()
