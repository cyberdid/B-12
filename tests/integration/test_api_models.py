"""Owner-only model switching and feedback routes (ADR-023, TUI)."""

import json
import shutil

import httpx

from b12.tui.client import ApiClient


def auth(token):
    return {"Authorization": f"Bearer {token}"}


def _isolate(app, tmp_path, settings_profile, tokenizer_dir, *clis):
    """Point the catalog at a test share dir and a fake PATH."""
    models = app.state.runtime.models
    share = tmp_path / "share"
    (share / "profiles").mkdir(parents=True, exist_ok=True)
    spec = json.loads(settings_profile.read_text())
    (share / "profiles" / "test.json").write_text(json.dumps(spec))
    target = share / "tokenizers" / "test" / spec["revision"]
    if not target.exists():
        shutil.copytree(tokenizer_dir, target)
    models.share = share
    models.which = lambda name: f"/usr/bin/{name}" if name in clis else None
    return models


async def _guest(client, token):
    return (
        await client.post(
            "/api/guests",
            json={"consent": True, "capabilities": ["time.read"]},
            headers=auth(token),
        )
    ).json()["token"]


async def test_routes_are_owner_only(api):
    _, client, token, _, _ = api
    guest = await _guest(client, token)
    for method, path, body in (
        ("GET", "/api/models", None),
        ("GET", "/api/models/status", None),
        ("POST", "/api/models/active", {"id": "codex:gpt-6-luna"}),
        ("POST", "/api/feedback", {"turn_id": "t", "session_id": "s", "note": "x"}),
    ):
        response = await client.request(method, path, json=body, headers=auth(guest))
        assert response.status_code == 403, path


async def test_list_switch_and_status(api):
    _, client, token, app, tmp_path = api
    settings = app.state.runtime.settings
    _isolate(app, tmp_path, settings.model_profile, settings.tokenizer_dir, "codex")
    listed = (await client.get("/api/models", headers=auth(token))).json()
    ids = [c["id"] for c in listed["choices"]]
    assert listed["active"] == "local:test-model" and "codex:gpt-6-luna" in ids
    switched = await client.post(
        "/api/models/active", json={"id": "codex:gpt-6-luna"}, headers=auth(token)
    )
    assert switched.status_code == 200 and switched.json()["active"] == "codex:gpt-6-luna"
    status = (await client.get("/api/models/status", headers=auth(token))).json()
    assert status["id"] == "codex:gpt-6-luna" and status["state"] == "ready"
    unknown = await client.post("/api/models/active", json={"id": "nope"}, headers=auth(token))
    assert unknown.status_code == 404


async def test_feedback_is_appended_with_the_active_model(api):
    _, client, token, app, _ = api
    response = await client.post(
        "/api/feedback",
        json={"turn_id": "t-1", "session_id": "s-1", "note": "вигадала дату"},
        headers=auth(token),
    )
    assert response.status_code == 200
    path = app.state.runtime.settings.state_dir / "feedback.jsonl"
    (entry,) = [json.loads(line) for line in path.read_text().splitlines()]
    assert entry["note"] == "вигадала дату" and entry["model_id"] == "local:test-model"
    assert entry["turn_id"] == "t-1" and entry["at"]


async def test_client_methods_hit_the_routes():
    seen = []

    def handler(request):
        seen.append((request.method, request.url.path, request.content))
        return httpx.Response(200, json={"ok": True})

    client = ApiClient("http://x", "tok", transport=httpx.MockTransport(handler))
    await client.models()
    await client.switch_model("claude:claude-opus-5-5")
    await client.model_status()
    await client.feedback("t", "s", "нотатка")
    await client.close()
    assert [(m, p) for m, p, _ in seen] == [
        ("GET", "/api/models"),
        ("POST", "/api/models/active"),
        ("GET", "/api/models/status"),
        ("POST", "/api/feedback"),
    ]
    assert json.loads(seen[1][2]) == {"id": "claude:claude-opus-5-5"}
