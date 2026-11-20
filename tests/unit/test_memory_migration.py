"""Schema v1 -> v2 keeps every memory and every evidence link, and leaves a verified backup."""

import sqlite3
from pathlib import Path

import pytest

from b12.contracts import Actor
from b12.memory import MemoryStore
from b12.migrations import (
    _SCHEMA_V1,
    _UPGRADE_V1_TO_V2,
    _UPGRADE_V2_TO_V3,
    _UPGRADE_V3_TO_V4,
    SCHEMA_VERSION,
    backup_before_upgrade,
)


def _make_v1(path: Path) -> dict:
    connection = sqlite3.connect(path, isolation_level=None)
    for statement in _SCHEMA_V1:
        connection.execute(statement)
    connection.execute("PRAGMA user_version=1")
    rows = [
        ("00000000-0000-4000-8000-000000000001", "owner-1", "fact", "перший факт", "user"),
        ("00000000-0000-4000-8000-000000000002", "owner-1", "fact", "другий факт", "user"),
        ("00000000-0000-4000-8000-000000000003", "owner-1", "reflection", "висновок", "model"),
    ]
    connection.executemany(
        "INSERT INTO memories(id, actor_id, kind, text, source, created_at)"
        " VALUES (?,?,?,?,?,'2026-10-29T00:00:00+00:00')",
        [(i, a, k, t, s) for i, a, k, t, s in rows],
    )
    connection.executemany(
        "INSERT INTO evidence VALUES (?,?,?)",
        [(rows[2][0], rows[0][0], 0), (rows[2][0], rows[1][0], 1)],
    )
    connection.close()
    return {"memories": 3, "evidence": 2}


def test_upgrade_keeps_every_memory_and_evidence_link(tmp_path):
    path = tmp_path / "memory.sqlite3"
    expected = _make_v1(path)
    store = MemoryStore(path)
    try:
        version = store._connection.execute("PRAGMA user_version").fetchone()[0]
        assert version == SCHEMA_VERSION == 5  # v1 upgrades straight to the current schema
        count = store._connection.execute("SELECT COUNT(*) FROM memories").fetchone()[0]
        links = store._connection.execute(
            "SELECT COUNT(*) FROM memory_sources WHERE kind='memory'"
        ).fetchone()[0]
        assert (count, links) == (expected["memories"], expected["evidence"])
    finally:
        store.close()


def test_upgrade_writes_a_verified_backup_of_the_v1_store(tmp_path):
    path = tmp_path / "memory.sqlite3"
    _make_v1(path)
    store = MemoryStore(path)
    store.close()
    backups = sorted(tmp_path.glob("memory.v1-*.sqlite3"))
    assert len(backups) == 1
    check = sqlite3.connect(f"file:{backups[0]}?mode=ro", uri=True)
    try:
        assert check.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert check.execute("SELECT COUNT(*) FROM memories").fetchone()[0] == 3
        assert check.execute("SELECT COUNT(*) FROM evidence").fetchone()[0] == 2
        assert check.execute("PRAGMA user_version").fetchone()[0] == 1
    finally:
        check.close()


def test_backup_is_refused_when_its_counts_do_not_match(tmp_path):
    path = tmp_path / "memory.sqlite3"
    _make_v1(path)
    connection = sqlite3.connect(path, isolation_level=None)
    try:
        with pytest.raises(RuntimeError, match="backup verification"):
            backup_before_upgrade(connection, path, expected={"memories": 99, "evidence": 2})
    finally:
        connection.close()


def test_v4_store_upgrades_losslessly_with_backup_and_nullable_importance(tmp_path):
    path = tmp_path / "memory.sqlite3"
    connection = sqlite3.connect(path, isolation_level=None)
    for statement in (*_SCHEMA_V1, *_UPGRADE_V1_TO_V2, *_UPGRADE_V2_TO_V3, *_UPGRADE_V3_TO_V4):
        connection.execute(statement)
    rec_id = "00000000-0000-4000-8000-000000000010"
    connection.execute(
        "INSERT INTO memories(id, actor_id, kind, text, source, created_at)"
        " VALUES (?,'owner-1','fact','старий спогад v4','user','2026-11-18T00:00:00+00:00')",
        (rec_id,),
    )
    connection.execute("PRAGMA user_version=4")
    connection.close()

    store = MemoryStore(path)
    try:
        assert SCHEMA_VERSION == 5
        assert store._connection.execute("PRAGMA user_version").fetchone()[0] == 5
        record = store.get(rec_id, Actor(id="owner-1", owner=True, consent=True))
        assert record is not None
        assert record.text == "старий спогад v4"
        assert record.importance is None
        with pytest.raises(sqlite3.IntegrityError):
            store._connection.execute(
                "INSERT INTO memories(id, actor_id, kind, text, source, created_at, importance)"
                " VALUES ('00000000-0000-4000-8000-000000000011','owner-1','fact','x','user',"
                "'2026-11-18T00:00:00+00:00', 0)"
            )
        with pytest.raises(sqlite3.IntegrityError):
            store._connection.execute(
                "INSERT INTO memories(id, actor_id, kind, text, source, created_at, importance)"
                " VALUES ('00000000-0000-4000-8000-000000000012','owner-1','fact','x','user',"
                "'2026-11-18T00:00:00+00:00', 11)"
            )
    finally:
        store.close()

    backups = sorted(tmp_path.glob("memory.v4-*.sqlite3"))
    assert len(backups) == 1
    check = sqlite3.connect(f"file:{backups[0]}?mode=ro", uri=True)
    try:
        assert check.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert check.execute("SELECT COUNT(*) FROM memories").fetchone()[0] == 1
        assert check.execute("PRAGMA user_version").fetchone()[0] == 4
    finally:
        check.close()
