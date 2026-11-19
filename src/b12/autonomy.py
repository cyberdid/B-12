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
STOP_POLL_S = 0.1  # how quickly an owner stop cancels a background turn in flight


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
        if getattr(rt.settings, "task_ledger", False):
            rt.control.link_task_goal(task, goal["id"], goal.get("plan_revision", 1))
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
        cancel = asyncio.Event()
        preempted_by: list[str] = []

        async def watch_owner_stop():
            # Owner stop halts background work already in flight, not only the next step;
            # a due goal of higher priority preempts it (the preempted goal yields and stays).
            while not cancel.is_set():
                if not rt.attention.execution_allowed(actor.id):
                    cancel.set()
                    return
                higher = [
                    g["id"]
                    for g in rt.goals.due(self.clock())
                    if g["id"] != goal["id"] and g["priority"] > goal["priority"]
                ]
                if higher:
                    preempted_by.append(higher[0])
                    cancel.set()
                    return
                await asyncio.sleep(STOP_POLL_S)

        watcher = asyncio.create_task(watch_owner_stop())
        try:
            result = await rt.agent.turn(
                goal["session_id"], grant, prompt, task_id=task, timeout_s=300, cancel=cancel
            )
        finally:
            watcher.cancel()
            await asyncio.gather(watcher, return_exceptions=True)
        now = self.clock()
        next_review = now + timedelta(seconds=goal["review_interval_s"])
        checkpoint = f"[{result.state}] {result.content}"[:4000]
        updated = rt.goals.checkpoint(
            goal["id"], actor.id, checkpoint, next_review, evidence_ids=result.evidence_ids
        )
        outcome = {
            "goal_id": goal["id"],
            "state": result.state,
            "error_code": result.error_code,
            "status": updated["status"],
        }
        if preempted_by:
            outcome["preempted_by"] = preempted_by[0]
        if result.state == "awaiting_approval":
            rt.goals.set_status(goal["id"], actor.id, "paused", "approval_pending")
            outcome["status"] = "paused"
        if getattr(rt.settings, "task_ledger", False) and rt.control.steps_needing_owner(
            goal["id"]
        ):
            # ADR-017: an effect whose outcome is unknown and cannot be checked is never
            # retried blindly; the goal waits for the owner.
            if rt.goals.get(goal["id"], actor.id)["status"] == "active":
                rt.goals.set_status(goal["id"], actor.id, "paused", "unknown_outcome_needs_owner")
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
        text = f"Ціль «{goal['intent'][:80]}»: {result.content[:600]}"
        if getattr(rt.settings, "initiative_gate", False):
            outcome.update(self._gated_proposal(goal, actor, result, text))
            return outcome
        decision = rt.attention.decide(actor.id)
        attention_id = rt.attention.record(actor.id, decision) if decision.allowed else None
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

    def _gated_proposal(self, goal, actor, result, text) -> dict:
        """ADR-018: a deterministic five-way decision instead of attention alone."""
        from b12.attention import Decision
        from b12.initiative import GateContext, InitiativeCandidate, decide

        rt, now = self.runtime, self.clock()
        effectful = any(
            effect.get("state") == "completed"
            for item in result.tool_results
            for effect in item.side_effects
        )
        new_evidence = set(result.evidence_ids) - set(goal["evidence_ids"])
        risk = "high" if result.state == "awaiting_approval" else "action" if effectful else "info"
        candidate = InitiativeCandidate(
            actor_id=actor.id,
            goal_id=goal["id"],
            trigger="goal_review",
            text=result.content or text,
            risk=risk,
            evidence_ids=tuple(result.evidence_ids),
            novel=effectful or bool(new_evidence) or result.state == "awaiting_approval",
        )
        current = rt.goals.get(goal["id"], actor.id)
        attention = rt.attention.decide(actor.id)
        context = GateContext(
            # A goal this run paused (budget, approval) or completed still reports; only a
            # goal the owner closed meanwhile is silent.
            goal_status="active"
            if current and current["status"] not in ("abandoned", "failed")
            else (current or {}).get("status"),
            evidence_live={
                e: bool(rt.agent.resolver.live(e, "memory", actor)) for e in result.evidence_ids
            },
            recent_keys=rt.goals.recent_proposal_keys(actor.id, now - timedelta(hours=24)),
            muted=rt.goals.is_muted(goal["id"]),
            attention_reason=attention.reason,
            attention_allowed=attention.allowed,
        )
        gate = decide(candidate, context, now)
        attention_id = None
        if gate.decision == "deliver":
            attention_id = rt.attention.record(actor.id, Decision(True, gate.reason, gate.urgent))
        proposal = rt.goals.add_proposal(
            actor.id,
            goal["id"],
            text,
            delivered=gate.decision == "deliver",
            reason=gate.reason,
            attention_id=attention_id,
            tags={**goal["tags"], **dict.fromkeys(result.evidence_ids, "memory")},
            decision=gate.decision,
            dedupe_key=gate.dedupe_key,
            not_before=gate.not_before,
            expires_at=gate.expires_at,
        )
        return {
            "proposal_id": proposal,
            "delivered": gate.decision == "deliver",
            "initiative_decision": gate.decision,
            "initiative_reason": gate.reason,
        }

    def redecide_deferred(self) -> list[dict]:
        """ADR-018: deferred proposals get one more attention decision once their window opens;
        after 48 h they expire unsaid."""
        from b12.attention import Decision

        rt, now, settled = self.runtime, self.clock(), []
        for actor_id in rt.control.actor_ids():
            for item in rt.goals.due_deferred(actor_id, now):
                if item["expires_at"] and datetime.fromisoformat(item["expires_at"]) <= now:
                    rt.goals.settle_proposal(
                        item["id"], decision="drop", reason="defer_expired", delivered=False
                    )
                    settled.append({"proposal_id": item["id"], "decision": "drop"})
                    continue
                attention = rt.attention.decide(actor_id)
                if attention.allowed:
                    attention_id = rt.attention.record(actor_id, Decision(True, "deferred"))
                    rt.goals.settle_proposal(
                        item["id"],
                        decision="deliver",
                        reason="deferred",
                        delivered=True,
                        attention_id=attention_id,
                    )
                    settled.append({"proposal_id": item["id"], "decision": "deliver"})
        return settled

    async def tick(self) -> list[dict]:
        outcomes, ran = [], set()
        if getattr(self.runtime.settings, "initiative_gate", False):
            outcomes.extend(self.redecide_deferred())
        while len(ran) < self.max_goals:
            # Re-read the due list each step: a goal that preempted the last one runs next.
            goal = next(
                (g for g in self.runtime.goals.due(self.clock()) if g["id"] not in ran), None
            )
            if goal is None:
                break
            ran.add(goal["id"])
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
            outcomes.append({"actor_id": actor_id, **await Reflector(rt).reflect(actor)})
            if getattr(rt.settings, "memory_enrichment", False):
                from b12.enrichment import Enricher

                enriched = await Enricher(rt).enrich(actor)
                outcomes.append({"actor_id": actor_id, "enrichment": enriched})
            # Marked only once the reflection has finished, so an interrupted run is not counted.
            rt.control.set_meta(key, now.isoformat())
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
