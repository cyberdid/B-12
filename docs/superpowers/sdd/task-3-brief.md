### Task 3: Derived knowledge retrieval і pinned archive reuse

**Files:** `src/b12/retrieval.py`, `_vendor/archive_index/{__init__,lexical,store,search}.py`, `_vendor/archive_index/{LICENSE,NOTICE,SOURCE.json}`, `tests/integration/test_retrieval.py`.

**Consumes:** exact Actor scope and canonical records. **Produces:** `KnowledgeIndex(path: Path)`, `index_document(path: Path, actor: Actor)`, `search(query: str, actor: Actor, limit: int = 5) -> list[dict]`, `remove_document(path: Path, actor: Actor)`; hits include stable evidence ID/source/locator/text.

- [ ] RED: same word in B-12 and B-12-other namespaces returns only exact authorized document; update/delete reflected immediately; unrelated files not scanned implicitly.
- [ ] Copy exact pinned modules/notices from reviewed raw snapshot; use zero-length vectors for lexical-only chunks. Wrap source ingestion/lookup with exact ownership guards.
- [ ] Canonical memory may use its own transactional FTS with shared lexical functions; knowledge documents use derived archive Store/search. No blanket use of production archive DB.
- [ ] GREEN: real temp SQLite integration; test Cyrillic apostrophes/morphology and missing query, not just mocked arrays.
- [ ] Commit/review source attribution and cache invalidation.

## Binding architecture constraints and task boundaries

Read spec §15.3 and plan Binding review amendments. Use separate derived archive Store files per exact actor.id, mapping to generated safe filenames, never raw actor ID paths. Role owner is not namespace. Two actors must be able to ingest the SAME absolute source path independently. Consent is checked before source read/persistence; no owner bypass.

Add strict versioned EvidenceRef DTO to contracts.py: opaque UUID id, owner_id, kind memory|document|tool_result, source_id opaque UUID, revision opaque version identity, locator, active bool. Knowledge evidence IDs and source IDs survive close/reopen and unchanged re-ingestion; update/delete invalidates old revision references. SQLite rowids are never public evidence IDs. Produce actor-bound resolve_evidence(evidence_id, actor) for knowledge; callers cannot use a hit from another actor/revision/deleted document. Shared application resolver for canonical/document/tool evidence is wired in Task7 before reflections; this task must make document verification possible and document its API, not claim full cross-store integration.

Document re-ingestion after remove requires a NEW explicit control decision; expose an explicit keyword such as allow_reingest=False on index_document for the later control adapter. Repeated ingestion of unchanged active source is idempotent. External original files are never deleted. If dependent projection invalidation crosses stores, return invalidated evidence IDs from update/remove for later coordinator hooks; do not silently claim canonical dependents are already removed.

Vendor modules are exact copies from raw/archive-index-public-7ad80dcdc7e3/src/archive_index/{__init__,lexical,store,search}.py. Preserve upstream formatting; don't lint-rewrite originals. Use local adapter and a narrowly scoped vendor lint exclusion if needed. LICENSE/NOTICE copied exactly, SOURCE.json records pinned commit, per-file hashes and provenance. No Torch/model download. No production archive DB. Tests use real temporary SQLite/FTS and actual source files.

Additional tests: same absolute path across actors; role changes preserve scope; opaque path traversal-like actor IDs cannot escape index dir; revision/ID stability after restart; stale evidence resolution after update/delete denied; explicit re-ingest requirement; unknown/empty query safe; bytes of unique forgotten text absent from managed DB/WAL after successful remove/cleanup (busy cleanup must be reported pending). Keep per-actor paths/index metadata and audit-free source data private; don't chmod unrelated existing parents. Do not scan unrelated files or use prefix filters as auth.

