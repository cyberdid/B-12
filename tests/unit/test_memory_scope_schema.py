"""Schema v4 (ADR-016): preference scope (applies_when), origin, revocation."""

import sqlite3

import pytest

from b12.contracts import Actor
from b12.memory import MemoryStore
from b12.migrations import _SCHEMA_V1, _UPGRADE_V1_TO_V2, _UPGRADE_V2_TO_V3, SCHEMA_VERSION

OWNER = Actor(id="owner", owner=True, consent=True)


def _make_v3(path):
    connection = sqlite3.connect(path, isolation_level=None)
    for statement in (*_SCHEMA_V1, *_UPGRADE_V1_TO_V2, *_UPGRADE_V2_TO_V3):
        connection.execute(statement)
    connection.execute(
        "INSERT INTO memories(id, actor_id, kind, text, source, created_at, valid_to)"
        " VALUES ('00000000-0000-4000-8000-000000000002','owner','preference','без цукру','user',"
        "'2026-11-01T00:00:00+00:00','2026-11-20')"
    )
    connection.execute("PRAGMA user_version=3")
    connection.close()


def test_new_store_is_v4(tmp_path):
    store = MemoryStore(tmp_path / "m.sqlite3")
    try:
        assert SCHEMA_VERSION == 4
        assert store._connection.execute("PRAGMA user_version").fetchone()[0] == 4
    finally:
        store.close()


def test_v3_store_upgrades_losslessly_with_scope_left_unknown(tmp_path):
    path = tmp_path / "m.sqlite3"
    _make_v3(path)
    store = MemoryStore(path)
    try:
        record = store.get("00000000-0000-4000-8000-000000000002", OWNER)
        assert record.text == "без цукру" and record.valid_to == "2026-11-20"
        assert record.applies_when is None and record.origin is None
    finally:
        store.close()


def test_scope_and_origin_round_trip(tmp_path):
    store = MemoryStore(tmp_path / "m.sqlite3")
    try:
        record = store.remember(
            "Не дзвонити до 14:00.",
            OWNER,
            kind="preference",
            applies_when="коли власник працює в нічну зміну",
            origin="explicit",
        )
        again = store.get(record.id, OWNER)
        assert again.applies_when == "коли власник працює в нічну зміну"
        assert again.origin == "explicit"
    finally:
        store.close()


@pytest.mark.parametrize(
    "fields", [{"origin": "guessed"}, {"applies_when": ""}, {"applies_when": "x" * 201}]
)
def test_invalid_scope_fields_are_refused_before_writing(tmp_path, fields):
    store = MemoryStore(tmp_path / "m.sqlite3")
    try:
        with pytest.raises(ValueError):
            store.remember("правило", OWNER, kind="preference", **fields)
        assert store.recent(OWNER) == []
    finally:
        store.close()


def test_supersede_without_replacement_is_a_revocation(tmp_path):
    store = MemoryStore(tmp_path / "m.sqlite3")
    try:
        rule = store.remember("Звіти лише у PDF.", OWNER, kind="preference")
        old = store.remember("Напруга 12 В.", OWNER)
        new = store.remember("Напруга 24 В.", OWNER)
        assert store.supersede(rule.id, OWNER)
        assert store.supersede(old.id, OWNER, replaced_by=new.id)
        assert store.get(rule.id, OWNER).status_reason == "revoked"
        assert store.get(old.id, OWNER).status_reason == "superseded"
    finally:
        store.close()
