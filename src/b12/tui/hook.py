"""Telemetry-only provider hooks: reduce untrusted input before storing anything."""

import hashlib
import math
import re
from datetime import datetime

MAX_INPUT_BYTES = 65_536
SOURCES = ("claude-code", "codex", "antigravity")
_TOKEN = re.compile(r"[A-Za-z0-9_.:-]{1,96}\Z")
_PROJECT = re.compile(r"[\w .-]{1,96}\Z", re.UNICODE)

# Provider names are explicit allowlists; no provider output/decision is interpreted.
_COMMON = {
    "SessionStart": ("session_started", "started"),
    "UserPromptSubmit": ("prompt_submitted", "running"),
    "PreToolUse": ("tool_started", "running"),
    "PostToolUse": ("tool_completed", "completed"),
    "PostToolUseFailure": ("tool_failed", "failed"),
    "PermissionRequest": ("approval_requested", "waiting"),
    "Stop": ("turn_completed", "completed"),
    "SessionEnd": ("session_ended", "ended"),
    "Notification": ("notification", "waiting"),
}
_EVENTS = {source: dict(_COMMON) for source in SOURCES}


def normalize_hook(source: str, payload: dict, now: float | datetime) -> dict | None:
    """Return only bounded metadata; all text, arguments, outputs and paths are dropped.

    Event time is local receipt time, never a provider-supplied timestamp. Session IDs
    are hashed so even a mislabelled path or secret cannot be retained in that field.
    Unknown lifecycle names are deliberately ignored rather than guessed.
    """
    if source not in SOURCES or not isinstance(payload, dict):
        return None
    name = payload.get("hook_event_name")
    if not isinstance(name, str) or name not in _EVENTS[source]:
        return None
    session = payload.get("session_id")
    if not isinstance(session, str) or not session or len(session) > 256:
        return None
    try:
        stamp = now.timestamp() if isinstance(now, datetime) else float(now)
    except (ValueError, TypeError, OverflowError, OSError):
        return None
    if not math.isfinite(stamp) or stamp < 0:
        return None
    kind, status = _EVENTS[source][name]
    session_hash = hashlib.sha256(f"{source}\0{session}".encode(errors="replace")).hexdigest()
    event = {
        "version": 1,
        "source": source,
        "session_id": session_hash[:32],
        "kind": kind,
        "timestamp": stamp,
        "project": "",
        "tool": "",
        "status": status,
    }
    # Never expand or resolve provider paths (including Windows-form paths).
    cwd = payload.get("cwd")
    if isinstance(cwd, str) and len(cwd) <= 4096:
        basename = cwd.replace("\\", "/").rstrip("/").rsplit("/", 1)[-1]
        if basename not in (".", "..") and _PROJECT.fullmatch(basename):
            event["project"] = basename
    tool = payload.get("tool_name")
    if kind.startswith("tool_") and isinstance(tool, str) and _TOKEN.fullmatch(tool):
        event["tool"] = tool
    return event
