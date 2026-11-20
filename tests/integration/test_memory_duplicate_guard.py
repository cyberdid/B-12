"""Task A1: recall-loop / duplicate guard in memory_store."""

from b12.auth import owner_capabilities
from b12.contracts import Actor
from b12.memory import MemoryStore
from b12.runtime import open_runtime


async def test_restating_a_stored_fact_writes_nothing(scripted_ollama, tmp_path):
    state, base = scripted_ollama
    runtime = open_runtime(base.model_copy(update={"state_dir": tmp_path / "state"}))
    try:
        actor = runtime.control.create_actor(owner=True, consent=True)
        seeded = runtime.memory.remember("Власник п’є каву з однією ложкою цукру.", actor)
        session = runtime.control.create_session(actor.id)
        task = runtime.control.create_task(session)
        grant = runtime.control.issue_grant(
            actor.id, session, owner_capabilities(runtime.settings), task_id=task, ttl_s=600
        )
        state["script"] = [
            {"tool_calls": [("memory_store", {"text": "Власник п'є каву з однією ложкою цукру"})]},
            {"content": "Запам'ятала."},
        ]
        result = await runtime.agent.turn(
            session, grant, "Пам'ятаєш, яку каву я п'ю?", task_id=task, timeout_s=60
        )
        assert len(runtime.memory.recent(actor, limit=10)) == 1
        stored = [r for r in result.tool_results if r.name == "memory_store"]
        assert len(stored) == 1
        assert stored[0].status == "completed"
        assert stored[0].content == {"duplicate_of": seeded.id, "stored": False}
        assert stored[0].side_effects == ()
    finally:
        runtime.close()


def test_find_duplicate_handles_apostrophes_punctuation_and_scope(tmp_path):
    store = MemoryStore(tmp_path / "memory.sqlite3")
    owner = Actor(id="owner", owner=True, consent=True)
    other = Actor(id="other", owner=False, consent=True)
    try:
        coffee = store.remember("Власник п’є каву.", owner)
        assert store.find_duplicate("Власник п'є каву", owner).id == coffee.id
        assert store.find_duplicate("  власник   пʼє  каву! ", owner).id == coffee.id
        assert store.find_duplicate("Власник п`є каву?", owner).id == coffee.id
        assert store.find_duplicate("Власник п'є чай.", owner) is None
        assert store.find_duplicate("Власник п'є каву.", other) is None

        # Superseded / revoked records are not treated as live duplicates.
        assert store.supersede(coffee.id, owner)
        assert store.find_duplicate("Власник п'є каву.", owner) is None
        re_added = store.remember("Власник п'є каву.", owner)
        assert store.find_duplicate("Власник п’є каву!", owner).id == re_added.id
    finally:
        store.close()
