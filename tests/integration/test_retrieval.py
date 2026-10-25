"""Real derived Store boundaries; fixtures contain synthetic text only."""

import hashlib
import json
import sqlite3
from pathlib import Path
from uuid import UUID

import pytest
from pydantic import ValidationError

from b12.contracts import Actor


def knowledge(path):
    # A missing public module is reported as the intended assertion failure in RED.
    import importlib.util

    assert importlib.util.find_spec("b12.retrieval") is not None, "KnowledgeIndex is missing"
    from b12.retrieval import KnowledgeIndex

    return KnowledgeIndex(path)


@pytest.fixture
def actor():
    return Actor(id="B-12", owner=True, consent=True)


def source(tmp_path, text="Синтетична м’ята. Точка доступу працює."):
    path = tmp_path / "source.md"
    path.write_text(text, encoding="utf-8")
    return path


def test_exact_scope_same_source_path_and_role_change(tmp_path, actor):
    path = source(tmp_path)
    other = Actor(id="B-12-other", consent=True)
    index = knowledge(tmp_path / "index")
    try:
        index.index_document(path, actor)
        assert index.search("м'ята", other) == []
        index.index_document(path, other)
        own = index.search("м'ята", actor)[0]
        theirs = index.search("м'ята", other)[0]
        assert own["evidence_id"] != theirs["evidence_id"]
        assert index.resolve_evidence(own["evidence_id"], other) is None
        assert index.search("м'ята", actor.model_copy(update={"owner": False})) == [own]
        assert own["source"] == str(path.resolve())
        assert own["locator"] == "line 1"
        assert own["text"] == path.read_text()
        UUID(own["evidence_id"])
        assert not (tmp_path / "unrelated.md").exists()
    finally:
        index.close()


def test_consent_denial_precedes_source_read_and_no_owner_bypass(tmp_path):
    root = tmp_path / "index"
    index = knowledge(root)
    try:
        denied = Actor(id="owner", owner=True)
        with pytest.raises(PermissionError):
            index.index_document(tmp_path / "does-not-exist", denied)
        with pytest.raises(PermissionError):
            index.search("anything", denied)
        with pytest.raises(PermissionError):
            index.resolve_evidence("not-a-uuid", denied)
        assert not list(root.glob("scope-*.sqlite3"))
    finally:
        index.close()


def test_lexical_morphology_apostrophes_and_unknown_queries(tmp_path, actor):
    path = source(tmp_path)
    unrelated = tmp_path / "unrelated.md"
    unrelated.write_text("унікальний секретний слон")
    index = knowledge(tmp_path / "index")
    try:
        index.index_document(path, actor)
        for query in ("м'ята", "мʼята", "м’ята", "точку доступу"):
            assert index.search(query, actor)[0]["text"] == path.read_text()
        for query in ("", "  ", '" OR *', "нескінченнийжираф", "слон"):
            assert index.search(query, actor) == []
        assert index.search("м'ята", actor, limit=0) == []
        with pytest.raises(ValueError):
            index.search("м'ята", actor, limit=-1)
    finally:
        index.close()


def test_stable_ids_restart_idempotence_and_update_invalidation(tmp_path, actor):
    path = source(tmp_path, "Синтетична бурштинова ракета")
    root = tmp_path / "index"
    index = knowledge(root)
    index.index_document(path, actor)
    hit = index.search("ракета", actor)[0]
    before = index.resolve_evidence(hit["evidence_id"], actor)
    index.close()
    index = knowledge(root)
    try:
        receipt = index.index_document(path, actor)
        assert receipt["invalidated_evidence_ids"] == []
        assert index.resolve_evidence(hit["evidence_id"], actor) == before
        path.write_text("Синтетичний волошковий човен")
        receipt = index.index_document(path, actor)
        assert receipt["invalidated_evidence_ids"] == [hit["evidence_id"]]
        assert receipt["state"] == "complete"
        assert index.search("ракета", actor) == []
        current = index.search("човен", actor)[0]
        assert current["evidence_id"] != hit["evidence_id"]
        after = index.resolve_evidence(current["evidence_id"], actor)
        assert after.source_id == before.source_id
        assert after.revision != before.revision
        assert index.resolve_evidence(hit["evidence_id"], actor) is None
    finally:
        index.close()


def test_remove_physically_erases_managed_text_and_requires_new_control(tmp_path, actor):
    forgotten = "unique-forgotten-6e8954436c6140e5a209ac731ea0319c"
    path = source(tmp_path, forgotten)
    root = tmp_path / "index"
    index = knowledge(root)
    index.index_document(path, actor)
    hit = index.search(forgotten, actor)[0]
    result = index.remove_document(path, actor)
    assert result["state"] == "complete"
    assert result["invalidated_evidence_ids"] == [hit["evidence_id"]]
    assert index.search(forgotten, actor) == []
    assert index.resolve_evidence(hit["evidence_id"], actor) is None
    assert path.read_text() == forgotten
    for managed in root.iterdir():
        if managed.is_file():
            assert forgotten.encode() not in managed.read_bytes()
            assert str(path).encode() not in managed.read_bytes()
    index.close()
    index = knowledge(root)
    try:
        assert index.remove_document(path, actor) == result
        with pytest.raises(PermissionError):
            index.index_document(path, actor)
        index.index_document(path, actor, allow_reingest=True)
        fresh = index.search(forgotten, actor)[0]
        assert fresh["evidence_id"] != hit["evidence_id"]
        assert index.resolve_evidence(hit["evidence_id"], actor) is None
    finally:
        index.close()


def test_busy_cleanup_is_durable_pending_and_retried_after_restart(tmp_path, actor):
    path = source(tmp_path, "unique-forgotten-busy-0de6058a1a374d74")
    root = tmp_path / "index"
    index = knowledge(root)
    index.index_document(path, actor)
    hit = index.search("forgotten", actor)[0]
    (db_path,) = root.glob("scope-*.sqlite3")
    reader = sqlite3.connect(db_path)
    reader.execute("BEGIN")
    reader.execute("SELECT * FROM chunks").fetchall()
    result = index.remove_document(path, actor)
    assert result["state"] == "pending"
    assert result["error_code"] == "cleanup_busy"
    assert result["invalidated_evidence_ids"] == [hit["evidence_id"]]
    assert index.search("forgotten", actor) == []
    index.close()
    index = knowledge(root)
    repeated = index.remove_document(path, actor)
    assert repeated["operation_id"] == result["operation_id"]
    assert repeated["invalidated_evidence_ids"] == result["invalidated_evidence_ids"]
    assert repeated["state"] == "pending"
    reader.close()
    resumed = index.resume_cleanup(actor)
    assert resumed[0]["operation_id"] == result["operation_id"]
    assert resumed[0]["state"] == "complete"
    assert index.resolve_evidence(hit["evidence_id"], actor) is None
    index.close()
    for managed in root.iterdir():
        if managed.is_file():
            assert path.read_bytes() not in managed.read_bytes()


def test_actor_ids_never_become_paths_and_private_parents_unchanged(tmp_path):
    parent = tmp_path / "existing"
    parent.mkdir(mode=0o755)
    mode = parent.stat().st_mode & 0o777
    path = source(tmp_path)
    root = parent / "index"
    index = knowledge(root)
    try:
        index.index_document(path, Actor(id="../../outside/opaque", consent=True))
        assert parent.stat().st_mode & 0o777 == mode
        assert root.stat().st_mode & 0o777 == 0o700
        for child in root.iterdir():
            assert child.stat().st_mode & 0o777 == 0o600
            assert "opaque" not in child.name
        assert not (tmp_path / "outside").exists()
    finally:
        index.close()


def test_evidence_ref_is_strict_versioned_and_validated():
    from b12 import contracts

    assert hasattr(contracts, "EvidenceRef"), "EvidenceRef contract is missing"
    valid = dict(
        id="8a977314-7572-4f54-b749-4586cbb69858",
        owner_id="B-12",
        kind="document",
        source_id="f0142e53-c6b5-458d-bac2-760c5b020ad7",
        revision="7fe4040a-8e89-45dc-91ce-396c88740f55",
        locator="line 1",
        active=True,
    )
    assert contracts.EvidenceRef(**valid).schema_version == 1
    for field, value in (
        ("id", "rowid:1"),
        ("source_id", "path"),
        ("revision", ""),
        ("kind", "other"),
        ("active", 1),
        ("schema_version", True),
        ("locator", "  "),
        ("owner_id", " owner"),
        ("unknown", "x"),
    ):
        with pytest.raises(ValidationError):
            contracts.EvidenceRef(**(valid | {field: value}))


def test_vendored_source_hashes_match_reviewed_snapshot():
    root = Path(__file__).resolve().parents[2]
    upstream = root / "raw/archive-index-public-7ad80dcdc7e3"
    vendor = root / "src/b12/_vendor/archive_index"
    assert vendor.is_dir(), "Pinned vendor modules are missing"
    manifest = json.loads((vendor / "SOURCE.json").read_text())
    assert manifest["commit"] == "7ad80dcdc7e327b7dd1b352ab5e6dc38a00d784a"
    for name in ("__init__.py", "lexical.py", "store.py", "search.py", "LICENSE", "NOTICE"):
        origin = upstream / (name if name in ("LICENSE", "NOTICE") else f"src/archive_index/{name}")
        assert (vendor / name).read_bytes() == origin.read_bytes()
        assert manifest["sha256"][name] == hashlib.sha256(origin.read_bytes()).hexdigest()


def test_pending_update_retains_invalidation_receipt_across_restart(tmp_path, actor):
    path = source(tmp_path, "Синтетична помаранчева ракета")
    root = tmp_path / "index"
    index = knowledge(root)
    index.index_document(path, actor)
    old = index.search("ракета", actor)[0]
    (db_path,) = root.glob("scope-*.sqlite3")
    reader = sqlite3.connect(db_path)
    reader.execute("BEGIN")
    reader.execute("SELECT * FROM chunks").fetchall()
    path.write_text("Синтетичний фіолетовий човен")
    pending = index.index_document(path, actor)
    assert pending["state"] == "pending"
    assert pending["invalidated_evidence_ids"] == [old["evidence_id"]]
    assert index.resolve_evidence(old["evidence_id"], actor) is None
    assert index.search("човен", actor) == []
    index.close()
    reader.close()
    index = knowledge(root)
    try:
        retried = index.index_document(path, actor)
        assert retried["state"] == "complete"
        assert retried["operation_id"] == pending["operation_id"]
        assert retried["invalidated_evidence_ids"] == [old["evidence_id"]]
        assert index.search("човен", actor)
        assert index.resolve_evidence(old["evidence_id"], actor) is None
    finally:
        index.close()


def test_resume_returns_receipt_when_first_call_after_restart(tmp_path, actor):
    path = source(tmp_path)
    root = tmp_path / "index"
    index = knowledge(root)
    index.index_document(path, actor)
    (db_path,) = root.glob("scope-*.sqlite3")
    reader = sqlite3.connect(db_path)
    reader.execute("BEGIN")
    reader.execute("SELECT * FROM chunks").fetchall()
    pending = index.remove_document(path, actor)
    index.close()
    reader.close()
    index = knowledge(root)
    try:
        receipts = index.resume_cleanup(actor)
        assert len(receipts) == 1
        assert receipts[0]["operation_id"] == pending["operation_id"]
        assert receipts[0]["state"] == "complete"
    finally:
        index.close()


def test_failure_after_upstream_replace_rolls_back_entire_revision(tmp_path, actor, monkeypatch):
    from b12.retrieval_storage import ActorStore

    path = source(tmp_path, "Синтетична зелена ракета")
    root = tmp_path / "index"
    index = knowledge(root)
    index.index_document(path, actor)
    hit = index.search("ракета", actor)[0]
    original = ActorStore.replace_document

    def failing_replace(self, **kwargs):
        original(self, **kwargs)  # Exercise upstream's internal commit, then inject a crash.
        raise RuntimeError("injected storage failure")

    monkeypatch.setattr(ActorStore, "replace_document", failing_replace)
    path.write_text("Синтетичний синій човен")
    with pytest.raises(RuntimeError, match="injected"):
        index.index_document(path, actor)
    index.close()
    index = knowledge(root)
    try:
        assert index.search("ракета", actor) == [hit]
        assert index.search("човен", actor) == []
        assert index.resolve_evidence(hit["evidence_id"], actor) is not None
    finally:
        index.close()


def test_explicit_erasure_still_available_after_consent_revocation(tmp_path, actor):
    path = source(tmp_path)
    index = knowledge(tmp_path / "index")
    try:
        index.index_document(path, actor)
        hit = index.search("м'ята", actor)[0]
        revoked = actor.model_copy(update={"consent": False})
        result = index.remove_document(path, revoked)
        assert result["state"] == "complete"
        assert result["invalidated_evidence_ids"] == [hit["evidence_id"]]
        assert index.resume_cleanup(revoked) == []
        assert index.resolve_evidence(hit["evidence_id"], actor) is None
    finally:
        index.close()


def test_failed_cleanup_keeps_evidence_hidden_and_receipt_discoverable(tmp_path, actor):
    path = source(tmp_path, "Синтетична бузкова ракета")
    root = tmp_path / "index"
    index = knowledge(root)
    index.index_document(path, actor)
    hit = index.search("ракета", actor)[0]
    store = index._stores[actor.id]
    # VACUUM uses ATTACH internally; deny it to exercise a real SQLite cleanup failure.
    store.conn.set_authorizer(
        lambda action, *_: (
            sqlite3.SQLITE_DENY if action == sqlite3.SQLITE_ATTACH else sqlite3.SQLITE_OK
        )
    )
    result = index.remove_document(path, actor)
    assert result["state"] == "failed"
    assert result["error_code"] == "cleanup_failed"
    assert index.resolve_evidence(hit["evidence_id"], actor) is None
    assert index.search("ракета", actor) == []
    store.conn.set_authorizer(None)
    index.close()
    index = knowledge(root)
    try:
        assert hasattr(index, "operation_receipts"), "durable invalidations need a recovery API"
        receipts = index.operation_receipts(actor)
        receipt = next(row for row in receipts if row["operation_id"] == result["operation_id"])
        assert receipt["state"] == "complete"
        assert receipt["invalidated_evidence_ids"] == [hit["evidence_id"]]
        assert index.operation_receipts(Actor(id="other", consent=True)) == []
    finally:
        index.close()


def test_independent_index_instances_observe_updates_without_stale_cache(tmp_path, actor):
    path = source(tmp_path, "Синтетична червона ракета")
    root = tmp_path / "index"
    writer, reader = knowledge(root), knowledge(root)
    try:
        writer.index_document(path, actor)
        old = reader.search("ракета", actor)[0]
        path.write_text("Синтетичний жовтий човен")
        writer.index_document(path, actor)
        assert reader.search("ракета", actor) == []
        assert reader.search("човен", actor)
        assert reader.resolve_evidence(old["evidence_id"], actor) is None
        writer.remove_document(path, actor)
        assert reader.search("човен", actor) == []
    finally:
        writer.close()
        reader.close()
