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
from b12.schedules import catchup_window
from b12.tools.network import host_allowed
from b12.tools.process import reaches_network

log = logging.getLogger(__name__)
STOP_POLL_S = 0.1  # how quickly an owner stop cancels a background turn in flight
_TRANSPORT_ERROR_CODES = frozenset({"transport_error", "transport_timeout", "http_error"})


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
        rt = self.runtime
        current = rt.goals.get(goal["id"], actor.id)
        # A goal this run paused (budget, approval) or completed still reports; only a
        # goal the owner closed meanwhile is silent.
        goal_status = (
            "active"
            if current and current["status"] not in ("abandoned", "failed")
            else (current or {}).get("status")
        )
        return self._gate_candidate(
            actor=actor,
            goal_id=goal["id"],
            goal_status=goal_status,
            known_evidence=set(goal["evidence_ids"]),
            tags=goal["tags"],
            result=result,
            text=text,
            force_needs_owner=force_needs_owner,
            pause_reason=pause_reason,
        )

    def _gate_candidate(
        self,
        *,
        actor,
        goal_id: str,
        goal_status: str | None,
        known_evidence: set[str],
        tags: dict,
        result,
        text: str,
        always_novel: bool = False,
        force_high_risk: bool = False,
        force_needs_owner: bool = False,
        pause_reason: str | None = None,
    ) -> dict:
        """ADR-018: run InitiativeCandidate through initiative.decide and store proposal."""
        from b12.attention import Decision
        from b12.initiative import GateContext, InitiativeCandidate, decide

        rt, now = self.runtime, self.clock()
        effectful = any(
            effect.get("state") == "completed"
            for item in result.tool_results
            for effect in item.side_effects
        )
        new_evidence = set(result.evidence_ids) - known_evidence
        needs_owner = force_high_risk or force_needs_owner or result.state == "awaiting_approval"
        risk = "high" if needs_owner else "action" if effectful else "info"
        candidate_text = result.content or text
        if pause_reason and pause_reason not in candidate_text:
            candidate_text = f"[{pause_reason}] {candidate_text}"
        candidate = InitiativeCandidate(
            actor_id=actor.id,
            goal_id=goal_id,
            trigger="goal_review",
            text=candidate_text,
            risk=risk,
            evidence_ids=tuple(result.evidence_ids),
            novel=always_novel or effectful or bool(new_evidence) or needs_owner,
        )
        attention = rt.attention.decide(actor.id)
        context = GateContext(
            goal_status=goal_status,
            evidence_live={
                e: bool(rt.agent.resolver.live(e, "memory", actor)) for e in result.evidence_ids
            },
            recent_keys=rt.goals.recent_proposal_keys(actor.id, now - timedelta(hours=24)),
            muted=rt.goals.is_muted(goal_id),
            attention_reason=attention.reason,
            attention_allowed=attention.allowed,
        )
        gate = decide(candidate, context, now)
        attention_id = None
        if gate.decision == "deliver":
            attention_id = rt.attention.record(actor.id, Decision(True, gate.reason, gate.urgent))
        proposal = rt.goals.add_proposal(
            actor.id,
            goal_id,
            text,
            delivered=gate.decision == "deliver",
            reason=gate.reason,
            attention_id=attention_id,
            tags={**tags, **dict.fromkeys(result.evidence_ids, "memory")},
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

    async def _run_schedule(self, sched: dict, occ_str: str, actor) -> dict:
        rt = self.runtime
        owner_caps = set(owner_capabilities(rt.settings))
        allowed = set(sched["allowed_tools"]) & owner_caps
        caps = tuple(
            sorted(c for c in allowed if not c.startswith(("schedule.", "schedules.")))
        ) or ("time.read",)
        task = rt.control.create_task(sched["session_id"])
        step_goal_id = f"schedule:{sched['id']}:{occ_str}"
        if getattr(rt.settings, "task_ledger", False):
            rt.control.link_task_goal(task, step_goal_id, 1)
        grant = rt.control.issue_grant(
            actor.id,
            sched["session_id"],
            caps,
            task_id=task,
            ttl_s=900,
            full_execution=False,
        )
        prompt = (
            f"Заплановане завдання власника: {sched['prompt']}\n"
            "Виконай необхідні дії доступними інструментами і стисло звітуй. "
            "У цьому ході заборонено створювати або змінювати розклади. "
            "Якщо повідомляти нічого, відповідай точно: [SILENT]"
        )
        cancel = asyncio.Event()

        async def watch_owner_stop():
            while not cancel.is_set():
                if not rt.attention.execution_allowed(actor.id):
                    cancel.set()
                    return
                await asyncio.sleep(STOP_POLL_S)

        watcher = asyncio.create_task(watch_owner_stop())
        try:
            result = await rt.agent.turn(
                sched["session_id"], grant, prompt, task_id=task, timeout_s=300, cancel=cancel
            )
        finally:
            watcher.cancel()
            await asyncio.gather(watcher, return_exceptions=True)

        needs_owner_step = getattr(rt.settings, "task_ledger", False) and bool(
            rt.control.steps_needing_owner(step_goal_id)
        )
        if (
            result.state == "failed"
            and result.error_code in _TRANSPORT_ERROR_CODES
            and not result.model_metrics
            and not result.tool_results
        ):
            updated = rt.schedules.finish(
                sched["id"],
                occ_str,
                "transport_failed",
                now=self.clock(),
                turn_id=result.turn_id,
                error_code=result.error_code,
            )
            return {
                "schedule_id": sched["id"],
                "occurrence": occ_str,
                "state": "failed",
                "error_code": result.error_code,
                "retry_scheduled": updated["retry_at"] is not None,
                "status": updated["status"],
            }

        reply_text = (result.content or "").strip()
        if result.state == "completed" and reply_text == "[SILENT]":
            updated = rt.schedules.finish(
                sched["id"], occ_str, "silent", now=self.clock(), turn_id=result.turn_id
            )
            tags = {**sched["tags"], **dict.fromkeys(result.evidence_ids, "memory")}
            proposal = rt.goals.add_proposal(
                actor.id,
                f"schedule:{sched['id']}",
                "[SILENT]",
                delivered=False,
                reason="silent",
                attention_id=None,
                tags=tags,
                decision="drop",
            )
            return {
                "schedule_id": sched["id"],
                "occurrence": occ_str,
                "state": "completed",
                "status": updated["status"],
                "proposal_id": proposal,
                "delivered": False,
                "initiative_decision": "drop",
                "initiative_reason": "silent",
            }

        if result.state == "awaiting_approval" or needs_owner_step:
            run_outcome = "paused"
            err = "unknown_outcome_needs_owner" if needs_owner_step else "approval_pending"
        elif result.state == "cancelled":
            run_outcome = "cancelled"
            err = result.error_code
        elif result.state == "failed":
            run_outcome = "failed"
            err = result.error_code
        else:
            run_outcome = "completed"
            err = None
        updated = rt.schedules.finish(
            sched["id"],
            occ_str,
            run_outcome,
            now=self.clock(),
            turn_id=result.turn_id,
            error_code=err,
        )
        outcome = {
            "schedule_id": sched["id"],
            "occurrence": occ_str,
            "state": result.state,
            "error_code": result.error_code,
            "status": updated["status"],
        }
        goal_key = f"schedule:{sched['id']}"
        text = result.content or f"Розклад «{sched['prompt'][:80]}»: {result.state}"
        if getattr(rt.settings, "initiative_gate", False):
            current = rt.schedules.get(sched["id"], actor.id)
            if current is None:
                gate_status = None
            elif current["status"] == "paused" and current.get("status_reason") == "owner_control":
                gate_status = "paused"
            else:
                gate_status = "active"
            outcome.update(
                self._gate_candidate(
                    actor=actor,
                    goal_id=goal_key,
                    goal_status=gate_status,
                    known_evidence=set(),
                    tags=sched["tags"],
                    result=result,
                    text=text,
                    always_novel=True,
                    force_high_risk=result.state in ("awaiting_approval", "failed")
                    or needs_owner_step,
                )
            )
            return outcome
        decision = rt.attention.decide(actor.id)
        attention_id = rt.attention.record(actor.id, decision) if decision.allowed else None
        outcome["proposal_id"] = rt.goals.add_proposal(
            actor.id,
            goal_key,
            text,
            delivered=decision.allowed,
            reason=decision.reason,
            attention_id=attention_id,
            tags={**sched["tags"], **dict.fromkeys(result.evidence_ids, "memory")},
        )
        outcome["delivered"] = decision.allowed
        return outcome

    async def run_schedules(self) -> list[dict]:
        """ADR-022: run due owner schedules through the initiative gate."""
        rt = self.runtime
        if not getattr(rt.settings, "schedules", False) or getattr(rt, "schedules", None) is None:
            return []
        outcomes = []
        for sched in list(rt.schedules.due(self.clock())):
            now = self.clock()
            now_iso = now.astimezone(UTC).isoformat()
            next_run = sched["next_run"]
            retry_at = sched["retry_at"]
            if next_run is not None and next_run <= now_iso:
                occ_str = next_run
                occ_dt = datetime.fromisoformat(occ_str).astimezone(UTC)
                if now.astimezone(UTC) - occ_dt > catchup_window(sched["spec"]):
                    if rt.schedules.skip_missed(sched["id"], occ_str, now=now):
                        outcomes.append(
                            {
                                "schedule_id": sched["id"],
                                "occurrence": occ_str,
                                "state": "missed",
                            }
                        )
                    refreshed = rt.schedules.get(sched["id"], sched["actor_id"])
                    if (
                        not refreshed
                        or refreshed["status"] != "active"
                        or not refreshed["next_run"]
                        or refreshed["next_run"] > now_iso
                    ):
                        continue
                    sched = refreshed
                    occ_str = sched["next_run"]
            elif retry_at is not None and retry_at <= now_iso:
                occ_str = f"retry:{retry_at}"
            else:
                continue

            actor = rt.control.resolve_actor(sched["actor_id"])
            if not rt.attention.execution_allowed(actor.id):
                outcomes.append(
                    {"schedule_id": sched["id"], "state": "skipped", "reason": "owner_stop"}
                )
                continue
            if self._busy(actor.id):
                outcomes.append(
                    {"schedule_id": sched["id"], "state": "skipped", "reason": "user_active"}
                )
                continue
            if not rt.schedules.claim(sched["id"], occ_str, now=now):
                continue
            try:
                outcomes.append(await self._run_schedule(sched, occ_str, actor))
            except Exception:
                log.exception("scheduled run failed")
                rt.schedules.finish(
                    sched["id"],
                    occ_str,
                    "failed",
                    now=self.clock(),
                    error_code="scheduler_error",
                )
                outcomes.append(
                    {"schedule_id": sched["id"], "occurrence": occ_str, "state": "failed"}
                )
        return outcomes

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
        if getattr(self.runtime.settings, "schedules", False):
            outcomes.extend(await self.run_schedules())
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
