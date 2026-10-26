import sqlite3
from uuid import uuid4

import pytest


def turn(text="Привіт", answer="Вітаю"):
    return [
        {"role": "user", "content": text},
        {"role": "assistant", "content": answer},
    ]


def new_ids(count):
    return [str(uuid4()) for _ in range(count)]


def test_completed_turns_survive_restart_in_order_with_private_files(tmp_path):
    from b12.sessions import SessionStore

    actor, session = new_ids(2)
    path = tmp_path / "sessions"
    store = SessionStore(path)
    first, second = new_ids(2)
    store.commit_turn(session, actor, first, turn("перший", "один"), tags={})
    store.commit_turn(session, actor, second, turn("другий", "два"), tags={})
    store.close()
    assert oct(path.stat().st_mode & 0o777) == "0o700"
    assert oct((path / "sessions.sqlite3").stat().st_mode & 0o777) == "0o600"
    reopened = SessionStore(path)
    history = reopened.history(session, actor)
    assert [m["content"] for m in history] == ["перший", "один", "другий", "два"]
    assert [m["turn_id"] for m in history] == [first, first, second, second]
    reopened.close()


def test_history_is_exactly_actor_and_session_bound(tmp_path):
    from b12.sessions import SessionStore

    actor, other, session, foreign = new_ids(4)
    store = SessionStore(tmp_path / "sessions")
    store.commit_turn(session, actor, str(uuid4()), turn("секрет"), tags={})
    assert store.history(session, other) == []
    assert store.history(foreign, actor) == []
    with pytest.raises(PermissionError):
        store.commit_turn(session, other, str(uuid4()), turn("чужий"), tags={})
    store.close()


def test_history_returns_only_latest_complete_turns(tmp_path):
    from b12.sessions import SessionStore

    actor, session = new_ids(2)
    store = SessionStore(tmp_path / "sessions")
    for index in range(5):
        store.commit_turn(session, actor, str(uuid4()), turn(f"q{index}", f"a{index}"), tags={})
    assert [m["content"] for m in store.history(session, actor, max_turns=2)] == [
        "q3",
        "a3",
        "q4",
        "a4",
    ]
    store.close()


def test_commit_rejects_duplicate_turn_and_invalid_tags(tmp_path):
    from b12.sessions import SessionStore

    actor, session, turn_id = new_ids(3)
    store = SessionStore(tmp_path / "sessions")
    store.commit_turn(session, actor, turn_id, turn(), tags={})
    with pytest.raises(sqlite3.IntegrityError):
        store.commit_turn(session, actor, turn_id, turn(), tags={})
    with pytest.raises(ValueError):
        store.commit_turn(session, actor, str(uuid4()), turn(), tags={"not-a-uuid": "memory"})
    with pytest.raises(ValueError):
        store.commit_turn(session, actor, str(uuid4()), turn(), tags={str(uuid4()): "invented"})
    store.close()


def test_purge_evidence_removes_every_tagged_turn_and_is_idempotent(tmp_path):
    from b12.sessions import SessionStore

    actor, session, memory, unrelated = new_ids(4)
    path = tmp_path / "sessions"
    store = SessionStore(path)
    tagged, recall, clean = new_ids(3)
    store.commit_turn(
        session, actor, tagged, turn("Запам'ятай PIN 4321", "Збережено"), tags={memory: "memory"}
    )
    store.commit_turn(session, actor, recall, turn("Який PIN?", "4321"), tags={memory: "memory"})
    store.commit_turn(session, actor, clean, turn("Погода?", "Не знаю"), tags={unrelated: "memory"})
    operation = str(uuid4())
    assert set(store.purge_evidence(operation, actor, (memory,))) == {tagged, recall}
    assert [m["turn_id"] for m in store.history(session, actor)] == [clean, clean]
    # Retry after restart reports the same affected turns, without re-deleting anything else.
    store.close()
    store = SessionStore(path)
    assert set(store.purge_evidence(operation, actor, (memory,))) == {tagged, recall}
    assert [m["turn_id"] for m in store.history(session, actor)] == [clean, clean]
    store.close()
    raw = (path / "sessions.sqlite3").read_bytes()
    assert b"4321" not in raw and b"PIN" not in raw


def test_purge_is_actor_scoped(tmp_path):
    from b12.sessions import SessionStore

    actor, other, session, other_session, memory = new_ids(5)
    store = SessionStore(tmp_path / "sessions")
    store.commit_turn(session, actor, str(uuid4()), turn("мій"), tags={memory: "memory"})
    store.commit_turn(other_session, other, str(uuid4()), turn("чужий"), tags={memory: "memory"})
    assert store.purge_evidence(str(uuid4()), actor, (memory,))
    assert store.history(session, actor) == []
    assert len(store.history(other_session, other)) == 2
    store.close()


def test_history_filter_hides_turns_with_dead_evidence_before_hook_runs(tmp_path):
    from b12.sessions import SessionStore

    actor, session, dead, live = new_ids(4)
    store = SessionStore(tmp_path / "sessions")
    hidden, shown = new_ids(2)
    store.commit_turn(session, actor, hidden, turn("старе"), tags={dead: "memory"})
    store.commit_turn(session, actor, shown, turn("нове"), tags={live: "document"})
    history = store.history(session, actor, live=lambda evidence_id, kind: evidence_id == live)
    assert {m["turn_id"] for m in history} == {shown}
    store.close()


def test_checkpoint_roundtrip_is_bound_and_purgeable(tmp_path):
    from b12.sessions import SessionStore

    actor, session, turn_id, memory = new_ids(4)
    path = tmp_path / "sessions"
    store = SessionStore(path)
    state = {"messages": turn("секретний чекпойнт"), "sequence": 3}
    store.save_checkpoint(turn_id, session, actor, state, tags={memory: "memory"})
    store.close()
    store = SessionStore(path)
    assert store.load_checkpoint(turn_id, actor) == state
    assert store.load_checkpoint(turn_id, str(uuid4())) is None
    store.purge_evidence(str(uuid4()), actor, (memory,))
    assert store.load_checkpoint(turn_id, actor) is None
    store.close()
    assert "секретний".encode() not in (path / "sessions.sqlite3").read_bytes()


def test_drop_checkpoint_and_clear_session(tmp_path):
    from b12.sessions import SessionStore

    actor, session, turn_id = new_ids(3)
    store = SessionStore(tmp_path / "sessions")
    store.save_checkpoint(turn_id, session, actor, {"sequence": 1}, tags={})
    store.drop_checkpoint(turn_id, actor)
    assert store.load_checkpoint(turn_id, actor) is None
    store.commit_turn(session, actor, str(uuid4()), turn(), tags={})
    store.clear_session(session, actor)
    assert store.history(session, actor) == []
    store.close()


def test_applied_invalidation_ledger_deduplicates_operations(tmp_path):
    from b12.sessions import SessionStore

    store = SessionStore(tmp_path / "sessions")
    operation = str(uuid4())
    assert not store.invalidation_applied(operation)
    store.mark_invalidation_applied(operation)
    store.mark_invalidation_applied(operation)
    assert store.invalidation_applied(operation)
    store.close()
