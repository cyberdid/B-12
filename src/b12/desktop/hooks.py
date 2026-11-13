"""Minimal stdin hook entrypoint for Claude Code, Codex, and Antigravity.

The process is observational: it never runs a tool, opens a network socket, or
persists the provider payload. Antigravity receives only protocol-required
pass-through decisions; its configured policies remain authoritative.
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import BinaryIO

from b12.desktop.activity import (
    ACCEPTED_EVENTS,
    HOOK_OWNER_MARKER,
    ActivityJournal,
    default_activity_path,
)

MAX_HOOK_PAYLOAD_BYTES = 512 * 1024


def _session_id(provider: str, payload: dict) -> str | None:
    candidates = {
        "claude": ("session_id", "sessionId"),
        "codex": ("session_id", "sessionId"),
        "antigravity": ("conversationId", "session_id", "sessionId"),
    }.get(provider, ())
    for key in candidates:
        value = payload.get(key)
        if isinstance(value, str) and value and len(value) <= 512:
            return value
    return None


def _read_payload(stream: BinaryIO) -> dict | None:
    raw = stream.read(MAX_HOOK_PAYLOAD_BYTES + 1)
    if len(raw) > MAX_HOOK_PAYLOAD_BYTES:
        return None
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError, TypeError):
        return None
    return value if isinstance(value, dict) else None


def handle_payload(
    provider: str,
    event: str,
    payload: dict,
    *,
    journal: ActivityJournal | None = None,
) -> bool:
    """Validate and persist only event metadata; never retain ``payload`` itself."""
    if provider not in ACCEPTED_EVENTS or event not in ACCEPTED_EVENTS[provider]:
        return False
    if not isinstance(payload, dict):
        return False
    payload_event = payload.get("hook_event_name")
    if isinstance(payload_event, str) and payload_event != event:
        return False
    return (journal or ActivityJournal.default()).record(
        provider,
        event,
        _session_id(provider, payload),
    )


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--provider", required=True)
    parser.add_argument("--event", required=True)
    parser.add_argument("--owner-marker", required=True)
    parser.add_argument("--journal-file", default=str(default_activity_path()))
    return parser.parse_args(argv)


def main(argv: list[str] | None = None, *, stdin: BinaryIO | None = None, stdout=None) -> int:
    """Entry point used by provider hook commands; failures never block the provider."""
    try:
        args = _parse_args(argv)
        if args.owner_marker != HOOK_OWNER_MARKER:
            return _neutral_exit(args.provider, args.event, stdout)
        if args.provider not in ACCEPTED_EVENTS or args.event not in ACCEPTED_EVENTS[args.provider]:
            return _neutral_exit(args.provider, args.event, stdout)
        payload = _read_payload(stdin or sys.stdin.buffer)
        if payload is not None:
            handle_payload(
                args.provider,
                args.event,
                payload,
                journal=ActivityJournal(args.journal_file),
            )
    except (SystemExit, Exception):
        # Hook observers must not break or delay the coding assistant if B-12's
        # journal is unavailable or the provider sends an unexpected payload.
        pass
    parsed = locals().get("args")
    return _neutral_exit(getattr(parsed, "provider", ""), getattr(parsed, "event", ""), stdout)


def _neutral_exit(provider: str, event: str = "", stdout=None) -> int:
    # Antigravity requires a decision for PreToolUse and Stop. `allow` delegates
    # to later hooks/default policy; `stop` permits the normal stop path.
    if provider == "antigravity":
        stream = stdout or sys.stdout
        try:
            if event == "PreToolUse":
                response = {"decision": "allow"}
            elif event == "Stop":
                response = {"decision": "stop"}
            else:
                response = {}
            stream.write(json.dumps(response, separators=(",", ":")) + "\n")
            stream.flush()
        except Exception:
            pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
