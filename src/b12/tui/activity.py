"""Private, versioned, bounded local UI telemetry; independent of B-12 memory."""

import json
import os
import sqlite3
import time
import uuid
from contextlib import contextmanager
from pathlib import Path

from b12.tui.hook import MAX_INPUT_BYTES, normalize_hook

MAX_EVENTS = 10_000
RETENTION_SECONDS = 14 * 24 * 60 * 60
BUSY_TIMEOUT_SECONDS = 0.1


class ActivityStore:
    """Short-lived SQLite connections allow hook writers while the server owns runtime.

    No runtime stores, model, provider decisions or Textual imports are involved.
    append returns 0 for dropped input; callers may safely ignore telemetry failure.
    """

    def __init__(self, state_dir: Path | str):
        self.directory = Path(state_dir) / "ui"
        self.path = self.directory / "activity.sqlite3"

    @contextmanager
    def _connect(self):
        self.directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        if self.directory.is_symlink():
            raise OSError("activity directory must not be a symlink")
        self.directory.chmod(0o700)
        fd = os.open(self.path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        try:
            os.fchmod(fd, 0o600)
        finally:
            os.close(fd)
        connection = sqlite3.connect(self.path, timeout=BUSY_TIMEOUT_SECONDS)
        try:
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute("PRAGMA secure_delete=ON")
            version = connection.execute("PRAGMA user_version").fetchone()[0]
            if version not in (0, 1):
                raise sqlite3.DatabaseError("unsupported activity schema")
            connection.execute(
                "CREATE TABLE IF NOT EXISTS events ("
                "seq INTEGER PRIMARY KEY AUTOINCREMENT, version INTEGER NOT NULL, "
                "source TEXT NOT NULL, session_id TEXT NOT NULL, task_id TEXT NOT NULL, "
                "kind TEXT NOT NULL, timestamp REAL NOT NULL, project TEXT NOT NULL, "
                "tool TEXT NOT NULL, status TEXT NOT NULL)"
            )
            connection.execute(
                "CREATE TABLE IF NOT EXISTS tasks (source TEXT NOT NULL, "
                "session_id TEXT NOT NULL, task_id TEXT NOT NULL, "
                "PRIMARY KEY (source, session_id))"
            )
            connection.execute("PRAGMA user_version=1")
            for suffix in ("", "-wal", "-shm"):
                path = Path(str(self.path) + suffix)
                if path.exists() and not path.is_symlink():
                    path.chmod(0o600)
            yield connection
        finally:
            connection.close()

    @staticmethod
    def _prune(connection, now):
        connection.execute("DELETE FROM events WHERE timestamp < ?", (now - RETENTION_SECONDS,))
        connection.execute(
            "DELETE FROM events WHERE seq NOT IN "
            "(SELECT seq FROM events ORDER BY seq DESC LIMIT ?)",
            (MAX_EVENTS,),
        )
        connection.execute("DELETE FROM tasks WHERE task_id NOT IN (SELECT task_id FROM events)")

    def append(self, source: str, payload: dict, *, event: str | None = None) -> int:
        """Normalize a single bounded JSON object, persist it, or return 0 on drop."""
        try:
            if not isinstance(payload, dict):
                return 0
            size = 0
            for chunk in json.JSONEncoder(ensure_ascii=True).iterencode(payload):
                size += len(chunk)
                if size > MAX_INPUT_BYTES:
                    return 0
            now = time.time()
            metadata = normalize_hook(source, payload, now, event=event)
            if metadata is None:
                return 0
            with self._connect() as connection, connection:
                connection.execute("BEGIN IMMEDIATE")
                self._prune(connection, now)
                task = connection.execute(
                    "SELECT task_id FROM tasks WHERE source=? AND session_id=?",
                    (metadata["source"], metadata["session_id"]),
                ).fetchone()
                task_id = task[0] if task else uuid.uuid4().hex
                if metadata["kind"] in ("session_started", "prompt_submitted"):
                    task_id = uuid.uuid4().hex
                connection.execute(
                    "INSERT OR REPLACE INTO tasks VALUES (?, ?, ?)",
                    (metadata["source"], metadata["session_id"], task_id),
                )
                metadata["task_id"] = task_id
                columns = ", ".join(metadata)
                marks = ", ".join("?" for _ in metadata)
                cursor = connection.execute(
                    f"INSERT INTO events ({columns}) VALUES ({marks})", tuple(metadata.values())
                )
                if metadata["kind"] in ("turn_completed", "session_ended"):
                    connection.execute(
                        "DELETE FROM tasks WHERE source=? AND session_id=?",
                        (metadata["source"], metadata["session_id"]),
                    )
                self._prune(connection, now)
                return int(cursor.lastrowid)
        except (OSError, sqlite3.Error, ValueError, TypeError, OverflowError, RecursionError):
            return 0

    def after(self, cursor: int, limit: int = 100) -> list[dict]:
        """New events in monotonic sequence order; expiry also runs when only reading."""
        try:
            cursor, limit = max(0, int(cursor)), min(1000, max(0, int(limit)))
            if not limit:
                return []
            with self._connect() as connection, connection:
                self._prune(connection, time.time())
                rows = connection.execute(
                    "SELECT * FROM events WHERE seq > ? ORDER BY seq LIMIT ?", (cursor, limit)
                ).fetchall()
                return [dict(row) for row in rows]
        except (OSError, sqlite3.Error, ValueError, TypeError, OverflowError):
            return []

    def recent(self, limit: int = 100) -> list[dict]:
        """Newest retained events in ascending sequence order for initial UI history."""
        try:
            limit = min(1000, max(0, int(limit)))
            if not limit:
                return []
            with self._connect() as connection, connection:
                self._prune(connection, time.time())
                rows = connection.execute(
                    "SELECT * FROM events ORDER BY seq DESC LIMIT ?", (limit,)
                ).fetchall()
                return [dict(row) for row in reversed(rows)]
        except (OSError, sqlite3.Error, ValueError, TypeError, OverflowError):
            return []

    def clear(self) -> None:
        """Delete UI activity only; keep sequence monotonic for existing polling cursors."""
        with self._connect() as connection:
            with connection:
                connection.execute("DELETE FROM events")
                connection.execute("DELETE FROM tasks")
            connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")
