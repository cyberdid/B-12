"""Backup/restore, deletion replay, snapshot purge, graceful stop and crash recovery."""

import asyncio
import json
import os
import signal
import socket
import sqlite3
import sys

import httpx
import pytest


@pytest.fixture
def ops(scripted_ollama, tmp_path):
    from b12.runtime import open_runtime

    state, base = scripted_ollama
    settings = base.model_copy(update={"state_dir": tmp_path / "state"})
    runtimes = []

    def open_one():
        runtime = open_runtime(settings)
        runtimes.append(runtime)
        return runtime

    yield state, settings, open_one
    for runtime in runtimes:
        runtime.close()


def all_bytes(root):
    return b"".join(p.read_bytes() for p in root.rglob("*") if p.is_file())


async def test_snapshot_verify_restore_and_deletion_replay(ops):
    _, settings, open_one = ops
    runtime = open_one()
    actor = runtime.control.create_actor(owner=True, consent=True)
    kept = runtime.memory.remember("залишається після restore", actor)
    secret = runtime.memory.remember("секрет-до-знімка ЖОВТОКРИЛ", actor)
    snapshot = runtime.operations.create_snapshot()
    assert runtime.operations.verify(snapshot["id"])["ok"]
    later = runtime.memory.remember("запис після знімка", actor)
    receipt = await runtime.purge.forget(secret.id, actor.id)
    assert receipt.state == "complete"
    snapshot_root = settings.state_dir / "snapshots" / snapshot["id"]
    # forget reached the managed snapshot
    assert "ЖОВТОКРИЛ".encode() not in all_bytes(snapshot_root)
    verified = runtime.operations.verify(snapshot["id"])
    assert verified["ok"], verified  # resealed manifest
    runtime.close()

    from b12.service import Operations

    report = await Operations(settings.state_dir).restore(snapshot["id"], settings)
    runtime = open_one()
    assert runtime.memory.is_live(kept.id, actor)
    assert not runtime.memory.is_live(later.id, actor)
    assert not runtime.memory.is_live(secret.id, actor)
    assert runtime.memory.search("ЖОВТОКРИЛ", actor) == []
    pre_restore = report["pre_restore"]
    assert runtime.operations.verify(pre_restore)["ok"]
    assert "ЖОВТОКРИЛ".encode() not in all_bytes(settings.state_dir)


async def test_restore_replays_deletions_missing_from_old_snapshot(ops, tmp_path):
    _, settings, open_one = ops
    runtime = open_one()
    actor = runtime.control.create_actor(owner=True, consent=True)
    secret = runtime.memory.remember("старий секрет 4242", actor)
    snapshot = runtime.operations.create_snapshot()
    # Simulate an unmanaged-at-purge-time copy: restore an older copy of the snapshot.
    import shutil

    preserved = tmp_path / "older"
    shutil.copytree(settings.state_dir / "snapshots" / snapshot["id"], preserved)
    await runtime.purge.forget(secret.id, actor.id)
    runtime.close()
    shutil.rmtree(settings.state_dir / "snapshots" / snapshot["id"])
    shutil.copytree(preserved, settings.state_dir / "snapshots" / snapshot["id"])
    from b12.service import Operations

    report = await Operations(settings.state_dir).restore(snapshot["id"], settings)
    assert report["replayed"] == [{"target": secret.id, "state": "complete"}]
    runtime = open_one()
    assert not runtime.memory.is_live(secret.id, actor)


async def test_restore_refuses_tampered_snapshot_and_running_owner(ops):
    _, settings, open_one = ops
    runtime = open_one()
    runtime.control.create_actor(owner=True, consent=True)
    snapshot = runtime.operations.create_snapshot()
    target = settings.state_dir / "snapshots" / snapshot["id"] / "control" / "control.sqlite3"
    runtime.close()
    from b12.service import Operations, RuntimeLock

    lock = RuntimeLock(settings.state_dir)
    with pytest.raises(RuntimeError):
        await Operations(settings.state_dir).restore(snapshot["id"], settings)
    lock.release()
    with target.open("r+b") as handle:
        handle.seek(200)
        handle.write(b"tamper")
    assert not Operations(settings.state_dir).verify(snapshot["id"])["ok"]
    with pytest.raises(RuntimeError):
        await Operations(settings.state_dir).restore(snapshot["id"], settings)


def test_logs_redact_exception_messages(tmp_path):
    import logging

    from b12.service import configure_logging

    path = configure_logging(tmp_path)
    log = logging.getLogger("b12.test")
    try:
        raise ValueError("payload секрет 777")
    except ValueError:
        log.exception("handled failure")
    for handler in logging.getLogger("b12").handlers:
        handler.flush()
    text = path.read_text()
    assert "handled failure" in text and "ValueError" in text and "777" not in text
    assert oct(path.stat().st_mode & 0o777) == "0o600"


def free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


async def start_server(settings, tmp_path, port):
    env = {
        "PATH": os.environ["PATH"],
        "HOME": str(tmp_path / "home"),
        "B12_STATE_DIR": str(settings.state_dir),
        "B12_MODEL": settings.model,
        "B12_OLLAMA_URL": settings.ollama_url,
        "B12_MODEL_PROFILE": str(settings.model_profile),
        "B12_TOKENIZER_DIR": str(settings.tokenizer_dir),
        "B12_NUM_CTX": str(settings.num_ctx),
        "B12_OUTPUT_TOKENS": str(settings.output_tokens),
    }
    init = await asyncio.create_subprocess_exec(
        sys.executable, "-m", "b12.cli", "init", env=env, stdout=asyncio.subprocess.DEVNULL
    )
    await init.wait()
    server = await asyncio.create_subprocess_exec(
        sys.executable,
        "-m",
        "b12.cli",
        "serve",
        "--port",
        str(port),
        "--no-autonomy",
        env=env,
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.DEVNULL,
    )
    async with httpx.AsyncClient(trust_env=False) as client:
        for _ in range(100):
            try:
                if (await client.get(f"http://127.0.0.1:{port}/api/health")).status_code == 200:
                    break
            except httpx.TransportError:
                await asyncio.sleep(0.1)
    return server


def alive(pid):
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    stat = open(f"/proc/{pid}/stat").read().rpartition(") ")[2].split()[0]
    return stat != "Z"


async def run_child_turn(state, settings, port, pid_file):
    token = (settings.state_dir / "api" / "owner.token").read_text().strip()
    headers = {"Authorization": f"Bearer {token}"}
    script = "import os,sys,time;open(sys.argv[1],'w').write(str(os.getpid()));time.sleep(120)"
    state["script"] = [
        {
            "tool_calls": [
                (
                    "shell_exec",
                    {
                        "executable": sys.executable,
                        "argv": ["-c", script, str(pid_file)],
                        "cwd": str(settings.state_dir.parent),
                        "declared_effects": ["temp pid file", "sleeping child"],
                    },
                )
            ]
        }
    ]
    client = httpx.AsyncClient(base_url=f"http://127.0.0.1:{port}", trust_env=False, timeout=30)
    session = (await client.post("/api/sessions", json={}, headers=headers)).json()["session_id"]
    request = asyncio.create_task(
        client.post("/api/chat", json={"session_id": session, "text": "запусти"}, headers=headers)
    )
    for _ in range(100):
        if pid_file.exists() and pid_file.read_text():
            break
        await asyncio.sleep(0.1)
    return client, request, int(pid_file.read_text())


async def test_graceful_shutdown_cancels_turn_and_child_processes(ops, tmp_path):
    state, settings, open_one = ops
    port = free_port()
    server = await start_server(settings, tmp_path, port)
    client, request, child = await run_child_turn(state, settings, port, tmp_path / "child.pid")
    assert alive(child)
    server.send_signal(signal.SIGTERM)
    # uvicorn re-raises the captured SIGTERM after a completed graceful shutdown.
    assert await asyncio.wait_for(server.wait(), 20) in (0, -signal.SIGTERM)
    for _ in range(50):
        if not alive(child):
            break
        await asyncio.sleep(0.1)
    assert not alive(child)
    request.cancel()
    await client.aclose()
    runtime = open_one()
    finished = [e for e in runtime.control.audit_events() if e["name"] == "shell_exec"]
    # Graceful path finished the operation itself; a crash would show "interrupted".
    assert [e["error_code"] for e in finished][-1] == "cancelled"


async def test_abrupt_kill_recovers_integrity_and_marks_started_unknown(ops, tmp_path):
    state, settings, open_one = ops
    port = free_port()
    server = await start_server(settings, tmp_path, port)
    client, request, child = await run_child_turn(state, settings, port, tmp_path / "kill.pid")
    server.kill()
    await server.wait()
    request.cancel()
    await client.aclose()
    # PR_SET_PDEATHSIG: the direct child dies with the killed server, no orphan remains.
    for _ in range(50):
        if not alive(child):
            break
        await asyncio.sleep(0.1)
    if alive(child):
        os.kill(child, signal.SIGKILL)
        pytest.fail("child process outlived SIGKILL of the server")
    runtime = open_one()
    states = [e["state"] for e in runtime.control.audit_events()]
    assert states[-1] == "unknown" and "started" in states
    for path in settings.state_dir.rglob("*.sqlite3"):
        connection = sqlite3.connect(path)
        try:
            assert connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok", path
        finally:
            connection.close()
    status = json.loads(json.dumps(__import__("b12.telemetry").telemetry.status(runtime)))
    assert status["pending_purges"] == 0 and status["active_turns"] == 0


async def test_second_server_on_same_state_refuses_to_start(ops, tmp_path):
    _, settings, _ = ops
    first = await start_server(settings, tmp_path, free_port())
    second = await asyncio.create_subprocess_exec(
        sys.executable,
        "-m",
        "b12.cli",
        "serve",
        "--port",
        str(free_port()),
        "--no-autonomy",
        env={
            "PATH": os.environ["PATH"],
            "HOME": str(tmp_path / "home"),
            "B12_STATE_DIR": str(settings.state_dir),
            "B12_MODEL": settings.model,
            "B12_MODEL_PROFILE": str(settings.model_profile),
            "B12_TOKENIZER_DIR": str(settings.tokenizer_dir),
            "B12_NUM_CTX": str(settings.num_ctx),
            "B12_OUTPUT_TOKENS": str(settings.output_tokens),
        },
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.DEVNULL,
    )
    assert await asyncio.wait_for(second.wait(), 20) != 0
    assert first.returncode is None
    first.terminate()
    await first.wait()


async def test_failed_migration_rolls_back_by_restoring_snapshot(ops):
    _, settings, open_one = ops
    runtime = open_one()
    actor = runtime.control.create_actor(owner=True, consent=True)
    record = runtime.memory.remember("перед міграцією", actor)
    snapshot = runtime.operations.create_snapshot(kind="pre_migration")
    runtime.close()
    # Simulate an interrupted/incompatible migration that leaves a future schema version.
    database = settings.state_dir / "memory" / "memory.sqlite3"
    connection = sqlite3.connect(database)
    connection.execute("PRAGMA user_version=99")
    connection.commit()
    connection.close()
    from b12.runtime import open_runtime
    from b12.service import Operations

    with pytest.raises(RuntimeError, match="schema"):
        open_runtime(settings)
    await Operations(settings.state_dir).restore(snapshot["id"], settings)
    restored = open_one()
    assert restored.memory.is_live(record.id, actor)
