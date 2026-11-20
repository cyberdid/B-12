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
import hashlib
import logging
import os
import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import urlsplit

import httpx

from b12.agent import extract_goal_blocked_reason
from b12.auth import owner_capabilities
from b12.tools.network import host_allowed
from b12.tools.process import reaches_network

log = logging.getLogger(__name__)
STOP_POLL_S = 0.1  # how quickly an owner stop cancels a background turn in flight


def _clock():
    return datetime.now(UTC)


def run_check(
    spec: dict,
    settings=None,
    *,
    goal_check_commands: tuple[tuple[str, ...], ...] | None = None,
    network_allow: tuple[str, ...] | None = None,
) -> tuple[bool, str]:
    """Trusted deterministic acceptance checks; returns (passed, bounded output tail)."""
    kind = spec.get("kind")
    if kind == "file_contains":
        path = Path(spec["path"])
        try:
            if not path.is_file():
                return False, "file missing"
            ok = spec["text"] in path.read_text(errors="replace")
            return ok, "" if ok else "expected text not found"
        except OSError as exc:
            return False, f"file_error: {type(exc).__name__}"
    if kind == "file_sha256":
        path = Path(spec["path"])
        expected = str(spec["sha256"]).strip().lower()
        try:
            if not path.is_file():
                return False, "file missing"
            with path.open("rb") as handle:
                actual = hashlib.file_digest(handle, "sha256").hexdigest()
            ok = actual == expected
            return ok, "" if ok else f"sha256 mismatch: got {actual}, expected {expected}"
        except OSError as exc:
            return False, f"file_error: {type(exc).__name__}"
    if kind == "command_exit_zero":
        argv = spec.get("argv")
        commands = (
            goal_check_commands
            if goal_check_commands is not None
            else (getattr(settings, "goal_check_commands", ()) if settings is not None else ())
        )
        if (
            not isinstance(argv, (list, tuple))
            or not argv
            or not all(isinstance(arg, str) for arg in argv)
        ):
            return False, "invalid_command"
        if tuple(argv) not in commands:
            return False, "command_not_allowlisted"
        if reaches_network({"executable": argv[0], "argv": list(argv[1:])}):
            return False, "network_denied"
        try:
            proc = subprocess.run(
                list(argv),
                timeout=60,
                shell=False,
                capture_output=True,
                text=True,
                stdin=subprocess.DEVNULL,
                env={"PATH": os.defpath, "LANG": "C.UTF-8"},
            )
        except (subprocess.TimeoutExpired, OSError) as exc:
            return False, f"command_error: {type(exc).__name__}"
        tail = "\n".join(
            part for part in ((proc.stdout or "").strip(), (proc.stderr or "").strip()) if part
        )[-400:]
        return proc.returncode == 0, tail or f"exit_code={proc.returncode}"
    if kind == "http_status":
        url = spec.get("url")
        expected_status = spec.get("status")
        allow = (
            network_allow
            if network_allow is not None
            else (getattr(settings, "network_allow", ()) if settings is not None else ())
        )
        if not isinstance(url, str) or any(ord(c) < 32 or ord(c) == 127 for c in url):
            return False, "invalid_url"
        parsed = urlsplit(url)
        if (
            parsed.scheme not in ("http", "https")
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
            or parsed.fragment
        ):
            return False, "invalid_url"
        if not host_allowed(parsed.hostname, allow):
            return False, "network_denied"
        try:
            with httpx.Client(trust_env=False, follow_redirects=False, timeout=10.0) as client:
                reply = client.get(url)
        except (httpx.HTTPError, ValueError) as exc:
            return False, f"http_error: {type(exc).__name__}"
        return reply.status_code == expected_status, f"http_status={reply.status_code}"
    return False, "unsupported_check"


def check_passes(
    spec: dict,
    settings=None,
    *,
    goal_check_commands: tuple[tuple[str, ...], ...] | None = None,
    network_allow: tuple[str, ...] | None = None,
) -> bool:
    """Trusted deterministic acceptance checks; the model cannot define new kinds."""
    return run_check(
        spec,
        settings,
        goal_check_commands=goal_check_commands,
        network_allow=network_allow,
    )[0]


_ORIGINAL_CHECK_PASSES = check_passes


def _eval_check(spec: dict, settings) -> tuple[bool, str]:
    if check_passes is _ORIGINAL_CHECK_PASSES:
        return run_check(spec, settings)
    return bool(check_passes(spec)), ""


def _complete_goal_from_check(rt, goal, actor, check_spec, tail: str = "") -> str | None:
    if not actor.consent:
        return None
    note = f"Перевірку цілі {goal['id']} ({check_spec['kind']}) пройдено."
    if tail:
        note += f" ({tail})"
    evidence = rt.memory.remember(note, actor, kind="goal_evidence", source="autonomy:check")
    rt.goals.complete(
        goal["id"],
        actor,
        [evidence.id],
        lambda e: rt.agent.resolver.live(e, "memory", actor),
    )
    return evidence.id


def _record_ungated_proposal(
    rt,
    goal,
    actor,
    text,
    evidence_ids,
    *,
    force_needs_owner: bool = False,
    pause_reason: str | None = None,
) -> dict:
    tags = {**goal["tags"], **dict.fromkeys(evidence_ids, "memory")}
    if force_needs_owner:
        proposal_id = rt.goals.add_proposal(
            actor.id,
            goal["id"],
            text,
            delivered=False,
            reason=pause_reason or "needs_owner",
            attention_id=None,
            tags=tags,
            decision="needs_owner",
        )
        return {
            "proposal_id": proposal_id,
            "delivered": False,
            "initiative_decision": "needs_owner",
        }
    decision = rt.attention.decide(actor.id)
    attention_id = rt.attention.record(actor.id, decision) if decision.allowed else None
    proposal_id = rt.goals.add_proposal(
        actor.id,
        goal["id"],
        text,
        delivered=decision.allowed,
        reason=decision.reason,
        attention_id=attention_id,
        tags=tags,
    )
    return {"proposal_id": proposal_id, "delivered": decision.allowed}


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
        goal_contract = getattr(rt.settings, "goal_contract", False)
        contract = goal.get("contract") or {}
        check_spec = goal.get("check_spec")
        if check_spec is None and goal_contract and isinstance(contract.get("verification"), dict):
            check_spec = contract["verification"]
        if (
            not goal_contract
            and check_spec is not None
            and check_spec.get("kind") != "file_contains"
        ):
            check_spec = None

        pre_tail = ""
        if goal_contract and check_spec is not None:
            passed, pre_tail = await asyncio.to_thread(_eval_check, check_spec, rt.settings)
            if passed:
                rt.goals.record_check(goal["id"], True, actor_id=actor.id)
                evidence_id = _complete_goal_from_check(rt, goal, actor, check_spec, pre_tail)
                evidence_ids = (evidence_id,) if evidence_id else ()
                text = f"Ціль «{goal['intent'][:80]}»: перевірку {check_spec['kind']} пройдено."
                outcome = {
                    "goal_id": goal["id"],
                    "state": "completed",
                    "error_code": None,
                    "status": "achieved" if evidence_id else goal["status"],
                }
                synthetic = SimpleNamespace(
                    state="completed",
                    content=text,
                    tool_results=(),
                    evidence_ids=evidence_ids,
                )
                if getattr(rt.settings, "initiative_gate", False):
                    outcome.update(self._gated_proposal(goal, actor, synthetic, text))
                else:
                    outcome.update(_record_ungated_proposal(rt, goal, actor, text, evidence_ids))
                return outcome

        owner_caps = set(owner_capabilities(rt.settings))
        caps = tuple(sorted(set(goal["allowed_tools"]) & owner_caps)) or ("time.read",)
        task = rt.control.create_task(goal["session_id"])
        if getattr(rt.settings, "task_ledger", False) or goal_contract:
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
        )
        if pre_tail:
            prompt += f"Попередня перевірка не пройдена: {pre_tail}\n"
        if goal_contract and contract:
            prompt += (
                "Якщо виконано умову зупинки (stop_when) або прогрес неможливий без власника, "
                "почни відповідь із `[GOAL_BLOCKED] <причина>`.\n"
            )
        prompt += (
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
                goal["session_id"],
                grant,
                prompt,
                task_id=task,
                timeout_s=300,
                cancel=cancel,
                _manage_goal_block=False,
            )
        finally:
            watcher.cancel()
            await asyncio.gather(watcher, return_exceptions=True)
        now = self.clock()
        next_review = now + timedelta(seconds=goal["review_interval_s"])
        checkpoint = f"[{result.state}] {result.content}"[:4000]
        blocked_reason = extract_goal_blocked_reason(result.content) if goal_contract else None
        force_needs_owner = False
        pause_reason = None
        post_check: tuple[bool, str, int] | None = None
        if (
            goal_contract
            and check_spec is not None
            and blocked_reason is None
            and result.state not in ("cancelled", "awaiting_approval")
            and not (
                getattr(rt.settings, "task_ledger", False)
                and rt.control.steps_needing_owner(goal["id"])
            )
        ):
            passed, tail = await asyncio.to_thread(_eval_check, check_spec, rt.settings)
            streak = rt.goals.record_check(goal["id"], passed, actor_id=actor.id)
            post_check = (passed, tail, streak)
            if not passed and tail:
                checkpoint = f"{checkpoint}\n[перевірка не пройдена ({streak}/3)] {tail}"[:4000]

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
        if blocked_reason is not None:
            status_reason = (
                f"needs_owner: {blocked_reason}"[:200] if blocked_reason else "needs_owner"
            )
            rt.goals.set_status(goal["id"], actor.id, "paused", status_reason)
            outcome["status"] = "paused"
            force_needs_owner = True
            pause_reason = status_reason
        elif post_check is not None:
            passed, tail, streak = post_check
            if passed and _complete_goal_from_check(rt, goal, actor, check_spec, tail):
                outcome["status"] = "achieved"
            elif not passed and streak >= 3:
                rt.goals.set_status(goal["id"], actor.id, "paused", "check_failed_3x")
                outcome["status"] = "paused"
                outcome["failure_streak"] = streak
                force_needs_owner = True
                pause_reason = "check_failed_3x"
        elif (
            not goal_contract
            and check_spec
            and check_passes(check_spec)
            and _complete_goal_from_check(rt, goal, actor, check_spec)
        ):
            outcome["status"] = "achieved"
        text = f"Ціль «{goal['intent'][:80]}»: {result.content[:600]}"
        if getattr(rt.settings, "initiative_gate", False):
            outcome.update(
                self._gated_proposal(
                    goal,
                    actor,
                    result,
                    text,
                    force_needs_owner=force_needs_owner,
                    pause_reason=pause_reason,
                )
            )
            return outcome
        outcome.update(
            _record_ungated_proposal(
                rt,
                goal,
                actor,
                text,
                result.evidence_ids,
                force_needs_owner=force_needs_owner,
                pause_reason=pause_reason,
            )
        )
        return outcome

    def _gated_proposal(
        self, goal, actor, result, text, *, force_needs_owner: bool = False, pause_reason=None
    ) -> dict:
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
        needs_owner = force_needs_owner or result.state == "awaiting_approval"
        risk = "high" if needs_owner else "action" if effectful else "info"
        candidate_text = result.content or text
        if pause_reason and pause_reason not in candidate_text:
            candidate_text = f"[{pause_reason}] {candidate_text}"
        candidate = InitiativeCandidate(
            actor_id=actor.id,
            goal_id=goal["id"],
            trigger="goal_review",
            text=candidate_text,
            risk=risk,
            evidence_ids=tuple(result.evidence_ids),
            novel=effectful or bool(new_evidence) or needs_owner,
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
