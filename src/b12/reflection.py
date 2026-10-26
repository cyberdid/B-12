"""Evidence-backed reflection: a cautious hypothesis, never a personality rewrite.

A reflection is a canonical memory of kind "reflection" whose evidence IDs must be
live memories of the same actor; MemoryStore's transitive purge then removes it with
its evidence. The deletion revision is captured before the model call, so a purge
during reflection rejects the late write. Hidden model reasoning is never stored.
"""

import asyncio
import json
import re
from uuid import uuid4

from b12.agent import _Active
from b12.model_errors import ModelError

PROMPT = (
    "Ти — модуль рефлексії B-12. Нижче спостереження з пам’яті (id: текст). "
    "Сформулюй ОДНУ обережну, перевірювану гіпотезу про власника або спільну роботу, "
    "спираючись лише на ці спостереження. Не вигадуй фактів. Відповідай тільки JSON: "
    '{"hypothesis": "...", "evidence_ids": ["id", ...]}'
)


class Reflector:
    def __init__(self, runtime):
        self.runtime = runtime

    def record(self, actor, hypothesis: str, evidence_ids, *, expected_revision: int):
        if not isinstance(hypothesis, str) or not 1 <= len(hypothesis.strip()) <= 600:
            raise ValueError("hypothesis size")
        evidence = tuple(dict.fromkeys(evidence_ids))
        resolver = self.runtime.agent.resolver
        if not evidence or not all(resolver.live(e, "memory", actor) for e in evidence):
            raise PermissionError("reflection requires live evidence in the actor namespace")
        return self.runtime.memory.remember(
            hypothesis.strip(),
            actor,
            kind="reflection",
            source="reflection",
            evidence_ids=evidence,
            expected_deletion_revision=expected_revision,
        )

    async def reflect(self, actor, *, limit: int = 8, cancel=None, timeout_s: float = 120):
        """One bounded reflection; returns a payload-free outcome dict."""
        if not actor.consent:
            return {"state": "skipped", "reason": "consent_required"}
        memory, agent = self.runtime.memory, self.runtime.agent
        revision = memory.deletion_revision(actor)
        observations = memory.recent(actor, limit=limit, exclude_kinds=("reflection",))
        if len(observations) < 2:
            return {"state": "skipped", "reason": "insufficient_evidence"}
        offered = {record.id for record in observations}
        lines = "\n".join(f"{r.id}: {r.text[:300]}" for r in observations)
        request = agent.builder.build(PROMPT, [{"role": "user", "content": lines}], [], [])
        # Registered as the actor's active work so a purge can cancel it promptly.
        active = _Active(actor.id, cancel or asyncio.Event())
        key = f"reflection-{uuid4()}"
        agent.active[key] = active
        try:
            async with agent.model_lock:
                reply = await agent.model.chat(request, cancel=active.cancel, deadline=None)
        except ModelError as exc:
            return {"state": "failed", "reason": exc.code}
        finally:
            active.done.set()
            agent.active.pop(key, None)
        if active.invalidated:
            return {"state": "failed", "reason": "cancelled"}
        match = re.search(r"\{.*\}", reply.content, re.S)
        try:
            data = json.loads(match.group(0)) if match else None
            hypothesis, cited = data["hypothesis"], data["evidence_ids"]
            if not isinstance(cited, list) or not set(cited) <= offered:
                raise ValueError("uncited or foreign evidence")
        except (TypeError, KeyError, ValueError):
            return {"state": "rejected", "reason": "invalid_output"}
        try:
            record = self.record(actor, hypothesis, cited, expected_revision=revision)
        except PermissionError:
            return {"state": "rejected", "reason": "stale_or_dead_evidence"}
        except ValueError:
            return {"state": "rejected", "reason": "invalid_output"}
        return {"state": "recorded", "memory_id": record.id, "evidence_ids": list(cited)}
