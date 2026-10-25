import json
import sqlite3
from uuid import uuid4

import pytest
from pydantic import ValidationError

from b12.contracts import Actor


def test_remember_validates_before_any_payload_write(tmp_path):
    from b12.memory import MemoryStore

    store = MemoryStore(tmp_path / "memory.sqlite3")
    actor = Actor(id="owner", owner=True, consent=True)
    for kwargs in (
        {"text": " "},
        {"text": "sentinel", "source": " "},
        {"text": "sentinel", "kind": " "},
        {"text": "sentinel", "evidence_ids": ("not-uuid",)},
    ):
        with pytest.raises((ValueError, ValidationError)):
            store.remember(actor=actor, **kwargs)
    assert store.search("sentinel", actor) == []
    assert store.audit_events(actor) == []
    store.close()


def test_search_returns_only_safe_lexical_matches_and_honors_limit(tmp_path):
    from b12.memory import MemoryStore

    store = MemoryStore(tmp_path / "memory.sqlite3")
    actor = Actor(id="owner", consent=True)
    saved = [store.remember(f"мікрофон тест {i}", actor) for i in range(3)]
    assert len(store.search("мікрофон", actor, limit=2)) == 2
    assert {m.id for m in store.search("мікрофон", actor)} == {m.id for m in saved}
    assert store.search('"; DROP TABLE memories; --', actor) == []
    assert store.search('***()"', actor) == []
    assert len(store.search("мікрофон", actor)) == 3
    with pytest.raises(ValueError):
        store.search("мікрофон", actor, limit=-1)
    store.close()


def test_forget_cascades_transitively_and_retains_unrelated_payload(tmp_path):
    from b12.memory import MemoryStore

    path = tmp_path / "memory.sqlite3"
    store = MemoryStore(path)
    actor = Actor(id="owner", consent=True)
    root = store.remember("purge_root_private_marker", actor, source="private_source_marker")
    child = store.remember(
        "purge_child_private_marker", actor, kind="reflection", evidence_ids=(root.id,)
    )
    leaf = store.remember(
        "purge_leaf_private_marker", actor, kind="reflection", evidence_ids=(child.id,)
    )
    keep = store.remember("retained unrelated microphone", actor)
    assert store.forget(root.id, actor) is True
    assert store.forget(root.id, actor) is False
    assert store.search("private", actor) == []
    assert [m.id for m in store.search("microphone", actor)] == [keep.id]
    with sqlite3.connect(path) as connection:
        assert connection.execute("SELECT count(*) FROM evidence").fetchone()[0] == 0
        assert connection.execute("SELECT count(*) FROM memories").fetchone()[0] == 1
    for file in tmp_path.iterdir():
        data = file.read_bytes()
        for marker in (root.text, child.text, leaf.text, root.source):
            assert marker.encode() not in data
    store.close()


def test_audit_is_payload_free_append_only_and_detects_corruption(tmp_path):
    from b12.memory import MemoryStore

    path = tmp_path / "memory.sqlite3"
    actor = Actor(id="owner", consent=True)
    store = MemoryStore(path)
    saved = store.remember("text-secret-marker", actor, source="/secret/path-marker")
    store.forget(saved.id, actor)
    events = store.audit_events(actor)
    assert events
    serialized = json.dumps(events)
    assert "text-secret-marker" not in serialized
    assert "/secret/path-marker" not in serialized
    assert all(not ({"text", "source", "path", "arguments"} & event.keys()) for event in events)
    with sqlite3.connect(path) as connection:
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute("UPDATE audit SET action='forged'")
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute("DELETE FROM audit")
        connection.execute("DROP TRIGGER audit_no_update")
        connection.execute("UPDATE audit SET action='forged' WHERE sequence=1")
    with pytest.raises(RuntimeError, match="audit"):
        store.audit_events(actor)
    store.close()
    with pytest.raises(RuntimeError, match="audit"):
        MemoryStore(path)


def test_purge_receipt_is_strict_and_versioned():
    from b12.contracts import PurgeReceipt

    valid = {
        "operation_id": str(uuid4()),
        "target_ids": (str(uuid4()),),
        "state": "pending",
        "pending_stores": ("canonical",),
    }
    assert PurgeReceipt(**valid).schema_version == 1
    for change in (
        {"operation_id": "bad"},
        {"target_ids": ("bad",)},
        {"state": "done"},
        {"pending_stores": (" ",)},
        {"error_code": " "},
        {"schema_version": True},
        {"schema_version": 2},
        {"pending_stores": ["canonical"]},
        {"extra": 1},
    ):
        with pytest.raises(ValidationError):
            PurgeReceipt(**(valid | change))


def test_unknown_memory_cannot_be_evidence_or_silently_purged(tmp_path):
    from b12.memory import MemoryStore

    store = MemoryStore(tmp_path / "memory.sqlite3")
    actor = Actor(id="owner", consent=True)
    missing = str(uuid4())
    with pytest.raises(ValueError):
        store.remember("unproven statement", actor, evidence_ids=(missing,))
    assert store.forget(missing, actor) is False
    with pytest.raises(KeyError):
        store.begin_purge(missing, actor)
    assert store.deletion_revision(actor) == 0
    store.close()


def test_forget_after_explicit_purge_is_already_forgotten(tmp_path):
    from b12.memory import MemoryStore

    store = MemoryStore(tmp_path / "memory.sqlite3")
    actor = Actor(id="owner", consent=True)
    saved = store.remember("explicitly purged event", actor)
    receipt = store.begin_purge(saved.id, actor)
    assert receipt.state == "complete"
    assert store.forget(saved.id, actor) is False
    assert store.begin_purge(saved.id, actor) == receipt
    assert store.deletion_revision(actor) == 1
    store.close()


def test_invalid_hook_error_is_rejected_without_poisoning_persistent_receipt(tmp_path):
    from b12.memory import MemoryStore

    store = MemoryStore(tmp_path / "memory.sqlite3")
    actor = Actor(id="owner", consent=True)
    saved = store.remember("event", actor)
    receipt = store.begin_purge(saved.id, actor, stores=("backup",))
    with pytest.raises(ValueError):
        store.acknowledge_purge(receipt.operation_id, "backup", actor, error_code="x" * 129)
    assert store.pending_purges(actor) == [receipt]
    store.close()


def test_deletion_closure_handles_shared_evidence_without_deleting_other_parent(tmp_path):
    from b12.memory import MemoryStore

    store = MemoryStore(tmp_path / "memory.sqlite3")
    actor = Actor(id="owner", consent=True)
    root = store.remember("root", actor)
    retained = store.remember("retained", actor)
    child = store.remember("combined", actor, evidence_ids=(retained.id, root.id))
    grandchild = store.remember("derived", actor, evidence_ids=(root.id, child.id))
    assert store.search("combined", actor)[0].evidence_ids == (retained.id, root.id)
    receipt = store.begin_purge(root.id, actor)
    assert set(receipt.target_ids) == {root.id, child.id, grandchild.id}
    assert [m.id for m in store.search("retained", actor)] == [retained.id]
    with pytest.raises(ValueError):
        store.remember("resurrected derived", actor, evidence_ids=(root.id,))
    with pytest.raises(ValueError):
        store.begin_purge(root.id, actor, stores=("new-hook",))
    store.close()


def test_deleted_audit_tail_is_detected_via_persisted_head(tmp_path):
    from b12.memory import MemoryStore

    path = tmp_path / "memory.sqlite3"
    store = MemoryStore(path)
    actor = Actor(id="owner", consent=True)
    store.remember("first", actor)
    store.remember("second", actor)
    with sqlite3.connect(path) as connection:
        connection.execute("DROP TRIGGER audit_no_delete")
        connection.execute("DELETE FROM audit WHERE sequence=2")
    with pytest.raises(RuntimeError, match="audit"):
        store.search("first", actor)
    with pytest.raises(RuntimeError, match="audit"):
        store.remember("never persisted", actor)
    store.close()
