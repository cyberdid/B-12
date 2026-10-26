"""Local API over real ASGI and a separate live uvicorn process."""

import asyncio
import json
import os
import socket
import sys

import httpx
import pytest


def auth(token):
    return {"Authorization": f"Bearer {token}"}


def lines(response):
    return [json.loads(line) for line in response.text.splitlines() if line]


async def test_chat_streams_events_and_real_tool_effect(api, tmp_path):
    state, client, token, _, _ = api
    session = (await client.post("/api/sessions", json={}, headers=auth(token))).json()
    target = tmp_path / "api-note.txt"
    state["script"] = [
        {"tool_calls": [("file_write", {"path": str(target), "text": "через API"})]},
        {"content": "Записано."},
    ]
    response = await client.post(
        "/api/chat",
        json={"session_id": session["session_id"], "text": "запиши"},
        headers=auth(token),
    )
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/x-ndjson")
    items = lines(response)
    types = [item["type"] for item in items]
    assert types[0] == "turn_started" and types[-1] == "result"
    assert types.count("turn_completed") == 1
    assert items[-1]["state"] == "completed" and items[-1]["content"] == "Записано."
    assert target.read_text() == "через API"
    history = await client.get(
        f"/api/sessions/{session['session_id']}/history", headers=auth(token)
    )
    assert [m["content"] for m in history.json() if m["role"] != "tool"][-1] == "Записано."


async def test_approval_and_resume_over_api(api):
    state, client, token, _, _ = api
    session = (await client.post("/api/sessions", json={}, headers=auth(token))).json()
    record = (
        await client.post("/api/memory", json={"text": "видалити"}, headers=auth(token))
    ).json()
    state["script"] = [
        {"tool_calls": [("memory_forget", {"memory_id": record["id"]})]},
        {"content": "Забуто."},
    ]
    response = await client.post(
        "/api/chat",
        json={"session_id": session["session_id"], "text": "забудь"},
        headers=auth(token),
    )
    waiting = lines(response)[-1]
    assert waiting["state"] == "awaiting_approval"
    queue = (await client.get("/api/approvals", headers=auth(token))).json()
    assert queue[0]["operation_id"] == waiting["pending_operations"][0]
    decided = await client.post(
        f"/api/approvals/{queue[0]['operation_id']}", json={"approve": True}, headers=auth(token)
    )
    assert decided.status_code == 200
    resumed = await client.post(f"/api/turns/{waiting['turn_id']}/resume", headers=auth(token))
    assert lines(resumed)[-1]["state"] == "completed"
    assert (await client.get("/api/memory?q=видалити", headers=auth(token))).json() == []


async def test_memory_forget_returns_receipt(api):
    _, client, token, _, _ = api
    record = (
        await client.post("/api/memory", json={"text": "факт API"}, headers=auth(token))
    ).json()
    receipt = await client.delete(f"/api/memory/{record['id']}", headers=auth(token))
    assert receipt.status_code == 200 and receipt.json()["state"] == "complete"
    missing = await client.delete(f"/api/memory/{record['id']}", headers=auth(token))
    assert missing.status_code in (200, 404)


async def test_cancel_route_requires_turn_ownership(api):
    _, client, token, _, _ = api
    guest = (
        await client.post(
            "/api/guests",
            json={"consent": True, "capabilities": ["time.read"]},
            headers=auth(token),
        )
    ).json()
    response = await client.post(
        "/api/turns/00000000-0000-0000-0000-000000000000/cancel", headers=auth(guest["token"])
    )
    assert response.status_code == 404


def free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


@pytest.fixture
async def live_server(scripted_ollama, tmp_path):
    state, settings = scripted_ollama
    port = free_port()
    env = {
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
    init = await asyncio.create_subprocess_exec(
        sys.executable, "-m", "b12.cli", "init", env=env, stdout=asyncio.subprocess.DEVNULL
    )
    assert await init.wait() == 0
    server = await asyncio.create_subprocess_exec(
        sys.executable,
        "-m",
        "b12.cli",
        "serve",
        "--port",
        str(port),
        env=env,
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.DEVNULL,
    )
    base = f"http://127.0.0.1:{port}"
    async with httpx.AsyncClient(base_url=base, trust_env=False) as client:
        for _ in range(100):
            try:
                if (await client.get("/api/health")).status_code == 200:
                    break
            except httpx.TransportError:
                await asyncio.sleep(0.1)
        token = (tmp_path / "state" / "api" / "owner.token").read_text().strip()
        yield state, client, token, server
    server.terminate()
    assert await asyncio.wait_for(server.wait(), 10) is not None


async def test_live_server_binds_loopback_and_disconnect_cancels_turn(live_server):
    state, client, token, server = live_server
    session = (await client.post("/api/sessions", json={}, headers=auth(token))).json()
    state["script"] = [{"content": "довга відповідь", "hang": True}, {"content": "після"}]
    async with client.stream(
        "POST",
        "/api/chat",
        json={"session_id": session["session_id"], "text": "довго"},
        headers=auth(token),
    ) as response:
        async for line in response.aiter_lines():
            if json.loads(line)["type"] == "text_delta":
                break
    # Disconnect must cancel the turn: nothing persisted, next turn works.
    for _ in range(50):
        history = await client.get(
            f"/api/sessions/{session['session_id']}/history", headers=auth(token)
        )
        if history.json() == []:
            break
        await asyncio.sleep(0.1)
    response = await client.post(
        "/api/chat",
        json={"session_id": session["session_id"], "text": "ще"},
        headers=auth(token),
    )
    final = lines(response)[-1]
    assert final["state"] == "completed" and final["content"] == "після"
    contents = [m["content"] for m in state["requests"][-1]["messages"]]
    assert "довга відповідь" not in contents and "довго" not in contents
    assert server.returncode is None


async def test_goals_attention_and_proposals_over_api(api):
    _, client, token, app, _ = api
    created = await client.post(
        "/api/goals",
        json={"intent": "Ціль через API", "criteria": "звіт", "allowed_tools": ["time.read"]},
        headers=auth(token),
    )
    assert created.status_code == 200 and created.json()["allowed_tools"] == ["time.read"]
    goal_id = created.json()["id"]
    assert [g["id"] for g in (await client.get("/api/goals", headers=auth(token))).json()] == [
        goal_id
    ]
    paused = await client.post(
        f"/api/goals/{goal_id}/status", json={"status": "paused"}, headers=auth(token)
    )
    assert paused.json()["status"] == "paused"
    achieved = await client.post(
        f"/api/goals/{goal_id}/status", json={"status": "achieved"}, headers=auth(token)
    )
    assert achieved.status_code == 422
    state = await client.post("/api/attention", json={"quiet": True}, headers=auth(token))
    assert state.json() == {"quiet": True, "stopped": False}
    guest = (
        await client.post(
            "/api/guests",
            json={"consent": True, "capabilities": ["time.read"]},
            headers=auth(token),
        )
    ).json()
    denied = await client.post(
        "/api/goals", json={"intent": "x", "criteria": "y"}, headers=auth(guest["token"])
    )
    assert denied.status_code == 403
    assert (await client.get("/api/proposals", headers=auth(token))).json() == []
