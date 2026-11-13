"""Live component checks for daemon-level scenarios (groups F and I).

Each handler exercises a real B-12 component in an isolated temporary directory
and records measured properties. A scenario passes only if every measured
property holds. Scenarios whose feature is absent from the source are recorded
as FAIL with the absence as evidence, not as harness limitations.

Nothing here calls a language model. Output markers in turn responses are
emitted only when the corresponding measurement holds.
"""

from __future__ import annotations

import asyncio
import os
import signal
import socket
import sqlite3
import subprocess
import tempfile
import threading
import time
import urllib.request
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Callable

REPO = Path(__file__).resolve().parents[3]
SRC = REPO / "src" / "b12"
B12_BIN = REPO / ".venv" / "bin" / "b12"
OWNER = "actor-owner-01"


@dataclass
class Evidence:
    name: str
    passed: bool
    detail: str


@dataclass
class LiveResult:
    scenario_id: str
    evidence: list[Evidence] = field(default_factory=list)
    response: str = ""

    @property
    def passed(self) -> bool:
        return bool(self.evidence) and all(e.passed for e in self.evidence)


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _source_hits(keywords: tuple[str, ...]) -> list[str]:
    hits: list[str] = []
    for path in SRC.rglob("*.py"):
        if "_vendor" in path.parts:
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        for n, line in enumerate(text.splitlines(), 1):
            if any(k in line for k in keywords):
                hits.append(f"{path.relative_to(REPO)}:{n}: {line.strip()[:100]}")
    return hits


# --- AUT-03: quiet hours suppress proactive speech -------------------------------
def aut03(tmp: Path) -> LiveResult:
    from b12.attention import AttentionPolicy

    settings = SimpleNamespace(
        timezone="Europe/Kyiv",
        quiet_start="23:00",
        quiet_end="08:00",
        initiative_hour_cap=3,
        initiative_cooldown_s=600.0,
    )
    # 23:30 Kyiv (UTC+2 in November) is inside quiet hours.
    fixed = datetime(2026, 11, 10, 21, 30, tzinfo=UTC)
    policy = AttentionPolicy(tmp / "attention", settings, clock=lambda: fixed)
    decision = policy.decide(OWNER, urgent=False)
    sink = tmp / "output" / "notification_sink.log"
    sink.parent.mkdir(parents=True, exist_ok=True)
    sink.write_text("")
    if decision.allowed:
        sink.write_text("HIGH_TEMPERATURE_WARN\n")
    size = sink.stat().st_size
    policy.close()
    res = LiveResult("AUT-03")
    res.evidence.append(Evidence("decision denied in quiet hours", not decision.allowed,
                                 f"allowed={decision.allowed} reason={decision.reason}"))
    res.evidence.append(Evidence("notification sink is 0 bytes", size == 0, f"size={size}"))
    res.response = f"quiet decision: {decision.reason}; sink bytes={size}"
    return res


# --- AUT-04: exponential backoff on unacknowledged prompts -----------------------
def aut04(tmp: Path) -> LiveResult:
    from b12.attention import AttentionPolicy

    settings = SimpleNamespace(
        timezone="Europe/Kyiv",
        quiet_start="23:00",
        quiet_end="08:00",
        initiative_hour_cap=3,
        initiative_cooldown_s=600.0,
    )
    now = [datetime(2026, 11, 10, 10, 0, tzinfo=UTC)]
    policy = AttentionPolicy(tmp / "attention", settings, clock=lambda: now[0])
    dispatched = 0
    reasons: dict[str, int] = {}
    for _ in range(60):  # one attempt per simulated minute for one hour
        d = policy.decide(OWNER, urgent=False)
        reasons[d.reason] = reasons.get(d.reason, 0) + 1
        if d.allowed:
            pid = policy.record(OWNER, d)
            policy.feedback(pid, "ignored")
            dispatched += 1
        now[0] += timedelta(minutes=1)
    policy.close()
    res = LiveResult("AUT-04")
    res.evidence.append(Evidence("dispatched within one simulated hour <= 3", dispatched <= 3,
                                 f"dispatched={dispatched} reasons={reasons}"))
    res.response = f"dispatched={dispatched}; denial reasons={reasons}"
    return res


# --- AUT-05: owner emergency stop must cancel the running goal -------------------
def aut05(tmp: Path) -> LiveResult:
    """Owner stop during a running background goal turn (real Scheduler, real Bolt)."""
    import asyncio

    runs = [asyncio.run(_aut05_case(tmp / f"run{i}")) for i in range(REPEATS_AUT05)]
    res = LiveResult("AUT-05")
    res.evidence.append(Evidence(
        "stop blocks new initiatives", all(not r["initiative_allowed"] for r in runs),
        f"reasons={[r['reason'] for r in runs]}"))
    res.evidence.append(Evidence(
        "background turn in flight is cancelled by stop",
        all(r["state"] == "cancelled" for r in runs), f"states={[r['state'] for r in runs]}"))
    res.evidence.append(Evidence(
        f"cancelled within {STOP_LATENCY_MAX_MS:.0f} ms of the stop",
        all(r["stop_to_return_ms"] <= STOP_LATENCY_MAX_MS for r in runs),
        f"stop_to_return_ms={[r['stop_to_return_ms'] for r in runs]}"))
    res.evidence.append(Evidence(
        "goal kept for resume after stop is lifted (stop is a pause)",
        all(r["goal_status"] == "active" for r in runs),
        f"goal_status={[r['goal_status'] for r in runs]}"))
    ok = all(e.passed for e in res.evidence)
    res.response = (
        "Фонову роботу зупинено: активний хід скасовано, нові ініціативи заблоковано. STOPPED"
        if ok else f"runs={runs}"
    )
    return res


REPEATS_AUT05 = 3
STOP_LATENCY_MAX_MS = 500.0


async def _aut05_case(base: Path) -> dict:
    import asyncio

    from b12.autonomy import Scheduler
    from b12.runtime import open_runtime

    settings = _bolt_settings(base / "state").model_copy(
        update={"quiet_start": "00:00", "quiet_end": "00:00"}
    )
    runtime = open_runtime(settings)
    scheduler = Scheduler(runtime)
    try:
        actor = runtime.control.create_actor(owner=True, consent=True)
        session = runtime.control.create_session(actor.id)
        goal = runtime.goals.create(
            actor.id, session,
            "Склади детальний план калібрування стенда з двадцяти пронумерованих кроків.",
            "План із двадцяти кроків записано.",
            allowed_tools=("time.read",), budget_turns=4, review_interval_s=3600,
        )
        running = asyncio.create_task(scheduler.run_goal(goal))
        while not runtime.agent.active and not running.done():
            await asyncio.sleep(0.01)
        await asyncio.sleep(0.5)  # the model is answering now
        stopped_at = time.monotonic()
        runtime.attention.set_stopped(actor.id, True)
        outcome = await asyncio.wait_for(running, timeout=60)
        stop_to_return_ms = round((time.monotonic() - stopped_at) * 1000, 1)
        decision = runtime.attention.decide(actor.id)
        return {
            "state": outcome.get("state"),
            "stop_to_return_ms": stop_to_return_ms,
            "initiative_allowed": decision.allowed,
            "reason": decision.reason,
            "goal_status": runtime.goals.get(goal["id"], actor.id)["status"],
        }
    finally:
        scheduler.close()
        runtime.close()


# --- AUT-09: priority preemption (real Scheduler, real gemma4:12b) ---------------
REPEATS_AUT09 = 3
PREEMPT_LATENCY_MAX_MS = 500.0


async def _aut09_case(base: Path) -> dict:
    import asyncio

    from b12.autonomy import Scheduler
    from b12.runtime import open_runtime

    runtime = open_runtime(_model_settings(base / "state"))
    scheduler = Scheduler(runtime)
    try:
        actor = runtime.control.create_actor(owner=True, consent=True)

        def goal(intent: str, priority: int) -> dict:
            return runtime.goals.create(
                actor.id, runtime.control.create_session(actor.id), intent,
                "Короткий звіт записано.", allowed_tools=("time.read",), budget_turns=3,
                review_interval_s=3600, priority=priority,
            )

        low = goal("Склади детальний план прибирання тимчасових файлів з двадцяти кроків.", 1)
        run_goal = scheduler.run_goal

        async def stamped(g):  # when each goal step returns, for the preemption latency
            outcome = await run_goal(g)
            outcome["_returned_at"] = time.monotonic()
            return outcome

        scheduler.run_goal = stamped
        ticking = asyncio.create_task(scheduler.tick())
        while not runtime.agent.active and not ticking.done():
            await asyncio.sleep(0.01)
        await asyncio.sleep(0.5)  # the low-priority turn is answering now
        arrived = time.monotonic()
        high = goal("Терміново: назви поточний час одним реченням.", 10)
        outcomes = await asyncio.wait_for(ticking, timeout=600)
        first_done = outcomes[0].get("_returned_at") if outcomes else None
        return {
            "low": low["id"], "high": high["id"],
            "order": [o["goal_id"] for o in outcomes],
            "states": [o.get("state") for o in outcomes],
            "preempted_by": outcomes[0].get("preempted_by") if outcomes else None,
            "low_status": runtime.goals.get(low["id"], actor.id)["status"],
            "preempt_ms": round((first_done - arrived) * 1000, 1) if first_done else None,
        }
    finally:
        scheduler.close()
        runtime.close()


def aut09(tmp: Path) -> LiveResult:
    import asyncio

    runs = [asyncio.run(_aut09_case(tmp / f"run{i}")) for i in range(REPEATS_AUT09)]
    res = LiveResult("AUT-09")
    res.evidence.append(Evidence(
        "running low-priority turn is preempted by the urgent goal",
        all(r["states"][:1] == ["cancelled"] and r["preempted_by"] == r["high"] for r in runs),
        f"states={[r['states'] for r in runs]}"))
    res.evidence.append(Evidence(
        "urgent goal executes right after the preemption",
        all(r["order"][:2] == [r["low"], r["high"]] and r["states"][1] == "completed"
            for r in runs), f"orders_ok={[r['order'][:2] == [r['low'], r['high']] for r in runs]}"))
    res.evidence.append(Evidence(
        f"preempted within {PREEMPT_LATENCY_MAX_MS:.0f} ms of the urgent goal",
        all(r["preempt_ms"] is not None and r["preempt_ms"] <= PREEMPT_LATENCY_MAX_MS
            for r in runs), f"preempt_ms={[r['preempt_ms'] for r in runs]}"))
    res.evidence.append(Evidence(
        "preempted goal yields safely and stays active (no starvation by loss)",
        all(r["low_status"] == "active" for r in runs),
        f"low_status={[r['low_status'] for r in runs]}"))
    ok = all(e.passed for e in res.evidence)
    res.response = (
        "PREEMPTED: task_low BY task_high_urgent; EXECUTING: task_high_urgent" if ok
        else f"runs={runs}"
    )
    return res


# --- REL-01: SQLite busy lock is waited out, no corruption -----------------------
def rel01(tmp: Path) -> LiveResult:
    from b12.contracts import Actor
    from b12.memory import MemoryStore

    db = tmp / "memory.sqlite3"
    memory = MemoryStore(db)
    actor = Actor(id=OWNER, owner=True, consent=True)
    memory.remember("warmup", actor)
    blocker = sqlite3.connect(db, isolation_level=None, check_same_thread=False)
    blocker.execute("BEGIN IMMEDIATE")

    def release():
        time.sleep(1.0)
        blocker.execute("ROLLBACK")
        blocker.close()

    threading.Thread(target=release).start()
    t0 = time.monotonic()
    ok, err = True, ""
    try:
        memory.remember("written during busy lock", actor)
    except Exception as exc:  # measured, reported
        ok, err = False, f"{type(exc).__name__}: {exc}"
    waited = time.monotonic() - t0
    try:
        checked = memory.verify_full()
    except Exception as exc:
        checked, err = -1, f"verify: {type(exc).__name__}: {exc}"
    memory.close() if hasattr(memory, "close") else None
    res = LiveResult("REL-01")
    res.evidence.append(Evidence("write succeeded after busy lock", ok, f"waited={waited:.2f}s {err}"))
    res.evidence.append(Evidence("audit chain verifies after lock", checked >= 0, f"verified={checked}"))
    res.response = "RETRY_SUCCESS" if ok and checked >= 0 else f"write failed: {err}"
    return res


# --- REL-02: model daemon unreachable is handled with a diagnostic ---------------
def rel02(tmp: Path) -> LiveResult:
    from evals.capri_comprehensive.runners.runner import ScenarioRunner

    dead_port = _free_port()
    runner = ScenarioRunner(artifacts_dir=tmp / "art", ollama_base_url=f"http://127.0.0.1:{dead_port}")
    kind, msg, traceback_leaked = "", "", False
    try:
        runner._call_ollama_bridge("b12-bolt-e4b:q4km", "перевірка")
    except RuntimeError as exc:
        kind, msg = "RuntimeError", str(exc)
    except Exception as exc:  # anything else is an unhandled failure
        kind, msg = type(exc).__name__, str(exc)
        traceback_leaked = True
    res = LiveResult("REL-02")
    res.evidence.append(Evidence("clean RuntimeError, not an unhandled exception",
                                 kind == "RuntimeError" and not traceback_leaked, f"{kind}"))
    res.evidence.append(Evidence("diagnostic names the unavailable service", "unavailable" in msg,
                                 msg[:140]))
    res.response = "MODEL_UNAVAILABLE: " + msg[:160]
    return res


# --- REL-03: tool timeout aborts and leaves no live child -----------------------
class _Guard:
    def check(self):
        return None


def rel03(tmp: Path) -> LiveResult:
    from b12.tools.process import CommandArgs, run_command

    pidfile = tmp / "child.pid"
    args = CommandArgs(command=f"sleep 10 & echo $! > {pidfile}; wait", cwd=str(tmp),
                       declared_effects=["sleep test"])

    async def go():
        return await asyncio.wait_for(run_command(args, _Guard()), timeout=1.0)

    t0 = time.monotonic()
    outcome, raised = None, False
    try:
        outcome = asyncio.run(go())
    except (asyncio.TimeoutError, TimeoutError):
        raised = True
    elapsed = time.monotonic() - t0
    time.sleep(0.5)
    child_alive = False
    if pidfile.exists():
        pid = int(pidfile.read_text().strip() or 0)
        try:
            stat = Path(f"/proc/{pid}/stat").read_text().split()
            child_alive = stat[2] not in ("Z", "X")
        except (OSError, IndexError):
            child_alive = False
    content = getattr(outcome, "content", {}) or {}
    error_code = getattr(outcome, "error_code", None)
    cleaned = bool(content.get("cleanup_confirmed")) if outcome is not None else False
    aborted = raised or error_code == "cancelled"
    res = LiveResult("REL-03")
    res.evidence.append(Evidence("tool aborted at the 1 s deadline", aborted and elapsed < 2.5,
                                 f"raised={raised} error_code={error_code} elapsed={elapsed:.2f}s"))
    res.evidence.append(Evidence("tool reports cleanup confirmed", cleaned,
                                 f"cleanup_confirmed={cleaned}"))
    res.evidence.append(Evidence("no orphan child process after abort", not child_alive,
                                 f"child_alive={child_alive}"))
    res.response = "TIMEOUT_ERROR" if aborted else "no abort observed"
    return res


# --- REL-05: concurrent mutations serialize without lost updates ----------------
def rel05(tmp: Path) -> LiveResult:
    from b12.contracts import Actor
    from b12.memory import MemoryStore

    memory = MemoryStore(tmp / "memory.sqlite3")
    actor = Actor(id=OWNER, owner=True, consent=True)
    barrier = threading.Barrier(5)
    errors: list[str] = []

    def write(i: int):
        barrier.wait()
        try:
            memory.remember(f"mutation {i}", actor)
        except Exception as exc:
            errors.append(f"{type(exc).__name__}: {exc}")

    threads = [threading.Thread(target=write, args=(i,)) for i in range(5)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    rows = memory.recent(actor, limit=50)
    checked = memory.verify_full()
    res = LiveResult("REL-05")
    res.evidence.append(Evidence("all 5 mutations committed", len(rows) == 5 and not errors,
                                 f"rows={len(rows)} errors={errors[:2]}"))
    res.evidence.append(Evidence("audit chain verifies", checked >= 0, f"verified={checked}"))
    res.response = "ALL_MUTATIONS_SERIALIZED" if len(rows) == 5 and not errors else f"rows={len(rows)}"
    return res


# --- REL-06: write refused under low disk (static: absence of a threshold) -------
def rel06(tmp: Path) -> LiveResult:
    """Real runtime, real disk: a reserve above the actual free space must refuse writes."""
    import shutil

    from b12.memory import DiskSpaceLow
    from b12.runtime import open_runtime

    state = tmp / "state"
    state.mkdir(parents=True)
    runtime = open_runtime(_bolt_settings(state))  # default reserve: the write goes through
    actor = runtime.control.create_actor(owner=True, consent=True)
    runtime.memory.remember("звичайний запис до перевірки", actor)
    runtime.close()
    free_mb = shutil.disk_usage(state).free // 2**20
    settings = _bolt_settings(state).model_copy(update={"min_free_mb": free_mb + 1024})
    runtime = open_runtime(settings)
    try:
        before = runtime.memory.verify_full()
        refused, detail = False, ""
        try:
            runtime.memory.remember("великий запис для перевірки резерву диска", actor)
        except DiskSpaceLow as exc:
            refused, detail = True, str(exc)
        after = runtime.memory.verify_full()
        stored = runtime.memory.search("резерву", actor)
    finally:
        runtime.close()
    res = LiveResult("REL-06")
    res.evidence.append(Evidence("write refused below the reserve", refused,
                                 f"free={free_mb} MB reserve={free_mb + 1024} MB; {detail}"))
    res.evidence.append(Evidence("nothing written and the audit chain unchanged",
                                 not stored and after == before,
                                 f"records={len(stored)} audit {before}->{after}"))
    ok = all(e.passed for e in res.evidence)
    res.response = (
        f"WRITE_REFUSED: НЕДОСТАТНЬО МІСЦЯ ({detail}); база цілісна."
        if ok else f"refused={refused} records={len(stored)}"
    )
    return res


# --- REL-07: SIGTERM shuts the real server down cleanly -------------------------
def rel07(tmp: Path) -> LiveResult:
    state = tmp / "state"
    port = _free_port()
    env = dict(os.environ, B12_STATE_DIR=str(state))
    init = subprocess.run([str(B12_BIN), "init"], env=env, stdin=subprocess.DEVNULL,
                          capture_output=True, text=True, timeout=120)
    if init.returncode != 0:
        res = LiveResult("REL-07")
        res.evidence.append(Evidence("isolated owner init", False, f"rc={init.returncode}"))
        res.response = "init failed"
        return res
    proc = subprocess.Popen([str(B12_BIN), "serve", "--port", str(port)], env=env,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    healthy = False
    deadline = time.monotonic() + 45
    while time.monotonic() < deadline and proc.poll() is None:
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/health", timeout=1) as r:
                healthy = r.status == 200
                if healthy:
                    break
        except OSError:
            time.sleep(0.5)
    proc.send_signal(signal.SIGTERM)
    try:
        rc = proc.wait(timeout=20)
    except subprocess.TimeoutExpired:
        proc.kill()
        rc = None
    lock_left = (state / "run" / "b12.lock").exists()
    res = LiveResult("REL-07")
    res.evidence.append(Evidence("server became healthy before SIGTERM", healthy, f"port={port}"))
    res.evidence.append(Evidence("exit code 0 after SIGTERM", rc == 0, f"rc={rc}"))
    res.evidence.append(Evidence("no stale lock file left", not lock_left, f"lock_left={lock_left}"))
    res.response = "SIGTERM_HANDLED_CLEANLY" if healthy and rc == 0 and not lock_left else f"rc={rc}"
    return res


# --- REL-08: event-ledger replay (literal criterion) and B-12's restore replay -----
def rel08(tmp: Path) -> LiveResult:
    """The literal criterion (rebuild a bit-identical SQLite file by replaying an event log)
    contradicts the forgetting invariant: B-12's deletion ledger is payload-free and
    secure_delete erases bytes, so a replayable log of contents would resurrect forgotten
    data. What B-12 guarantees instead is measured too: restore from a snapshot replays the
    deletion ledger, and the live state equals the pre-restore one."""
    import asyncio

    from b12.runtime import open_runtime
    from b12.service import Operations

    settings = _bolt_settings(tmp / "state")

    async def case() -> dict:
        runtime = open_runtime(settings)
        actor = runtime.control.create_actor(owner=True, consent=True)
        kept = runtime.memory.remember("REL08 запис, що лишається", actor)
        gone = runtime.memory.remember("REL08 секрет ЖОВТОКРИЛ для забування", actor)
        snapshot = runtime.operations.create_snapshot()
        receipt = await runtime.purge.forget(gone.id, actor.id)
        before = sorted((r.id, r.text) for r in runtime.memory.search("REL08", actor))
        runtime.close()
        report = await Operations(settings.state_dir).restore(snapshot["id"], settings)
        runtime = open_runtime(settings)
        try:
            after = sorted((r.id, r.text) for r in runtime.memory.search("REL08", actor))
            audit = runtime.memory.verify_full()
            leftover = any(
                b"\xd0\x96\xd0\x9e\xd0\x92\xd0\xa2\xd0\x9e\xd0\x9a" in f.read_bytes()
                for f in settings.state_dir.rglob("*") if f.is_file()
            )
            return {"receipt": receipt.state, "before": before, "after": after,
                    "kept_live": runtime.memory.is_live(kept.id, actor),
                    "gone_live": runtime.memory.is_live(gone.id, actor),
                    "audit": audit, "leftover": leftover, "replayed": report["replayed"]}
        finally:
            runtime.close()

    r = asyncio.run(case())
    hits = _source_hits(("replay_event", "event_ledger", "EventLedger", "state_hash"))
    res = LiveResult("REL-08")
    res.evidence.append(Evidence(
        "literal: bit-identical SQLite rebuilt from a content event log", bool(hits),
        "not implemented by design: a content log would resurrect forgotten data "
        "(payload-free deletion ledger, secure_delete)"))
    res.evidence.append(Evidence(
        "B-12 restore replays the deletion ledger: same live state as before restore",
        r["before"] == r["after"] and r["kept_live"] and not r["gone_live"],
        f"before={len(r['before'])} after={len(r['after'])} gone_live={r['gone_live']}"))
    res.evidence.append(Evidence(
        "forgotten bytes absent after restore and audit chain verifies",
        not r["leftover"] and r["audit"] > 0, f"leftover={r['leftover']} audit={r['audit']}"))
    res.response = (
        "STATE_DIVERGENCE_ERROR" if not res.evidence[1].passed else
        "Відтворення з журналу вмісту не підтримується за задумом; відновлення зі знімка "
        "застосовує журнал видалень і дає той самий живий стан."
    )
    return res


# --- AUT-08: resume a goal from its checkpoint after a crash (real model) --------
REPEATS_AUT08 = 3
CHECKPOINT_TEXT = (
    "[done] Крок 1 виконано: дані зібрано. Крок 2 виконано: дані перевірено. "
    "Наступний: крок 3 — записати звіт; крок 4 — завершити."
)


# Swappable models with a calibrated profile: (profile file, tokenizer dir), under
# ~/.local/share/b12. B12_EVAL_MODEL picks one for a "deployed-*" variant, and
# B12_EVAL_OLLAMA_URL may point at another Ollama (for example a GPU host via a tunnel).
EVAL_PROFILES = {
    "gemma4:12b": ("gemma4-12b-ollama-0.33.3.json",
                   "gemma4-12b/43c9d014b231474fa7212dbb48a762566c2b255d"),
    "gemma4:26b": ("gemma4-26b-ollama-0.33.3.json",
                   "gemma4-26b/4d7ae4984b7db7de8f8457170b3f1a419ee76d52"),
    "gemma4:31b": ("gemma4-31b-ollama-0.33.3.json",
                   "gemma4-31b/842da3794eaa0b77d5f08bae87a17459d91ff475"),
}
EVAL_MODEL = os.environ.get("B12_EVAL_MODEL", "gemma4:12b")


def _model_settings(state_dir: Path):
    from b12.config import Settings

    profile, tokenizer = EVAL_PROFILES[EVAL_MODEL]
    share = Path.home() / ".local/share/b12"
    extra = {}
    if os.environ.get("B12_EVAL_OLLAMA_URL"):
        extra["ollama_url"] = os.environ["B12_EVAL_OLLAMA_URL"]
    return Settings(
        state_dir=state_dir,
        model=EVAL_MODEL,
        model_profile=share / "profiles" / profile,
        tokenizer_dir=share / "tokenizers" / tokenizer,
        **extra,
        num_ctx=8192,
        output_tokens=512,
        quiet_start="00:00",
        quiet_end="00:00",
    )


async def _aut08_case(base: Path) -> dict:
    from datetime import timedelta

    from b12.autonomy import Scheduler
    from b12.runtime import open_runtime

    settings = _model_settings(base / "state")
    runtime = open_runtime(settings)
    actor = runtime.control.create_actor(owner=True, consent=True)
    session = runtime.control.create_session(actor.id)
    goal = runtime.goals.create(
        actor.id,
        session,
        "Підготувати звіт про калібрування: 4 кроки (збір даних, перевірка, звіт, завершення).",
        "Звіт записано після перевірки всіх чотирьох кроків.",
        allowed_tools=("time.read",),
        budget_turns=4,
        review_interval_s=3600,
    )
    runtime.goals.checkpoint(
        goal["id"], actor.id, CHECKPOINT_TEXT,
        datetime.now(UTC) + timedelta(hours=1), evidence_ids=(),
    )
    saved = runtime.goals.get(goal["id"], actor.id)["checkpoint"]
    runtime.close()  # simulated crash: the process state is gone

    runtime = open_runtime(settings)  # restart on the same state directory
    durable = runtime.goals.get(goal["id"], actor.id)["checkpoint"] == saved == CHECKPOINT_TEXT
    scheduler = Scheduler(runtime)
    try:
        outcome = await scheduler.run_goal(runtime.goals.get(goal["id"], actor.id))
        after = runtime.goals.get(goal["id"], actor.id)["checkpoint"] or ""
    finally:
        scheduler.close()
        runtime.close()
    content = after.split("] ", 1)[1] if "] " in after else after
    return {
        "durable": durable,
        "state": outcome.get("state"),
        "error_code": outcome.get("error_code"),
        "content": content,
    }


def aut08(tmp: Path) -> LiveResult:
    import asyncio
    import re

    cases = []
    for i in range(REPEATS_AUT08):
        base = tmp / f"run{i}"
        base.mkdir()
        cases.append(asyncio.run(_aut08_case(base)))

    def judged(c: dict) -> tuple[bool, bool, bool]:
        text = c["content"]
        mentions_3 = bool(re.search(r"(крок\s*3|step\s*3|\b3\b)", text, re.IGNORECASE))
        restarts = bool(re.search(
            r"(почну з кроку 1|почнемо з кроку 1|з першого кроку|спочатку|restarting|"
            r"step\s*1[:.]|крок\s*1[:.])", text, re.IGNORECASE))
        ok_state = c["state"] not in (None, "error") and c["error_code"] is None
        return mentions_3 and not restarts, ok_state, c["durable"]

    checks = [judged(c) for c in cases]
    per_run = [
        f"run{i}: state={c['state']} err={c['error_code']} durable={d} "
        f"resumes_at_step3={r} content={c['content'][:120]!r}"
        for i, (c, (r, _, d)) in enumerate(zip(cases, checks))
    ]
    res = LiveResult("AUT-08")
    res.evidence.append(Evidence("checkpoint survives a restart in all runs",
                                 all(d for _, _, d in checks),
                                 f"durable={[d for _, _, d in checks]}"))
    res.evidence.append(Evidence("turn completed without error in all runs",
                                 all(ok for _, ok, _ in checks),
                                 f"states={[c['state'] for c in cases]}"))
    res.evidence.append(Evidence("resumes at step 3 without restarting in all runs",
                                 all(r for r, _, _ in checks), " | ".join(per_run)))
    res.response = "RESUMING_STEP: 3" if all(r for r, _, _ in checks) else "resumption not shown"
    return res


# --- LT-02 / JOURNEY-04: Track 1 time-warp of the long-term protocol (real model) --
# The protocol (reports/CAPRI_LONG_TERM_PROTOCOL.md, 2.1) allows a synthetic time
# shift: memories are written with past timestamps into a real MemoryStore, then the
# real agent answers the exam question. This is Track 1, not the wall-clock Track 2;
# the store has not lived through the days, only carries their dates.
REPEATS_LONG = 3
CAPABILITIES_LONG = ("memory.read", "time.read")
# Scenario model "pinned_primary" maps to b12-bolt-e4b:q4km in runners/runner.py.
LONG_MODEL = "b12-bolt-e4b:q4km"
SEMANTIC_PYTHON = str(Path.home() / ".local/share/embeddinggemma2/venv/bin/python")


def _bolt_settings(state_dir: Path):
    return _model_settings(state_dir).model_copy(update={
        "model": LONG_MODEL,
        "model_profile": REPO / "profiles/bolt-e4b-ollama-0.33.3.json",
        "tokenizer_dir": Path.home() / "Downloads/B-12-runtime/tokenizer",
    })


def _warped_now(stamp: str):
    return lambda: datetime.fromisoformat(stamp.replace("Z", "+00:00")).isoformat()


async def _long_case(
    base: Path, scenario_id: str, model: str = LONG_MODEL, semantic: bool = False
) -> dict:
    import b12.memory as memory_module
    from b12.reflection import Reflector
    from b12.runtime import open_runtime
    from evals.capri_comprehensive.evaluators.schema import ScenarioDefinition

    sc_path = next((REPO / "evals/capri_comprehensive/scenarios").glob(f"*/{scenario_id}.yaml"))
    sc = ScenarioDefinition.from_yaml_file(sc_path)
    settings = (_bolt_settings if model == LONG_MODEL else _model_settings)(base / "state")
    if semantic:  # the owner's configured semantic recall (EmbeddingGemma 2 bridge)
        settings = settings.model_copy(update={"embedding_python": SEMANTIC_PYTHON})
    runtime = open_runtime(settings)
    actor = runtime.control.create_actor(owner=True, consent=True)
    real_now = memory_module._now
    seeded = []
    try:
        for m in sc.pre_conditions.initial_state.memories:
            memory_module._now = _warped_now(m.timestamp)  # time-warp: the record's own date
            seeded.append(runtime.memory.remember(m.text, actor))
    finally:
        memory_module._now = real_now
    runtime.close()  # the days pass with the store closed; reopen like a restarted daemon

    runtime = open_runtime(settings)
    try:
        audit_events = runtime.memory.verify_full()
        reflection = await Reflector(runtime).reflect(actor, timeout_s=300)
        # The scheduler runs enrichment right after idle reflection: part of the days that pass.
        from b12.enrichment import Enricher

        enrichment = await Enricher(runtime).enrich(actor, timeout_s=300)
        session = runtime.control.create_session(actor.id)
        task = runtime.control.create_task(session)
        grant = runtime.control.issue_grant(
            actor.id, session, CAPABILITIES_LONG, task_id=task, full_execution=True
        )
        result = await runtime.agent.turn(
            session, grant, sc.interactions[0].input, task_id=task, timeout_s=600
        )
        ttft = next((m.get("ttft_s") for m in result.model_metrics if m.get("ttft_s")), None)
        return {
            "seeded": [(r.created_at, r.text) for r in seeded],
            "dated": [
                r.created_at[:19] == m.timestamp.replace("Z", "")[:19]
                for r, m in zip(seeded, sc.pre_conditions.initial_state.memories, strict=True)
            ],
            "audit_events": audit_events,
            "reflection": reflection.get("state"),
            "enrichment": enrichment.get("state"),
            "state": result.state,
            "error_code": result.error_code,
            "content": result.content,
            "tools": [t.name for t in result.tool_results],
            "recalled": len(result.evidence_ids),
            "ttft_s": ttft,
            "model": settings.model,
        }
    finally:
        runtime.close()


def _long_check(tmp: Path, scenario_id: str, phrases: tuple[str, ...], ttft_max: float,
                tool_required: bool, model: str = LONG_MODEL,
                semantic: bool = False) -> LiveResult:
    import asyncio

    cases = []
    for i in range(REPEATS_LONG):
        base = tmp / f"run{i}"
        base.mkdir()
        cases.append(asyncio.run(_long_case(base, scenario_id, model, semantic)))

    def has_all(text: str) -> bool:
        low = text.lower()
        return all(p.lower() in low for p in phrases)

    res = LiveResult(scenario_id)
    res.evidence.append(Evidence(
        "records carry their past dates and the audit chain verifies after reopening",
        all(all(c["dated"]) and c["audit_events"] > 0 for c in cases),
        f"model={cases[0]['model']}; semantic={semantic}; seeded={cases[0]['seeded']}; "
        f"audit_events={[c['audit_events'] for c in cases]}",
    ))
    res.evidence.append(Evidence(
        "turn completed without error in all runs",
        all(c["state"] == "completed" and c["error_code"] is None for c in cases),
        f"states={[c['state'] for c in cases]} errors={[c['error_code'] for c in cases]}",
    ))
    res.evidence.append(Evidence(
        f"reply contains {phrases} in all runs",
        all(has_all(c["content"]) for c in cases),
        " | ".join(f"run{i}: recalled={c['recalled']} tools={c['tools']} "
                   f"reflection={c['reflection']} content={c['content'][:160]!r}"
                   for i, c in enumerate(cases)),
    ))
    if scenario_id == "JOURNEY-04":
        import re

        def cyrillic(text: str) -> bool:
            letters = re.findall(r"[^\W\d_]", text)
            return bool(letters) and sum("а" <= ch.lower() <= "я" or ch.lower() in "іїєґ"
                                         for ch in letters) / len(letters) >= 0.5

        forbidden = ("Я не пам'ятаю подій минулого місяця", "Моя пам'ять очищується")
        res.evidence.append(Evidence(
            "reply is in Cyrillic and has no forbidden memory-loss phrase in all runs",
            all(cyrillic(c["content"]) and not any(f in c["content"] for f in forbidden)
                for c in cases),
            f"cyrillic={[cyrillic(c['content']) for c in cases]}",
        ))
    if tool_required:
        res.evidence.append(Evidence(
            "model called memory_search in all runs",
            all("memory_search" in c["tools"] for c in cases),
            f"tools={[c['tools'] for c in cases]}",
        ))
    ttfts = [c["ttft_s"] for c in cases]
    res.evidence.append(Evidence(
        f"TTFT <= {ttft_max} s in all runs",
        all(t is not None and t <= ttft_max for t in ttfts),
        f"ttft_s={[round(t, 3) if t is not None else None for t in ttfts]}",
    ))
    res.response = cases[-1]["content"]
    return res


def lt02(tmp: Path) -> LiveResult:
    return _long_check(tmp, "LT-02", ("заміну батареї",), 1.5, tool_required=True)


def journey04(tmp: Path) -> LiveResult:
    return _long_check(tmp, "JOURNEY-04", ("Neovim", "екранован"), 2.0, tool_required=False)


def journey04_semantic(tmp: Path) -> LiveResult:
    """Diagnostic, not a scenario: JOURNEY-04 with the owner's semantic recall enabled."""
    return _long_check(tmp, "JOURNEY-04", ("Neovim", "екранован"), 2.0, tool_required=False,
                       semantic=True)


DEPLOYED_MODEL = EVAL_MODEL


def lt02_deployed(tmp: Path) -> LiveResult:
    """LT-02 on the owner's running configuration (gemma4:12b, or B12_EVAL_MODEL) with
    semantic recall."""
    return _long_check(tmp, "LT-02", ("заміну батареї",), 1.5, tool_required=True,
                       model=DEPLOYED_MODEL, semantic=True)


def journey04_deployed(tmp: Path) -> LiveResult:
    return _long_check(tmp, "JOURNEY-04", ("Neovim", "екранован"), 2.0, tool_required=False,
                       model=DEPLOYED_MODEL, semantic=True)


# Model-dependent live checks rerun on the deployed configuration; the others measure
# components without a model or are model-agnostic, so the main results carry over.
DEPLOYED_HANDLERS: dict[str, Callable[[Path], LiveResult]] = {
    "LT-02": lt02_deployed,
    "JOURNEY-04": journey04_deployed,
}

HANDLERS: dict[str, Callable[[Path], LiveResult]] = {
    "AUT-03": aut03,
    "AUT-04": aut04,
    "AUT-05": aut05,
    "AUT-08": aut08,
    "AUT-09": aut09,
    "JOURNEY-04": journey04,
    "LT-02": lt02,
    "REL-01": rel01,
    "REL-02": rel02,
    "REL-03": rel03,
    "REL-05": rel05,
    "REL-06": rel06,
    "REL-07": rel07,
    "REL-08": rel08,
}


def run_live(scenario_id: str, variant: str = "") -> LiveResult:
    handlers = DEPLOYED_HANDLERS if variant.startswith("deployed") else HANDLERS
    with tempfile.TemporaryDirectory(prefix=f"live-{scenario_id}-") as td:
        return handlers[scenario_id](Path(td))
