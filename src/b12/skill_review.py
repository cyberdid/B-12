"""Background skill review (spec 2026-11-24-skill-review-design.md): stage learned procedures.

An idle pass over finished interactive turns, mirroring the ADR-020 memory review: one bounded
model call per batch, strict JSON, and every result goes to the ADR-021 approval queue through
`SkillStore.propose`. It never writes SKILL.md, never deletes or archives.
"""

import asyncio
import json
import re
import time
from uuid import uuid4

from b12.agent import _Active
from b12.memory_review import MemoryReviewer
from b12.model_errors import ModelError
from b12.skills import validate_frontmatter

_MAX_TURNS = 6
_MAX_SKILLS = 2
_KEYS = {"name", "description", "body", "turn_id"}
_SKILL_TEXT_EACH = 2000  # characters of one skill shown to the review
_SKILL_TEXT_BUDGET = 6000  # characters of all skills shown to the review

PROMPT = (
    "Ти — модуль фонової рецензії навичок Capri. Нижче наведено нещодавні завершені ходи "
    "власника (turn_id, репліки user і assistant) та поточний текст уже наявних навичок. "
    "Знайди лише процедури, які варто повторювати: щонайменше два кроки, і власник сам їх "
    "описав або підтвердив, що вони спрацювали. Кожну оформи як навичку: кроки з конкретними "
    "налаштуваннями й командами; пастка — це правило і одне речення «чому», прив'язане до кроку; "
    "без дат, номерів інцидентів і цитат. Не є навичкою: разовий факт, невдала чи ще не вдала "
    "спроба, здогадка, порада без підтвердження власника. Якщо процедура стосується наявної "
    "навички, використай ту саму назву й напиши повний оновлений текст, зберігши незмінні "
    "кроки. Назва — латиницею: малі літери, цифри, дефіс; опис — до 60 символів. Якщо не "
    f"впевнений — поверни порожній список. Не більше {_MAX_SKILLS} навичок на пакет. "
    "Відповідай тільки JSON: "
    '{"skills": [{"name": "...", "description": "...", "body": "...", "turn_id": "..."}]}'
)


def _parse_skills(content: str, eligible_turn_ids: set[str]) -> list[dict] | None:
    """Return the proposed skills, or None when the reply breaks the contract."""
    raw = (content or "").strip()
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", raw, re.S)
        try:
            data = json.loads(match.group(0)) if match else None
        except json.JSONDecodeError:
            data = None
    if (
        not isinstance(data, dict)
        or set(data) != {"skills"}
        or not isinstance(data["skills"], list)
    ):
        return None
    parsed = []
    for item in data["skills"]:
        if (
            not isinstance(item, dict)
            or set(item) != _KEYS
            or not all(isinstance(item[k], str) and item[k].strip() for k in _KEYS)
            or item["turn_id"] not in eligible_turn_ids
        ):
            return None
        parsed.append({k: item[k].strip() for k in _KEYS})
    return parsed


class SkillReviewer(MemoryReviewer):
    """Reuses the memory review's goal and network-taint exclusions."""

    def _format_skill_batch(self, turns: list[dict]) -> str:
        """Turns plus the current skills: names for matching, and their text, so an update can
        keep the unchanged steps (gemma4:12b dropped them seeing only the index, M116)."""
        store = self.runtime.skills
        sections, budget = [], _SKILL_TEXT_BUDGET
        for item in store.index(limit=20):
            try:
                text = store.view(item["name"], "")
            except (ValueError, OSError, UnicodeDecodeError):
                continue
            text = text[:_SKILL_TEXT_EACH]
            if len(text) > budget:
                break
            budget -= len(text)
            sections.append(f"--- навичка {item['name']} ---\n{text.strip()}")
        known = "Наявні навички (поточний текст):\n" + "\n\n".join(sections) if sections else ""
        body = self._format_batch(turns, [])
        return f"{known}\n\n{body}" if known else body

    async def review(self, actor, *, cancel=None, timeout_s: float = 120) -> dict:
        rt = self.runtime
        settings = rt.settings
        if not (settings.skills and settings.skill_review and rt.skills is not None):
            return {"state": "skipped", "reason": "skills_off"}
        if not actor.consent:
            return {"state": "skipped", "reason": "consent_required"}
        control, memory, agent = rt.control, rt.memory, rt.agent
        cursor_key = f"skill_review:{actor.id}"
        try:
            after_sequence = int(control.get_meta(cursor_key) or 0)
        except ValueError:
            after_sequence = 0
        turns = rt.sessions.turns_since(
            actor.id,
            after_sequence=after_sequence,
            limit=_MAX_TURNS,
            live=lambda eid, kind: agent.resolver.live(eid, kind, actor),
        )
        if not turns:
            return {"state": "skipped", "reason": "no_turns"}
        last_sequence = turns[-1]["sequence"]
        candidate_turns = [
            t for t in turns if not self._is_goal_turn(t["turn_id"]) and not self._is_tainted(t)
        ]
        if not candidate_turns:
            control.set_meta(cursor_key, str(last_sequence))
            return {"state": "skipped", "reason": "no_turns"}
        sessions_by_turn = {t["turn_id"]: t.get("session_id") for t in candidate_turns}

        rev = memory.deletion_revision(actor)
        try:
            request = agent.builder.build(
                PROMPT,
                [{"role": "user", "content": self._format_skill_batch(candidate_turns)}],
                [],
                [],
            )
        except ModelError as exc:
            return {"state": "failed", "reason": exc.code}
        active = _Active(actor.id, cancel or asyncio.Event())
        key = f"skill_review-{uuid4()}"
        agent.active[key] = active
        try:
            async with agent.model_lock:
                reply = await agent.model.chat(
                    request, cancel=active.cancel, deadline=time.monotonic() + timeout_s
                )
        except ModelError as exc:
            if active.invalidated or memory.deletion_revision(actor) != rev:
                return {"state": "rejected", "reason": "stale_deletion_revision"}
            return {"state": "failed", "reason": exc.code}
        finally:
            active.done.set()
            agent.active.pop(key, None)
        if active.invalidated or memory.deletion_revision(actor) != rev:
            return {"state": "rejected", "reason": "stale_deletion_revision"}
        if active.cancel.is_set():
            return {"state": "failed", "reason": "cancelled"}

        skills = _parse_skills(reply.content, set(sessions_by_turn))
        if skills is None:
            return {"state": "rejected", "reason": "invalid_output"}
        if not skills:
            control.set_meta(cursor_key, str(last_sequence))
            return {"state": "skipped", "reason": "no_candidates"}

        pending_names = {item.get("name") for item in rt.skills.list_pending()}
        pending_ids, names = [], []
        for item in skills[:_MAX_SKILLS]:
            if item["name"] in pending_names:
                continue
            text = (
                f"---\nname: {item['name']}\ndescription: {item['description']}\n---\n"
                f"{item['body']}\n"
            )
            if validate_frontmatter(text) is None:
                continue
            try:
                pending_ids.append(
                    rt.skills.propose(
                        item["name"],
                        text,
                        turn_id=item["turn_id"],
                        session_id=sessions_by_turn[item["turn_id"]],
                        actor_id=actor.id,
                    )
                )
            except ValueError:
                continue
            names.append(item["name"])
            pending_names.add(item["name"])
        control.set_meta(cursor_key, str(last_sequence))
        if not pending_ids:
            return {"state": "skipped", "reason": "duplicate"}
        return {"state": "staged", "pending_ids": pending_ids, "names": names, "count": len(names)}
