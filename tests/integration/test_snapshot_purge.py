"""A global purge inside snapshots must also remove the purged memories' vectors (A-09)."""

import sqlite3
from uuid import uuid4

from b12.contracts import Actor
from b12.memory import MemoryStore
from b12.service import Operations


def test_snapshot_purge_removes_the_vectors_of_purged_memories(tmp_path):
    state = tmp_path / "state"
    actor = Actor(id="owner-1", owner=True, consent=True)
    memory = MemoryStore(state / "memory" / "memory.sqlite3")
    record = memory.remember("факт, який буде забуто", actor)
    memory.close()
    (state / "semantic").mkdir(parents=True, exist_ok=True)
    vectors = sqlite3.connect(state / "semantic" / "vectors.sqlite3")
    vectors.execute(
        "CREATE TABLE IF NOT EXISTS vectors(actor_id TEXT NOT NULL, memory_id TEXT NOT NULL,"
        " digest TEXT NOT NULL, vector BLOB NOT NULL, PRIMARY KEY(actor_id, memory_id))"
    )
    vectors.execute("INSERT INTO vectors VALUES (?,?,?,?)", (actor.id, record.id, "d", b"\x00\x01"))
    vectors.commit()
    vectors.close()

    operations = Operations(state)
    snapshot = operations.create_snapshot()
    operations.purge_snapshots(str(uuid4()), actor.id, [record.id])

    snap_db = state / "snapshots" / snapshot["id"] / "semantic" / "vectors.sqlite3"
    check = sqlite3.connect(snap_db)
    left = check.execute("SELECT COUNT(*) FROM vectors WHERE memory_id=?", (record.id,)).fetchone()
    check.close()
    assert left[0] == 0
