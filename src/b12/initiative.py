"""ADR-018 initiative gate: a deterministic five-way decision for background proposals.

The gate never reads model text to decide; it uses the goal state, evidence liveness, a
dedupe key, the owner's attention policy and the candidate's declared trigger and risk.
Decisions: drop, needs_owner, deliver, defer, inbox (first matching rule wins).
"""

import hashlib
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta

TRIGGERS = ("goal_review", "deadline", "source_revision", "dependency")
RISKS = ("info", "action", "high")
DECISIONS = ("drop", "needs_owner", "deliver", "defer", "inbox")
DEDUPE_WINDOW = timedelta(hours=24)
URGENT_WINDOW = timedelta(hours=2)
NOVELTY_DEADLINE_WINDOW = timedelta(hours=24)
DEFER_TTL = timedelta(hours=48)


@dataclass(frozen=True)
class InitiativeCandidate:
    actor_id: str
    goal_id: str
    trigger: str
    text: str
    risk: str = "info"
    evidence_ids: tuple[str, ...] = ()
    due_at: datetime | None = None
    novel: bool = True

    def __post_init__(self):
        if self.trigger not in TRIGGERS:
            raise ValueError("unknown trigger")
        if self.risk not in RISKS:
            raise ValueError("unknown risk")
        if self.due_at is not None and self.due_at.tzinfo is None:
            raise ValueError("timezone-aware due_at required")


@dataclass(frozen=True)
class GateDecision:
    decision: str
    reason: str
    dedupe_key: str
    not_before: datetime | None = None
    expires_at: datetime | None = None
    urgent: bool = False


@dataclass
class GateContext:
    """What the gate may look at. Callables keep it testable without the runtime."""

    goal_status: str | None
    evidence_live: dict[str, bool] = field(default_factory=dict)
    recent_keys: tuple[tuple[str, datetime], ...] = ()  # (dedupe_key, when) of this actor
    muted: bool = False
    attention_reason: str = "allowed"  # AttentionPolicy.decide(...).reason, non-urgent
    attention_allowed: bool = True
    window_end: datetime | None = None  # end of quiet hours / cooldown, when known


def dedupe_key(goal_id: str, text: str) -> str:
    normal = re.sub(r"\s+", " ", re.sub(r"[^\w\s]", "", text.lower())).strip()
    return hashlib.sha256(f"{goal_id}\x00{normal}".encode()).hexdigest()


def decide(candidate: InitiativeCandidate, ctx: GateContext, now: datetime) -> GateDecision:
    key = dedupe_key(candidate.goal_id, candidate.text)
    urgent = (
        candidate.trigger == "deadline"
        and candidate.due_at is not None
        and now <= candidate.due_at <= now + URGENT_WINDOW
    )
    # 1. drop: the source is closed or stale, a repeat, or nothing new and nothing due.
    if ctx.goal_status != "active":
        return GateDecision("drop", f"goal_{ctx.goal_status or 'missing'}", key)
    if any(not ctx.evidence_live.get(e, False) for e in candidate.evidence_ids):
        return GateDecision("drop", "stale_evidence", key)
    if any(k == key and now - when < DEDUPE_WINDOW for k, when in ctx.recent_keys):
        return GateDecision("drop", "duplicate", key)
    due_soon = candidate.due_at is not None and candidate.due_at <= now + NOVELTY_DEADLINE_WINDOW
    if not candidate.novel and not due_soon:
        return GateDecision("drop", "not_novel", key)
    if ctx.muted and not urgent:
        return GateDecision("drop", "goal_muted", key)
    # 2. needs_owner: high-risk suggestions are never spoken unprompted.
    if candidate.risk == "high":
        return GateDecision("needs_owner", "high_risk", key)
    # 3. deliver: allowed now, or an urgent deadline (quiet mode yes, owner stop no).
    if ctx.attention_reason == "owner_stop":
        return GateDecision("inbox", "owner_stop", key)
    if urgent:
        return GateDecision("deliver", "urgent_deadline", key, urgent=True)
    if ctx.attention_allowed:
        return GateDecision("deliver", "allowed", key)
    # 4. defer: a time window will open; 5. inbox: the owner asked for quiet.
    if ctx.attention_reason in ("quiet_hours", "cooldown", "backoff", "hour_cap"):
        return GateDecision(
            "defer",
            ctx.attention_reason,
            key,
            not_before=ctx.window_end or now + timedelta(hours=1),
            expires_at=now + DEFER_TTL,
        )
    return GateDecision("inbox", ctx.attention_reason, key)
