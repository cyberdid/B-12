"""Real temporary effects exercise validation, dispatch and result association."""

import asyncio
import time
from dataclasses import replace
from pathlib import Path
from uuid import uuid4

import pytest
from pydantic import BaseModel, ConfigDict, Field

from b12.contracts import Actor, ToolCall


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
        return {"written": True}

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
        return {}

    registry.register("late", "Пізній handler", WriteArgs, late, "host.write")
    result = await registry.execute(call(path, name="late"), context)
    assert result.status == "unknown" and result.outcome_unknown
    assert not path.exists()


@pytest.mark.parametrize("kind", ["sync", "lax", "extras", "nested"])
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
        return {}

    model = {"lax": Lax, "extras": Extras, "nested": Nested}.get(kind, WriteArgs)
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
        return {}

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
        return {}

    registry.register(
        "destructive", "Контрольований effect", WriteArgs, handler, "host.write", risk="destructive"
    )
    request = call(path, name="destructive")
    pending = await registry.execute(request, context)
    assert pending.status == "approval_pending" and not path.exists()
    store.decide_approval(pending.content["operation_id"], True)
    assert (await registry.execute(request, context)).status == "completed"
    assert path.read_text() == "approved"
