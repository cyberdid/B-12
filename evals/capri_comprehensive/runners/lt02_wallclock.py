"""LT-02 Track 2: a real 7-day wall-clock run in an isolated eval state directory.

The protocol's Day-0 anchor (2026-11-03) was never written to the owner's memory, and
writing it backdated would be a fabrication. This script instead starts a fresh
wall-clock run: `seed` writes the LT-02 anchor at the real current time into a
separate state directory (never the owner's), `exam` asks the LT-02 question once at
least 7 days later and records the outcome.

Usage (from the repository root):
    uv run python -m evals.capri_comprehensive.runners.lt02_wallclock seed
    uv run python -m evals.capri_comprehensive.runners.lt02_wallclock exam
"""

from __future__ import annotations

import asyncio
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

from evals.capri_comprehensive.runners.live_components import (
    CAPABILITIES_LONG,
    REPO,
    _bolt_settings,
)

STATE = Path.home() / ".local/state/b12-evals/lt02-wallclock"
RECORD = STATE / "run.json"
ARTIFACT = REPO / "evals/capri_comprehensive/artifacts/LT-02-wallclock/exam.json"
MIN_DAYS = 7.0


def _scenario():
    from evals.capri_comprehensive.evaluators.schema import ScenarioDefinition

    path = next((REPO / "evals/capri_comprehensive/scenarios").glob("*/LT-02.yaml"))
    return ScenarioDefinition.from_yaml_file(path)


def seed() -> dict:
    from b12.runtime import open_runtime

    if RECORD.exists():
        raise SystemExit(f"already seeded: {RECORD.read_text()}")
    sc = _scenario()
    runtime = open_runtime(_bolt_settings(STATE / "state"))
    try:
        actor = runtime.control.create_actor(owner=True, consent=True)
        record = runtime.memory.remember(sc.pre_conditions.initial_state.memories[0].text, actor)
    finally:
        runtime.close()
    data = {"actor_id": actor.id, "memory_id": record.id, "seeded_at": record.created_at,
            "text": record.text}
    RECORD.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return data


async def _exam(run: dict) -> dict:
    from b12.runtime import open_runtime

    sc = _scenario()
    runtime = open_runtime(_bolt_settings(STATE / "state"))
    try:
        audit_events = runtime.memory.verify_full()
        actor = runtime.control.resolve_actor(run["actor_id"])
        live = runtime.memory.is_live(run["memory_id"], actor)
        session = runtime.control.create_session(actor.id)
        task = runtime.control.create_task(session)
        grant = runtime.control.issue_grant(
            actor.id, session, CAPABILITIES_LONG, task_id=task, full_execution=True
        )
        result = await runtime.agent.turn(
            session, grant, sc.interactions[0].input, task_id=task, timeout_s=600
        )
    finally:
        runtime.close()
    ttft = next((m.get("ttft_s") for m in result.model_metrics if m.get("ttft_s")), None)
    tools = [t.name for t in result.tool_results]
    content = result.content
    checks = {
        "anchor_live_and_audit_ok": live and audit_events > 0,
        "turn_completed": result.state == "completed" and result.error_code is None,
        "reply_contains_zaminu_batarei": "заміну батареї" in content.lower(),
        "memory_search_called": "memory_search" in tools,
        "ttft_le_1_5_s": ttft is not None and ttft <= 1.5,
    }
    return {"checks": checks, "passed": all(checks.values()), "ttft_s": ttft, "tools": tools,
            "state": result.state, "error_code": result.error_code, "content": content,
            "audit_events": audit_events}


def exam() -> dict:
    run = json.loads(RECORD.read_text(encoding="utf-8"))
    seeded = datetime.fromisoformat(run["seeded_at"])
    elapsed = (datetime.now(UTC) - seeded).total_seconds() / 86400
    if elapsed < MIN_DAYS:
        raise SystemExit(f"only {elapsed:.3f} days elapsed; exam needs >= {MIN_DAYS}")
    out = {"seeded_at": run["seeded_at"], "examined_at": datetime.now(UTC).isoformat(),
           "elapsed_days": round(elapsed, 3), "model": _bolt_settings(STATE).model,
           **asyncio.run(_exam(run))}
    ARTIFACT.parent.mkdir(parents=True, exist_ok=True)
    ARTIFACT.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    return out


if __name__ == "__main__":
    command = sys.argv[1] if len(sys.argv) > 1 else ""
    if command not in ("seed", "exam"):
        raise SystemExit("usage: lt02_wallclock (seed|exam)")
    print(json.dumps(seed() if command == "seed" else exam(), ensure_ascii=False, indent=2))
