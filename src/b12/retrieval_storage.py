"""Private actor stores, atomic upstream writes and durable physical cleanup.

The upstream Store commits inside mutators. DeferredCommit delays only that commit
inside our explicit transaction, so documents, revisions and outbox change together.
No upstream source bytes are changed.
"""

import json
import os
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from uuid import UUID, uuid4

from b12._vendor.archive_index.store import Store

SCHEMA = """
CREATE TABLE IF NOT EXISTS scope_identity(owner_id TEXT NOT NULL, secret BLOB NOT NULL);
CREATE TABLE IF NOT EXISTS sources(
    source_key BLOB PRIMARY KEY, source_id TEXT UNIQUE NOT NULL,
    revision TEXT NOT NULL, active INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS evidence(
    id TEXT PRIMARY KEY, source_id TEXT NOT NULL, revision TEXT NOT NULL,
    locator TEXT NOT NULL, chunk_id INTEGER UNIQUE, active INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS evidence_source ON evidence(source_id);
CREATE TABLE IF NOT EXISTS operations(
    sequence INTEGER PRIMARY KEY, operation_id TEXT UNIQUE NOT NULL,
    source_id TEXT NOT NULL, kind TEXT NOT NULL, invalidated TEXT NOT NULL,
    state TEXT NOT NULL, error_code TEXT
);
"""

VISIBLE = """e.active=1 AND s.active=1 AND e.revision=s.revision
AND NOT EXISTS(SELECT 1 FROM operations o WHERE o.source_id=s.source_id
               AND o.state!='complete')"""


def private_directory(path: Path) -> None:
    if path.is_symlink():
        raise ValueError("managed directory must not be a symlink")
    if path.is_dir():
        return
    private_directory(path.parent)
    try:
        path.mkdir(mode=0o700)
    except FileExistsError:
        if not path.is_dir():
            raise


def private_file(path: Path) -> None:
    if path.is_symlink():
        raise ValueError("managed database must not be a symlink")
    try:
        descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError:
        os.chmod(path, 0o600)
    else:
        os.close(descriptor)


class DeferredCommit:
    def __init__(self, connection):
        self.connection = connection

    def __getattr__(self, name):
        return getattr(self.connection, name)

    def commit(self):
        pass


@contextmanager
def atomic(store: Store) -> Iterator[None]:
    connection = store.conn
    connection.execute("BEGIN IMMEDIATE")
    store.conn = DeferredCommit(connection)
    try:
        yield
        connection.commit()
    except BaseException:
        connection.rollback()
        raise
    finally:
        store.conn = connection


class ActorStore(Store):
    """Lifecycle visibility is applied before upstream candidate limits/top-k."""

    def __init__(self, path: Path, owner_id: str):
        private_file(path)
        super().__init__(path)
        try:
            self.conn.row_factory = sqlite3.Row
            self.conn.execute("PRAGMA busy_timeout=50")
            self.conn.execute("PRAGMA secure_delete=ON")
            self.conn.execute("PRAGMA temp_store=MEMORY")
            self.conn.execute("PRAGMA synchronous=FULL")
            self.conn.executescript(SCHEMA)
            with atomic(self):
                identity = self.conn.execute("SELECT * FROM scope_identity").fetchone()
                if identity is None:
                    self.conn.execute(
                        "INSERT INTO scope_identity VALUES(?,?)", (owner_id, os.urandom(32))
                    )
                elif identity["owner_id"] != owner_id:
                    raise PermissionError("actor store ownership mismatch")
            self.secret = self.conn.execute("SELECT secret FROM scope_identity").fetchone()[0]
        except BaseException:
            self.close()
            raise

    def lexical(self, match, *, collections, project, limit, suffixes=None):
        # Private per-actor DB is the authorization boundary; prefix filters are never used.
        if not match:
            return []
        if collections is not None or project is not None or suffixes is not None:
            raise ValueError("adapter uses exact per-actor stores without prefix filters")
        sql = f"""SELECT f.rowid, bm25(chunks_fts) FROM chunks_fts f
                  JOIN evidence e ON e.chunk_id=f.rowid
                  JOIN sources s ON s.source_id=e.source_id
                  WHERE chunks_fts MATCH ? AND {VISIBLE}
                  ORDER BY bm25(chunks_fts) LIMIT ?"""
        return [(row[0], row[1]) for row in self.conn.execute(sql, (match, limit))]

    def receipt(self, operation_id: str) -> dict:
        row = self.conn.execute(
            "SELECT * FROM operations WHERE operation_id=?", (operation_id,)
        ).fetchone()
        return dict(
            operation_id=row["operation_id"],
            state=row["state"],
            invalidated_evidence_ids=json.loads(row["invalidated"]),
            error_code=row["error_code"],
        )

    def cleanup(self) -> list[dict]:
        operations = [
            row[0]
            for row in self.conn.execute(
                "SELECT operation_id FROM operations WHERE state!='complete' ORDER BY sequence"
            )
        ]
        if not operations:
            return []
        try:
            # A snapshot reader may still expose old payload. Never report completion then.
            if self.conn.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()[0]:
                raise sqlite3.OperationalError("database is locked")
            self.conn.execute("INSERT INTO chunks_fts(chunks_fts) VALUES('rebuild')")
            self.conn.commit()
            self.conn.execute("VACUUM")
            if self.conn.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()[0]:
                raise sqlite3.OperationalError("database is locked")
        except sqlite3.Error as error:
            self.conn.rollback()
            busy = (
                getattr(error, "sqlite_errorcode", None)
                in (sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED)
                or "locked" in str(error).lower()
            )
            state, code = ("pending", "cleanup_busy") if busy else ("failed", "cleanup_failed")
        else:
            state, code = "complete", None
        # Only acknowledge the operations included in this cleanup attempt.
        with atomic(self):
            self.conn.executemany(
                "UPDATE operations SET state=?, error_code=? WHERE operation_id=?",
                [(state, code, op) for op in operations],
            )
        return [self.receipt(op) for op in operations]


class ScopeRegistry:
    def __init__(self, root: Path):
        private_directory(root)
        # root is explicitly the dedicated managed directory; leave its parents alone.
        os.chmod(root, 0o700)
        self.root = root
        path = root / "scopes.sqlite3"
        private_file(path)
        self.conn = sqlite3.connect(path)
        self.conn.execute("CREATE TABLE IF NOT EXISTS scopes(actor_id TEXT PRIMARY KEY, id TEXT)")
        self.conn.commit()

    def scope(self, actor_id: str, *, create: bool) -> ActorStore | None:
        self.conn.execute("BEGIN IMMEDIATE")
        try:
            row = self.conn.execute(
                "SELECT id FROM scopes WHERE actor_id=?", (actor_id,)
            ).fetchone()
            if row is None and create:
                scope_id = str(uuid4())
                self.conn.execute("INSERT INTO scopes VALUES(?,?)", (actor_id, scope_id))
            elif row is not None:
                scope_id = str(UUID(row[0]))
            else:
                return None
            self.conn.commit()
        finally:
            if self.conn.in_transaction:
                self.conn.rollback()
        return ActorStore(self.root / f"scope-{scope_id}.sqlite3", actor_id)
