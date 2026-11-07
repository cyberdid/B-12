"""Authenticated HTTP client for the optional B-12 desktop companion."""

from __future__ import annotations

import ipaddress
import json
from collections.abc import Callable
from urllib.parse import quote, urlsplit

import httpx


class DesktopApiError(RuntimeError):
    """A stable, display-safe API failure code."""

    def __init__(self, code: str, status_code: int | None = None):
        self.code = code
        self.status_code = status_code
        super().__init__(code)


def validate_loopback_url(url: str) -> str:
    """Return normalized loopback API URL; reject remote or credential-bearing URLs."""
    try:
        parsed = urlsplit(url)
        hostname = (parsed.hostname or "").lower().rstrip(".")
        port = parsed.port
    except ValueError as exc:
        raise ValueError("api_url_invalid") from exc
    if (
        parsed.scheme not in {"http", "https"}
        or not hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or parsed.path not in {"", "/"}
    ):
        raise ValueError("api_url_invalid")
    try:
        loopback = ipaddress.ip_address(hostname).is_loopback
    except ValueError:
        loopback = hostname == "localhost"
    if not loopback:
        raise ValueError("api_url_must_be_loopback")
    authority = f"[{hostname}]" if ":" in hostname else hostname
    if port is not None:
        authority += f":{port}"
    return f"{parsed.scheme}://{authority}"


class DesktopApiClient:
    """Owner-authenticated client; never opens B-12 stores or starts its runtime."""

    def __init__(
        self,
        base_url: str,
        token: str,
        *,
        transport: httpx.BaseTransport | None = None,
    ):
        if not token.strip():
            raise ValueError("owner_token_missing")
        self.base_url = validate_loopback_url(base_url)
        self.http = httpx.Client(
            base_url=self.base_url,
            headers={"Authorization": f"Bearer {token.strip()}"},
            timeout=httpx.Timeout(connect=5.0, read=None, write=30.0, pool=5.0),
            transport=transport,
            trust_env=False,
        )

    def close(self) -> None:
        self.http.close()

    def call(self, method: str, path: str, **kwargs) -> dict | list:
        try:
            response = self.http.request(method, path, **kwargs)
        except httpx.HTTPError as exc:
            raise DesktopApiError("server_unavailable") from exc
        if response.status_code >= 400:
            try:
                detail = response.json().get("detail")
            except (ValueError, AttributeError):
                detail = None
            code = detail if isinstance(detail, str) else f"http_{response.status_code}"
            raise DesktopApiError(code, response.status_code)
        try:
            return response.json()
        except ValueError as exc:
            raise DesktopApiError("invalid_api_response", response.status_code) from exc

    def health(self) -> bool:
        try:
            return self.call("GET", "/api/health") == {"ok": True}
        except DesktopApiError:
            return False

    def me(self) -> dict:
        return self.call("GET", "/api/me")

    def sessions(self) -> list[str]:
        return self.call("GET", "/api/sessions")

    def new_session(self) -> str:
        return self.call("POST", "/api/sessions", json={})["session_id"]

    def history(self, session_id: str) -> list[dict]:
        return self.call("GET", f"/api/sessions/{_segment(session_id)}/history")

    def approvals(self) -> list[dict]:
        return self.call("GET", "/api/approvals")

    def decide(self, operation_id: str, *, approve: bool) -> dict:
        return self.call(
            "POST", f"/api/approvals/{_segment(operation_id)}", json={"approve": approve}
        )

    def resume(self, turn_id: str, on_event: Callable[[dict], None]) -> dict:
        return self._stream("POST", f"/api/turns/{_segment(turn_id)}/resume", {}, on_event)

    def cancel(self, turn_id: str) -> dict:
        return self.call("POST", f"/api/turns/{_segment(turn_id)}/cancel", json={})

    def turn_status(self, turn_id: str) -> dict:
        return self.call("GET", f"/api/turns/{_segment(turn_id)}/status")

    def set_consent(self, consent: bool) -> dict:
        return self.call("POST", "/api/control/consent", json={"consent": consent})

    def memory_records(self, limit: int = 200) -> list[dict]:
        return self.call("GET", f"/api/memory/records?limit={limit}")

    def memory_search(self, query: str) -> list[dict]:
        return self.call("GET", "/api/memory", params={"q": query})

    def memory_add(self, text: str) -> dict:
        return self.call("POST", "/api/memory", json={"text": text})

    def memory_forget(self, memory_id: str) -> dict:
        return self.call("DELETE", f"/api/memory/{_segment(memory_id)}")

    def status(self) -> dict:
        return self.call("GET", "/api/status")

    def voice_status(self) -> dict:
        return self.call("GET", "/api/voice/status")

    def set_voice_muted(self, muted: bool) -> dict:
        return self.call("POST", "/api/voice/mute", json={"muted": muted})

    def cli_session(self) -> str:
        return self.call("GET", "/api/cli-session")["session_id"]

    def stream_turn(
        self,
        session_id: str,
        text: str,
        *,
        persist: bool,
        on_event: Callable[[dict], None],
    ) -> dict:
        body = {
            "session_id": session_id,
            "text": text,
            "persist": persist,
            "timeout_s": 1800.0 if persist else 600.0,
        }
        return self._stream("POST", "/api/chat", body, on_event)

    def _stream(
        self,
        method: str,
        path: str,
        body: dict,
        on_event: Callable[[dict], None],
    ) -> dict:
        result = None
        try:
            with self.http.stream(method, path, json=body) as response:
                if response.status_code >= 400:
                    response.read()
                    try:
                        detail = response.json().get("detail")
                    except (ValueError, AttributeError):
                        detail = None
                    code = detail if isinstance(detail, str) else f"http_{response.status_code}"
                    raise DesktopApiError(code, response.status_code)
                for line in response.iter_lines():
                    if not line.strip():
                        continue
                    try:
                        event = json.loads(line)
                    except (ValueError, TypeError) as exc:
                        raise DesktopApiError("invalid_stream_event") from exc
                    if not isinstance(event, dict) or not isinstance(event.get("type"), str):
                        raise DesktopApiError("invalid_stream_event")
                    on_event(event)
                    if event["type"] == "result":
                        result = event
                    elif event["type"] == "error":
                        result = event
        except httpx.HTTPError as exc:
            raise DesktopApiError("server_unavailable") from exc
        if result is None:
            raise DesktopApiError("turn_result_missing")
        return result


def _segment(value: str) -> str:
    """Encode opaque server identifiers as one path segment."""
    return quote(value, safe="")
