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


def test_new_store_is_v3(tmp_path):
    store = MemoryStore(tmp_path / "m.sqlite3")
    try:
        assert SCHEMA_VERSION == 3
        assert store._connection.execute("PRAGMA user_version").fetchone()[0] == 3
    finally:
        store.close()


def test_v2_store_upgrades_losslessly_with_unknown_times_left_unknown(tmp_path):
    path = tmp_path / "m.sqlite3"
    _make_v2(path)
    store = MemoryStore(path)
    try:
        assert store._connection.execute("PRAGMA user_version").fetchone()[0] == 3
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
