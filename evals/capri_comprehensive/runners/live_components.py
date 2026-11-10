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
    from b12.attention import AttentionPolicy
    from b12.goals import GoalStore

    settings = SimpleNamespace(timezone="Europe/Kyiv", quiet_start="23:00", quiet_end="08:00",
                               initiative_hour_cap=3, initiative_cooldown_s=600.0)
    goals = GoalStore(tmp / "goals.sqlite3")
    goal = goals.create(OWNER, "session-1", "Довгий пошук у файлах", "Завершити пошук")
    policy = AttentionPolicy(tmp / "attention", settings, clock=lambda: datetime(2026, 11, 10, 10, 0, tzinfo=UTC))
    policy.set_stopped(OWNER, True)
    after = goals.get(goal["id"], OWNER)
    stop_decision = policy.decide(OWNER)
    policy.close()
    goals.close()
    status = after["status"] if after else "missing"
    res = LiveResult("AUT-05")
    res.evidence.append(Evidence("stop blocks new initiatives", not stop_decision.allowed,
                                 f"reason={stop_decision.reason}"))
    res.evidence.append(Evidence("running goal cancelled by stop", status == "cancelled",
                                 f"goal status after stop={status}"))
    res.response = f"stop reason={stop_decision.reason}; goal status={status}"
    return res


# --- AUT-09: priority preemption (static: absence of the mechanism) --------------
def aut09(tmp: Path) -> LiveResult:
    hits = _source_hits(("preempt", "PREEMPT"))
    res = LiveResult("AUT-09")
    res.evidence.append(Evidence("priority preemption implemented in src/b12", bool(hits),
                                 f"matches={len(hits)}; {hits[:3]}"))
    res.response = f"preemption matches in src: {len(hits)}"
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
    hits = _source_hits(("disk_usage", "free_space", "статфс", "statvfs"))
    res = LiveResult("REL-06")
    res.evidence.append(Evidence("free-space threshold guards writes in src/b12", bool(hits),
                                 f"matches={len(hits)}; {hits[:3]}"))
    res.response = f"free-space checks in src: {len(hits)}"
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


# --- REL-08: state reconstructed bit-for-bit from an event ledger (static) -------
def rel08(tmp: Path) -> LiveResult:
    hits = _source_hits(("replay_event", "event_ledger", "EventLedger", "state_hash"))
    res = LiveResult("REL-08")
    res.evidence.append(Evidence("general event-ledger replay with state hash in src/b12",
                                 bool(hits), f"matches={len(hits)}; {hits[:3]}"))
    res.response = f"event-ledger replay matches in src: {len(hits)}"
    return res


HANDLERS: dict[str, Callable[[Path], LiveResult]] = {
    "AUT-03": aut03,
    "AUT-04": aut04,
    "AUT-05": aut05,
    "AUT-09": aut09,
    "REL-01": rel01,
    "REL-02": rel02,
    "REL-03": rel03,
    "REL-05": rel05,
    "REL-06": rel06,
    "REL-07": rel07,
    "REL-08": rel08,
}


def run_live(scenario_id: str) -> LiveResult:
    with tempfile.TemporaryDirectory(prefix=f"live-{scenario_id}-") as td:
        return HANDLERS[scenario_id](Path(td))
