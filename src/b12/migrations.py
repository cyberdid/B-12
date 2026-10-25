"""Версійована canonical SQLite schema; жодних автоматичних downgrade."""

import sqlite3

SCHEMA_VERSION = 1

_SCHEMA = (
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


def check_schema(connection: sqlite3.Connection) -> int:
    version = connection.execute("PRAGMA user_version").fetchone()[0]
    if version not in (0, SCHEMA_VERSION):
        raise RuntimeError(f"unsupported memory schema version: {version}")
    return version


def migrate(connection: sqlite3.Connection) -> None:
    connection.execute("BEGIN IMMEDIATE")
    try:
        if check_schema(connection) == 0:
            for statement in _SCHEMA:
                connection.execute(statement)
            connection.execute(f"PRAGMA user_version={SCHEMA_VERSION}")
        connection.commit()
    except BaseException:
        connection.rollback()
        raise
