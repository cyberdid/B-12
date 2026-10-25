import sqlite3
from concurrent.futures import ThreadPoolExecutor

import pytest

from b12.contracts import Actor


def test_restart_retains_allowed_memory(tmp_path):
    from b12.memory import MemoryStore

    actor = Actor(id="owner", owner=True, consent=True)
    path = tmp_path / "memory.sqlite3"
    store = MemoryStore(path)
    saved = store.remember("Учора тестували мікрофон і знайшли ехо", actor, source="event-test-17")
    store.close()
    reopened = MemoryStore(path)
    hits = reopened.search("мікрофон", actor)
    assert [(m.id, m.text, m.source) for m in hits] == [
        (saved.id, "Учора тестували мікрофон і знайшли ехо", "event-test-17")
    ]
    assert hits[0].created_at == saved.created_at
    reopened.close()


def test_pending_hooks_survive_restart_and_ack_is_actor_bound_idempotent(tmp_path):
    from b12.memory import MemoryStore

    path = tmp_path / "memory.sqlite3"
    actor = Actor(id="owner", consent=True)
    store = MemoryStore(path)
    saved = store.remember("private event", actor)
    receipt = store.begin_purge(saved.id, actor, stores=("canonical", "retrieval", "backup"))
    assert receipt.state == "pending"
    assert set(receipt.pending_stores) == {"retrieval", "backup"}
    store.close()
    store = MemoryStore(path)
    assert store.pending_purges(actor) == [receipt]
    assert store.resume_purges(actor) == [receipt]
    with pytest.raises(PermissionError):
        store.acknowledge_purge(receipt.operation_id, "backup", Actor(id="guest", consent=True))
    with pytest.raises(ValueError):
        store.acknowledge_purge(receipt.operation_id, "invented", actor)
    first = store.acknowledge_purge(receipt.operation_id, "retrieval", actor)
    assert first.pending_stores == ("backup",)
    assert store.acknowledge_purge(receipt.operation_id, "retrieval", actor) == first
    complete = store.acknowledge_purge(receipt.operation_id, "backup", actor)
    assert complete.state == "complete"
    assert complete.pending_stores == ()
    assert store.pending_purges(actor) == []
    assert (
        store.acknowledge_purge(receipt.operation_id, "backup", actor, error_code="late-error")
        == complete
    )
    store.close()


def test_failed_hook_is_persisted_and_can_be_retried(tmp_path):
    from b12.memory import MemoryStore

    actor = Actor(id="owner", consent=True)
    path = tmp_path / "memory.sqlite3"
    store = MemoryStore(path)
    saved = store.remember("private event", actor)
    receipt = store.begin_purge(saved.id, actor, stores=("backup",))
    failed = store.acknowledge_purge(
        receipt.operation_id, "backup", actor, error_code="backup_unavailable"
    )
    assert failed.state == "failed"
    assert failed.error_code == "backup_unavailable"
    store.close()
    store = MemoryStore(path)
    assert store.pending_purges(actor) == [failed]
    assert store.resume_purges(actor) == [failed]
    assert store.acknowledge_purge(receipt.operation_id, "backup", actor).state == "complete"
    store.close()


def test_busy_wal_reader_keeps_physical_purge_pending_until_resume(tmp_path):
    from b12.memory import MemoryStore

    actor = Actor(id="owner", consent=True)
    path = tmp_path / "memory.sqlite3"
    store = MemoryStore(path)
    saved = store.remember("held_wal_private_payload", actor)
    reader = sqlite3.connect(path)
    reader.execute("BEGIN")
    assert reader.execute("SELECT text FROM memories").fetchone()[0] == saved.text
    receipt = store.begin_purge(saved.id, actor)
    assert receipt.state == "pending"
    assert receipt.pending_stores == ("canonical",)
    assert store.search("held", actor) == []
    assert reader.execute("SELECT text FROM memories").fetchone()[0] == saved.text
    assert store.acknowledge_purge(receipt.operation_id, "canonical", actor).state == "pending"
    store.close()
    store = MemoryStore(path)
    assert store.pending_purges(actor)[0].state == "pending"
    reader.rollback()
    reader.close()
    assert store.resume_purges(actor)[0].state == "complete"
    for file in tmp_path.iterdir():
        assert saved.text.encode() not in file.read_bytes()
    store.close()


def test_deletion_revision_survives_restart_and_rejects_late_write(tmp_path):
    from b12.memory import MemoryStore

    actor = Actor(id="owner", consent=True)
    path = tmp_path / "memory.sqlite3"
    store = MemoryStore(path)
    revision = store.deletion_revision(actor)
    saved = store.remember("event before forgetting", actor)
    store.forget(saved.id, actor)
    assert store.deletion_revision(actor) == revision + 1
    store.close()
    store = MemoryStore(path)
    with pytest.raises(PermissionError):
        store.remember("stale_private_write_marker", actor, expected_deletion_revision=revision)
    assert store.deletion_revision(actor) == revision + 1
    assert store.remember("fresh permitted event", actor, expected_deletion_revision=revision + 1)
    with pytest.raises(ValueError):
        store.remember("bad revision", actor, expected_deletion_revision=True)
    for file in tmp_path.iterdir():
        assert b"stale_private_write_marker" not in file.read_bytes()
    store.close()


def test_independent_writers_serialize_revision_and_preserve_audit(tmp_path):
    from b12.memory import MemoryStore

    actor = Actor(id="owner", consent=True)
    path = tmp_path / "memory.sqlite3"
    initial = MemoryStore(path)
    saved = initial.remember("forget me", actor)
    revision = initial.deletion_revision(actor)

    def write(index):
        store = MemoryStore(path)
        try:
            return store.remember(
                f"concurrent event {index}", actor, expected_deletion_revision=revision
            )
        except PermissionError:
            return None
        finally:
            store.close()

    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = [executor.submit(write, i) for i in range(12)]
        initial.forget(saved.id, actor)
        results = [future.result() for future in futures]
    assert initial.audit_events(actor)
    assert len(initial.search("concurrent", actor, limit=100)) == sum(
        record is not None for record in results
    )
    assert initial.search("forget", actor) == []
    initial.close()


def test_newer_schema_is_rejected_before_data_mutation(tmp_path):
    from b12.memory import MemoryStore

    path = tmp_path / "future.sqlite3"
    with sqlite3.connect(path) as connection:
        connection.execute("PRAGMA user_version=999")
        connection.execute("CREATE TABLE future(data TEXT)")
        connection.execute("INSERT INTO future VALUES ('unchanged')")
    before = path.read_bytes()
    with pytest.raises(RuntimeError, match="schema"):
        MemoryStore(path)
    assert path.read_bytes() == before


def test_sql_cleanup_failure_retains_durable_closure_and_resumes_after_restart(tmp_path):
    from b12.memory import MemoryStore

    path = tmp_path / "memory.sqlite3"
    store = MemoryStore(path)
    actor = Actor(id="owner", consent=True)
    saved = store.remember("interrupted private event", actor)
    derived = store.remember("interrupted derived event", actor, evidence_ids=(saved.id,))
    with sqlite3.connect(path) as connection:
        connection.execute("""CREATE TRIGGER simulate_failed_delete BEFORE DELETE ON memories
                              BEGIN SELECT RAISE(ABORT, 'synthetic failure'); END""")
    receipt = store.begin_purge(saved.id, actor)
    assert receipt.state == "failed"
    assert receipt.error_code == "canonical_cleanup_failed"
    assert set(receipt.target_ids) == {saved.id, derived.id}
    assert store.search("interrupted", actor) == []
    assert store.deletion_revision(actor) == 1
    with sqlite3.connect(path) as connection:
        assert connection.execute("SELECT count(*) FROM memories").fetchone()[0] == 2
        assert connection.execute("SELECT count(*) FROM tombstones").fetchone()[0] == 2
    with pytest.raises(ValueError):
        store.remember("late derived event", actor, evidence_ids=(saved.id,))
    store.close()
    with sqlite3.connect(path) as connection:
        connection.execute("DROP TRIGGER simulate_failed_delete")
    store = MemoryStore(path)
    assert store.pending_purges(actor) == [receipt]
    assert store.resume_purges(actor)[0].state == "complete"
    with sqlite3.connect(path) as connection:
        assert connection.execute("SELECT count(*) FROM memories").fetchone()[0] == 0
    store.close()
