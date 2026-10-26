"""Per-operation cost must not grow with history: soak found O(audit) transactions."""

import time
from uuid import uuid4

from b12.contracts import Actor


def per_call_ms(store, actor, calls=50):
    started = time.perf_counter()
    for _ in range(calls):
        store.is_live(str(uuid4()), actor)
    return (time.perf_counter() - started) / calls * 1000


def test_memory_operation_cost_is_independent_of_audit_size(tmp_path):
    from b12.memory import MemoryStore

    actor = Actor(id="owner", consent=True)
    store = MemoryStore(tmp_path / "memory.sqlite3")
    for index in range(200):
        store.remember(f"запис {index}", actor)
    small = per_call_ms(store, actor)
    for index in range(200, 6000):
        store.remember(f"запис {index}", actor)
    large = per_call_ms(store, actor)
    store.close()
    assert large < max(3 * small, 1.0), (small, large)


def test_appends_by_another_connection_are_still_verified(tmp_path):
    import sqlite3

    import pytest

    from b12.memory import MemoryStore

    actor = Actor(id="owner", consent=True)
    first = MemoryStore(tmp_path / "memory.sqlite3")
    second = MemoryStore(tmp_path / "memory.sqlite3")
    first.remember("один", actor)
    second.remember("два", actor)
    assert len(first.search("два", actor)) == 1  # incremental check accepts valid appends
    raw = sqlite3.connect(tmp_path / "memory.sqlite3")
    raw.execute("DROP TRIGGER IF EXISTS audit_no_update")
    sequence = raw.execute("SELECT MAX(sequence) FROM audit").fetchone()[0]
    raw.execute("UPDATE audit SET action='forged' WHERE sequence=?", (sequence,))
    raw.commit()
    raw.close()
    with pytest.raises(RuntimeError, match="audit"):
        first.search("один", actor)
    first.close()
    second.close()
