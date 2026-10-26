"""Canonical local memory. Actor надходить з довіреного контрольного шляху.

Забуття тут охоплює canonical SQLite та оголошені hooks. Sessions, backups,
runtime tasks і зовнішні індекси має координувати майбутній application layer.
"""

import functools
import hashlib
import json
import os
import re
import sqlite3
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

from b12.contracts import Actor, MemoryRecord, PurgeReceipt, _identifier
from b12.migrations import check_schema, migrate


@functools.lru_cache(maxsize=50_000)
def _forms(term: str) -> tuple[str, ...]:
    """The term plus inflections of its dictionary lemmas (uk; ru only without uk letters)."""
    forms = {term}
    if any("\u0400" <= ch <= "\u04ff" for ch in term):
        from b12._vendor.archive_index.lexical import _analyzer

        languages = ["uk"] if any(ch in "іїєґ" for ch in term) else ["uk", "ru"]
        for language in languages:
            try:
                parses = [p for p in _analyzer(language).parse(term) if p.is_known]
            except Exception:  # missing dictionary: keep the literal term
                continue
            for parse in parses[:3]:
                forms.update(f.word for f in parse.lexeme)
            if parses:
                break
    return tuple(sorted(forms, key=lambda f: (f != term, f)))[:48]


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _encoded(value: object) -> str:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"))


def _digest(event: dict) -> str:
    return hashlib.sha256(_encoded(event).encode()).hexdigest()


def _private_directory(path: Path) -> None:
    if path.is_dir():
        return
    _private_directory(path.parent)
    try:
        path.mkdir(mode=0o700)
    except FileExistsError:
        if not path.is_dir():
            raise


class MemoryStore:
    """Thread-safe connection; independent stores serialize mutations in SQLite.

    actor.id — exact namespace. owner є capability, а не інша identity.
    expected_deletion_revision слід передавати з асинхронних derived writers.
    """

    def __init__(self, path: Path):
        self.path = Path(path)
        self._lock = threading.RLock()
        _private_directory(self.path.parent)
        if self.path.is_symlink():
            raise ValueError("memory database must not be a symlink")
        self._connection = sqlite3.connect(
            self.path, isolation_level=None, check_same_thread=False, timeout=5
        )
        self._connection.row_factory = sqlite3.Row
        try:
            # Reject future schema before journal, schema, permissions or payload mutation.
            check_schema(self._connection)
            os.chmod(self.path, 0o600)
            self._connection.execute("PRAGMA foreign_keys=ON")
            self._connection.execute("PRAGMA secure_delete=ON")
            self._connection.execute("PRAGMA temp_store=MEMORY")
            self._connection.execute("PRAGMA journal_mode=WAL")
            self._connection.execute("PRAGMA synchronous=FULL")
            migrate(self._connection)
            with self._transaction():
                pass
        except BaseException:
            self._connection.close()
            raise

    @contextmanager
    def _transaction(self, *, write: bool = False) -> Iterator[None]:
        with self._lock:
            self._connection.execute("BEGIN IMMEDIATE" if write else "BEGIN")
            try:
                self._verify_audit()
                yield
                self._connection.commit()
            except BaseException:
                self._connection.rollback()
                raise

    def _verify_audit(self, *, full: bool = False) -> None:
        """Chain check. Full on open/verify_full; otherwise incremental from a cursor.

        Incremental mode re-hashes the cursor row and every newer row. Any commit by
        another connection (process or tamperer) forces a full check, so edits of old
        rows are still caught; our own commits keep cost independent of history.
        """
        # data_version changes only when ANOTHER connection commits (another process or
        # tampering): then re-verify everything; our own commits keep the cheap path.
        version = self._connection.execute("PRAGMA data_version").fetchone()[0]
        if version != getattr(self, "_data_version", None):
            full = True
        self._data_version = version
        cursor = None if full else getattr(self, "_audit_cursor", None)
        sequence, previous_hash = (0, "") if cursor is None else cursor
        start = 0 if cursor is None else sequence - 1
        if cursor is not None and sequence:
            rows = self._connection.execute(
                "SELECT * FROM audit WHERE sequence>=? ORDER BY sequence", (sequence,)
            ).fetchall()
            event = dict(rows[0]) if rows else None
            if event is None or event["sequence"] != sequence:
                raise RuntimeError("memory audit chain is corrupt")
            actual = event.pop("hash")
            if actual != previous_hash or actual != _digest(event):
                raise RuntimeError("memory audit chain is corrupt")
            rows = rows[1:]
        else:
            rows = self._connection.execute(
                "SELECT * FROM audit WHERE sequence>? ORDER BY sequence", (start,)
            ).fetchall()
        for row in rows:
            event = dict(row)
            actual_hash = event.pop("hash")
            if (
                event["sequence"] != sequence + 1
                or event["previous_hash"] != previous_hash
                or actual_hash != _digest(event)
            ):
                raise RuntimeError("memory audit chain is corrupt")
            sequence = event["sequence"]
            previous_hash = actual_hash
        head = self._connection.execute("SELECT sequence, hash FROM audit_head").fetchall()
        if len(head) != 1 or tuple(head[0]) != (sequence, previous_hash):
            raise RuntimeError("memory audit head is corrupt")
        self._audit_cursor = (sequence, previous_hash)

    def verify_full(self) -> int:
        """Re-verify the whole audit chain; returns the number of events."""
        with self._lock:
            self._connection.execute("BEGIN")
            try:
                self._verify_audit(full=True)
            finally:
                self._connection.rollback()
            return self._audit_cursor[0]

    def _audit(
        self,
        actor: Actor,
        action: str,
        *,
        memory_id: str | None = None,
        operation_id: str | None = None,
    ) -> None:
        sequence, previous_hash = self._connection.execute(
            "SELECT sequence, hash FROM audit_head WHERE singleton=1"
        ).fetchone()
        event = dict(
            sequence=sequence + 1,
            actor_id=actor.id,
            action=action,
            memory_id=memory_id,
            operation_id=operation_id,
            created_at=_now(),
            previous_hash=previous_hash,
        )
        event_hash = _digest(event)
        self._connection.execute(
            """INSERT INTO audit(sequence, actor_id, action, memory_id, operation_id,
               created_at, previous_hash, hash) VALUES (?,?,?,?,?,?,?,?)""",
            (*event.values(), event_hash),
        )
        self._connection.execute(
            "UPDATE audit_head SET sequence=?, hash=? WHERE singleton=1", (sequence + 1, event_hash)
        )

    @staticmethod
    def _consent(actor: Actor) -> None:
        if not isinstance(actor, Actor):
            raise TypeError("actor must be a trusted Actor")
        if not actor.consent:
            raise PermissionError("memory consent is required")

    @staticmethod
    def _limit(limit: int) -> None:
        if type(limit) is not int or not 0 <= limit <= 1000:
            raise ValueError("limit must be an integer between 0 and 1000")

    def _revision(self, actor: Actor) -> int:
        row = self._connection.execute(
            "SELECT revision FROM revisions WHERE actor_id=?", (actor.id,)
        ).fetchone()
        return row[0] if row else 0

    def deletion_revision(self, actor: Actor) -> int:
        with self._transaction():
            return self._revision(actor)

    def is_live(self, memory_id: str, actor: Actor) -> bool:
        """Payload-free liveness for trusted resolvers; tombstoned IDs are never live."""
        try:
            UUID(memory_id)
        except (ValueError, TypeError, AttributeError):
            return False
        with self._transaction():
            return bool(
                self._connection.execute(
                    """SELECT 1 FROM memories m WHERE id=? AND actor_id=?
                       AND NOT EXISTS (SELECT 1 FROM tombstones WHERE memory_id=m.id)""",
                    (memory_id, actor.id),
                ).fetchone()
            )

    def remember(
        self,
        text: str,
        actor: Actor,
        *,
        kind: str = "fact",
        source: str = "user",
        evidence_ids: tuple[str, ...] = (),
        expected_deletion_revision: int | None = None,
    ) -> MemoryRecord:
        self._consent(actor)
        if expected_deletion_revision is not None and (
            type(expected_deletion_revision) is not int or expected_deletion_revision < 0
        ):
            raise ValueError("expected deletion revision must be a nonnegative integer")
        record = MemoryRecord(
            id=str(uuid4()),
            owner_id=actor.id,
            kind=kind,
            text=text,
            source=source,
            created_at=_now(),
            evidence_ids=evidence_ids,
        )
        if len(set(evidence_ids)) != len(evidence_ids):
            raise ValueError("duplicate evidence IDs")
        with self._transaction(write=True):
            if (
                expected_deletion_revision is not None
                and expected_deletion_revision != self._revision(actor)
            ):
                raise PermissionError("stale deletion revision")
            for evidence_id in evidence_ids:
                if not self._connection.execute(
                    """SELECT 1 FROM memories m WHERE id=? AND actor_id=?
                       AND NOT EXISTS (SELECT 1 FROM tombstones WHERE memory_id=m.id)""",
                    (evidence_id, actor.id),
                ).fetchone():
                    raise ValueError("evidence must be live memory in the exact actor namespace")
            self._connection.execute(
                """INSERT INTO memories(id, actor_id, kind, text, source, created_at)
                   VALUES (?,?,?,?,?,?)""",
                (record.id, actor.id, record.kind, record.text, record.source, record.created_at),
            )
            self._connection.executemany(
                "INSERT INTO evidence VALUES (?,?,?)",
                ((record.id, item, i) for i, item in enumerate(evidence_ids)),
            )
            self._audit(actor, "remember", memory_id=record.id)
        return record

    def get(self, memory_id: str, actor: Actor) -> MemoryRecord | None:
        self._consent(actor)
        with self._transaction():
            row = self._connection.execute(
                """SELECT m.* FROM memories m WHERE id=? AND actor_id=?
                   AND NOT EXISTS (SELECT 1 FROM tombstones WHERE memory_id=m.id)""",
                (memory_id, actor.id),
            ).fetchone()
            return self._record(row) if row else None

    def recent(self, actor: Actor, *, limit: int = 20, exclude_kinds=()) -> list[MemoryRecord]:
        """Newest live records in the exact actor namespace (consent required)."""
        self._consent(actor)
        self._limit(limit)
        with self._transaction():
            rows = self._connection.execute(
                """SELECT m.* FROM memories m WHERE actor_id=?
                   AND NOT EXISTS (SELECT 1 FROM tombstones WHERE memory_id=m.id)
                   ORDER BY m.rowid DESC""",
                (actor.id,),
            )
            records = [self._record(row) for row in rows if row["kind"] not in exclude_kinds]
            return records[:limit]

    def _record(self, row: sqlite3.Row) -> MemoryRecord:
        evidence = tuple(
            item[0]
            for item in self._connection.execute(
                "SELECT evidence_id FROM evidence WHERE memory_id=? ORDER BY position", (row["id"],)
            )
        )
        return MemoryRecord(
            id=row["id"],
            owner_id=row["actor_id"],
            kind=row["kind"],
            text=row["text"],
            source=row["source"],
            created_at=row["created_at"],
            evidence_ids=evidence,
        )

    def search(self, query: str, actor: Actor, *, limit: int = 8) -> list[MemoryRecord]:
        self._consent(actor)
        self._limit(limit)
        if not isinstance(query, str):
            raise TypeError("query must be text")
        # Only literal Unicode alphanumeric tokens; no FTS operators or SQL syntax.
        terms = re.findall(r"[^\W_]+", query, flags=re.UNICODE)[:64]
        # Each term matches any inflection of its lemma (шафку ~ шафки); every form is a
        # quoted literal, so the query can never inject FTS operators.
        expression = " AND ".join(
            "(" + " OR ".join('"' + form + '"' for form in _forms(term.lower())) + ")"
            for term in terms
        )
        with self._transaction():
            if not terms or not limit:
                return []
            rows = self._connection.execute(
                """SELECT m.* FROM memory_fts JOIN memories m ON m.rowid=memory_fts.rowid
                   WHERE memory_fts MATCH ? AND m.actor_id=?
                   AND NOT EXISTS (SELECT 1 FROM tombstones WHERE memory_id=m.id)
                   ORDER BY bm25(memory_fts), m.rowid DESC LIMIT ?""",
                (expression, actor.id, limit),
            ).fetchall()
            return [self._record(row) for row in rows]

    def audit_events(self, actor: Actor, *, limit: int = 100) -> list[dict]:
        self._limit(limit)
        with self._transaction():
            return [
                dict(row)
                for row in self._connection.execute(
                    "SELECT * FROM audit WHERE actor_id=? ORDER BY sequence DESC LIMIT ?",
                    (actor.id, limit),
                )
            ]

    def _receipt(self, operation_id: str, actor: Actor) -> PurgeReceipt:
        operation = self._connection.execute(
            "SELECT target_ids FROM purge_operations WHERE operation_id=? AND actor_id=?",
            (operation_id, actor.id),
        ).fetchone()
        if operation is None:
            raise PermissionError("purge operation is unavailable in actor namespace")
        stores = self._connection.execute(
            """SELECT store, state, error_code FROM purge_stores
               WHERE operation_id=? ORDER BY position""",
            (operation_id,),
        ).fetchall()
        pending = tuple(row["store"] for row in stores if row["state"] != "complete")
        errors = [row["error_code"] for row in stores if row["state"] == "failed"]
        return PurgeReceipt(
            operation_id=operation_id,
            target_ids=tuple(json.loads(operation[0])),
            state="failed" if errors else "pending" if pending else "complete",
            pending_stores=pending,
            error_code=errors[0] if errors else None,
        )

    def begin_purge(
        self,
        memory_id: str,
        actor: Actor,
        *,
        stores: tuple[str, ...] = ("canonical",),
    ) -> PurgeReceipt:
        receipt, _ = self._begin_purge(memory_id, actor, stores=stores)
        return receipt

    def _begin_purge(
        self,
        memory_id: str,
        actor: Actor,
        *,
        stores: tuple[str, ...] = ("canonical",),
    ) -> tuple[PurgeReceipt, bool]:
        UUID(memory_id)
        if not isinstance(stores, tuple) or any(not isinstance(item, str) for item in stores):
            raise ValueError("stores must be a tuple of identifiers")
        for store in stores:
            _identifier(store)
        required = tuple(dict.fromkeys(("canonical", *stores)))
        with self._transaction(write=True):
            tombstone = self._connection.execute(
                "SELECT operation_id FROM tombstones WHERE memory_id=? AND actor_id=?",
                (memory_id, actor.id),
            ).fetchone()
            if tombstone:
                # Do not silently add new obligations to an existing operation.
                existing = tuple(
                    row[0]
                    for row in self._connection.execute(
                        "SELECT store FROM purge_stores WHERE operation_id=?", (tombstone[0],)
                    )
                )
                if not set(required) <= set(existing):
                    raise ValueError("purge already exists with different required stores")
                return self._receipt(tombstone[0], actor), False
            if not self._connection.execute(
                "SELECT 1 FROM memories WHERE id=? AND actor_id=?", (memory_id, actor.id)
            ).fetchone():
                raise KeyError("memory is unavailable in actor namespace")
            targets = tuple(
                row[0]
                for row in self._connection.execute(
                    """WITH RECURSIVE closure(id) AS (
                       SELECT id FROM memories WHERE id=? AND actor_id=?
                       UNION
                       SELECT e.memory_id FROM evidence e JOIN closure c ON e.evidence_id=c.id
                       JOIN memories m ON m.id=e.memory_id WHERE m.actor_id=?
                   ) SELECT id FROM closure ORDER BY id""",
                    (memory_id, actor.id, actor.id),
                )
            )
            operation_id = str(uuid4())
            self._connection.execute(
                "INSERT INTO purge_operations(operation_id, actor_id, target_ids) VALUES (?,?,?)",
                (operation_id, actor.id, _encoded(targets)),
            )
            self._connection.executemany(
                "INSERT INTO purge_stores VALUES (?,?,?,'pending',NULL)",
                ((operation_id, store, i) for i, store in enumerate(required)),
            )
            self._connection.executemany(
                "INSERT OR IGNORE INTO tombstones VALUES (?,?,?)",
                ((target, actor.id, operation_id) for target in targets),
            )
            self._connection.execute(
                """INSERT INTO revisions VALUES (?,1) ON CONFLICT(actor_id)
                   DO UPDATE SET revision=revision+1""",
                (actor.id,),
            )
            self._audit(actor, "purge_requested", memory_id=memory_id, operation_id=operation_id)
        # Outbox + closure + tombstones + revision are durable before deleting payload.
        return self._cleanup_canonical(operation_id, actor), True

    def _cleanup_canonical(self, operation_id: str, actor: Actor) -> PurgeReceipt:
        try:
            return self._attempt_cleanup_canonical(operation_id, actor)
        except sqlite3.Error:
            # Never persist SQL exception text: it may contain payload or filesystem paths.
            with self._transaction(write=True):
                self._receipt(operation_id, actor)
                self._connection.execute(
                    """UPDATE purge_stores SET state='failed', error_code='canonical_cleanup_failed'
                       WHERE operation_id=? AND store='canonical' AND state!='complete'""",
                    (operation_id,),
                )
                self._audit(actor, "canonical_cleanup_failed", operation_id=operation_id)
                return self._receipt(operation_id, actor)

    def _attempt_cleanup_canonical(self, operation_id: str, actor: Actor) -> PurgeReceipt:
        with self._lock:
            with self._transaction(write=True):
                receipt = self._receipt(operation_id, actor)
                if "canonical" not in receipt.pending_stores:
                    return receipt
                operation = self._connection.execute(
                    "SELECT payload_deleted FROM purge_operations WHERE operation_id=?",
                    (operation_id,),
                ).fetchone()
                if not operation[0]:
                    # JSON closure avoids SQL placeholder limits for large transitive purges.
                    self._connection.execute(
                        """DELETE FROM evidence WHERE memory_id IN
                           (SELECT value FROM json_each(?)) OR evidence_id IN
                           (SELECT value FROM json_each(?))""",
                        (_encoded(receipt.target_ids), _encoded(receipt.target_ids)),
                    )
                    self._connection.execute(
                        """DELETE FROM memories WHERE actor_id=?
                           AND id IN (SELECT value FROM json_each(?))""",
                        (actor.id, _encoded(receipt.target_ids)),
                    )
                    # Rebuild removes obsolete FTS segments, not only query-visible rows.
                    self._connection.execute(
                        "INSERT INTO memory_fts(memory_fts) VALUES ('rebuild')"
                    )
                    self._connection.execute(
                        "UPDATE purge_operations SET payload_deleted=1 WHERE operation_id=?",
                        (operation_id,),
                    )
                    self._audit(actor, "canonical_deleted", operation_id=operation_id)
            self._connection.execute("PRAGMA busy_timeout=0")
            try:
                busy, _, _ = self._connection.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()
            finally:
                self._connection.execute("PRAGMA busy_timeout=5000")
            with self._transaction(write=True):
                if not busy:
                    self._connection.execute(
                        """UPDATE purge_stores SET state='complete', error_code=NULL
                           WHERE operation_id=? AND store='canonical' AND state!='complete'""",
                        (operation_id,),
                    )
                    self._audit(actor, "canonical_checkpointed", operation_id=operation_id)
                return self._receipt(operation_id, actor)

    def forget(self, memory_id: str, actor: Actor) -> bool:
        """True означає локальне canonical забуття; це не global R05 receipt."""
        try:
            _, created = self._begin_purge(memory_id, actor)
        except KeyError:
            return False
        return created

    def acknowledge_purge(
        self,
        operation_id: str,
        store: str,
        actor: Actor,
        *,
        error_code: str | None = None,
    ) -> PurgeReceipt:
        UUID(operation_id)
        _identifier(store)
        if error_code is not None:
            _identifier(error_code)
        with self._transaction(write=True):
            self._receipt(operation_id, actor)
            state = self._connection.execute(
                "SELECT state FROM purge_stores WHERE operation_id=? AND store=?",
                (operation_id, store),
            ).fetchone()
            if state is None:
                raise ValueError("store was not requested for purge operation")
            if state[0] == "complete":
                return self._receipt(operation_id, actor)
            if store != "canonical" or error_code is not None:
                self._connection.execute(
                    """UPDATE purge_stores SET state=?, error_code=?
                       WHERE operation_id=? AND store=?""",
                    ("failed" if error_code else "complete", error_code, operation_id, store),
                )
                self._audit(
                    actor,
                    "purge_hook_failed" if error_code else "purge_hook_acknowledged",
                    operation_id=operation_id,
                )
                return self._receipt(operation_id, actor)
        # External acknowledgements cannot bypass a blocked canonical checkpoint.
        return self._cleanup_canonical(operation_id, actor)

    def purge_receipt(self, operation_id: str, actor: Actor) -> PurgeReceipt:
        UUID(operation_id)
        with self._transaction():
            return self._receipt(operation_id, actor)

    def pending_purges(self, actor: Actor) -> list[PurgeReceipt]:
        with self._transaction():
            operations = self._connection.execute(
                """SELECT operation_id FROM purge_operations p WHERE actor_id=? AND EXISTS
                   (SELECT 1 FROM purge_stores s WHERE s.operation_id=p.operation_id
                    AND s.state!='complete') ORDER BY p.rowid""",
                (actor.id,),
            ).fetchall()
            return [self._receipt(row[0], actor) for row in operations]

    def resume_purges(self, actor: Actor) -> list[PurgeReceipt]:
        return [
            self._cleanup_canonical(receipt.operation_id, actor)
            for receipt in self.pending_purges(actor)
        ]

    def close(self) -> None:
        with self._lock:
            self._connection.close()
