"""Run runtime-backed scenarios behind a loopback-to-Unix-socket model bridge.

The enclosing bubblewrap process must unshare networking. Inside that namespace the only
model route is the loopback listener below, which relays to a host-side allowlist broker.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import httpx

from evals.capri_comprehensive.runners import run_runtime_suite
from evals.socket_bridge import SocketBridge

SANDBOX_MARKER = "B12_EVAL_SANDBOX"
BROKER_SOCKET = "B12_EVAL_BROKER_SOCKET"
EXPECTED_OLLAMA_URL = "http://127.0.0.1:11434"
REQUIRED_MODELS = {"b12-bolt-e4b:q4km"}


def _transport_check() -> None:
    required = REQUIRED_MODELS | {os.environ.get("B12_EVAL_MODEL", "gemma4:12b")}
    try:
        with httpx.Client(base_url=EXPECTED_OLLAMA_URL, timeout=5, trust_env=False) as client:
            response = client.get("/api/tags")
            response.raise_for_status()
            models = response.json()["models"]
        installed = {
            item.get("name") or item.get("model") for item in models if isinstance(item, dict)
        }
    except (httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
        raise SystemExit(f"model broker transport check failed: {type(exc).__name__}") from None
    missing = sorted(required - installed)
    if missing:
        raise SystemExit(f"required allowlisted models are unavailable: {', '.join(missing)}")
    print(f"networkless model transport passed: {', '.join(sorted(required))}", flush=True)


def main(ids: list[str] | None = None) -> None:
    if os.environ.get(SANDBOX_MARKER) != "1":
        raise SystemExit("refusing runtime suite outside bubblewrap sandbox")
    socket_value = os.environ.get(BROKER_SOCKET)
    if not socket_value:
        raise SystemExit("missing private model broker socket")
    socket_path = Path(socket_value)
    if not socket_path.is_socket():
        raise SystemExit("model broker socket is unavailable")
    if os.environ.get("B12_EVAL_OLLAMA_URL") != EXPECTED_OLLAMA_URL:
        raise SystemExit("runtime model URL must point to the isolated loopback bridge")

    chosen_ids = sys.argv[1:] if ids is None else ids
    with SocketBridge(socket_path, host="127.0.0.1", port=11434):
        if chosen_ids == ["--transport-check"]:
            _transport_check()
        else:
            run_runtime_suite.main(chosen_ids)


if __name__ == "__main__":
    main()
