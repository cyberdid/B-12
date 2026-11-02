"""CLI access while `b12 serve` runs: the server is the only owner of the active runtime.

The CLI decides the mode from the state directory's runtime lock, which `serve` holds for its
whole life. Lock free: the CLI opens the local runtime under that lock. Lock held: the CLI calls
the server's API and never opens the databases itself. If the API cannot be reached while the
lock is held, the CLI reports `server_unavailable` and stops; it never falls back to direct access.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import httpx

DEFAULT_URL = "http://127.0.0.1:8712"


class ServerUnavailable(RuntimeError):
    """The state directory is held by a running B-12, but its API cannot be used."""


class RemoteError(RuntimeError):
    """The API answered with an error; `code` is the API error code."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def api_url() -> str:
    return os.environ.get("B12_API_URL", DEFAULT_URL)


def read_owner_token(state_dir: Path) -> str:
    path = Path(state_dir) / "api" / "owner.token"
    try:
        token = path.read_text().strip()
    except OSError as exc:
        raise ServerUnavailable("owner_token_missing") from exc
    if not token:
        raise ServerUnavailable("owner_token_missing")
    return token


class RemoteClient:
    def __init__(self, url: str, token: str, *, transport=None, timeout: float = 300.0):
        self.http = httpx.Client(
            base_url=url,
            headers={"Authorization": f"Bearer {token}"},
            timeout=timeout,
            transport=transport,
        )

    def call(self, method: str, path: str, **kwargs):
        try:
            response = self.http.request(method, path, **kwargs)
        except httpx.HTTPError as exc:
            raise ServerUnavailable("server_unreachable") from exc
        if response.status_code >= 400:
            try:
                code = response.json().get("detail", f"http_{response.status_code}")
            except ValueError:
                code = f"http_{response.status_code}"
            raise RemoteError(code if isinstance(code, str) else f"http_{response.status_code}")
        return response.json()

    def stream_result(self, method: str, path: str, *, json_body=None) -> dict:
        """Run a streaming endpoint (a turn) through the server; return its final result event."""
        result: dict = {}
        try:
            with self.http.stream(method, path, json=json_body) as response:
                if response.status_code >= 400:
                    raise RemoteError(f"http_{response.status_code}")
                for line in response.iter_lines():
                    if not line.strip():
                        continue
                    event = json.loads(line)
                    if event.get("type") == "result":
                        result = event
        except httpx.HTTPError as exc:
            raise ServerUnavailable("server_unreachable") from exc
        return result

    def close(self) -> None:
        self.http.close()
