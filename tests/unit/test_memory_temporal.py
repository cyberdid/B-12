"""Schema v3 (ADR-015): event time, validity, reliability, locator and supersession lineage."""

import sqlite3

import pytest

from b12.contracts import Actor
from b12.memory import MemoryStore
from b12.migrations import _SCHEMA_V1, _UPGRADE_V1_TO_V2, SCHEMA_VERSION

OWNER = Actor(id="owner", owner=True, consent=True)


def _make_v2(path):
    connection = sqlite3.connect(path, isolation_level=None)
    for statement in (*_SCHEMA_V1, *_UPGRADE_V1_TO_V2):
        connection.execute(statement)
    connection.execute(
        "INSERT INTO memories(id, actor_id, kind, text, source, created_at)"
        " VALUES ('00000000-0000-4000-8000-000000000001','owner','fact','старий факт','user',"
        "'2026-11-01T00:00:00+00:00')"
    )
    connection.execute("PRAGMA user_version=2")
    connection.close()


def test_new_store_is_v3_or_later(tmp_path):
    store = MemoryStore(tmp_path / "m.sqlite3")
    try:
        assert SCHEMA_VERSION >= 3
        assert store._connection.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION
    finally:
        store.close()


def test_v2_store_upgrades_losslessly_with_unknown_times_left_unknown(tmp_path):
    path = tmp_path / "m.sqlite3"
    _make_v2(path)
    store = MemoryStore(path)
    try:
        assert store._connection.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION
        record = store.get("00000000-0000-4000-8000-000000000001", OWNER)
        assert record.text == "старий факт"
        assert (record.event_time, record.valid_from, record.valid_to) == (None, None, None)
        assert record.reliability is None and record.superseded_by is None
    finally:
        store.close()


def test_temporal_fields_round_trip(tmp_path):
    store = MemoryStore(tmp_path / "m.sqlite3")
    try:
        record = store.remember(
            "Склад закрито на ремонт.",
            OWNER,
            event_time="2026-11-18",
            valid_from="2026-11-18",
            valid_to="2026-11-25",
            reliability="high",
            source_locator="наказ №7",
            temporal_source="owner",
        )
        again = store.get(record.id, OWNER)
        assert (again.event_time, again.valid_from, again.valid_to) == (
            "2026-11-18",
            "2026-11-18",
            "2026-11-25",
        )
        assert (again.reliability, again.source_locator, again.temporal_source) == (
            "high",
            "наказ №7",
            "owner",
        )
    finally:
        store.close()


@pytest.mark.parametrize(
    "fields",
    [
        {"valid_from": "2026-11-20", "valid_to": "2026-11-10"},
        {"event_time": "вчора"},
        {"reliability": "certain"},
        {"temporal_source": "guess"},
    ],
)
def test_invalid_temporal_fields_are_refused_before_writing(tmp_path, fields):
    store = MemoryStore(tmp_path / "m.sqlite3")
    try:
        with pytest.raises(ValueError):
            store.remember("факт", OWNER, **fields)
        assert store._connection.execute("SELECT COUNT(*) FROM memories").fetchone()[0] == 0
    finally:
        store.close()


def test_supersede_records_the_replacement(tmp_path):
    store = MemoryStore(tmp_path / "m.sqlite3")
    try:
        old = store.remember("Напруга 12 В.", OWNER)
        new = store.remember("Напруга 24 В.", OWNER)
        assert store.supersede(old.id, OWNER, replaced_by=new.id)
        stale = store.get(old.id, OWNER)
        assert stale.status == "stale" and stale.superseded_by == new.id
        assert store.superseded_by_records([new.id], OWNER) == {new.id: [stale]}
    finally:
        store.close()


def test_supersede_refuses_a_replacement_from_another_actor(tmp_path):
    store = MemoryStore(tmp_path / "m.sqlite3")
    guest = Actor(id="guest", consent=True)
    try:
        old = store.remember("A", OWNER)
        foreign = store.remember("B", guest)
        with pytest.raises(ValueError):
            store.supersede(old.id, OWNER, replaced_by=foreign.id)
    finally:
        store.close()


def test_as_of_returns_the_value_that_held_then(tmp_path):
    store = MemoryStore(tmp_path / "m.sqlite3")
    try:
        old = store.remember("Адреса: Київ.", OWNER, valid_from="2026-01-01", valid_to="2026-10-31")
        new = store.remember("Адреса: Львів.", OWNER, valid_from="2026-11-01")
        assert store.supersede(old.id, OWNER, replaced_by=new.id)
        future = store.remember(
            "Адреса: Одеса.",
            OWNER,
            event_time="2026-12-10",
            valid_from="2026-12-10",
        )
        revoked = store.remember("Адреса: фейк.", OWNER, valid_from="2026-01-01")
        assert store.supersede(revoked.id, OWNER)
        open_fact = store.remember("Адреса офісу: Поділ.", OWNER)

        assert {r.id for r in store.search("Адреса", OWNER, as_of="2026-10-15")} == {
            open_fact.id,
            old.id,
        }
        assert {r.id for r in store.search("Адреса", OWNER, as_of="2026-11-15")} == {
            open_fact.id,
            new.id,
        }
        # Newer non-matching rows must not crowd out an older valid match before limit.
        for i in range(6):
            store.remember(f"Адреса філії {i}: Тернопіль.", OWNER, valid_from="2026-11-01")
        bounded = store.search("Адреса", OWNER, limit=2, as_of="2026-10-31")
        assert {r.id for r in bounded} == {open_fact.id, old.id}
        assert len(store.search("Адреса", OWNER, limit=1, as_of="2026-10-31")) == 1
        # Event time in the future relative to as_of is excluded even with open valid_from/valid_to.
        later_event = store.remember("Адреса складу: Харків.", OWNER, event_time="2026-11-20")
        before = [r.id for r in store.search("складу", OWNER, as_of="2026-11-15")]
        after = [r.id for r in store.search("складу", OWNER, as_of="2026-11-20")]
        assert before == []
        assert after == [later_event.id]
        # Default as_of=None keeps existing search behavior.
        assert {r.id for r in store.search("Адреса", OWNER)} >= {old.id, new.id, future.id}
        with pytest.raises(ValueError):
            store.search("Адреса", OWNER, as_of="вчора")
    finally:
        store.close()


def test_recent_important_outranks_old_trivial(tmp_path):
    from datetime import UTC, datetime

    from b12.retrieval import memory_score, rank_memory_candidates

    assert memory_score(1.0, age_days=0.0, importance=10) == pytest.approx(1.5)
    assert memory_score(1.0, age_days=30.0, importance=5) == pytest.approx(0.5)
    assert memory_score(1.0, age_days=0.0, importance=9) > memory_score(
        1.0, age_days=60.0, importance=2
    )

    store = MemoryStore(tmp_path / "m.sqlite3")
    try:
        old_trivial = store.remember("Коротка примітка про каву.", OWNER, importance=1)
        recent_important = store.remember("Критичний пароль резерву кави.", OWNER, importance=10)
        store._connection.execute(
            "UPDATE memories SET created_at=? WHERE id=?",
            ("2026-09-01T12:00:00+00:00", old_trivial.id),
        )
        store._connection.execute(
            "UPDATE memories SET created_at=? WHERE id=?",
            ("2026-11-19T12:00:00+00:00", recent_important.id),
        )
        old_row = store.get(old_trivial.id, OWNER)
        new_row = store.get(recent_important.id, OWNER)
        assert old_row.importance == 1 and new_row.importance == 10
        ranked = rank_memory_candidates(
            [(old_row, 1.0), (new_row, 1.0)], now=datetime(2026, 11, 20, 12, 0, tzinfo=UTC)
        )
        assert [r.id for r in ranked] == [recent_important.id, old_trivial.id]
        with pytest.raises(ValueError):
            store.remember("погано", OWNER, importance=0)
        with pytest.raises(ValueError):
            store.remember("погано", OWNER, importance=11)
    finally:
        store.close()


def test_unknown_importance_is_neutral(tmp_path):
    from datetime import datetime

    from b12.retrieval import memory_score, rank_memory_candidates

    assert memory_score(1.0, age_days=0.0, importance=None) == pytest.approx(1.0)
    assert memory_score(1.0, age_days=0.0, importance=None) == pytest.approx(
        memory_score(1.0, age_days=0.0, importance=5)
    )

    store = MemoryStore(tmp_path / "m.sqlite3")
    try:
        unknown = store.remember("Факт без оцінки.", OWNER)
        assert unknown.importance is None
        low = store.remember("Дрібний факт.", OWNER, importance=1)
        high = store.remember("Важливий факт.", OWNER, importance=9)
        ts = "2026-11-20T12:00:00+00:00"
        store._connection.execute("UPDATE memories SET created_at=?", (ts,))
        ranked = rank_memory_candidates(
            [
                (store.get(low.id, OWNER), 1.0),
                (store.get(unknown.id, OWNER), 1.0),
                (store.get(high.id, OWNER), 1.0),
            ],
            now=datetime.fromisoformat(ts),
        )
        assert [r.id for r in ranked] == [high.id, unknown.id, low.id]
    finally:
        store.close()
