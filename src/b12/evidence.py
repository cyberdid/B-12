"""Shared evidence liveness before context, history or reflection use.

Canonical memory and current document revisions are checked against their stores.
tool_result references live exactly as long as the session turn that holds them.
"""

from b12.contracts import Actor


class EvidenceResolver:
    def __init__(self, memory, knowledge=None):
        self.memory, self.knowledge = memory, knowledge

    def live(self, evidence_id: str, kind: str, actor: Actor) -> bool:
        if kind == "memory":
            return self.memory.is_live(evidence_id, actor)
        if kind == "document":
            if self.knowledge is None or not actor.consent:
                return False
            return self.knowledge.resolve_evidence(evidence_id, actor) is not None
        return kind == "tool_result"
