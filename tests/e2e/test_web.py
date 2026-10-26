"""Web UI is served by the API with a strict CSP and uses only real API routes."""

import re
from pathlib import Path

WEB = Path(__file__).resolve().parents[2] / "src" / "b12" / "web"


def auth(token):
    return {"Authorization": f"Bearer {token}"}


async def test_index_and_assets_are_served_with_strict_csp(api):
    _, client, _, _, _ = api
    page = await client.get("/")
    assert page.status_code == 200 and "text/html" in page.headers["content-type"]
    csp = page.headers["content-security-policy"]
    for directive in ("default-src 'self'", "script-src 'self'", "frame-ancestors 'none'"):
        assert directive in csp
    assert "unsafe-inline" not in csp and "unsafe-eval" not in csp
    assert page.headers["x-content-type-options"] == "nosniff"
    assert '<html lang="uk">' in page.text and "<script>" not in page.text
    for asset in ("/static/app.js", "/static/style.css"):
        assert (await client.get(asset)).status_code == 200


async def test_me_and_session_listing_reflect_control_state(api):
    _, client, token, _, _ = api
    me = (await client.get("/api/me", headers=auth(token))).json()
    assert (
        me["owner"] is True and me["consent"] is True and "filesystem.write" in me["capabilities"]
    )
    created = (await client.post("/api/sessions", json={}, headers=auth(token))).json()
    listed = (await client.get("/api/sessions", headers=auth(token))).json()
    assert created["session_id"] in listed
    assert (await client.get("/api/me")).status_code == 401


def test_ui_never_puts_token_in_urls_or_renders_html_from_data():
    script = (WEB / "app.js").read_text()
    assert "innerHTML" not in script and "outerHTML" not in script
    assert "insertAdjacentHTML" not in script and "eval(" not in script
    assert not re.search(r"[?&]token=", script)
    assert 'localStorage.setItem("b12.token"' not in script
    used = set(re.findall(r"[\"'`](/api/[a-z/${}._]*)", script))
    assert used, "UI must call the real API"
