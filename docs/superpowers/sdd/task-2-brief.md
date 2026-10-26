### Task 2: Canonical persistent memory та забуття

**Files:** Create `src/b12/memory.py`, `src/b12/migrations.py`, `tests/unit/test_memory.py`, `tests/integration/test_memory_restart.py`, `tests/security/test_memory_isolation.py`.

**Consumes:** Actor/MemoryRecord from Task 1. **Produces:**

```python
MemoryStore(path: Path)
MemoryStore.remember(text: str, actor: Actor, *, kind: str = 'fact',
                     source: str = 'user', evidence_ids: tuple[str, ...] = (),
                     expected_deletion_revision: int | None = None) -> MemoryRecord
MemoryStore.search(query: str, actor: Actor, *, limit: int = 8) -> list[MemoryRecord]
MemoryStore.forget(memory_id: str, actor: Actor) -> bool
MemoryStore.audit_events(actor: Actor, *, limit: int = 100) -> list[dict]
MemoryStore.close() -> None
MemoryStore.deletion_revision(actor: Actor) -> int
MemoryStore.begin_purge(memory_id: str, actor: Actor,
                        *, stores: tuple[str, ...] = ('canonical',)) -> PurgeReceipt
MemoryStore.acknowledge_purge(operation_id: str, store: str, actor: Actor,
                              *, error_code: str | None = None) -> PurgeReceipt
MemoryStore.pending_purges(actor: Actor) -> list[PurgeReceipt]
MemoryStore.resume_purges(actor: Actor) -> list[PurgeReceipt]
```

PurgeReceipt is a new strict schema_version=1 DTO in contracts.py: operation_id UUID, target_ids tuple UUID, state pending|complete|failed, pending_stores tuple nonblank strings, error_code optional nonblank string. Storage primitive forget bool describes canonical state only, never global R05. begin_purge persists payload-free operation/closure before deleting allowed payload; canonical acknowledgement occurs only after physical cleanup/checkpoint. Busy checkpoint remains pending. Other hook acknowledgements are idempotent and actor-scoped; resume_purges retries canonical cleanup without pretending to execute external hooks. Retain IDs/deletion revision after restart. expected_deletion_revision rejects a late memory write after forget; no extra payload is stored in rejection or audit.

Tests include: denied consent leaves no payload bytes; exact owner/guest isolation; cross-scope evidence rejection; restart; transitive reflection purge; unrelated memory retained; audit has no text/source/path/arguments and is tamper-evident; SQL injection-like queries safe; pending external hooks survive restart; acknowledgement completes only after every required store; held WAL reader cannot produce a false physical complete; stale expected deletion revision denied. Existing permissions of unrelated parent directories are not changed. Future/newer schema rejected before data mutation. Use SQLite temporary files and actual independent connections/threads for concurrency, not mocked SQL.

- [ ] RED: store an allowed memory, close/reopen, retrieve exact text/source/ID; no-consent raises PermissionError before any payload persistence.
- [ ] RED: owner/guest namespaces exact; evidence from another actor rejected; forgetting cascades dependent reflections while leaving unrelated memory.
- [ ] Implement transactional payload/evidence/FTS tables, append-only payload-free audit metadata, schema version, parameterized queries, safe FTS terms, WAL/secure_delete, hash chain and restrictive state permissions.
- [ ] Implement forget transaction plus FTS/evidence cleanup and WAL checkpoint; memory lookup never uses forgotten payload. Corrupt audit chain returns explicit failure, not silently repaired history.
- [ ] GREEN: `uv run pytest tests/unit/test_memory.py tests/integration/test_memory_restart.py tests/security/test_memory_isolation.py -q`.
- [ ] Commit and review real SQL effects, durable bytes after forget and restart; no code-only assertions.

```python
def test_restart_retains_allowed_memory(tmp_path):
    actor = Actor(id='owner', owner=True, consent=True)
    path = tmp_path / 'memory.sqlite3'
    store = MemoryStore(path)
    saved = store.remember('Учора тестували мікрофон і знайшли ехо', actor, source='event-test-17')
    store.close()
    reopened = MemoryStore(path)
    hits = reopened.search('мікрофон', actor)
    assert [(m.id, m.source) for m in hits] == [(saved.id, 'event-test-17')]
```

