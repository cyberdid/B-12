"""Privacy-minimal, bounded activity journal for optional desktop integrations.

Only provider, allowlisted event name, UTC timestamp, keyed session pseudonym, and
an event count are persisted. Hook payloads are never retained.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import secrets
import tempfile
import threading
from collections import Counter
from datetime import UTC, date, datetime, timedelta
from datetime import time as datetime_time
from pathlib import Path
from typing import Any

ACCEPTED_EVENTS: dict[str, tuple[str, ...]] = {
    "claude": (
        "SessionStart",
        "UserPromptSubmit",
        "PreToolUse",
        "PostToolUse",
        "PostToolUseFailure",
        "PermissionRequest",
        "Notification",
        "Stop",
        "StopFailure",
        "Interrupt",
        "SubagentStart",
        "SubagentStop",
        "PreCompact",
        "PostCompact",
        "SessionEnd",
    ),
    "codex": (
        "SessionStart",
        "UserPromptSubmit",
        "PreToolUse",
        "PermissionRequest",
        "PostToolUse",
        "PreCompact",
        "SubagentStart",
        "SubagentStop",
        "Stop",
        "Interrupt",
        "SessionEnd",
    ),
    # Antigravity hooks receive only metadata. PreToolUse/Stop have required
    # protocol decisions; the observer delegates to policy and allows normal stop.
    "antigravity": ("SessionStart", "PreInvocation", "PreToolUse", "PostToolUse", "Stop"),
}
HOOK_OWNER_MARKER = "b12-desktop-observer-v1"

_SESSION_KEY_RE = re.compile(r"^[0-9a-f]{24}$")
_RECORD_KEYS = {"provider", "event", "at", "session", "count"}
_THREAD_LOCK = threading.RLock()


def default_activity_path() -> Path:
    """Return a stable per-user location shared by the UI and hook subprocesses."""
    explicit = os.environ.get("B12_DESKTOP_ACTIVITY_FILE")
    if explicit:
        return Path(explicit).expanduser()
    state_dir = os.environ.get("B12_STATE_DIR")
    if state_dir:
        return Path(state_dir).expanduser() / "desktop" / "activity.jsonl"
    xdg_state = os.environ.get("XDG_STATE_HOME")
    base = Path(xdg_state).expanduser() if xdg_state else Path.home() / ".local" / "state"
    return base / "b12" / "desktop" / "activity.jsonl"


def _utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")


class ActivityJournal:
    """Read and append privacy-minimal event records without retaining hook payloads."""

    def __init__(
        self,
        path: str | Path | None = None,
        *,
        max_records: int = 1000,
        max_bytes: int = 256 * 1024,
    ):
        self.path = Path(path) if path is not None else default_activity_path()
        self.max_records = max(1, min(int(max_records), 10_000))
        self.max_bytes = max(4096, min(int(max_bytes), 4 * 1024 * 1024))
        self._salt_path = self.path.with_name(f".{self.path.name}.salt")
        self._lock_path = self.path.with_name(f".{self.path.name}.lock")

    @classmethod
    def default(cls) -> ActivityJournal:
        return cls(default_activity_path())

    def record(
        self,
        provider: str,
        event: str,
        session_id: str | None = None,
        *,
        at: str | None = None,
    ) -> bool:
        """Persist one allowlisted metadata record; return False for invalid input."""
        if provider not in ACCEPTED_EVENTS or event not in ACCEPTED_EVENTS[provider]:
            return False
        if at is None:
            at = _utc_now()
        if not _valid_timestamp(at):
            return False
        session_key = self._session_pseudonym(provider, session_id) if session_id else None
        record = {
            "provider": provider,
            "event": event,
            "at": at,
            "session": session_key,
            "count": 1,
        }
        line = json.dumps(record, sort_keys=True, separators=(",", ":"))
        if len(line.encode("utf-8")) > 2048:
            return False
        try:
            with self._file_lock():
                records = self._read_records_unlocked()
                records.append(record)
                self._write_records_unlocked(records[-self.max_records :])
        except OSError:
            return False
        return True

    def snapshot(self, *, limit: int = 200) -> list[dict[str, Any]]:
        """Return newest valid records only; no raw hook data is present in the schema."""
        limit = max(0, min(int(limit), self.max_records))
        if limit == 0 or not self.path.exists():
            return []
        try:
            with self._file_lock():
                records = self._read_records_unlocked()
        except OSError:
            return []
        return records[-limit:]

    def counts(self, *, since: datetime | None = None) -> dict[str, Any]:
        """Summarize event counts by provider/type and distinct session pseudonyms."""
        rows = self.snapshot(limit=self.max_records)
        if since is not None:
            if since.tzinfo is None:
                since = since.replace(tzinfo=UTC)
            rows = [row for row in rows if _parse_timestamp(row["at"]) >= since]
        providers = Counter(row["provider"] for row in rows)
        events = Counter(row["event"] for row in rows)
        sessions = {row["session"] for row in rows if row["session"]}
        return {
            "total": sum(row["count"] for row in rows),
            "by_provider": dict(providers),
            "by_event": dict(events),
            "sessions": len(sessions),
            "last_event_at": rows[-1]["at"] if rows else None,
        }

    def mission_report(
        self, day: date | None = None, *, provider: str | None = None
    ) -> dict[str, int | str]:
        """Summarize today's privacy-minimal coding-agent events without payloads."""
        local_now = datetime.now().astimezone()
        report_day = day or local_now.date()
        local_midnight = datetime.combine(report_day, datetime_time.min, tzinfo=local_now.tzinfo)
        rows = [
            row
            for row in self.snapshot(limit=self.max_records)
            if _parse_timestamp(row["at"]) >= local_midnight.astimezone(UTC)
            and _parse_timestamp(row["at"]) < (local_midnight + timedelta(days=1)).astimezone(UTC)
            and (provider in (None, "all") or row["provider"] == provider)
        ]
        prompts = sum(row["event"] == "UserPromptSubmit" for row in rows)
        actions = sum(row["event"] == "PreToolUse" for row in rows)
        approvals = sum(row["event"] in {"PermissionRequest", "Notification"} for row in rows)
        errors = sum(row["event"] in {"PostToolUseFailure", "StopFailure"} for row in rows)
        completed = sum(row["event"] in {"Stop", "SessionEnd"} for row in rows)
        sessions = {
            row["session"]
            for row in rows
            if row["session"] and row["event"] in {"SessionStart", "UserPromptSubmit"}
        }
        return {
            "day": report_day.isoformat(),
            "prompts": prompts,
            "actions": actions,
            "approvals": approvals,
            "errors": errors,
            "completed": completed,
            "sessions": len(sessions),
        }

    def clear(self) -> None:
        """Delete journal records and its pseudonym salt after explicit user action."""
        with self._file_lock():
            self.path.unlink(missing_ok=True)
            self._salt_path.unlink(missing_ok=True)

    def _session_pseudonym(self, provider: str, session_id: str | None) -> str | None:
        if not isinstance(session_id, str) or not session_id or len(session_id) > 512:
            return None
        salt = self._load_or_create_salt()
        material = f"{provider}\0{session_id}".encode("utf-8", "replace")
        return hmac.new(salt, material, hashlib.sha256).hexdigest()[:24]

    def _load_or_create_salt(self) -> bytes:
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        try:
            os.chmod(self.path.parent, 0o700)
        except OSError:
            pass
        try:
            data = self._salt_path.read_bytes()
            if len(data) == 32:
                try:
                    os.chmod(self._salt_path, 0o600)
                except OSError:
                    pass
                return data
        except FileNotFoundError:
            pass
        candidate = secrets.token_bytes(32)
        try:
            fd = os.open(self._salt_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            data = self._salt_path.read_bytes()
            if len(data) == 32:
                return data
            raise OSError("invalid_activity_salt") from None
        with os.fdopen(fd, "wb") as output:
            output.write(candidate)
            output.flush()
            os.fsync(output.fileno())
        return candidate

    def _read_records_unlocked(self) -> list[dict[str, Any]]:
        try:
            raw = self.path.read_bytes()
        except FileNotFoundError:
            return []
        if len(raw) > self.max_bytes * 2:
            raw = raw[-self.max_bytes * 2 :]
        rows: list[dict[str, Any]] = []
        for line in raw.splitlines()[-self.max_records * 2 :]:
            if len(line) > 2048:
                continue
            try:
                value = json.loads(line)
            except (ValueError, TypeError):
                continue
            if _valid_record(value):
                rows.append(value)
        return rows[-self.max_records :]

    def _write_records_unlocked(self, rows: list[dict[str, Any]]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        payload = "".join(
            json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n" for row in rows
        ).encode("utf-8")
        while len(payload) > self.max_bytes and rows:
            rows.pop(0)
            payload = "".join(
                json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n" for row in rows
            ).encode("utf-8")
        mode = 0o600
        fd, temporary = tempfile.mkstemp(prefix=f".{self.path.name}.", dir=self.path.parent)
        try:
            os.fchmod(fd, mode)
            with os.fdopen(fd, "wb") as output:
                output.write(payload)
                output.flush()
                os.fsync(output.fileno())
            os.replace(temporary, self.path)
            _fsync_directory(self.path.parent)
        except BaseException:
            try:
                os.close(fd)
            except OSError:
                pass
            try:
                os.unlink(temporary)
            except OSError:
                pass
            raise

    class _Lock:
        def __init__(self, journal: ActivityJournal):
            self.journal = journal
            self.file = None

        def __enter__(self):
            _THREAD_LOCK.acquire()
            try:
                self.journal.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
                self.file = self.journal._lock_path.open("a+b")
                try:
                    os.chmod(self.journal._lock_path, 0o600)
                except OSError:
                    pass
                if os.name == "nt":
                    import msvcrt

                    self.file.seek(0, os.SEEK_END)
                    if self.file.tell() == 0:
                        self.file.write(b"\0")
                        self.file.flush()
                    self.file.seek(0)
                    msvcrt.locking(self.file.fileno(), msvcrt.LK_LOCK, 1)
                else:
                    import fcntl

                    fcntl.flock(self.file.fileno(), fcntl.LOCK_EX)
            except BaseException:
                if self.file is not None:
                    self.file.close()
                _THREAD_LOCK.release()
                raise
            return self

        def __exit__(self, *_exc):
            try:
                if self.file is not None:
                    if os.name == "nt":
                        import msvcrt

                        self.file.seek(0)
                        msvcrt.locking(self.file.fileno(), msvcrt.LK_UNLCK, 1)
                    else:
                        import fcntl

                        fcntl.flock(self.file.fileno(), fcntl.LOCK_UN)
                    self.file.close()
            finally:
                _THREAD_LOCK.release()

    def _file_lock(self) -> ActivityJournal._Lock:
        return self._Lock(self)


def _valid_record(value: Any) -> bool:
    if not isinstance(value, dict) or set(value) != _RECORD_KEYS:
        return False
    provider = value.get("provider")
    event = value.get("event")
    session = value.get("session")
    return (
        provider in ACCEPTED_EVENTS
        and event in ACCEPTED_EVENTS[provider]
        and isinstance(value.get("at"), str)
        and _valid_timestamp(value["at"])
        and (session is None or (isinstance(session, str) and _SESSION_KEY_RE.fullmatch(session)))
        and type(value.get("count")) is int
        and value["count"] == 1
    )


def _valid_timestamp(value: str) -> bool:
    try:
        _parse_timestamp(value)
    except (TypeError, ValueError):
        return False
    return True


def _parse_timestamp(value: str) -> datetime:
    if not isinstance(value, str):
        raise TypeError("timestamp must be text")
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    result = datetime.fromisoformat(normalized)
    if result.tzinfo is None:
        raise ValueError("timestamp must include timezone")
    return result.astimezone(UTC)


def _fsync_directory(path: Path) -> None:
    if os.name == "nt":
        return
    fd = os.open(path, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)
