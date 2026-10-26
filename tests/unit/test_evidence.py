from uuid import uuid4

from b12.contracts import Actor


def test_memory_liveness_follows_tombstones_and_actor_scope(tmp_path):
    from b12.evidence import EvidenceResolver
    from b12.memory import MemoryStore

    actor, other = Actor(id="owner", consent=True), Actor(id="guest", consent=True)
    memory = MemoryStore(tmp_path / "memory.sqlite3")
    record = memory.remember("тестовий факт", actor)
    resolver = EvidenceResolver(memory)
    assert resolver.live(record.id, "memory", actor)
    assert not resolver.live(record.id, "memory", other)
    assert not resolver.live("not-a-uuid", "memory", actor)
    receipt = memory.begin_purge(record.id, actor, stores=("canonical", "sessions"))
    assert not resolver.live(record.id, "memory", actor)
    assert memory.purge_receipt(receipt.operation_id, actor) == receipt
    memory.close()


def test_document_liveness_follows_current_revision(tmp_path):
    from b12.evidence import EvidenceResolver
    from b12.memory import MemoryStore
    from b12.retrieval import KnowledgeIndex

    actor = Actor(id="owner", consent=True)
    memory = MemoryStore(tmp_path / "memory.sqlite3")
    knowledge = KnowledgeIndex(tmp_path / "knowledge")
    source = tmp_path / "note.txt"
    source.write_text("Синтетична нотатка про калібрування мікрофона")
    knowledge.index_document(source, actor)
    hit = knowledge.search("калібрування", actor)[0]
    resolver = EvidenceResolver(memory, knowledge)
    assert resolver.live(hit["evidence_id"], "document", actor)
    assert not resolver.live(hit["evidence_id"], "document", Actor(id="owner", consent=False))
    knowledge.remove_document(source, actor)
    assert not resolver.live(hit["evidence_id"], "document", actor)
    assert resolver.live(str(uuid4()), "tool_result", actor)
    assert not resolver.live(str(uuid4()), "invented", actor)
    knowledge.close()
    memory.close()
