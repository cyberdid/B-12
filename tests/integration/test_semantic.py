"""Semantic recall through the real stdio bridge process with a deterministic backend."""

import sys
from pathlib import Path

import pytest

from b12.contracts import Actor

FIXTURES = str(Path(__file__).resolve().parents[1] / "fixtures")


def embedder(backend="fake_embedder:HashEmbedder"):
    from b12.semantic import BridgeEmbedder

    return BridgeEmbedder(sys.executable, backend=backend, env={"PYTHONPATH": FIXTURES})


@pytest.fixture
def index(tmp_path):
    from b12.memory import MemoryStore
    from b12.semantic import SemanticIndex

    memory = MemoryStore(tmp_path / "memory.sqlite3")
    semantic = SemanticIndex(tmp_path / "semantic", embedder(), memory, min_score=0.3)
    yield memory, semantic
    semantic.close()
    memory.close()


async def test_semantic_ranks_by_meaning_overlap_and_checks_liveness(index):
    memory, semantic = index
    actor = Actor(id="owner", consent=True)
    cat = memory.remember("Мого тестового кота звати Бублик", actor)
    memory.remember("Сервер стоїть у кімнаті двісті", actor)
    hits = await semantic.search("як звати кота", actor, k=1)
    assert [h[0] for h in hits] == [cat.id]
    memory.begin_purge(cat.id, actor)  # canonical tombstone without the semantic hook
    assert cat.id not in [h[0] for h in await semantic.search("як звати кота", actor)]


async def test_purge_hook_and_digest_change_drop_vectors(index):
    memory, semantic = index
    actor = Actor(id="owner", consent=True)
    record = memory.remember("вектор для видалення", actor)
    assert await semantic.sync(actor) == 1
    semantic.purge(actor.id, [record.id])
    assert semantic.db.execute("SELECT COUNT(*) FROM vectors").fetchone()[0] == 0
    await semantic.sync(actor)
    semantic.embedder.digest = "other/model@x"
    assert await semantic.sync(actor) == 1  # stale-digest vectors are re-embedded


async def test_actor_isolation(index):
    memory, semantic = index
    owner, guest = Actor(id="owner", consent=True), Actor(id="guest", consent=True)
    memory.remember("секрет власника про кота", owner)
    assert await semantic.search("кота", guest) == []


async def test_agent_uses_semantic_and_falls_back_to_lexical(scripted_ollama, tmp_path):
    from b12.runtime import open_runtime

    state, base = scripted_ollama
    settings = base.model_copy(
        update={
            "state_dir": tmp_path / "state",
            "embedding_python": sys.executable,
            "embedding_backend": "fake_embedder:HashEmbedder",
        }
    )
    runtime = open_runtime(settings)
    runtime.agent.semantic.embedder.env["PYTHONPATH"] = FIXTURES
    runtime.agent.semantic.min_score = 0.3  # hash embedder scale, not EmbeddingGemma 2
    try:
        actor = runtime.control.create_actor(owner=True, consent=True)
        record = runtime.memory.remember("Кота звати Бублик", actor)
        session = runtime.control.create_session(actor.id)
        grant = runtime.control.issue_grant(actor.id, session, ("time.read",))
        state["script"] = [{"content": "Бублик"}, {"content": "Бублик"}]
        await runtime.agent.turn(session, grant, "нагадай ім'я тварини кота")
        assert record.id in state["requests"][-1]["messages"][0]["content"]
        runtime.agent.semantic.embedder.backend = "missing_module:Nothing"
        runtime.agent.semantic.embedder.close()
        result = await runtime.agent.turn(session, grant, "Кота звати як?")
        assert result.state == "completed"  # embedding failure -> lexical recall still works
        assert record.id in state["requests"][-1]["messages"][0]["content"]
    finally:
        runtime.close()
