"""Authentication/control boundaries of the local API over real ASGI and stores."""

import json

import pytest


def auth(token):
    return {"Authorization": f"Bearer {token}"}


def lines(response):
    return [json.loads(line) for line in response.text.splitlines() if line]


async def test_owner_token_file_is_private_and_not_in_urls(api):
    _, client, token, app, tmp_path = api
    path = tmp_path / "state" / "api" / "owner.token"
    assert oct(path.stat().st_mode & 0o777) == "0o600"
    assert oct(path.parent.stat().st_mode & 0o777) == "0o700"
    response = await client.get(f"/api/tools?token={token}")
    assert response.status_code == 401


@pytest.mark.parametrize(
    "method,path,body",
    [
        ("GET", "/api/tools", None),
        ("POST", "/api/sessions", {}),
        ("POST", "/api/chat", {"session_id": "x", "text": "hi"}),
        ("GET", "/api/memory?q=x", None),
        ("POST", "/api/memory", {"text": "x"}),
        ("GET", "/api/approvals", None),
        ("POST", "/api/guests", {"consent": True, "capabilities": []}),
    ],
)
async def test_unauthenticated_and_wrong_token_are_denied(api, method, path, body):
    state, client, _, _, _ = api
    for headers in ({}, auth("wrong-token"), {"Authorization": "Basic abc"}):
        response = await client.request(method, path, json=body, headers=headers)
        assert response.status_code == 401
    assert state["requests"] == []


async def test_health_is_public_but_minimal(api):
    _, client, _, _, _ = api
    response = await client.get("/api/health")
    assert response.status_code == 200 and response.json() == {"ok": True}


async def test_foreign_origin_and_host_are_rejected(api):
    _, client, token, _, _ = api
    response = await client.post(
        "/api/sessions", json={}, headers={**auth(token), "Origin": "https://evil.example"}
    )
    assert response.status_code == 403
    response = await client.get(
        "/api/tools", headers={**auth(token), "Host": "rebind.evil.example"}
    )
    assert response.status_code == 400
    ok = await client.post(
        "/api/sessions", json={}, headers={**auth(token), "Origin": "http://127.0.0.1:80"}
    )
    assert ok.status_code == 200


async def test_body_cannot_set_actor_consent_or_grant_and_is_bounded(api):
    _, client, token, _, _ = api
    session = (await client.post("/api/sessions", json={}, headers=auth(token))).json()
    for extra in ({"actor_id": "x"}, {"consent": True}, {"grant_id": "g"}, {"owner": True}):
        response = await client.post(
            "/api/chat",
            json={"session_id": session["session_id"], "text": "hi", **extra},
            headers=auth(token),
        )
        assert response.status_code == 422
    huge = await client.post(
        "/api/memory", content=b'{"text":"' + b"x" * 70000 + b'"}', headers=auth(token)
    )
    assert huge.status_code == 413


async def test_guest_is_isolated_and_cannot_use_owner_controls(api):
    state, client, token, _, _ = api
    response = await client.post(
        "/api/guests",
        json={"consent": True, "capabilities": ["memory.read", "memory.write", "time.read"]},
        headers=auth(token),
    )
    guest = response.json()
    owner_record = (
        await client.post("/api/memory", json={"text": "секрет власника"}, headers=auth(token))
    ).json()
    guest_headers = auth(guest["token"])
    assert (await client.get("/api/memory?q=секрет", headers=guest_headers)).json() == []
    denied = await client.delete(f"/api/memory/{owner_record['id']}", headers=guest_headers)
    assert denied.status_code == 404
    assert (await client.get("/api/approvals", headers=guest_headers)).status_code == 403
    assert (
        await client.post(
            "/api/guests", json={"consent": True, "capabilities": []}, headers=guest_headers
        )
    ).status_code == 403
    assert (
        await client.post(
            "/api/control/consent",
            json={"actor_id": guest["actor_id"], "consent": True},
            headers=guest_headers,
        )
    ).status_code == 403
    owner_session = (await client.post("/api/sessions", json={}, headers=auth(token))).json()
    foreign = await client.post(
        "/api/chat",
        json={"session_id": owner_session["session_id"], "text": "чужа сесія"},
        headers=guest_headers,
    )
    assert foreign.status_code == 403 and state["requests"] == []


async def test_guest_cannot_receive_host_capabilities(api):
    _, client, token, _, _ = api
    for capability in ("process.execute", "filesystem.write", "network.http", "memory.forget"):
        response = await client.post(
            "/api/guests",
            json={"consent": True, "capabilities": [capability]},
            headers=auth(token),
        )
        assert response.status_code == 422


async def test_guest_without_consent_cannot_persist_memory(api):
    _, client, token, _, _ = api
    guest = (
        await client.post(
            "/api/guests",
            json={"consent": False, "capabilities": ["memory.write"]},
            headers=auth(token),
        )
    ).json()
    response = await client.post(
        "/api/memory", json={"text": "не зберігати"}, headers=auth(guest["token"])
    )
    assert response.status_code == 403


async def test_consent_changes_only_through_authenticated_owner_control(api):
    _, client, token, app, _ = api
    guest = (
        await client.post(
            "/api/guests",
            json={"consent": False, "capabilities": ["time.read"]},
            headers=auth(token),
        )
    ).json()
    response = await client.post(
        "/api/control/consent",
        json={"actor_id": guest["actor_id"], "consent": True},
        headers=auth(token),
    )
    assert response.status_code == 200
    runtime = app.state.runtime
    assert runtime.control.resolve_actor(guest["actor_id"]).consent is True
    revoke = await client.post(
        "/api/control/consent",
        json={"actor_id": guest["actor_id"], "consent": False},
        headers=auth(guest["token"]),
    )
    assert revoke.status_code == 200
    assert runtime.control.resolve_actor(guest["actor_id"]).consent is False


async def test_revoked_guest_token_stops_working(api):
    _, client, token, _, _ = api
    guest = (
        await client.post(
            "/api/guests",
            json={"consent": True, "capabilities": ["time.read"]},
            headers=auth(token),
        )
    ).json()
    assert (await client.get("/api/tools", headers=auth(guest["token"]))).status_code == 200
    response = await client.delete(f"/api/guests/{guest['actor_id']}", headers=auth(token))
    assert response.status_code == 200
    assert (await client.get("/api/tools", headers=auth(guest["token"]))).status_code == 401
