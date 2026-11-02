"""CLI while `b12 serve` runs: the server owns the runtime, the CLI goes through its API."""

import asyncio
import json
import os
import socket
import subprocess
import sys
import time

import httpx
import pytest

from b12.service import RuntimeLock


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


@pytest.fixture
def env(scripted_ollama, tmp_path):
    _, settings = scripted_ollama
    return {
        "PATH": os.environ["PATH"],
        "HOME": str(tmp_path / "home"),
        "B12_STATE_DIR": str(tmp_path / "state"),
        "B12_MODEL": settings.model,
        "B12_OLLAMA_URL": settings.ollama_url,
        "B12_MODEL_PROFILE": str(settings.model_profile),
        "B12_TOKENIZER_DIR": str(settings.tokenizer_dir),
        "B12_NUM_CTX": str(settings.num_ctx),
        "B12_OUTPUT_TOKENS": str(settings.output_tokens),
    }


def _cli(env, *args, api_url=None):
    run_env = {**env, **({"B12_API_URL": api_url} if api_url else {})}
    done = subprocess.run(
        [sys.executable, "-m", "b12.cli", *args],
        env=run_env,
        capture_output=True,
        text=True,
        timeout=120,
    )
    return done.returncode, done.stdout, done.stderr


async def _start_server(env, port):
    process = subprocess.Popen(
        [sys.executable, "-m", "b12.cli", "serve", "--port", str(port), "--no-autonomy"],
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    url = f"http://127.0.0.1:{port}"
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        try:
            if httpx.get(f"{url}/api/health", timeout=1).status_code == 200:
                return process, url
        except httpx.HTTPError:
            pass
        await asyncio.sleep(0.2)
    process.kill()
    raise AssertionError("server did not start")


def _stop(process):
    process.terminate()
    try:
        process.wait(timeout=20)
    except subprocess.TimeoutExpired:
        process.kill()


async def test_cli_uses_the_running_server_and_forgets_during_an_active_turn(scripted_ollama, env):
    state, _ = scripted_ollama
    code, out, err = await asyncio.to_thread(_cli, env, "init")
    assert code == 0, err

    process, url = await _start_server(env, _free_port())
    try:
        token = open(os.path.join(env["B12_STATE_DIR"], "api", "owner.token")).read().strip()
        headers = {"Authorization": f"Bearer {token}"}
        async with httpx.AsyncClient(base_url=url, headers=headers, timeout=60) as client:
            session = (await client.get("/api/cli-session")).json()["session_id"]

            code, out, err = await asyncio.to_thread(
                _cli, env, "memory", "remember", "Тестовий запис для A-02", api_url=url
            )
            assert code == 0, err
            memory_id = json.loads(out)["id"]

            state["script"] = [{"hang": True}]
            turn = asyncio.create_task(
                client.post(
                    "/api/chat",
                    json={"session_id": session, "text": "довга відповідь", "timeout_s": 120},
                )
            )
            await asyncio.wait_for(state["chat_started"].wait(), 30)

            code, out, err = await asyncio.to_thread(
                _cli, env, "memory", "forget", memory_id, api_url=url
            )
            assert code == 0, err
            receipt = json.loads(out)
            assert receipt["state"] == "complete"
            assert "database" not in err.lower()

            await asyncio.wait_for(turn, 60)
    finally:
        _stop(process)


async def test_cli_refuses_when_the_server_holds_the_state_but_its_api_is_unreachable(
    scripted_ollama, env
):
    state_dir = env["B12_STATE_DIR"]
    os.makedirs(state_dir, exist_ok=True)
    code, _, err = await asyncio.to_thread(_cli, env, "init")
    assert code == 0, err
    lock = RuntimeLock(state_dir)
    try:
        code, out, _ = await asyncio.to_thread(
            _cli, env, "status", api_url=f"http://127.0.0.1:{_free_port()}"
        )
        assert code == 4
        assert json.loads(out)["error"] == "server_unavailable"
    finally:
        lock.release()


async def test_a_command_without_an_api_endpoint_asks_for_a_stopped_server(scripted_ollama, env):
    code, _, err = await asyncio.to_thread(_cli, env, "init")
    assert code == 0, err
    process, url = await _start_server(env, _free_port())
    try:
        code, out, _ = await asyncio.to_thread(_cli, env, "session", "clear", api_url=url)
        assert code == 5
        assert json.loads(out)["error"] == "requires_stopped_server"
    finally:
        _stop(process)
