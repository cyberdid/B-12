"""Synthetic persisted control and one-shot boundaries; no real host tools."""

import asyncio
import json
import stat
import time
from dataclasses import FrozenInstanceError, replace

import pytest
from pydantic import BaseModel, ConfigDict

from b12.contracts import ToolCall


@pytest.fixture
def policy_rig(tmp_path):
    from b12.control import ControlStore
    from b12.tools.registry import ToolRegistry

    class Args(BaseModel):
        model_config = ConfigDict(strict=True, extra="forbid")
        executable: str
        argv: list[str]
        cwd: str
        declared_effects: list[str]

    store = ControlStore(tmp_path / "private")
    owner = store.create_actor(owner=True, consent=True)
    guest = store.create_actor(consent=True)
    session = store.create_session(owner.id)
    task = store.create_task(session)
    grant = store.issue_grant(owner.id, session, ("host.exec", "host.write"), task_id=task)
    context = store.begin_turn(session, grant, task_id=task, deadline=time.monotonic() + 5)
    registry = ToolRegistry(store)
    path = tmp_path / "effect"

    async def effect(args, guard):
        guard.check()
        path.write_text("effect")
        return {"done": True}

    registry.register("exec", "Виконання", Args, effect, "host.exec", risk="arbitrary")
    registry.register("typed", "Запис", Args, effect, "host.write")
    request = ToolCall(
        id="native-opaque-id",
        name="exec",
        arguments={
            "executable": "/private/interpreter",
            "argv": ["private text"],
            "cwd": "/private/cwd",
            "declared_effects": ["write"],
        },
    )
    yield store, registry, context, request, path, guest
    store.close()


@pytest.mark.parametrize(
    "mutation,code",
    [
        ("consent", "consent_required"),
        ("revoked", "grant_revoked"),
        ("expired", "grant_expired"),
        ("revision", "stale_control"),
        ("session", "invalid_context"),
        ("actor", "invalid_context"),
    ],
)
async def test_server_state_is_authority(policy_rig, mutation, code):
    store, registry, ctx, request, path, guest = policy_rig
    if mutation == "consent":
        store.set_consent(ctx.actor_id, False)
    elif mutation == "revoked":
        store.revoke_grant(ctx.grant_id)
    elif mutation == "expired":
        store.db.execute("UPDATE grants SET expires_at=0")
        store.db.commit()
    elif mutation == "revision":
        store.set_consent(ctx.actor_id, True)
    elif mutation == "session":
        ctx = replace(ctx, session_id=store.create_session(ctx.actor_id))
    else:
        ctx = replace(ctx, actor_id=guest.id)
    result = await registry.execute(request, ctx)
    assert result.error_code == code
    assert not path.exists()


async def test_guest_cannot_use_owner_grant(policy_rig):
    store, _, ctx, _, _, guest = policy_rig
    session = store.create_session(guest.id)
    with pytest.raises(PermissionError):
        store.begin_turn(session, ctx.grant_id, deadline=time.monotonic() + 3)


async def test_approval_is_pending_persistent_exact_and_one_shot(policy_rig):
    store, registry, ctx, request, path, _ = policy_rig
    result = await registry.execute(request, ctx)
    assert result.status == "approval_pending" and result.call_id == request.id
    operation = result.content["operation_id"]
    assert not path.exists()
    store.decide_approval(operation, True)
    result = await registry.execute(request, ctx)
    assert result.status == "completed" and path.exists()
    path.unlink()
    assert (await registry.execute(request, ctx)).error_code == "replay_blocked"
    assert not path.exists()
    assert store.db.execute("SELECT digest FROM approvals").fetchone()[0] is None


@pytest.mark.parametrize("alter", ["args", "call", "turn", "session"])
async def test_approval_cannot_be_rebound(policy_rig, alter):
    store, registry, ctx, request, path, _ = policy_rig
    pending = await registry.execute(request, ctx)
    store.decide_approval(pending.content["operation_id"], True)
    if alter == "args":
        request.arguments["argv"] = ["different"]
    elif alter == "call":
        request = request.model_copy(update={"id": "other"})
    elif alter == "turn":
        ctx = store.begin_turn(
            ctx.session_id, ctx.grant_id, task_id=ctx.task_id, deadline=time.monotonic() + 5
        )
    else:
        session = store.create_session(ctx.actor_id)
        grant = store.issue_grant(ctx.actor_id, session, ("host.exec",))
        ctx = store.begin_turn(session, grant, deadline=time.monotonic() + 5)
    assert (await registry.execute(request, ctx)).status != "completed"
    assert not path.exists()


async def test_stale_or_denied_or_expired_approval_never_executes(policy_rig):
    store, registry, ctx, request, path, _ = policy_rig
    pending = await registry.execute(request, ctx)
    store.decide_approval(pending.content["operation_id"], False)
    assert (await registry.execute(request, ctx)).error_code == "approval_denied"
    assert not path.exists()


async def test_explicit_task_arbitrary_grant_and_typed_tools_no_prompt(policy_rig):
    store, registry, ctx, request, path, _ = policy_rig
    typed = request.model_copy(update={"name": "typed"})
    assert (await registry.execute(typed, ctx)).status == "completed"
    path.unlink()
    grant = store.issue_grant(
        ctx.actor_id, ctx.session_id, ("host.exec",), task_id=ctx.task_id, full_execution=True
    )
    ctx = store.begin_turn(
        ctx.session_id, grant, task_id=ctx.task_id, deadline=time.monotonic() + 5
    )
    request = request.model_copy(update={"id": "explicit"})
    assert (await registry.execute(request, ctx)).status == "completed"
    assert path.exists()


async def test_revision_checked_at_effect_and_audit_has_no_payload(policy_rig):
    store, registry, ctx, request, path, _ = policy_rig
    from b12.tools.registry import ToolRegistry

    class Args(BaseModel):
        model_config = ConfigDict(strict=True, extra="forbid")
        text: str

    entered, proceed = asyncio.Event(), asyncio.Event()

    async def late(args, guard):
        entered.set()
        await proceed.wait()
        guard.check()
        path.write_text(args.text)
        return {}

    registry = ToolRegistry(store)
    registry.register("late", "Пізній запис", Args, late, "host.write")
    request = ToolCall(id="sensitive-call-id", name="late", arguments={"text": "sensitive"})
    task = asyncio.create_task(registry.execute(request, ctx))
    await entered.wait()
    store.set_consent(ctx.actor_id, False)
    proceed.set()
    assert (await task).status != "completed"
    assert not path.exists()
    audit = json.dumps(store.audit_events())
    assert all(secret not in audit for secret in ["sensitive", "/private", "digest", "argv"])
    assert stat.S_IMODE(store.path.stat().st_mode) == 0o700
    for file in store.path.iterdir():
        assert stat.S_IMODE(file.stat().st_mode) == 0o600
    with pytest.raises(FrozenInstanceError):
        ctx.actor_id = "forged"


@pytest.mark.parametrize("field", ["deadline", "cancel"])
async def test_runtime_context_limits_cannot_be_replaced(policy_rig, field):
    _, registry, ctx, request, path, _ = policy_rig
    forged = replace(
        ctx,
        **(
            {"deadline": ctx.deadline + 100} if field == "deadline" else {"cancel": asyncio.Event()}
        ),
    )
    assert (
        await registry.execute(request.model_copy(update={"name": "typed"}), forged)
    ).error_code == "invalid_context"
    assert not path.exists()


@pytest.mark.parametrize("state", ["pending", "approved", "started"])
async def test_restart_keeps_pending_and_unknown_without_automatic_effect(policy_rig, state):
    store, registry, ctx, request, path, _ = policy_rig
    pending = await registry.execute(request, ctx)
    operation = pending.content["operation_id"]
    if state != "pending":
        store.decide_approval(operation, True)
    if state == "started":
        # Real persisted start/effect, then process boundary without finish acknowledgement.
        assert store.prepare(ctx, request, "host.exec", True)[1] == "started"
        path.write_text("uncertain prior effect")
    store_path = store.path
    store.close()
    from b12.control import ControlStore
    from b12.tools.registry import ToolRegistry

    restarted = ControlStore(store_path)
    resumed = restarted.resume_turn(ctx.turn_id, deadline=time.monotonic() + 5)
    recovered = ToolRegistry(restarted)

    async def handler(args, guard):
        guard.check()
        path.write_text("executed")
        return {}

    recovered.register(
        "exec", "Виконання", registry._tools["exec"].model, handler, "host.exec", risk="arbitrary"
    )
    result = await recovered.execute(request, resumed)
    if state == "started":
        assert result.error_code == "replay_blocked" and result.outcome_unknown
        assert path.read_text() == "uncertain prior effect"
    elif state == "pending":
        assert result.status == "approval_pending"
        assert result.content["operation_id"] == operation
        assert not path.exists()
    else:
        assert result.status == "completed" and path.read_text() == "executed"
    restarted.close()


async def test_expired_approval_erases_digest_and_never_executes(policy_rig):
    store, registry, ctx, request, path, _ = policy_rig
    pending = await registry.execute(request, ctx)
    store.decide_approval(pending.content["operation_id"], True)
    store.db.execute("UPDATE approvals SET expires_at=0")
    store.db.commit()
    assert (await registry.execute(request, ctx)).error_code == "approval_expired"
    assert not path.exists()
    assert store.db.execute("SELECT digest FROM approvals").fetchone()[0] is None


async def test_approved_revision_is_rechecked(policy_rig):
    store, registry, ctx, request, path, _ = policy_rig
    pending = await registry.execute(request, ctx)
    store.decide_approval(pending.content["operation_id"], True)
    store.set_consent(ctx.actor_id, True)
    assert (await registry.execute(request, ctx)).error_code == "stale_control"
    assert not path.exists()


async def test_capability_does_not_imply_messaging_or_other_tools(policy_rig):
    store, registry, ctx, request, path, _ = policy_rig

    async def send(args, guard):
        guard.check()
        path.write_text("should not happen")
        return {}

    registry.register(
        "message", "Зовнішній tool", registry._tools["exec"].model, send, "external.message"
    )
    grant = store.issue_grant(
        ctx.actor_id, ctx.session_id, ("host.exec",), task_id=ctx.task_id, full_execution=True
    )
    ctx = store.begin_turn(
        ctx.session_id, grant, task_id=ctx.task_id, deadline=time.monotonic() + 5
    )
    assert (
        await registry.execute(request.model_copy(update={"name": "message"}), ctx)
    ).error_code == "capability_denied"
    assert not path.exists()


async def test_pending_turn_cancel_survives_restart_and_erases_approval(policy_rig):
    store, registry, ctx, request, path, _ = policy_rig
    pending = await registry.execute(request, ctx)
    assert hasattr(store, "cancel_turn"), "durable turn cancellation missing"
    store.cancel_turn(ctx.turn_id)
    assert store.audit_events()[-1]["state"] == "cancelled"
    assert store.db.execute("SELECT digest FROM approvals").fetchone()[0] is None
    from b12.control import ControlStore
    from b12.tools.registry import ToolRegistry

    location = store.path
    store.close()
    reopened = ControlStore(location)
    resumed = reopened.resume_turn(ctx.turn_id, deadline=time.monotonic() + 5)
    result = await ToolRegistry(reopened).execute(request, resumed)
    assert result.error_code == "cancelled" and not path.exists()
    assert pending.content["operation_id"] == reopened.audit_events()[-1]["operation_id"]
    reopened.close()


async def test_failed_approval_remains_failed_after_restart(policy_rig):
    store, registry, ctx, request, path, _ = policy_rig
    pending = await registry.execute(request, ctx)
    store.decide_approval(pending.content["operation_id"], False)
    from b12.control import ControlStore

    location = store.path
    store.close()
    reopened = ControlStore(location)
    assert reopened.audit_events()[-1]["state"] == "failed"
    assert reopened.db.execute("SELECT state FROM operations").fetchone()[0] == "failed"
    assert not path.exists()
    reopened.close()


async def test_control_can_issue_separate_typed_guest_grant(policy_rig):
    store, registry, _, request, path, guest = policy_rig
    session = store.create_session(guest.id)
    grant = store.issue_grant(guest.id, session, ("host.write",))
    ctx = store.begin_turn(session, grant, deadline=time.monotonic() + 5)
    assert (
        await registry.execute(request.model_copy(update={"name": "typed"}), ctx)
    ).status == "completed"
    assert path.exists()
