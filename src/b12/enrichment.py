"""Background category notes, so a fact is found by the general word a question uses.

"Which editor did we use?" never shares a word with "set up the Neovim environment", and
neither the semantic threshold nor asking the model to guess names at question time closes
that gap (measured 2026-11-12). Classifying a known fact is easier than recalling one: in
the background the model names 2-4 general category words for recent memories, and each
answer is stored as a derived memory that cites the original as evidence:

    "Категорії (програма, редактор): День 1: власник налаштував середовище Neovim."

The derived memory is ordinary, traceable memory: forgetting the original removes it
through the purge closure, consent is required, and nothing runs during a user's turn.
"""

from __future__ import annotations

import asyncio
import re
import time
from uuid import uuid4

from b12.model_errors import ModelError

KIND = "category"
PROMPT = (
    "Для кожного запису назви 3–4 українські слова-категорії для конкретних назв у ньому: "
    "спершу найточніший тип цієї речі (що саме це за програма, пристрій, напій чи місце), "
    "потім загальніші, щоб запис знаходився за загальним словом. "
    "Формат: номер: слово, слово. Без пояснень."
)
BATCH = 8
_LINE = re.compile(r"^\s*(\d{1,2})\s*[:.)]\s*(.+?)\s*$", re.M)
_WORD = re.compile(r"^[^\W\d_](?:[^\W\d_]|[ '’ʼ-]){1,29}$")


class Enricher:
    def __init__(self, runtime):
        self.runtime = runtime

    async def enrich(self, actor, *, cancel=None, timeout_s: float = 120) -> dict:
        """One bounded batch for this actor; returns a payload-free outcome."""
        if not actor.consent:
            return {"state": "skipped", "reason": "consent_required"}
        memory, agent = self.runtime.memory, self.runtime.agent
        revision = memory.deletion_revision(actor)
        done = memory.cited_by_kind(actor, KIND)
        candidates = [
            record
            for record in memory.recent(
                actor, limit=32, exclude_kinds=(KIND, "reflection", "goal_evidence")
            )
            if record.id not in done
        ][:BATCH]
        if not candidates:
            return {"state": "skipped", "reason": "nothing_new"}
        body = "\n".join(f"{i + 1}: {r.text[:300]}" for i, r in enumerate(candidates))
        request = agent.builder.build(PROMPT, [{"role": "user", "content": body}], [], [])
        from b12.agent import _Active

        active = _Active(actor.id, cancel or asyncio.Event())
        key = f"enrichment-{uuid4()}"
        agent.active[key] = active  # a purge can cancel it like any other work of the actor
        try:
            async with agent.model_lock:
                reply = await agent.model.chat(
                    request, cancel=active.cancel, deadline=time.monotonic() + timeout_s
                )
        except ModelError as exc:
            return {"state": "failed", "reason": exc.code}
        finally:
            active.done.set()
            agent.active.pop(key, None)
        if active.invalidated:
            return {"state": "failed", "reason": "cancelled"}
        recorded = []
        for number, rest in _LINE.findall(reply.content or ""):
            index = int(number) - 1
            if not 0 <= index < len(candidates):
                continue
            words = [
                w.strip(" .;\"'«»").lower() for w in rest.split(",") if w.strip(" .;\"'«»")
            ]
            words = list(dict.fromkeys(w for w in words if _WORD.match(w)))[:4]
            if not words:
                continue
            source = candidates[index]
            try:
                note = memory.remember(
                    f"Категорії ({', '.join(words)}): {source.text[:400]}",
                    actor,
                    kind=KIND,
                    source="enrichment",
                    evidence_ids=(source.id,),
                    expected_deletion_revision=revision,
                )
            except PermissionError:
                break  # something was forgotten meanwhile: retry on the next run
            except ValueError:
                continue  # the source stopped being live evidence
            recorded.append(note.id)
        return {"state": "recorded" if recorded else "rejected", "count": len(recorded)}
