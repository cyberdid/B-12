"""Lexical knowledge retrieval over exact, private actor scopes.

path is a dedicated managed directory, never an existing archive database. Actor
comes from trusted control. This local adapter does not implement cross-store purge
or control-revision checks (the application coordinator supplies those).
"""

import hashlib
import hmac
import json
from pathlib import Path
from uuid import UUID, uuid4

import numpy as np

from b12._vendor.archive_index.lexical import index_terms
from b12._vendor.archive_index.search import VectorCache, hybrid
from b12._vendor.archive_index.store import ChunkRecord
from b12.contracts import Actor, EvidenceRef
from b12.retrieval_storage import VISIBLE, ActorStore, ScopeRegistry, atomic


class KnowledgeIndex:
    """Same-thread SQLite connections; independent instances serialize mutations.

    Mutation receipts list invalidated_evidence_ids for later application hooks.
    Complete means local DB/FTS/WAL cleanup only. External originals are untouched.
    """

    def __init__(self, path: Path):
        self._registry = ScopeRegistry(Path(path))
        self._stores: dict[str, ActorStore] = {}
        self._closed = False

    def close(self) -> None:
        if not self._closed:
            for store in self._stores.values():
                store.close()
            self._registry.conn.close()
            self._closed = True

    @staticmethod
    def _consent(actor: Actor) -> None:
        if not actor.consent:
            raise PermissionError("knowledge access requires consent")

    def _store(
        self, actor: Actor, *, create: bool = False, resume: bool = True
    ) -> ActorStore | None:
        if self._closed:
            raise RuntimeError("knowledge index is closed")
        store = self._stores.get(actor.id)
        if store is None:
            store = self._registry.scope(actor.id, create=create)
            if store is not None:
                self._stores[actor.id] = store
                # Resume durable cleanup on first open, before affected data can be served.
                if resume:
                    store.cleanup()
        return store

    @staticmethod
    def _source_key(store: ActorStore, path: str) -> bytes:
        # Opaque keyed tombstone allows deny-by-path without retaining forgotten paths.
        # This is private control metadata, never a payload hash or audit substitute.
        return hmac.digest(store.secret, path.encode(), "sha256")

    @staticmethod
    def _invalidate(store: ActorStore, source_id: str) -> list[str]:
        ids = [
            row[0]
            for row in store.conn.execute(
                "SELECT id FROM evidence WHERE source_id=? AND active=1 ORDER BY rowid",
                (source_id,),
            )
        ]
        store.conn.execute(
            "UPDATE evidence SET active=0, chunk_id=NULL, locator='' WHERE source_id=?",
            (source_id,),
        )
        return ids

    @staticmethod
    def _operation(store: ActorStore, source_id: str, kind: str, invalidated: list[str]) -> str:
        operation_id = str(uuid4())
        store.conn.execute(
            """INSERT INTO operations(operation_id,source_id,kind,invalidated,state)
               VALUES(?,?,?,?,'pending')""",
            (operation_id, source_id, kind, json.dumps(invalidated)),
        )
        return operation_id

    def index_document(self, path: Path, actor: Actor, *, allow_reingest: bool = False) -> dict:
        self._consent(actor)  # before resolving/stat/reading the requested source
        if type(allow_reingest) is not bool:
            raise TypeError("allow_reingest must be a control boolean")
        absolute = str(Path(path).resolve())
        store = self._store(actor, create=True)
        key = self._source_key(store, absolute)
        with atomic(store):
            existing = store.conn.execute(
                "SELECT * FROM sources WHERE source_key=?", (key,)
            ).fetchone()
            if existing is not None and not existing["active"] and not allow_reingest:
                raise PermissionError(
                    "forgotten source requires a new explicit re-ingestion decision"
                )
            # Read only this explicit file, while serializing concurrent document mutations.
            data = Path(absolute).read_bytes()
            text = data.decode("utf-8")
            digest = hashlib.sha256(data).hexdigest()
            state = store.document_state(absolute)
            if existing is not None and existing["active"] and state and state.sha256 == digest:
                row = store.conn.execute(
                    "SELECT operation_id FROM operations WHERE source_id=? ORDER BY sequence DESC",
                    (existing["source_id"],),
                ).fetchone()
                operation_id = row[0]
            else:
                source_id = existing["source_id"] if existing is not None else str(uuid4())
                revision = str(uuid4())
                invalidated = self._invalidate(store, source_id)
                store.conn.execute(
                    "INSERT OR REPLACE INTO sources VALUES(?,?,?,1)", (key, source_id, revision)
                )
                stat = Path(absolute).stat()
                chunks = (
                    [
                        ChunkRecord(
                            ord=0,
                            heading="",
                            locator="line 1",
                            body=text,
                            terms=index_terms(text),
                            occurred_at="",
                            vector=np.zeros(0, dtype=np.float32),
                            body_sha=digest,
                        )
                    ]
                    if text.strip()
                    else []
                )
                doc_id = store.replace_document(
                    collection="knowledge",
                    path=absolute,
                    size=len(data),
                    mtime_ns=stat.st_mtime_ns,
                    sha256=digest,
                    title=Path(absolute).name,
                    project="",
                    chunks=chunks,
                )
                for row in store.conn.execute(
                    "SELECT id,locator FROM chunks WHERE doc_id=?", (doc_id,)
                ):
                    store.conn.execute(
                        "INSERT INTO evidence VALUES(?,?,?,?,?,1)",
                        (str(uuid4()), source_id, revision, row["locator"], row["id"]),
                    )
                operation_id = self._operation(store, source_id, "index", invalidated)
        store.cleanup()
        # Idempotent retries return the original operation, including invalidation IDs.
        # Coordinators deduplicate by operation_id; a restart must not erase hook work.
        return store.receipt(operation_id)

    def search(self, query: str, actor: Actor, limit: int = 5) -> list[dict]:
        self._consent(actor)
        if type(limit) is not int or limit < 0:
            raise ValueError("limit must be a nonnegative integer")
        if not query.strip() or not limit:
            return []
        store = self._store(actor)
        if store is None:
            return []
        # Fresh per-query cache: no stale vectors across writes or independent instances.
        # lexical mode never invokes an embedder or loads vectors/models.
        store.conn.execute("BEGIN")
        try:
            hits = hybrid(
                store,
                VectorCache(store),
                query,
                None,
                mode="lexical",
                k=limit,
                pool=max(100, limit),
                per_document=0,
            )
            result = []
            for hit in hits:
                row = store.conn.execute(
                    f"""SELECT e.*,c.body FROM evidence e JOIN sources s USING(source_id)
                        JOIN chunks c ON c.id=e.chunk_id WHERE e.chunk_id=? AND {VISIBLE}""",
                    (hit.chunk_id,),
                ).fetchone()
                if row is not None:
                    result.append(
                        dict(
                            evidence_id=row["id"],
                            source_id=row["source_id"],
                            revision=row["revision"],
                            source=hit.path,
                            locator=row["locator"],
                            text=row["body"],
                            score=hit.score,
                        )
                    )
            return result
        finally:
            store.conn.rollback()

    def resolve_evidence(self, evidence_id: str, actor: Actor) -> EvidenceRef | None:
        self._consent(actor)
        try:
            UUID(evidence_id)
        except (ValueError, TypeError, AttributeError):
            return None
        store = self._store(actor)
        if store is None:
            return None
        row = store.conn.execute(
            f"""SELECT e.* FROM evidence e JOIN sources s USING(source_id)
                JOIN chunks c ON c.id=e.chunk_id WHERE e.id=? AND {VISIBLE}""",
            (evidence_id,),
        ).fetchone()
        if row is None:
            return None
        return EvidenceRef(
            id=row["id"],
            owner_id=actor.id,
            kind="document",
            source_id=row["source_id"],
            revision=row["revision"],
            locator=row["locator"],
            active=True,
        )

    def remove_document(self, path: Path, actor: Actor) -> dict:
        # Revocation blocks new reads/ingestion, not explicit deletion of own existing data.
        absolute = str(Path(path).resolve())
        store = self._store(actor, create=True)
        key = self._source_key(store, absolute)
        with atomic(store):
            existing = store.conn.execute(
                "SELECT * FROM sources WHERE source_key=?", (key,)
            ).fetchone()
            if existing is not None and not existing["active"]:
                operation_id = store.conn.execute(
                    """SELECT operation_id FROM operations WHERE source_id=? AND kind='remove'
                       ORDER BY sequence DESC""",
                    (existing["source_id"],),
                ).fetchone()[0]
            else:
                source_id = existing["source_id"] if existing is not None else str(uuid4())
                invalidated = self._invalidate(store, source_id)
                state = store.document_state(absolute)
                if state:
                    store._delete_chunks(state.doc_id)
                    store.conn.execute("DELETE FROM documents WHERE id=?", (state.doc_id,))
                store.conn.execute(
                    "INSERT OR REPLACE INTO sources VALUES(?,?,?,0)", (key, source_id, str(uuid4()))
                )
                operation_id = self._operation(store, source_id, "remove", invalidated)
        store.cleanup()
        return store.receipt(operation_id)

    def operation_receipts(self, actor: Actor) -> list[dict]:
        """Recover payload-free invalidation work after crashes; exact actor scope.

        Local completion never acknowledges dependent projections in other stores.
        The later coordinator deduplicates delivery using operation_id.
        """
        store = self._store(actor)
        if store is None:
            return []
        return [
            store.receipt(row[0])
            for row in store.conn.execute("SELECT operation_id FROM operations ORDER BY sequence")
        ]

    def resume_cleanup(self, actor: Actor) -> list[dict]:
        """Retry local physical cleanup, including after consent revocation."""
        store = self._store(actor, resume=False)
        return store.cleanup() if store else []
