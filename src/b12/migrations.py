"""Версійована canonical SQLite schema; жодних автоматичних downgrade.

v1: спогади з evidence на спогади. v2: типізовані джерела (`memory_sources`: спогад або
документ KnowledgeIndex з ревізією) і статус спогаду (`active` / `stale`). Оновлення v1→v2
починається з перевіреної резервної копії і не втрачає жодного спогаду чи зв'язку.
"""

import os
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

SCHEMA_VERSION = 2

_SCHEMA_V1 = (
    """CREATE TABLE memories (
        rowid INTEGER PRIMARY KEY AUTOINCREMENT,
        id TEXT NOT NULL UNIQUE,
        actor_id TEXT NOT NULL,
        kind TEXT NOT NULL,
        text TEXT NOT NULL,
        source TEXT NOT NULL,
        created_at TEXT NOT NULL
    )""",
    "CREATE INDEX memories_actor ON memories(actor_id)",
    """CREATE TABLE evidence (
        memory_id TEXT NOT NULL REFERENCES memories(id) ON DELETE CASCADE,
        evidence_id TEXT NOT NULL REFERENCES memories(id),
        position INTEGER NOT NULL,
        PRIMARY KEY(memory_id, evidence_id)
    )""",
    "CREATE INDEX evidence_parent ON evidence(evidence_id)",
    """CREATE VIRTUAL TABLE memory_fts USING fts5(
        text, content='memories', content_rowid='rowid', tokenize='unicode61'
    )""",
    """CREATE TRIGGER memories_insert AFTER INSERT ON memories BEGIN
        INSERT INTO memory_fts(rowid, text) VALUES (new.rowid, new.text);
    END""",
    """CREATE TRIGGER memories_delete AFTER DELETE ON memories BEGIN
        INSERT INTO memory_fts(memory_fts, rowid, text) VALUES ('delete', old.rowid, old.text);
    END""",
    """CREATE TABLE revisions (
        actor_id TEXT PRIMARY KEY, revision INTEGER NOT NULL CHECK(revision >= 0)
    )""",
    """CREATE TABLE purge_operations (
        operation_id TEXT PRIMARY KEY,
        actor_id TEXT NOT NULL,
        target_ids TEXT NOT NULL,
        payload_deleted INTEGER NOT NULL DEFAULT 0 CHECK(payload_deleted IN (0, 1))
    )""",
    "CREATE INDEX purge_actor ON purge_operations(actor_id)",
    """CREATE TABLE purge_stores (
        operation_id TEXT NOT NULL REFERENCES purge_operations(operation_id),
        store TEXT NOT NULL,
        position INTEGER NOT NULL,
        state TEXT NOT NULL CHECK(state IN ('pending', 'complete', 'failed')),
        error_code TEXT,
        PRIMARY KEY(operation_id, store)
    )""",
    """CREATE TABLE tombstones (
        memory_id TEXT PRIMARY KEY,
        actor_id TEXT NOT NULL,
        operation_id TEXT NOT NULL REFERENCES purge_operations(operation_id)
    )""",
    """CREATE TABLE audit (
        sequence INTEGER PRIMARY KEY,
        actor_id TEXT NOT NULL,
        action TEXT NOT NULL,
        memory_id TEXT,
        operation_id TEXT,
        created_at TEXT NOT NULL,
        previous_hash TEXT NOT NULL,
        hash TEXT NOT NULL
    )""",
    """CREATE TRIGGER audit_no_update BEFORE UPDATE ON audit BEGIN
        SELECT RAISE(ABORT, 'audit is append-only');
    END""",
    """CREATE TRIGGER audit_no_delete BEFORE DELETE ON audit BEGIN
        SELECT RAISE(ABORT, 'audit is append-only');
    END""",
    """CREATE TABLE audit_head (
        singleton INTEGER PRIMARY KEY CHECK(singleton=1),
        sequence INTEGER NOT NULL, hash TEXT NOT NULL
    )""",
    "INSERT INTO audit_head VALUES (1, 0, '')",
)


_UPGRADE_V1_TO_V2 = (
    """CREATE TABLE memory_sources (
        memory_id TEXT NOT NULL REFERENCES memories(id) ON DELETE CASCADE,
        kind TEXT NOT NULL CHECK(kind IN ('memory', 'document')),
        ref_id TEXT NOT NULL,
        ref_revision TEXT NOT NULL DEFAULT '',
        position INTEGER NOT NULL,
        PRIMARY KEY(memory_id, kind, ref_id)
    )""",
    """INSERT INTO memory_sources(memory_id, kind, ref_id, ref_revision, position)
       SELECT memory_id, 'memory', evidence_id, '', position FROM evidence""",
    "DROP INDEX evidence_parent",
    "DROP TABLE evidence",
    "CREATE INDEX memory_sources_ref ON memory_sources(kind, ref_id)",
    "ALTER TABLE memories ADD COLUMN status TEXT NOT NULL DEFAULT 'active' "
    "CHECK(status IN ('active', 'stale'))",
    "ALTER TABLE memories ADD COLUMN status_reason TEXT NOT NULL DEFAULT ''",
)


def check_schema(connection: sqlite3.Connection) -> int:
    version = connection.execute("PRAGMA user_version").fetchone()[0]
    if version not in (0, 1, SCHEMA_VERSION):
        raise RuntimeError(f"unsupported memory schema version: {version}")
    return version


def _counts(connection: sqlite3.Connection) -> dict:
    return {
        "memories": connection.execute("SELECT COUNT(*) FROM memories").fetchone()[0],
        "evidence": connection.execute("SELECT COUNT(*) FROM evidence").fetchone()[0],
    }


def backup_before_upgrade(
    connection: sqlite3.Connection, path: Path, *, expected: dict | None = None
) -> Path:
    """Copy a v1 store next to itself and verify the copy before any change is made.

    The copy must pass integrity_check and carry the same row counts as the source; otherwise
    the upgrade is refused and the source is left as it was.
    """
    expected = expected if expected is not None else _counts(connection)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    target = Path(path).with_name(f"{Path(path).stem}.v1-{stamp}.sqlite3")
    copy = sqlite3.connect(target)
    try:
        connection.backup(copy)
    finally:
        copy.close()
    os.chmod(target, 0o600)
    check = sqlite3.connect(f"file:{target}?mode=ro", uri=True)
    try:
        ok = check.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        found = _counts(check)
    finally:
        check.close()
    if not ok or found != expected:
        raise RuntimeError("backup verification failed; the upgrade was not started")
    return target


def migrate(connection: sqlite3.Connection) -> None:
    connection.execute("BEGIN IMMEDIATE")
    try:
        version = check_schema(connection)
        if version == 0:
            for statement in _SCHEMA_V1:
                connection.execute(statement)
            version = 1
        if version == 1:
            before = _counts(connection)
            for statement in _UPGRADE_V1_TO_V2:
                connection.execute(statement)
            moved = connection.execute(
                "SELECT COUNT(*) FROM memory_sources WHERE kind='memory'"
            ).fetchone()[0]
            if moved != before["evidence"]:
                raise RuntimeError("evidence migration lost links; rolled back")
            connection.execute(f"PRAGMA user_version={SCHEMA_VERSION}")
        connection.commit()
    except BaseException:
        connection.rollback()
        raise
