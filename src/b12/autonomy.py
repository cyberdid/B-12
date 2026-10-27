"""Single idle scheduler: bounded goal turns, verified completion, gated proposals.

One scheduler per state directory (exclusive flock). Each tick runs at most
`max_goals_per_tick` due goals, never for an actor with an in-flight user turn or
an owner stop. Every background turn consumes goal budget before the next review.
"achieved" comes only from a trusted check plus a live evidence memory. Proposals
are always recorded; whether they are delivered (spoken/shown) is the attention
policy's decision, so quiet mode silences speech without pausing execution.
"""

import asyncio
import fcntl
import logging
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path

from b12.auth import owner_capabilities

log = logging.getLogger(__name__)


def _clock():
    return datetime.now(UTC)


def check_passes(spec: dict) -> bool:
    """Trusted deterministic acceptance checks; the model cannot define new kinds."""
    if spec["kind"] == "file_contains":
        path = Path(spec["path"])
        try:
            return path.is_file() and spec["text"] in path.read_text(errors="replace")
        except OSError:
            return False
    return False


class SchedulerLocked(RuntimeError):
    pass


class Scheduler:
    def __init__(
        self,
        runtime,
        *,
        clock=_clock,
        max_goals_per_tick: int = 2,
        reflection_interval_s: float = 6 * 3600,
    ):
        self.runtime, self.clock, self.max_goals = runtime, clock, max_goals_per_tick
        self.reflection_interval = timedelta(seconds=reflection_interval_s)
        path = runtime.settings.state_dir / "scheduler.lock"
        self._lock = os.open(path, os.O_CREAT | os.O_RDWR, 0o600)
        try:
            fcntl.flock(self._lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            os.close(self._lock)
            raise SchedulerLocked("another scheduler owns this state directory") from None

    def close(self):
        if self._lock is not None:
            fcntl.flock(self._lock, fcntl.LOCK_UN)
            os.close(self._lock)
            self._lock = None

    def _busy(self, actor_id: str) -> bool:
        return any(item.actor_id == actor_id for item in self.runtime.agent.active.values())

    async def run_goal(self, goal: dict) -> dict:
        rt = self.runtime
        actor = rt.control.resolve_actor(goal["actor_id"])
        if not rt.attention.execution_allowed(actor.id):
            return {"goal_id": goal["id"], "state": "skipped", "reason": "owner_stop"}
        if self._busy(actor.id):
            return {"goal_id": goal["id"], "state": "skipped", "reason": "user_active"}
        owner_caps = set(owner_capabilities(rt.settings))
        caps = tuple(sorted(set(goal["allowed_tools"]) & owner_caps)) or ("time.read",)
        task = rt.control.create_task(goal["session_id"])
        grant = rt.control.issue_grant(
            actor.id,
            goal["session_id"],
            caps,
            task_id=task,
            ttl_s=900,
            full_execution=False,  # unattended turns never get shell without approval
        )
        prompt = (
            f"Фонова ціль власника: {goal['intent']}\n"
            f"Критерії успіху: {goal['criteria']}\n"
            f"Попередній checkpoint: {goal['checkpoint'] or 'немає'}\n"
            "Зроби один наступний перевірюваний крок інструментами, якщо потрібно, "
            "і коротко звітуй: що зроблено, що перевірено, що далі."
        )
        result = await rt.agent.turn(goal["session_id"], grant, prompt, task_id=task, timeout_s=300)
        now = self.clock()
        next_review = now + timedelta(seconds=goal["review_interval_s"])
        checkpoint = f"[{result.state}] {result.content}"[:4000]
        updated = rt.goals.checkpoint(goal["id"], actor.id, checkpoint, next_review)
        outcome = {
            "goal_id": goal["id"],
            "state": result.state,
            "error_code": result.error_code,
            "status": updated["status"],
        }
        if result.state == "awaiting_approval":
            rt.goals.set_status(goal["id"], actor.id, "paused", "approval_pending")
            outcome["status"] = "paused"
        if goal["check_spec"] and check_passes(goal["check_spec"]) and actor.consent:
            evidence = rt.memory.remember(
                f"Перевірку цілі {goal['id']} ({goal['check_spec']['kind']}) пройдено.",
                actor,
                kind="goal_evidence",
                source="autonomy:check",
            )
            rt.goals.complete(
                goal["id"],
                actor,
                [evidence.id],
                lambda e: rt.agent.resolver.live(e, "memory", actor),
            )
            outcome["status"] = "achieved"
        decision = rt.attention.decide(actor.id)
        attention_id = rt.attention.record(actor.id, decision) if decision.allowed else None
        text = f"Ціль «{goal['intent'][:80]}»: {result.content[:600]}"
        outcome["proposal_id"] = rt.goals.add_proposal(
            actor.id,
            goal["id"],
            text,
            delivered=decision.allowed,
            reason=decision.reason,
            attention_id=attention_id,
            tags={**goal["tags"], **dict.fromkeys(result.evidence_ids, "memory")},
        )
        outcome["delivered"] = decision.allowed
        return outcome

    async def tick(self) -> list[dict]:
        outcomes = []
        for goal in self.runtime.goals.due(self.clock())[: self.max_goals]:
            try:
                outcomes.append(await self.run_goal(goal))
            except Exception:
                log.exception("background goal failed")
                self.runtime.goals.set_status(
                    goal["id"], goal["actor_id"], "failed", "scheduler_error"
                )
                outcomes.append({"goal_id": goal["id"], "state": "failed"})
        return outcomes

    async def reflect_idle(self) -> list[dict]:
        """At most one reflection per consented, idle, non-stopped actor per interval."""
        from b12.reflection import Reflector

        rt, now, outcomes = self.runtime, self.clock(), []
        for actor_id in rt.control.actor_ids():
            actor = rt.control.resolve_actor(actor_id)
            key = f"last_reflection:{actor_id}"
            last = rt.control.get_meta(key)
            if (
                not actor.consent
                or self._busy(actor_id)
                or not rt.attention.execution_allowed(actor_id)
                or (last and now - datetime.fromisoformat(last) < self.reflection_interval)
            ):
                continue
            rt.control.set_meta(key, now.isoformat())
            outcomes.append({"actor_id": actor_id, **await Reflector(rt).reflect(actor)})
        return outcomes

    async def run(self, stop: asyncio.Event):
        while not stop.is_set():
            await self.tick()
            try:
                await self.reflect_idle()
            except Exception:
                log.exception("idle reflection failed")
            try:
                await asyncio.wait_for(stop.wait(), self.runtime.settings.scheduler_tick_s)
            except TimeoutError:
                pass
