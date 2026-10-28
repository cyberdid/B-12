"""Actual temp filesystem/process/HTTP effects through trusted registry control."""

import asyncio
import base64
import json
import os
import signal
import sys
from datetime import datetime
from pathlib import Path
from uuid import UUID

import pytest


async def test_atomic_overwrite_keeps_original_backup_and_permissions(host_factory):
    rig = host_factory()
    path = rig.root / "original.txt"
    path.write_text("amber original")
    path.chmod(0o640)
    with path.open() as old_inode:
        result = await rig.invoke(
            "file_write", path=str(path), text="blue replacement", overwrite=True
        )
        assert result.status == "completed"
        assert old_inode.read() == "amber original"
    assert path.read_text() == "blue replacement"
    assert path.stat().st_mode & 0o777 == 0o640
    assert result.side_effects[0]["kind"] == "file_write"
    artifact = result.side_effects[0]["artifact_ids"][0]
    UUID(artifact)
    inventory = rig.backups.inventory(rig.actor.id)
    assert inventory[0]["artifact_id"] == artifact
    assert inventory[0]["turn_id"] == rig.context.turn_id
    with rig.backups.open_copy(rig.actor.id, artifact) as copy:
        assert copy.read() == b"amber original"
    read = await rig.invoke("file_read", path=str(path))
    assert read.content["text"] == "blue replacement"
    rig.backups.close()
    from b12.tools.filesystem import BackupStore

    rig.backups = BackupStore(rig.root / "backups")
    assert rig.backups.inventory(rig.actor.id)[0]["artifact_id"] == artifact
    receipt = rig.backups.purge(rig.actor.id, turn_ids=(rig.context.turn_id,))
    assert receipt["state"] == "complete"
    assert rig.backups.inventory(rig.actor.id) == []
    assert path.read_text() == "blue replacement"
    assert rig.backups.purge(rig.actor.id, turn_ids=(rig.context.turn_id,))["state"] == "complete"


async def test_bounded_binary_read_list_and_literal_search(host_factory):
    rig = host_factory()
    binary = rig.root / "binary"
    binary.write_bytes(b"\x00\xff" * 20000)
    result = await rig.invoke("file_read", path=str(binary), max_bytes=12)
    assert result.truncated
    assert result.content["encoding"] == "base64"
    assert base64.b64decode(result.content["data"]) == b"\x00\xff" * 6
    folder = rig.root / "documents"
    folder.mkdir()
    for name in ("one", "two", "three"):
        (folder / name).write_text("amber literal [.*]\nsecond line")
    listing = await rig.invoke("file_list", path=str(folder), limit=2)
    assert len(listing.content["entries"]) == 2 and listing.content["next_offset"] == 2
    search = await rig.invoke("file_search", path=str(folder), query="[.*]", limit=2)
    assert len(search.content["matches"]) == 2 and search.truncated
    assert all(m["line"] == 1 for m in search.content["matches"])


async def test_subprocess_argv_stderr_exit_and_bounded_drain(host_factory):
    rig = host_factory()
    literal = "$(touch forbidden); & | *"
    result = await rig.invoke(
        "shell_exec",
        executable=sys.executable,
        argv=[
            "-c",
            "import sys;print(sys.argv[1]);print('err',file=sys.stderr);sys.exit(7)",
            literal,
        ],
        cwd=str(rig.root),
        declared_effects=["stdout", "stderr"],
    )
    assert result.status == "completed"
    assert result.content["exit_code"] == 7 and not result.content["command_succeeded"]
    assert result.content["stdout"] == literal + "\n"
    assert result.content["stderr"] == "err\n"
    assert result.side_effects[0]["kind"] == "process_execution"
    assert not (rig.root / "forbidden").exists()
    bounded = await rig.invoke(
        "shell_exec",
        executable=sys.executable,
        argv=["-c", "import os;os.write(1,b'x'*100000);os.write(2,b'y'*100000)"],
        cwd=str(rig.root),
        declared_effects=["stdout", "stderr"],
        max_output_bytes=128,
    )
    assert bounded.status == "completed" and bounded.truncated
    assert bounded.content["stdout"] == "x" * 128
    assert bounded.content["stderr"] == "y" * 128


def running(pid):
    try:
        state = Path(f"/proc/{pid}/stat").read_text().rpartition(") ")[2].split()[0]
        return state not in ("Z", "X")
    except FileNotFoundError:
        return False


@pytest.mark.parametrize("interrupt", ["timeout", "event"])
async def test_interrupt_kills_real_child_and_grandchild_and_retains_evidence(
    host_factory, interrupt
):
    rig = host_factory(timeout_s=0.4 if interrupt == "timeout" else 3)
    pids_file = rig.root / "pids.json"
    script = (
        "import os,sys,subprocess,signal,time,json;"
        "signal.signal(signal.SIGTERM,signal.SIG_IGN);"
        "p=subprocess.Popen([sys.executable,'-c',"
        "'import signal,time;signal.signal(signal.SIGTERM,signal.SIG_IGN);time.sleep(30)']);"
        "open(sys.argv[1],'w').write(json.dumps([os.getpid(),p.pid]));"
        "print('started',flush=True);time.sleep(30)"
    )
    pending = asyncio.create_task(
        rig.invoke(
            "shell_exec",
            executable=sys.executable,
            argv=["-c", script, str(pids_file)],
            cwd=str(rig.root),
            declared_effects=["temp pid file", "child process"],
            call_id="interrupted",
        )
    )
    pids = []
    try:
        for _ in range(100):
            if pids_file.exists():
                pids = json.loads(pids_file.read_text())
                break
            await asyncio.sleep(0.01)
        assert len(pids) == 2
        if interrupt == "event":
            rig.context.cancel.set()
        result = await pending
        assert result.status == "unknown" and result.outcome_unknown
        assert result.error_code == ("deadline_exceeded" if interrupt == "timeout" else "cancelled")
        assert result.content["stdout"] == "started\n"
        assert result.content["cleanup_confirmed"]
        assert result.side_effects[0]["kind"] == "process_execution"
        assert all(not running(pid) for pid in pids)
    finally:
        if pids and any(running(pid) for pid in pids):
            os.killpg(pids[0], signal.SIGKILL)
        await asyncio.gather(pending, return_exceptions=True)


async def test_local_http_fetch_is_bounded_and_cancel_closes_transport(host_factory):
    rig = host_factory()
    disconnected = asyncio.Event()

    async def server(reader, writer):
        await reader.readuntil(b"\r\n\r\n")
        writer.write(
            b"HTTP/1.1 200 OK\r\nContent-Length: 100000\r\nContent-Type: text/plain\r\n\r\n"
        )
        await writer.drain()
        try:
            writer.write(b"a" * 100000)
            await writer.drain()
            await reader.read()
        finally:
            disconnected.set()
            writer.close()
            await writer.wait_closed()

    listener = await asyncio.start_server(server, "127.0.0.1", 0)
    async with listener:
        port = listener.sockets[0].getsockname()[1]
        result = await rig.invoke("http_fetch", url=f"http://127.0.0.1:{port}/", max_bytes=128)
        assert result.status == "completed" and result.truncated
        assert result.content["status_code"] == 200
        assert result.content["text"] == "a" * 128
        assert result.side_effects[0]["kind"] == "http_request"
        await asyncio.wait_for(disconnected.wait(), 1)


async def test_memory_tools_use_exact_actor_provenance_and_knowledge_evidence(host_factory):
    rig = host_factory()
    result = await rig.invoke("memory_store", text="synthetic amber launch", kind="fact")
    assert result.status == "completed"
    memory_id = result.content["id"]
    assert result.side_effects[0]["evidence_ids"] == [memory_id]
    found = await rig.invoke("memory_search", query="amber")
    assert found.content["records"][0]["id"] == memory_id
    assert found.content["records"][0]["source"] == "tool:" + result.side_effects[0]["operation_id"]
    source = rig.root / "source.md"
    source.write_text("synthetic amethyst robot")
    receipt = rig.knowledge.index_document(source, rig.actor)
    known = await rig.invoke("knowledge_search", query="amethyst")
    UUID(known.content["hits"][0]["evidence_id"])
    assert known.content["invalidation_receipts"][0]["operation_id"] == receipt["operation_id"]
    clock = await rig.invoke("current_time")
    assert datetime.fromisoformat(clock.content["utc"]).utcoffset().total_seconds() == 0
    info = await rig.invoke("system_info")
    assert info.content["cpu_count"] == os.cpu_count()
    processes = await rig.invoke("process_list", pid=os.getpid())
    assert any(p["pid"] == os.getpid() for p in processes.content["processes"])


@pytest.mark.parametrize("stage", ["after_temp", "after_backup"])
async def test_file_write_cancel_closes_fds_and_preserves_managed_evidence(
    host_factory, monkeypatch, stage
):
    rig = host_factory()
    path = rig.root / "target"
    path.write_text("original")
    reached = asyncio.Event()
    capture = rig.backups.capture

    async def interrupted_capture(*args):
        if stage == "after_backup":
            await capture(*args)
        reached.set()
        await asyncio.Event().wait()

    monkeypatch.setattr(rig.backups, "capture", interrupted_capture)
    fds = len(os.listdir("/proc/self/fd"))
    task = asyncio.create_task(
        rig.invoke("file_write", path=str(path), text="replacement", overwrite=True)
    )
    await asyncio.wait_for(reached.wait(), 1)
    rig.context.cancel.set()
    result = await task
    assert result.status == "unknown" and result.content["target_replaced"] is False
    assert path.read_text() == "original"
    assert not list(rig.root.glob(".b12-*"))
    assert len(os.listdir("/proc/self/fd")) == fds
    artifacts = [item["artifact_id"] for item in rig.backups.inventory(rig.actor.id)]
    assert set(result.side_effects[0]["artifact_ids"]) == set(artifacts)
    if stage == "after_backup":
        assert len(artifacts) == 1
        with rig.backups.open_copy(rig.actor.id, artifacts[0]) as copy:
            assert copy.read() == b"original"


async def test_http_event_cancel_closes_real_socket_with_unknown_effect(host_factory):
    rig = host_factory()
    accepted, closed = asyncio.Event(), asyncio.Event()

    async def server(reader, writer):
        await reader.readuntil(b"\r\n\r\n")
        accepted.set()
        await reader.read()
        closed.set()
        writer.close()
        await writer.wait_closed()

    listener = await asyncio.start_server(server, "127.0.0.1", 0)
    async with listener:
        port = listener.sockets[0].getsockname()[1]
        pending = asyncio.create_task(rig.invoke("http_fetch", url=f"http://127.0.0.1:{port}/"))
        await asyncio.wait_for(accepted.wait(), 1)
        rig.context.cancel.set()
        result = await pending
        assert result.status == "unknown" and result.error_code == "cancelled"
        assert result.side_effects[0]["kind"] == "http_request"
        await asyncio.wait_for(closed.wait(), 1)


async def test_real_canonical_purge_port_pending_is_not_global_success(host_factory):
    class PartialCoordinator:
        async def purge(self, memory_id, context, guard):
            guard.check()
            actor = guard.store.resolve_actor(context.actor_id)
            return rig.memory.begin_purge(memory_id, actor, stores=("canonical", "sessions"))

    rig = host_factory(purge=PartialCoordinator())
    memory = rig.memory.remember("synthetic port erasure", rig.actor)
    waiting = await rig.invoke("memory_forget", memory_id=memory.id, call_id="purge")
    rig.control.decide_approval(waiting.content["operation_id"], True)
    result = await rig.invoke("memory_forget", memory_id=memory.id, call_id="purge")
    assert result.status == "unknown" and result.outcome_unknown
    assert result.content["receipt"]["state"] == "pending"
    assert "sessions" in result.content["receipt"]["pending_stores"]
    assert rig.memory.search("erasure", rig.actor) == []


async def test_http_encoded_body_is_bounded_as_wire_bytes(host_factory):
    import gzip

    rig = host_factory()
    compressed = gzip.compress(b"z" * 1000000, mtime=0)

    async def server(reader, writer):
        await reader.readuntil(b"\r\n\r\n")
        writer.write(
            b"HTTP/1.1 200 OK\r\nContent-Encoding: gzip\r\nContent-Length: "
            + str(len(compressed)).encode()
            + b"\r\n\r\n"
            + compressed
        )
        await writer.drain()
        writer.close()
        await writer.wait_closed()

    listener = await asyncio.start_server(server, "127.0.0.1", 0)
    async with listener:
        port = listener.sockets[0].getsockname()[1]
        result = await rig.invoke("http_fetch", url=f"http://127.0.0.1:{port}/", max_bytes=128)
        assert result.truncated and result.content["content_encoding"] == "gzip"
        assert base64.b64decode(result.content["data"]) == compressed[:128]


async def test_overwrite_preserves_extended_attributes(host_factory):
    rig = host_factory()
    path = rig.root / "attributes"
    path.write_text("old")
    os.setxattr(path, "user.b12-test", b"synthetic attribute")
    result = await rig.invoke("file_write", path=str(path), text="new", overwrite=True)
    assert result.status == "completed"
    assert os.getxattr(path, "user.b12-test") == b"synthetic attribute"


async def test_store_exception_after_commit_keeps_possible_effect_metadata(
    host_factory, monkeypatch
):
    rig = host_factory()
    remember = rig.memory.remember

    def committed_then_error(*args, **kwargs):
        remember(*args, **kwargs)
        raise OSError("synthetic sensitive path")

    monkeypatch.setattr(rig.memory, "remember", committed_then_error)
    result = await rig.invoke("memory_store", text="synthetic uncertain commit")
    assert result.status == "unknown"
    assert result.side_effects[0]["kind"] == "memory_write"
    assert rig.memory.search("uncertain", rig.actor)
    assert "sensitive" not in json.dumps(rig.control.audit_events())


async def test_posix_acl_and_restore_metadata_survive_overwrite(host_factory):
    import errno

    rig = host_factory()
    path = rig.root / "acl"
    path.write_text("old acl content")
    acl = bytes.fromhex(
        "0200000001000600ffffffff02000400feff000004000400ffffffff10000400ffffffff20000000ffffffff"
    )
    try:
        os.setxattr(path, "system.posix_acl_access", acl)
    except OSError as error:
        if error.errno in (errno.ENOTSUP, errno.EOPNOTSUPP, errno.EPERM):
            pytest.skip("filesystem does not permit POSIX ACL fixture")
        raise
    mode = path.stat().st_mode & 0o777
    result = await rig.invoke("file_write", path=str(path), text="new acl content", overwrite=True)
    assert result.status == "completed"
    assert os.getxattr(path, "system.posix_acl_access") == acl
    assert path.stat().st_mode & 0o777 == mode
    metadata = rig.backups.copy_metadata(rig.actor.id, result.content["backup_id"])
    assert metadata["mode"] == mode
    assert base64.b64decode(metadata["xattrs"]["system.posix_acl_access"]) == acl


async def test_purge_exception_after_local_effect_remains_unknown_with_provenance(host_factory):
    class BrokenCoordinator:
        async def purge(self, memory_id, context, guard):
            guard.check()
            rig.memory.begin_purge(memory_id, rig.actor, stores=("canonical", "sessions"))
            raise OSError("synthetic secret path")

    rig = host_factory(purge=BrokenCoordinator())
    item = rig.memory.remember("synthetic exceptional purge", rig.actor)
    waiting = await rig.invoke("memory_forget", memory_id=item.id, call_id="exceptional")
    rig.control.decide_approval(waiting.content["operation_id"], True)
    result = await rig.invoke("memory_forget", memory_id=item.id, call_id="exceptional")
    assert result.status == "unknown"
    assert result.side_effects[0]["kind"] == "memory_forget"
    assert rig.memory.search("exceptional", rig.actor) == []


async def test_file_search_reports_truncation_when_depth_cap_hides_match(host_factory):
    rig = host_factory()
    root = rig.root / "tree"
    root.mkdir()
    deep = root
    for index in range(9):
        deep = deep / str(index)
        deep.mkdir()
    (deep / "needle").write_text("synthetic hidden deep needle")
    result = await rig.invoke("file_search", path=str(root), query="needle")
    assert result.status == "completed" and result.content["matches"] == []
    assert result.truncated


def test_registered_host_schemas_stay_in_calibrated_renderer_subset(host_factory):
    rig = host_factory()
    text = json.dumps(rig.registry.schemas(rig.context))
    for construct in ('"anyOf"', '"oneOf"', '"allOf"', '"$ref"', '"$defs"', '"not"'):
        assert construct not in text


def test_numeric_limits_are_stated_in_descriptions_the_model_can_see(host_factory):
    """Bolt's chat template renders only type/description, never maximum/minLength."""
    rig = host_factory()
    missing = []
    for schema in rig.registry.schemas(rig.context):
        function = schema["function"]
        for name, spec in function["parameters"].get("properties", {}).items():
            if "maximum" in spec and str(spec["maximum"]) not in spec.get("description", ""):
                missing.append((function["name"], name, spec["maximum"]))
    assert missing == []


async def test_memory_store_drops_non_uuid_evidence_ids_instead_of_failing(host_factory):
    rig = host_factory()
    result = await rig.invoke(
        "memory_store", text="нотатка про файл", evidence_ids=["979723", "not-a-uuid"]
    )
    assert result.status == "completed", result.error_code
    found = await rig.invoke("memory_search", query="нотатка")
    assert any("нотатка про файл" in str(item) for item in found.content["records"])


async def test_file_list_pages_sorted_entries_and_never_hides_a_name(host_factory):
    rig = host_factory()
    folder = rig.root / "many"
    folder.mkdir()
    for n in range(120):
        (folder / f"f{n:03d}.txt").write_text("x")
    (folder / "Projects").mkdir()
    seen, offset = [], 0
    while offset is not None:
        result = await rig.invoke("file_list", path=str(folder), limit=50, offset=offset)
        assert result.status == "completed" and result.truncated is False
        seen += [e.rstrip("/@") for e in result.content["entries"]]
        offset = result.content["next_offset"]
    assert len(seen) == result.content["total"] == 121
    assert seen == sorted(seen) and "Projects" in seen


async def test_chunked_read_reassembles_cyrillic_file_exactly(host_factory):
    rig = host_factory()
    path = rig.root / "uk.txt"
    original = ("Привіт, світе! Ґанок і їжак. " * 40).encode("utf-8")
    path.write_bytes(original)
    rebuilt, offset, steps = b"", 0, 0
    while True:
        result = await rig.invoke("file_read", path=str(path), max_bytes=7, offset=offset)
        assert result.status == "completed" and result.content["encoding"] == "utf-8"
        rebuilt += result.content["text"].encode("utf-8")
        steps += 1
        if result.content["eof"]:
            break
        offset = result.content["next_offset"]
    assert rebuilt == original and steps > 10


async def test_file_list_entries_are_short_strings_that_fit_the_result_budget(host_factory):
    rig = host_factory()
    folder = rig.root / "budget"
    folder.mkdir()
    for n in range(79):
        (folder / f"File-number-{n:03d}-with-a-long-name.txt").write_text("x")
    (folder / "Projects").mkdir()
    result = await rig.invoke("file_list", path=str(folder), limit=200)
    import json

    assert "Projects/" in result.content["entries"]
    assert all(isinstance(e, str) for e in result.content["entries"])
    assert len(json.dumps(result.content).encode()) < 4096
