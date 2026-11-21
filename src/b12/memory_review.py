"""ADR-020 post-turn memory review: extract grounded explicit facts from recent turns."""

import asyncio
import json
import re
import time
from uuid import uuid4

from b12.agent import _Active
from b12.memory import DiskSpaceLow
from b12.model_errors import ModelError
from b12.reflection import GROUNDING

_ALLOWED_KINDS = frozenset({"fact", "preference", "decision"})
_MAX_TURNS = 6
_MAX_CANDIDATES = 5

PROMPT = (
    "Ти — модуль фонової рецензії пам’яті Capri. Нижче наведено нещодавні завершені ходи "
    "співрозмовника (turn_id, репліки user і assistant) та вже збережені факти. "
    "Виділи лише стійкі факти, вподобання або рішення, які співрозмовник прямо повідомив "
    "чи підтвердив і які ще не збережено в пам’яті."
    + GROUNDING
    + " Якщо нових фактів немає — поверни порожній список. "
    f"Не більше {_MAX_CANDIDATES} кандидатів на пакет. Ніколи не видаляй і не замінюй записи. "
    "Відповідай тільки JSON: "
    '{"candidates": [{"text": "...", "kind": "fact|preference|decision", "turn_id": "..."}]}'
)


def _parse_candidates(content: str, eligible_turn_ids: set[str]) -> list[dict] | None:
    raw = (content or "").strip()
    if not raw:
        return None
    data = None
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", raw, re.S)
        if match:
            try:
                data = json.loads(match.group(0))
            except json.JSONDecodeError:
                data = None
    if not isinstance(data, dict) or set(data) != {"candidates"}:
        return None
    items = data["candidates"]
    if not isinstance(items, list):
        return None
    parsed: list[dict] = []
    for item in items:
        if not isinstance(item, dict) or set(item) != {"text", "kind", "turn_id"}:
            return None
        text, kind, turn_id = item["text"], item["kind"], item["turn_id"]
        if (
            not isinstance(text, str)
            or not text.strip()
            or len(text.strip().encode()) > 8192
            or kind not in _ALLOWED_KINDS
            or not isinstance(turn_id, str)
            or turn_id not in eligible_turn_ids
        ):
            return None
        parsed.append({"text": text.strip(), "kind": kind, "turn_id": turn_id})
    return parsed[:_MAX_CANDIDATES]


class MemoryReviewer:
    def __init__(self, runtime):
        self.runtime = runtime

    def _is_goal_turn(self, turn_id: str) -> bool:
        control = self.runtime.control
        task_id = control.turn_task_id(turn_id)
        if task_id is not None and control.task_goal(task_id) is not None:
            return True
        return control.task_goal(turn_id) is not None

    def _is_tainted(self, turn: dict) -> bool:
        turn_id = turn["turn_id"]
        agent, control = self.runtime.agent, self.runtime.control
        if turn_id in getattr(agent, "_tainted", ()):
            return True
        if turn_id in getattr(agent, "_tainted_history", ()):
            return True
        if control.get_meta(f"tainted_turn:{turn_id}") == "1":
            return True
        for message in turn.get("messages", ()):
            if message.get("tool_name") in ("http_fetch", "web_search"):
                content = message.get("content")
                if isinstance(content, str):
                    try:
                        parsed = json.loads(content)
                    except ValueError:
                        return True
                    if isinstance(parsed, dict) and parsed.get("status") not in (
                        None,
                        "completed",
                    ):
                        continue
                return True
        return False

    @staticmethod
    def _format_batch(turns: list[dict], existing: list) -> str:
        sections: list[str] = []
        if existing:
            known = "\n".join(f"- {record.text[:200]}" for record in existing)
            sections.append(f"Вже збережені факти:\n{known}")
        turn_blocks: list[str] = []
        for turn in turns:
            lines = [f"turn_id={turn['turn_id']}"]
            for message in turn.get("messages", ()):
                role = message.get("role")
                content = (message.get("content") or "").strip()
                if role in ("user", "assistant") and content:
                    lines.append(f"{role}: {content[:1500]}")
            turn_blocks.append("\n".join(lines))
        sections.append("Ходи для рецензії:\n" + "\n\n".join(turn_blocks))
        return "\n\n".join(sections)

    async def review(self, actor, *, cancel=None, timeout_s: float = 120) -> dict:
        """Review up to 6 unreviewed interactive turns; never forgets or supersedes."""
        if not actor.consent:
            return {"state": "skipped", "reason": "consent_required"}
        control, sessions, memory, agent = (
            self.runtime.control,
            self.runtime.sessions,
            self.runtime.memory,
            self.runtime.agent,
        )
        cursor_key = f"memory_review:{actor.id}"
        raw_cursor = control.get_meta(cursor_key)
        try:
            after_sequence = int(raw_cursor) if raw_cursor is not None else 0
        except ValueError:
            after_sequence = 0

        turns = sessions.turns_since(
            actor.id,
            after_sequence=after_sequence,
            limit=_MAX_TURNS,
            live=lambda eid, kind: agent.resolver.live(eid, kind, actor),
        )
        if not turns:
            return {"state": "skipped", "reason": "no_turns"}
        last_sequence = turns[-1]["sequence"]

        candidate_turns = [
            turn
            for turn in turns
            if not self._is_goal_turn(turn["turn_id"]) and not self._is_tainted(turn)
        ]
        if not candidate_turns:
            control.set_meta(cursor_key, str(last_sequence))
            return {"state": "skipped", "reason": "no_turns"}

        eligible_turn_ids = {turn["turn_id"] for turn in candidate_turns}
        existing = memory.recent(actor, limit=12, exclude_kinds=("reflection", "category"))
        body = self._format_batch(candidate_turns, existing)

        rev = memory.deletion_revision(actor)
        try:
            request = agent.builder.build(PROMPT, [{"role": "user", "content": body}], [], [])
        except ModelError as exc:
            return {"state": "failed", "reason": exc.code}

        active = _Active(actor.id, cancel or asyncio.Event())
        key = f"memory_review-{uuid4()}"
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

        candidates = _parse_candidates(reply.content, eligible_turn_ids)
        if candidates is None:
            return {"state": "rejected", "reason": "invalid_output"}
        if not candidates:
            control.set_meta(cursor_key, str(last_sequence))
            return {"state": "skipped", "reason": "no_candidates", "count": 0}

        if active.invalidated or memory.deletion_revision(actor) != rev:
            return {"state": "rejected", "reason": "stale_deletion_revision"}

        memory_ids: list[str] = []
        skipped_duplicates = 0
        for item in candidates[:_MAX_CANDIDATES]:
            if memory.find_duplicate(item["text"], actor) is not None:
                skipped_duplicates += 1
                continue
            try:
                record = memory.remember(
                    item["text"],
                    actor,
                    kind=item["kind"],
                    source="post_turn_review",
                    origin="explicit",
                    source_locator=f"turn:{item['turn_id']}",
                    expected_deletion_revision=rev,
                )
            except PermissionError:
                return {"state": "rejected", "reason": "stale_deletion_revision"}
            except DiskSpaceLow:
                return {"state": "failed", "reason": "disk_space_low"}
            memory_ids.append(record.id)

        control.set_meta(cursor_key, str(last_sequence))
        if not memory_ids:
            return {
                "state": "skipped",
                "reason": "duplicate",
                "count": 0,
                "skipped_duplicates": skipped_duplicates,
            }
        return {
            "state": "recorded",
            "reason": "recorded",
            "memory_ids": memory_ids,
            "count": len(memory_ids),
            "skipped_duplicates": skipped_duplicates,
        }
