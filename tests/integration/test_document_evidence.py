"""Document evidence (A-10): a memory can cite a document from KnowledgeIndex, and the citation
follows the document's life: created, used, re-indexed, changed, removed. Dependent memories
become stale, and the status survives a restart."""

import json

import pytest

from b12.runtime import open_runtime


@pytest.fixture
def runtime_env(scripted_ollama, tmp_path):
    _, base = scripted_ollama
    settings = base.model_copy(update={"state_dir": tmp_path / "state"})
    opened = []
    runtime = open_runtime(settings)
    opened.append(runtime)
    actor = runtime.control.create_actor(owner=True, consent=True)
    docs = tmp_path / "docs"
    docs.mkdir()
    yield settings, runtime, actor, docs, opened
    for item in opened:
        try:
            item.close()
        except Exception:  # noqa: BLE001 - a store closed by the test itself
            pass


def _write(path, text):
    path.write_text(text, encoding="utf-8")
    return path


def _find_document_evidence(runtime, actor, query):
    hits = runtime.knowledge.search(query, actor)
    assert hits, "the indexed fact must be searchable"
    return hits[0]["evidence_id"]


async def test_memory_cites_a_document_and_the_citation_is_checked(runtime_env):
    _, runtime, actor, docs, _ = runtime_env
    note = _write(docs / "zrazok.txt", "Вода закипає при сто градусах за Цельсієм.")
    runtime.knowledge.index_document(note, actor)
    evidence = _find_document_evidence(runtime, actor, "закипає")

    record = runtime.memory.remember("Вода закипає при 100 °C", actor, documents=(evidence,))
    assert record.status == "active"
    assert [(s["kind"], s["id"]) for s in record.sources] == [("document", evidence)]
    assert record.sources[0]["revision"]

    with pytest.raises(ValueError):
        runtime.memory.remember(
            "фальшиве джерело", actor, documents=("00000000-0000-4000-8000-000000000000",)
        )


async def test_changing_the_document_makes_the_citing_memory_stale(runtime_env):
    _, runtime, actor, docs, _ = runtime_env
    note = _write(docs / "zrazok.txt", "Вода закипає при сто градусах.")
    runtime.knowledge.index_document(note, actor)
    evidence = _find_document_evidence(runtime, actor, "закипає")
    record = runtime.memory.remember("Вода закипає при 100 °C", actor, documents=(evidence,))

    _write(note, "Вода закипає при дев'яноста градусах на висоті.")
    runtime.knowledge.index_document(note, actor)
    await runtime.purge.sync_knowledge(actor)

    stored = runtime.memory.get(record.id, actor)
    assert stored.status == "stale"
    assert stored.status_reason == "document_changed"
    assert not runtime.memory.is_live(record.id, actor)
    assert record.id not in [r.id for r in runtime.memory.recent(actor)]


async def test_a_memory_built_on_a_stale_memory_is_stale_too(runtime_env):
    _, runtime, actor, docs, _ = runtime_env
    note = _write(docs / "zrazok.txt", "Ртуть рідка при кімнатній температурі.")
    runtime.knowledge.index_document(note, actor)
    evidence = _find_document_evidence(runtime, actor, "Ртуть")
    base = runtime.memory.remember("Ртуть рідка", actor, documents=(evidence,))
    derived = runtime.memory.remember(
        "Ртуть — метал у рідкому стані", actor, evidence_ids=(base.id,)
    )

    _write(note, "Ртуть тепер тверда.")
    runtime.knowledge.index_document(note, actor)
    await runtime.purge.sync_knowledge(actor)

    assert runtime.memory.get(base.id, actor).status == "stale"
    derived_now = runtime.memory.get(derived.id, actor)
    assert derived_now.status == "stale"
    assert derived_now.status_reason == "source_stale"


async def test_removed_document_keeps_its_citations_visible_as_stale(runtime_env):
    _, runtime, actor, docs, _ = runtime_env
    note = _write(docs / "zrazok.txt", "Азот становить сімдесят вісім відсотків повітря.")
    runtime.knowledge.index_document(note, actor)
    evidence = _find_document_evidence(runtime, actor, "Азот")
    record = runtime.memory.remember("Азот — основна частина повітря", actor, documents=(evidence,))

    runtime.knowledge.remove_document(note, actor)
    await runtime.purge.sync_knowledge(actor)

    stored = runtime.memory.get(record.id, actor)
    assert stored.status == "stale"
    assert stored.sources[0]["id"] == evidence


async def test_a_citation_survives_a_restart_with_its_source(runtime_env, tmp_path):
    settings, runtime, actor, docs, opened = runtime_env
    note = _write(docs / "zrazok.txt", "Озон поглинає ультрафіолет.")
    runtime.knowledge.index_document(note, actor)
    evidence = _find_document_evidence(runtime, actor, "Озон")
    record = runtime.memory.remember("Озон поглинає ультрафіолет", actor, documents=(evidence,))
    runtime.close()

    reopened = open_runtime(settings)
    opened.append(reopened)
    hits = reopened.memory.search("ультрафіолет", actor)
    assert [h.id for h in hits] == [record.id]
    assert hits[0].status == "active"
    assert hits[0].sources[0]["id"] == evidence
    assert reopened.knowledge.resolve_evidence(evidence, actor) is not None


async def test_the_model_cites_a_document_found_by_knowledge_search(runtime_env, scripted_ollama):
    """End to end through a turn: knowledge_search finds the fact, memory_store cites it."""
    from tests.integration.test_agent_loop import CAPABILITIES, owner, run_turn

    _, runtime, _, docs, _ = runtime_env
    state, _ = scripted_ollama
    note = _write(docs / "zrazok.txt", "Срібло краще проводить електрику, ніж мідь.")
    who = owner(runtime, capabilities=CAPABILITIES)
    runtime.knowledge.index_document(note, who.actor)

    def cite_what_search_found(body):
        tool = [m for m in body["messages"] if m["role"] == "tool"][-1]
        hit = json.loads(tool["content"])["content"]["hits"][0]
        return {
            "tool_calls": [
                (
                    "memory_store",
                    {
                        "text": "Срібло проводить краще за мідь",
                        "document_evidence_ids": [hit["evidence_id"]],
                    },
                )
            ]
        }

    state["script"] = [
        {"tool_calls": [("knowledge_search", {"query": "срібло"})]},
        cite_what_search_found,
        {"content": "Запам'ятав. ГОТОВО"},
    ]
    result, _ = await run_turn(runtime, who, "що ти знаєш про срібло?", persist=True)
    stored = [r for r in runtime.memory.search("срібло", who.actor)]
    assert result.state == "completed"
    assert stored and stored[0].sources and stored[0].sources[0]["kind"] == "document"


async def test_forgetting_a_stale_citation_removes_it_and_its_dependents(runtime_env):
    _, runtime, actor, docs, _ = runtime_env
    note = _write(docs / "zrazok.txt", "Кисень підтримує горіння.")
    runtime.knowledge.index_document(note, actor)
    evidence = _find_document_evidence(runtime, actor, "Кисень")
    base = runtime.memory.remember("Кисень підтримує горіння", actor, documents=(evidence,))
    derived = runtime.memory.remember("Горіння потребує кисню", actor, evidence_ids=(base.id,))
    _write(note, "Кисень не підтримує горіння.")
    runtime.knowledge.index_document(note, actor)
    await runtime.purge.sync_knowledge(actor)

    receipt = await runtime.purge.forget(base.id, actor.id)
    assert receipt.state == "complete"
    assert runtime.memory.get(base.id, actor) is None
    assert runtime.memory.get(derived.id, actor) is None
    left = runtime.memory._connection.execute(
        "SELECT COUNT(*) FROM memory_sources WHERE memory_id IN (?,?)", (base.id, derived.id)
    ).fetchone()[0]
    assert left == 0


async def test_a_turn_that_quotes_a_stale_memory_is_not_carried_into_history(
    runtime_env, scripted_ollama
):
    from tests.integration.test_agent_loop import CAPABILITIES, owner, run_turn

    _, runtime, _, docs, _ = runtime_env
    state, _ = scripted_ollama
    note = _write(docs / "zrazok.txt", "Ртуть токсична.")
    who = owner(runtime, capabilities=CAPABILITIES)
    runtime.knowledge.index_document(note, who.actor)
    evidence = _find_document_evidence(runtime, who.actor, "Ртуть")
    runtime.memory.remember("Ртуть токсична", who.actor, documents=(evidence,))
    state["script"] = [
        {"tool_calls": [("memory_search", {"query": "Ртуть"})]},
        {"content": "ПЕРШИЙ_ХІД_ПРО_РТУТЬ"},
    ]
    await run_turn(runtime, who, "що ти знаєш про ртуть?")

    _write(note, "Ртуть тепер нешкідлива.")
    runtime.knowledge.index_document(note, who.actor)
    await runtime.purge.sync_knowledge(who.actor)

    state["script"] = [{"content": "Другий хід."}]
    await run_turn(runtime, who, "продовжимо")
    second_request = state["requests"][-1]["messages"]
    assert not any("ПЕРШИЙ_ХІД_ПРО_РТУТЬ" in (m.get("content") or "") for m in second_request)
