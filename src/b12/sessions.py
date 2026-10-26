"""Persistent working history for consented actors; volatile history lives in Agent.

Only complete turns are committed, atomically. Every turn carries opaque evidence
tags (memory/document/tool_result UUIDs) for dependent-copy purge: forgetting an
evidence ID deletes every tagged turn, including user text, tool arguments/results
and final replies. Text never linked to a tool/evidence ID is not tracked and is
removed only by clear_session. Checkpoints hold approval-waiting turn state.
"""

import json
import os
import sqlite3
from collections.abc import Callable, Mapping
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

EVIDENCE_KINDS = frozenset({"memory", "document", "tool_result"})

_SCHEMA = """
CREATE TABLE IF NOT EXISTS turns(sequence INTEGER PRIMARY KEY, turn_id TEXT UNIQUE NOT NULL,
 session_id TEXT NOT NULL, actor_id TEXT NOT NULL, created_at TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS turns_session ON turns(session_id, actor_id);
CREATE TABLE IF NOT EXISTS messages(id TEXT PRIMARY KEY, turn_id TEXT NOT NULL,
 position INTEGER NOT NULL, role TEXT NOT NULL, content TEXT NOT NULL, tool_calls TEXT,
 tool_name TEXT, tool_call_id TEXT);
CREATE INDEX IF NOT EXISTS messages_turn ON messages(turn_id, position);
CREATE TABLE IF NOT EXISTS checkpoints(turn_id TEXT PRIMARY KEY, session_id TEXT NOT NULL,
 actor_id TEXT NOT NULL, state TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS tags(turn_id TEXT NOT NULL, actor_id TEXT NOT NULL,
 evidence_id TEXT NOT NULL, kind TEXT NOT NULL, PRIMARY KEY(turn_id, evidence_id));
CREATE INDEX IF NOT EXISTS tags_evidence ON tags(actor_id, evidence_id);
CREATE TABLE IF NOT EXISTS purge_turns(operation_id TEXT NOT NULL, turn_id TEXT NOT NULL,
 PRIMARY KEY(operation_id, turn_id));
CREATE TABLE IF NOT EXISTS applied_invalidations(operation_id TEXT PRIMARY KEY);
"""


def _uuid(value) -> str:
    if not isinstance(value, str):
        raise ValueError("UUID text required")
    UUID(value)
    return value


def _tags(tags: Mapping[str, str]) -> list[tuple[str, str]]:
    if not isinstance(tags, Mapping):
        raise ValueError("tags must map evidence IDs to kinds")
    result = []
    for evidence_id, kind in tags.items():
        _uuid(evidence_id)
        if kind not in EVIDENCE_KINDS:
            raise ValueError("unsupported evidence kind")
        result.append((evidence_id, kind))
    return result


class SessionStore:
    """Dedicated private directory, same-thread API, physical delete on purge."""

    def __init__(self, path: Path):
        self.path = Path(path).absolute()
        if self.path.is_symlink():
            raise ValueError("session directory cannot be a symlink")
        missing = []
        parent = self.path
        while not parent.exists():
            missing.append(parent)
            parent = parent.parent
        for directory in reversed(missing):
            directory.mkdir(mode=0o700)
        self.path.chmod(0o700)
        db_path = self.path / "sessions.sqlite3"
        fd = os.open(db_path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        os.fchmod(fd, 0o600)
        os.close(fd)
        self.db = sqlite3.connect(db_path, isolation_level=None)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA secure_delete=ON")
        self.db.execute("PRAGMA journal_mode=DELETE")
        self.db.execute("PRAGMA synchronous=FULL")
        self.db.executescript(_SCHEMA)

    def close(self):
        self.db.close()

    @contextmanager
    def _atomic(self):
        self.db.execute("BEGIN IMMEDIATE")
        try:
            yield
            self.db.execute("COMMIT")
        except BaseException:
            self.db.execute("ROLLBACK")
            raise

    def _bound(self, session_id: str, actor_id: str) -> None:
        row = self.db.execute(
            "SELECT actor_id FROM turns WHERE session_id=? UNION "
            "SELECT actor_id FROM checkpoints WHERE session_id=? LIMIT 1",
            (session_id, session_id),
        ).fetchone()
        if row is not None and row[0] != actor_id:
            raise PermissionError("session is bound to another actor")

    def commit_turn(
        self,
        session_id: str,
        actor_id: str,
        turn_id: str,
        messages: list[dict],
        *,
        tags: Mapping[str, str],
    ) -> None:
        for value in (session_id, actor_id, turn_id):
            _uuid(value)
        rows = _tags(tags)
        with self._atomic():
            self._bound(session_id, actor_id)
            self.db.execute(
                "INSERT INTO turns(turn_id,session_id,actor_id,created_at) VALUES (?,?,?,?)",
                (turn_id, session_id, actor_id, datetime.now(UTC).isoformat()),
            )
            for position, message in enumerate(messages):
                calls = message.get("tool_calls")
                self.db.execute(
                    "INSERT INTO messages VALUES (?,?,?,?,?,?,?,?)",
                    (
                        _uuid(message.get("id") or str(uuid4())),
                        turn_id,
                        position,
                        message["role"],
                        message["content"],
                        json.dumps(calls, ensure_ascii=False) if calls else None,
                        message.get("tool_name"),
                        message.get("tool_call_id"),
                    ),
                )
            self.db.executemany(
                "INSERT INTO tags VALUES (?,?,?,?)",
                ((turn_id, actor_id, evidence_id, kind) for evidence_id, kind in rows),
            )
            self.db.execute("DELETE FROM checkpoints WHERE turn_id=?", (turn_id,))

    def history(
        self,
        session_id: str,
        actor_id: str,
        *,
        max_turns: int = 20,
        live: Callable[[str, str], bool] | None = None,
    ) -> list[dict]:
        """Latest complete turns, oldest first; `live` hides turns with dead evidence."""
        if type(max_turns) is not int or max_turns < 0:
            raise ValueError("max_turns must be a nonnegative integer")
        selected = []
        for row in self.db.execute(
            "SELECT turn_id FROM turns WHERE session_id=? AND actor_id=? ORDER BY sequence DESC",
            (session_id, actor_id),
        ):
            if len(selected) >= max_turns:
                break
            if live is not None and not all(
                live(tag["evidence_id"], tag["kind"])
                for tag in self.db.execute(
                    "SELECT evidence_id,kind FROM tags WHERE turn_id=?", (row["turn_id"],)
                )
            ):
                continue
            selected.append(row["turn_id"])
        result = []
        for turn_id in reversed(selected):
            for message in self.db.execute(
                "SELECT * FROM messages WHERE turn_id=? ORDER BY position", (turn_id,)
            ):
                item = {
                    "id": message["id"],
                    "turn_id": turn_id,
                    "role": message["role"],
                    "content": message["content"],
                }
                if message["tool_calls"]:
                    item["tool_calls"] = json.loads(message["tool_calls"])
                for key in ("tool_name", "tool_call_id"):
                    if message[key] is not None:
                        item[key] = message[key]
                result.append(item)
        return result

    def save_checkpoint(
        self, turn_id: str, session_id: str, actor_id: str, state: dict, *, tags: Mapping[str, str]
    ) -> None:
        for value in (session_id, actor_id, turn_id):
            _uuid(value)
        rows = _tags(tags)
        encoded = json.dumps(state, ensure_ascii=False, allow_nan=False)
        with self._atomic():
            self._bound(session_id, actor_id)
            self.db.execute(
                "INSERT OR REPLACE INTO checkpoints VALUES (?,?,?,?)",
                (turn_id, session_id, actor_id, encoded),
            )
            self.db.executemany(
                "INSERT OR IGNORE INTO tags VALUES (?,?,?,?)",
                ((turn_id, actor_id, evidence_id, kind) for evidence_id, kind in rows),
            )

    def load_checkpoint(self, turn_id: str, actor_id: str) -> dict | None:
        row = self.db.execute(
            "SELECT state FROM checkpoints WHERE turn_id=? AND actor_id=?", (turn_id, actor_id)
        ).fetchone()
        return json.loads(row[0]) if row else None

    def drop_checkpoint(self, turn_id: str, actor_id: str) -> None:
        with self._atomic():
            self.db.execute(
                "DELETE FROM checkpoints WHERE turn_id=? AND actor_id=?", (turn_id, actor_id)
            )
            if not self.db.execute("SELECT 1 FROM turns WHERE turn_id=?", (turn_id,)).fetchone():
                self.db.execute("DELETE FROM tags WHERE turn_id=?", (turn_id,))

    def _delete_turns(self, turn_ids) -> None:
        for turn_id in turn_ids:
            self.db.execute("DELETE FROM messages WHERE turn_id=?", (turn_id,))
            self.db.execute("DELETE FROM checkpoints WHERE turn_id=?", (turn_id,))
            self.db.execute("DELETE FROM tags WHERE turn_id=?", (turn_id,))
            self.db.execute("DELETE FROM turns WHERE turn_id=?", (turn_id,))

    def purge_evidence(
        self, operation_id: str, actor_id: str, evidence_ids: tuple[str, ...]
    ) -> list[str]:
        """Idempotent purge hook; returns every turn ID ever affected by this operation."""
        _uuid(operation_id)
        for evidence_id in evidence_ids:
            _uuid(evidence_id)
        with self._atomic():
            affected = {
                row[0]
                for evidence_id in evidence_ids
                for row in self.db.execute(
                    "SELECT turn_id FROM tags WHERE actor_id=? AND evidence_id=?",
                    (actor_id, evidence_id),
                )
            }
            self.db.executemany(
                "INSERT OR IGNORE INTO purge_turns VALUES (?,?)",
                ((operation_id, turn_id) for turn_id in sorted(affected)),
            )
            self._delete_turns(affected)
            return [
                row[0]
                for row in self.db.execute(
                    "SELECT turn_id FROM purge_turns WHERE operation_id=? ORDER BY turn_id",
                    (operation_id,),
                )
            ]

    def clear_session(self, session_id: str, actor_id: str) -> None:
        with self._atomic():
            turns = [
                row[0]
                for row in self.db.execute(
                    "SELECT turn_id FROM turns WHERE session_id=? AND actor_id=? UNION "
                    "SELECT turn_id FROM checkpoints WHERE session_id=? AND actor_id=?",
                    (session_id, actor_id, session_id, actor_id),
                )
            ]
            self._delete_turns(turns)

    def invalidation_applied(self, operation_id: str) -> bool:
        return bool(
            self.db.execute(
                "SELECT 1 FROM applied_invalidations WHERE operation_id=?", (operation_id,)
            ).fetchone()
        )

    def mark_invalidation_applied(self, operation_id: str) -> None:
        _uuid(operation_id)
        with self._atomic():
            self.db.execute(
                "INSERT OR IGNORE INTO applied_invalidations VALUES (?)", (operation_id,)
            )
