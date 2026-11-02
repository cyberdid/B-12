"""End to end through real CLI processes (each command is a fresh process, so every step after
the first is also a restart): a document with a new fact is indexed, a memory cites it, the
memory is recalled with its source, the document changes, and the memory's status follows."""

import asyncio
import json
import os
import socket
import subprocess
import sys
import time

import httpx
import pytest


def _env(settings, tmp_path):
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


@pytest.fixture
def env(scripted_ollama, tmp_path):
    _, settings = scripted_ollama
    return _env(settings, tmp_path)


async def test_a_document_fact_survives_restarts_and_its_memory_follows_the_document(
    scripted_ollama, env, tmp_path
):
    assert (await asyncio.to_thread(_cli, env, "init"))[0] == 0
    doc = tmp_path / "zrazok.txt"
    doc.write_text("Срібло проводить електрику краще за мідь.", encoding="utf-8")

    code, out, err = await asyncio.to_thread(_cli, env, "knowledge", "index", str(doc))
    assert code == 0, err

    code, out, err = await asyncio.to_thread(_cli, env, "knowledge", "search", "срібло")
    assert code == 0, err
    evidence = json.loads(out)[0]["evidence_id"]

    code, out, err = await asyncio.to_thread(
        _cli, env, "memory", "remember", "Срібло краще за мідь", "--document", evidence
    )
    assert code == 0, err
    memory_id = json.loads(out)["id"]

    code, out, err = await asyncio.to_thread(_cli, env, "memory", "search", "срібло")
    assert code == 0, err
    recalled = json.loads(out)
    assert [r["id"] for r in recalled] == [memory_id]
    assert recalled[0]["status"] == "active"
    assert recalled[0]["sources"][0]["id"] == evidence

    doc.write_text("Срібло тепер коштує дорожче за золото.", encoding="utf-8")
    code, out, err = await asyncio.to_thread(_cli, env, "knowledge", "index", str(doc))
    assert code == 0, err

    code, out, err = await asyncio.to_thread(_cli, env, "memory", "search", "срібло")
    assert code == 0, err
    changed = json.loads(out)
    assert changed[0]["status"] == "stale"
    assert changed[0]["status_reason"] == "document_changed"

    code, out, err = await asyncio.to_thread(_cli, env, "knowledge", "remove", str(doc))
    assert code == 0, err
    code, out, err = await asyncio.to_thread(_cli, env, "memory", "search", "срібло")
    assert json.loads(out)[0]["status"] == "stale"


async def test_the_same_lifecycle_through_a_running_server(scripted_ollama, env, tmp_path):
    assert (await asyncio.to_thread(_cli, env, "init"))[0] == 0
    doc = tmp_path / "zrazok.txt"
    doc.write_text("Озон поглинає ультрафіолетове випромінювання.", encoding="utf-8")
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    server = subprocess.Popen(
        [sys.executable, "-m", "b12.cli", "serve", "--port", str(port), "--no-autonomy"],
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    url = f"http://127.0.0.1:{port}"
    try:
        deadline = time.monotonic() + 60
        while True:
            try:
                if httpx.get(f"{url}/api/health", timeout=1).status_code == 200:
                    break
            except httpx.HTTPError:
                pass
            if time.monotonic() > deadline:
                raise AssertionError("server did not start")
            await asyncio.sleep(0.2)

        code, out, err = await asyncio.to_thread(
            _cli, env, "knowledge", "index", str(doc), api_url=url
        )
        assert code == 0, err
        code, out, err = await asyncio.to_thread(
            _cli, env, "knowledge", "search", "озон", api_url=url
        )
        assert code == 0, err
        evidence = json.loads(out)[0]["evidence_id"]
        code, out, err = await asyncio.to_thread(
            _cli,
            env,
            "memory",
            "remember",
            "Озон поглинає ультрафіолет",
            "--document",
            evidence,
            api_url=url,
        )
        assert code == 0, err

        doc.write_text("Озон майже не поглинає ультрафіолет.", encoding="utf-8")
        code, out, err = await asyncio.to_thread(
            _cli, env, "knowledge", "index", str(doc), api_url=url
        )
        assert code == 0, err

        code, out, err = await asyncio.to_thread(
            _cli, env, "memory", "search", "ультрафіолет", api_url=url
        )
        assert code == 0, err
        assert json.loads(out)[0]["status"] == "stale"
    finally:
        server.terminate()
        try:
            server.wait(timeout=20)
        except subprocess.TimeoutExpired:
            server.kill()
