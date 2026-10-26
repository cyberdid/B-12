"""Real host boundary denials; only temp data and controlled subprocesses."""

import json
import os
import sys
from uuid import uuid4

import pytest


async def test_leaf_symlink_write_is_rejected_without_touching_target(host_factory):
    rig = host_factory()
    target = rig.root / "target"
    target.write_text("protected")
    link = rig.root / "link"
    link.symlink_to(target)
    result = await rig.invoke("file_write", path=str(link), text="replacement", overwrite=True)
    assert result.status == "failed" and result.error_code == "unsupported"
    assert target.read_text() == "protected" and link.is_symlink()
    assert rig.backups.inventory(rig.actor.id) == []


async def test_write_validation_and_existing_file_refusal_have_no_effect(host_factory):
    rig = host_factory()
    path = rig.root / "existing"
    path.write_text("kept")
    refused = await rig.invoke("file_write", path=str(path), text="bad")
    assert refused.status == "failed" and not refused.side_effects
    forged = await rig.invoke("file_write", path=str(path), text="bad", approved=True)
    assert forged.error_code == "invalid_arguments"
    assert path.read_text() == "kept"
    absent = await rig.invoke("file_read", path=str(rig.root / "absent"))
    assert absent.error_code == "not_found"
    denied = await rig.invoke("file_write", path="relative", text="bad")
    assert denied.error_code == "invalid_arguments"


async def test_exact_shell_approval_precedes_real_process_effect(host_factory):
    rig = host_factory(full_execution=False)
    target = rig.root / "effect"
    args = dict(
        executable=sys.executable,
        argv=["-c", "open('effect','w').write('yes')"],
        cwd=str(rig.root),
        declared_effects=["temp file write"],
    )
    pending = await rig.invoke("shell_exec", call_id="approved-call", **args)
    assert pending.status == "approval_pending" and not target.exists()
    rig.control.decide_approval(pending.content["operation_id"], True)
    result = await rig.invoke("shell_exec", call_id="approved-call", **args)
    assert result.status == "completed" and target.read_text() == "yes"
    target.unlink()
    replay = await rig.invoke("shell_exec", call_id="approved-call", **args)
    assert replay.error_code == "replay_blocked" and not target.exists()


async def test_audit_has_no_raw_paths_arguments_stdout_or_secret(host_factory):
    rig = host_factory()
    secret = "SYNTHETIC_TOKEN_93a8"
    target = rig.root / secret
    await rig.invoke("file_write", path=str(target), text=secret)
    await rig.invoke(
        "shell_exec",
        executable=sys.executable,
        argv=["-c", f"print('{secret}')"],
        cwd=str(rig.root),
        declared_effects=["stdout"],
    )
    audit = json.dumps(rig.control.audit_events())
    assert secret not in audit and str(rig.root) not in audit
    assert "stdout" not in audit and "argv" not in audit


async def test_missing_purge_and_turn_revision_never_claim_global_forget_or_store(host_factory):
    rig = host_factory(revision=False)
    store = await rig.invoke("memory_store", text="must not persist")
    assert store.status == "failed" and store.error_code == "coordinator_unavailable"
    assert rig.memory.search("persist", rig.actor) == []
    target = rig.memory.remember("keep until coordinator", rig.actor)
    pending = await rig.invoke("memory_forget", memory_id=target.id, call_id="forget")
    assert pending.status == "approval_pending"
    rig.control.decide_approval(pending.content["operation_id"], True)
    missing = await rig.invoke("memory_forget", memory_id=target.id, call_id="forget")
    assert missing.status == "failed" and missing.error_code == "coordinator_unavailable"
    assert rig.memory.search("coordinator", rig.actor)


async def test_stale_turn_revision_and_backup_actor_scope_are_enforced(host_factory):
    rig = host_factory()
    first = rig.memory.remember("delete this", rig.actor)
    assert rig.memory.forget(first.id, rig.actor)
    stale = await rig.invoke("memory_store", text="stale resurrection")
    assert stale.status == "failed" and stale.error_code == "permission_denied"
    assert rig.memory.search("resurrection", rig.actor) == []
    path = rig.root / "source"
    path.write_text("private original")
    written = await rig.invoke("file_write", path=str(path), text="new", overwrite=True)
    artifact = written.side_effects[0]["artifact_ids"][0]
    other = str(uuid4())
    assert rig.backups.inventory(other) == []
    with pytest.raises(PermissionError):
        rig.backups.open_copy(other, artifact)
    assert rig.backups.purge(other, artifact_ids=(artifact,))["state"] == "complete"
    assert rig.backups.inventory(rig.actor.id)


async def test_os_permission_denial_is_honest_for_regular_unprivileged_user(host_factory):
    if os.geteuid() == 0:
        pytest.skip("root bypasses ordinary DAC; no fake permission claim")
    rig = host_factory()
    locked = rig.root / "locked"
    locked.mkdir()
    locked.chmod(0o500)
    try:
        result = await rig.invoke("file_write", path=str(locked / "denied"), text="no")
        assert result.error_code == "permission_denied" and result.status == "failed"
        assert not (locked / "denied").exists()
    finally:
        locked.chmod(0o700)


async def test_failed_staging_cleanup_remains_in_purge_inventory(host_factory, monkeypatch):
    import asyncio

    rig = host_factory()
    path = rig.root / "target"
    path.write_text("original")
    reached = asyncio.Event()

    async def pause(*args):
        reached.set()
        await asyncio.Event().wait()

    monkeypatch.setattr(rig.backups, "capture", pause)
    unlink = os.unlink

    def deny_staging(name, *args, **kwargs):
        if str(name).startswith(".b12-"):
            raise PermissionError("synthetic unlink denial")
        return unlink(name, *args, **kwargs)

    monkeypatch.setattr(os, "unlink", deny_staging)
    fds = len(os.listdir("/proc/self/fd"))
    pending = asyncio.create_task(
        rig.invoke("file_write", path=str(path), text="staged", overwrite=True)
    )
    await asyncio.wait_for(reached.wait(), 1)
    rig.context.cancel.set()
    result = await pending
    assert result.status == "unknown"
    inventory = rig.backups.inventory(rig.actor.id)
    assert len(inventory) == 1 and inventory[0]["state"] == "deleting"
    assert len(os.listdir("/proc/self/fd")) == fds
    monkeypatch.setattr(os, "unlink", unlink)
    assert rig.backups.purge(rig.actor.id, turn_ids=(rig.context.turn_id,))["state"] == "complete"
    assert not list(rig.root.glob(".b12-*")) and path.read_text() == "original"


@pytest.mark.parametrize(
    "url",
    [
        "file:///etc/passwd",
        "http://u:secret@127.0.0.1/",
        "http://127.0.0.1/#fragment",
        "http://127.0.0.1:bad/",
    ],
)
async def test_invalid_fetch_urls_never_start_network_effect(host_factory, url):
    rig = host_factory()
    result = await rig.invoke("http_fetch", url=url)
    assert result.error_code == "invalid_arguments" and not result.side_effects


async def test_backup_source_tombstone_cannot_be_bypassed_via_parent_symlink(host_factory):
    rig = host_factory()
    path = rig.root / "source"
    path.write_text("old")
    await rig.invoke("file_write", path=str(path), text="new", overwrite=True)
    item = rig.backups.inventory(rig.actor.id)[0]
    assert rig.backups.purge(rig.actor.id, source_ids=(item["source_id"],))["state"] == "complete"
    alias = rig.root / "alias"
    alias.symlink_to(rig.root, target_is_directory=True)
    denied = await rig.invoke(
        "file_write", path=str(alias / "source"), text="resurrect", overwrite=True
    )
    assert denied.status == "failed" and denied.error_code == "permission_denied"
    assert path.read_text() == "new"


async def test_purged_turn_cannot_create_another_managed_staging_copy(host_factory):
    rig = host_factory()
    rig.backups.purge(rig.actor.id, turn_ids=(rig.context.turn_id,))
    path = rig.root / "denied"
    denied = await rig.invoke("file_write", path=str(path), text="no late copy")
    assert denied.status == "failed" and not path.exists()
    assert rig.backups.inventory(rig.actor.id) == []


@pytest.mark.parametrize("invalid_revision", [None, False, True, -1, 0.0, "0"])
async def test_invalid_origin_revision_cannot_disable_stale_write_guard(
    host_factory, invalid_revision
):
    rig = host_factory(revision=lambda context: invalid_revision)
    original = rig.memory.remember("synthetic original before purge", rig.actor)
    assert rig.memory.forget(original.id, rig.actor)
    assert rig.memory.deletion_revision(rig.actor) > 0
    before = rig.memory.audit_events(rig.actor)
    result = await rig.invoke("memory_store", text="synthetic stale resurrection")
    assert result.status == "failed" and result.error_code == "coordinator_unavailable"
    assert not result.side_effects and not result.outcome_unknown
    assert rig.memory.search("resurrection", rig.actor) == []
    assert rig.memory.audit_events(rig.actor) == before


async def test_origin_revision_resolver_exception_is_sanitized_before_write(host_factory):
    def missing_snapshot(context):
        raise RuntimeError("synthetic private turn path")

    rig = host_factory(revision=missing_snapshot)
    original = rig.memory.remember("synthetic deleted original", rig.actor)
    assert rig.memory.forget(original.id, rig.actor)
    before = rig.memory.audit_events(rig.actor)
    result = await rig.invoke("memory_store", text="synthetic unresolved snapshot")
    assert result.status == "failed" and result.error_code == "coordinator_unavailable"
    assert not result.side_effects and not result.outcome_unknown
    assert rig.memory.search("snapshot", rig.actor) == []
    assert rig.memory.audit_events(rig.actor) == before
    assert "private turn path" not in json.dumps(rig.control.audit_events())


def directory_identity(path):
    info = path.stat()
    return info.st_dev, info.st_ino


def reject_directory_sync(monkeypatch, directory):
    identity = directory_identity(directory)
    original = os.fsync

    def fsync(fd):
        info = os.fstat(fd)
        if (info.st_dev, info.st_ino) == identity:
            raise OSError("synthetic directory sync failure")
        return original(fd)

    monkeypatch.setattr(os, "fsync", fsync)
    return original


async def test_backup_object_directory_sync_precedes_ready_and_target_install(
    host_factory, monkeypatch
):
    rig = host_factory()
    target = rig.root / "original"
    target.write_text("old durable bytes")
    identity = directory_identity(rig.backups.objects)
    original = os.fsync
    observed = []

    def observe(fd):
        info = os.fstat(fd)
        if (info.st_dev, info.st_ino) == identity:
            copies = rig.backups.inventory(rig.actor.id)
            observed.append((tuple(sorted(item["state"] for item in copies)), target.read_text()))
        return original(fd)

    monkeypatch.setattr(os, "fsync", observe)
    result = await rig.invoke("file_write", path=str(target), text="new bytes", overwrite=True)
    assert result.status == "completed"
    assert observed == [(("copying", "staging"), "old durable bytes")]


async def test_failed_object_directory_sync_keeps_tracked_copy_and_old_target(
    host_factory, monkeypatch
):
    rig = host_factory()
    target = rig.root / "original"
    target.write_text("old durable bytes")
    original = reject_directory_sync(monkeypatch, rig.backups.objects)
    result = await rig.invoke("file_write", path=str(target), text="new bytes", overwrite=True)
    assert result.status == "unknown" and target.read_text() == "old durable bytes"
    inventory = rig.backups.inventory(rig.actor.id)
    assert len(inventory) == 1 and inventory[0]["state"] == "deleting"
    monkeypatch.setattr(os, "fsync", original)
    rig.backups.close()
    from b12.tools.filesystem import BackupStore

    rig.backups = BackupStore(rig.root / "backups")
    assert rig.backups.inventory(rig.actor.id)[0]["state"] == "deleting"
    assert rig.backups.purge(rig.actor.id, turn_ids=(rig.context.turn_id,))["state"] == "complete"
    assert rig.backups.inventory(rig.actor.id) == []


async def test_backup_purge_directory_sync_failure_is_pending_across_reopen(
    host_factory, monkeypatch
):
    rig = host_factory()
    target = rig.root / "original"
    target.write_text("old")
    result = await rig.invoke("file_write", path=str(target), text="new", overwrite=True)
    artifact = result.content["backup_id"]
    original = reject_directory_sync(monkeypatch, rig.backups.objects)
    receipt = rig.backups.purge(rig.actor.id, artifact_ids=(artifact,))
    assert receipt["state"] == "pending" and receipt["pending_ids"] == [artifact]
    assert rig.backups.inventory(rig.actor.id)[0]["state"] == "deleting"
    monkeypatch.setattr(os, "fsync", original)
    rig.backups.close()
    from b12.tools.filesystem import BackupStore

    rig.backups = BackupStore(rig.root / "backups")
    assert rig.backups.inventory(rig.actor.id)[0]["state"] == "deleting"
    assert rig.backups.purge(rig.actor.id, artifact_ids=(artifact,))["state"] == "complete"
    assert target.read_text() == "new"


async def pending_staging(rig, monkeypatch):
    import asyncio

    parent = rig.root / "staging-parent"
    parent.mkdir()
    target = parent / "target"
    target.write_text("unmanaged original")
    reached = asyncio.Event()

    async def pause(*args):
        reached.set()
        await asyncio.Event().wait()

    original = os.unlink

    def denied(name, *args, **kwargs):
        if str(name).startswith(".b12-"):
            raise PermissionError("synthetic staging unlink denial")
        return original(name, *args, **kwargs)

    with monkeypatch.context() as patches:
        patches.setattr(rig.backups, "capture", pause)
        patches.setattr(os, "unlink", denied)
        task = asyncio.create_task(
            rig.invoke("file_write", path=str(target), text="staging payload", overwrite=True)
        )
        await asyncio.wait_for(reached.wait(), 1)
        rig.context.cancel.set()
        assert (await task).status == "unknown"
    return target, next(parent.glob(".b12-*"))


async def test_staging_purge_dir_sync_failure_retains_inventory_for_retry(
    host_factory, monkeypatch
):
    rig = host_factory()
    target, temp = await pending_staging(rig, monkeypatch)
    artifact = rig.backups.inventory(rig.actor.id)[0]["artifact_id"]
    original = reject_directory_sync(monkeypatch, temp.parent)
    receipt = rig.backups.purge(rig.actor.id, artifact_ids=(artifact,))
    assert receipt["state"] == "pending" and receipt["pending_ids"] == [artifact]
    assert rig.backups.inventory(rig.actor.id)[0]["state"] == "deleting"
    monkeypatch.setattr(os, "fsync", original)
    rig.backups.close()
    from b12.tools.filesystem import BackupStore

    rig.backups = BackupStore(rig.root / "backups")
    assert rig.backups.purge(rig.actor.id, artifact_ids=(artifact,))["state"] == "complete"
    assert not temp.exists() and target.read_text() == "unmanaged original"


async def test_staging_cleanup_dir_sync_failure_keeps_persisted_pending_row(
    host_factory, monkeypatch
):
    import asyncio

    rig = host_factory()
    target = rig.root / "original"
    target.write_text("old")
    reached = asyncio.Event()

    async def pause(*args):
        reached.set()
        await asyncio.Event().wait()

    monkeypatch.setattr(rig.backups, "capture", pause)
    original = reject_directory_sync(monkeypatch, rig.root)
    task = asyncio.create_task(
        rig.invoke("file_write", path=str(target), text="new", overwrite=True)
    )
    await asyncio.wait_for(reached.wait(), 1)
    rig.context.cancel.set()
    result = await task
    assert result.status == "unknown"
    inventory = rig.backups.inventory(rig.actor.id)
    assert len(inventory) == 1 and inventory[0]["state"] == "deleting"
    monkeypatch.setattr(os, "fsync", original)
    assert rig.backups.purge(rig.actor.id, turn_ids=(rig.context.turn_id,))["state"] == "complete"
    assert target.read_text() == "old"


async def test_staging_purge_unlinks_through_identity_checked_pinned_parent(
    host_factory, monkeypatch
):
    rig = host_factory()
    target, temp = await pending_staging(rig, monkeypatch)
    parent = temp.parent
    moved = rig.root / "moved-parent"
    original = os.unlink
    switched = False

    def switch_at_unlink(name, *args, **kwargs):
        nonlocal switched
        if not switched and (str(name) == temp.name or str(name) == str(temp)):
            switched = True
            parent.rename(moved)
            parent.mkdir()
            (parent / temp.name).write_text("unrelated replacement sentinel")
        return original(name, *args, **kwargs)

    monkeypatch.setattr(os, "unlink", switch_at_unlink)
    receipt = rig.backups.purge(rig.actor.id, turn_ids=(rig.context.turn_id,))
    assert receipt["state"] == "complete" and switched
    assert (parent / temp.name).read_text() == "unrelated replacement sentinel"
    assert not (moved / temp.name).exists()
    assert (moved / target.name).read_text() == "unmanaged original"
