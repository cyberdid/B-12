import os
import sqlite3

import pytest

from b12.contracts import Actor


@pytest.mark.parametrize("owner", [False, True])
def test_no_consent_cannot_reach_any_durable_payload(tmp_path, owner):
    from b12.memory import MemoryStore

    store = MemoryStore(tmp_path / "memory.sqlite3")
    actor = Actor(id="denied", owner=owner, consent=False)
    with pytest.raises(PermissionError):
        store.remember("denied_payload_marker", actor, source="denied_source_marker")
    assert store.audit_events(actor) == []
    with pytest.raises(PermissionError):
        store.search("marker", actor)
    for file in tmp_path.iterdir():
        for marker in (b"denied_payload_marker", b"denied_source_marker"):
            assert marker not in file.read_bytes()
    store.close()


def test_exact_actor_namespaces_apply_to_search_evidence_audit_and_forget(tmp_path):
    from b12.memory import MemoryStore

    path = tmp_path / "memory.sqlite3"
    store = MemoryStore(path)
    owner = Actor(id="owner", owner=True, consent=True)
    guest = Actor(id="owner-extra", consent=True)
    one = store.remember("shared lexical owner secret", owner)
    two = store.remember("shared lexical guest secret", guest)
    assert [m.id for m in store.search("shared", owner)] == [one.id]
    assert [m.id for m in store.search("shared", guest)] == [two.id]
    assert [m.id for m in store.search("shared", owner.model_copy(update={"owner": False}))] == [
        one.id
    ]
    with pytest.raises(ValueError):
        store.remember("cross_scope_marker", owner, evidence_ids=(two.id,))
    assert store.forget(two.id, owner) is False
    with pytest.raises(KeyError):
        store.begin_purge(two.id, owner)
    assert store.pending_purges(owner) == []
    assert all(event["actor_id"] == owner.id for event in store.audit_events(owner))
    assert all(event["actor_id"] == guest.id for event in store.audit_events(guest))
    assert store.forget(one.id, owner)
    assert store.deletion_revision(guest) == 0
    assert store.search("shared", guest)[0].text == two.text
    with sqlite3.connect(path) as connection:
        assert connection.execute("SELECT count(*) FROM evidence").fetchone()[0] == 0
    store.close()


def test_state_is_restricted_without_changing_existing_parent_permissions(tmp_path):
    from b12.memory import MemoryStore

    existing = tmp_path / "existing"
    existing.mkdir(mode=0o755)
    os.chmod(existing, 0o755)
    store = MemoryStore(existing / "private" / "memory.sqlite3")
    store.remember("allowed", Actor(id="owner", consent=True))
    assert existing.stat().st_mode & 0o777 == 0o755
    assert (existing / "private").stat().st_mode & 0o777 == 0o700
    for file in (existing / "private").iterdir():
        assert file.stat().st_mode & 0o777 == 0o600
    store.close()


def test_physical_purge_erases_unique_fts_terms_and_payload_bytes(tmp_path):
    from b12.memory import MemoryStore

    path = tmp_path / "memory.sqlite3"
    actor = Actor(id="owner", consent=True)
    store = MemoryStore(path)
    markers = ("purgesecretxqjv", "derivedsecretkzmt", "sourcesecrethnwp")
    saved = store.remember(markers[0], actor, source=markers[2])
    store.remember(markers[1], actor, evidence_ids=(saved.id,))
    store.remember("retaineduniqueterm", actor)
    with sqlite3.connect(path) as connection:
        connection.execute("CREATE VIRTUAL TABLE vocabulary USING fts5vocab(memory_fts, 'row')")
        assert {row[0] for row in connection.execute("SELECT term FROM vocabulary")} == {
            markers[0],
            markers[1],
            "retaineduniqueterm",
        }
    receipt = store.begin_purge(saved.id, actor)
    assert receipt.state == "complete"
    with sqlite3.connect(path) as connection:
        assert connection.execute("SELECT term FROM vocabulary").fetchall() == [
            ("retaineduniqueterm",)
        ]
    for file in tmp_path.iterdir():
        for marker in markers:
            assert marker.encode() not in file.read_bytes()
    store.close()
    reopened = MemoryStore(path)
    assert reopened.search(markers[0], actor) == []
    assert reopened.search("retaineduniqueterm", actor)[0].text == "retaineduniqueterm"
    reopened.close()
