"""U7 offline replay (ADR-018): synthetic initiative candidates with expected decisions.

Expected decisions are authored per class from the ADR's semantics, not computed by the gate.
Metrics: false-positive interventions (delivered while the expected decision is not deliver)
and missed high-value (expected deliver or needs_owner, got drop or inbox). Runs without a
model; deterministic.

    python -m evals.unified.initiative_replay [out.json]
"""

import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

from b12.initiative import GateContext, InitiativeCandidate, decide, dedupe_key

NOW = datetime(2026, 12, 1, 10, 0, tzinfo=UTC)
TEXTS = [
    "Знайшов, що в теці звітів з'явився новий файл за листопад.",
    "Тест стенду пройшов, напруга стабільна 24 В.",
    "Посилка прибуде завтра до 12:00, потрібен підпис.",
    "Резервна копія фото завершилась: 1240 файлів.",
    "Оновлення прошивки роутера вийшло, версія 2.5.",
]


def _case(cls, i, *, expected, ctx=None, **cand):
    candidate = {
        "actor_id": "owner",
        "goal_id": f"g-{cls}-{i}",
        "trigger": "goal_review",
        "text": TEXTS[i % len(TEXTS)],
        "evidence_ids": (f"e-{cls}-{i}",),
    }
    candidate.update(cand)
    context = {"goal_status": "active", "evidence_live": {f"e-{cls}-{i}": True}}
    context.update(ctx or {})
    return {
        "class": cls,
        "id": f"{cls}-{i}",
        "expected": expected,
        "candidate": candidate,
        "context": context,
    }


def cases():
    out = []
    for i in range(5):
        out.append(_case("relevant", i, expected="deliver"))
        out.append(_case("irrelevant", i, expected="drop", novel=False))
        out.append(
            _case(
                "quiet_mode",
                i,
                expected="inbox",
                ctx={"attention_allowed": False, "attention_reason": "quiet_mode"},
            )
        )
        out.append(
            _case(
                "quiet_hours",
                i,
                expected="defer",
                ctx={
                    "attention_allowed": False,
                    "attention_reason": "quiet_hours",
                    "window_end": NOW + timedelta(hours=8),
                },
            )
        )
        out.append(
            _case(
                "stale_evidence",
                i,
                expected="drop",
                ctx={"evidence_live": {f"e-stale_evidence-{i}": False}},
            )
        )
        out.append(
            _case(
                "cancelled_goal",
                i,
                expected="drop",
                ctx={"goal_status": ("abandoned", "achieved", "failed")[i % 3]},
            )
        )
        out.append(_case("high_risk", i, expected="needs_owner", risk="high"))
        dup = _case("duplicate", i, expected="drop")
        dup["context"]["recent_keys"] = (
            (
                dedupe_key(dup["candidate"]["goal_id"], dup["candidate"]["text"].upper() + "  "),
                NOW - timedelta(hours=3 + i),
            ),
        )
        out.append(dup)
        out.append(
            _case(
                "urgent_under_quiet",
                i,
                expected="deliver",
                trigger="deadline",
                due_at=NOW + timedelta(minutes=30 + 15 * i),
                ctx={"attention_allowed": False, "attention_reason": "quiet_mode"},
            )
        )
        out.append(
            _case(
                "owner_stop",
                i,
                expected="inbox",
                trigger="deadline",
                due_at=NOW + timedelta(minutes=30),
                ctx={"attention_allowed": False, "attention_reason": "owner_stop"},
            )
        )
    return out


def current_behaviour(candidate, ctx):
    """The runtime before ADR-018: every review is a proposal, gated by attention only
    (urgency is never set by autonomy); refused proposals are stored undelivered."""
    if ctx.goal_status != "active":
        return "drop"  # the scheduler runs only active goals (GoalStore.due)
    if ctx.attention_reason == "owner_stop":
        return "inbox"  # stop skips the goal run entirely; nothing is said
    return "deliver" if ctx.attention_allowed else "inbox"


def replay(rows, *, baseline=False):
    per_class, results = {}, []
    for row in rows:
        candidate = InitiativeCandidate(**row["candidate"])
        ctx = GateContext(**row["context"])
        if baseline:
            decision, reason = current_behaviour(candidate, ctx), "attention_only"
        else:
            got = decide(candidate, ctx, NOW)
            decision, reason = got.decision, got.reason
        expected = row["expected"]
        false_positive = decision == "deliver" and expected != "deliver"
        missed = expected in ("deliver", "needs_owner") and decision in ("drop", "inbox")
        stats = per_class.setdefault(row["class"], {"n": 0, "correct": 0, "fp": 0, "missed": 0})
        stats["n"] += 1
        stats["correct"] += decision == expected
        stats["fp"] += false_positive
        stats["missed"] += missed
        results.append({"id": row["id"], "expected": expected, "got": decision, "reason": reason})
    total = {k: sum(s[k] for s in per_class.values()) for k in ("n", "correct", "fp", "missed")}
    return {"per_class": per_class, "total": total, "results": results}


def main(argv=None):
    argv = argv if argv is not None else sys.argv[1:]
    rows = cases()
    report = {"gate": replay(rows), "current_behaviour": replay(rows, baseline=True)}
    if argv:
        Path(argv[0]).write_text(
            json.dumps(report, ensure_ascii=False, indent=1, default=str) + "\n", encoding="utf-8"
        )
    for arm, data in report.items():
        print("==", arm)
        for cls, s in data["per_class"].items():
            print(f"{cls:20} {s['correct']}/{s['n']} correct, FP {s['fp']}, missed {s['missed']}")
        print("total", data["total"])


if __name__ == "__main__":
    main()
