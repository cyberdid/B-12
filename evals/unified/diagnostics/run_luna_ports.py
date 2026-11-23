#!/usr/bin/env python3
# ruff: noqa: E501  -- diagnostic runner copied from the agent; long log and command lines
"""Diagnostic runner: ports-live-v1 (frozen) through gpt-6-luna via subscription_bridge.

Runs 6 arms (repeats=1, arm=A0, from .worktrees/eval-run at pin d116105):
1. baseline (control)
2. preference_placement (--preference-rules --preference-placement query)
3. memory_review (--memory-review)
4. memory_taint (--memory-taint)
5. session_search (--session-search)
6. memory_as_of (--memory-as-of)

NOTE: Diagnostic run only ("не deployed-конфігурація"); flags are NEVER turned on from it.
Judges must exclude Codex (use gemini + opus via Anthropic Claude Opus 5.5).
"""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import time
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

EVAL_REPO = Path(os.environ.get("B12_EVAL_REPO", Path.home() / "Projects/B-12/.worktrees/eval-run"))
if str(EVAL_REPO) not in sys.path:
    sys.path.insert(0, str(EVAL_REPO))

from evals.unified.score_u2_u3 import score  # noqa: E402

MANIFEST_REL = "evals/unified/scenario_sets/ports-live-v1.json"
CLOUD_BASE = "--variant deployed --model-timeout 230 --num-ctx 200000 --output-tokens 16384 --memory-temporal --goals-in-context"
BRIDGE_PORT = 11501
TRANSIENT_ERRORS = {"http_error", "transport_error", "transport_timeout", "deadline_exceeded"}
MAX_PILOT_ATTEMPTS = 4

SCRATCH_DIR = Path(os.environ.get("B12_LUNA_WORK", Path.home() / ".cache/b12-luna-diagnostic"))
BRIDGE_LOG = SCRATCH_DIR / "luna_bridge.log"
RUNNER_LOG = SCRATCH_DIR / "luna_runner.log"
STATUS_JSON = SCRATCH_DIR / "luna_status.json"

ARMS: list[tuple[str, str, str]] = [
    (
        "luna-ports-baseline",
        "evals/capri_comprehensive/artifacts/ports-live-v1-luna6-baseline-2026-11-22",
        "",
    ),
    (
        "luna-ports-preference_placement",
        "evals/capri_comprehensive/artifacts/ports-live-v1-luna6-preference_placement-2026-11-22",
        "--preference-rules --preference-placement query",
    ),
    (
        "luna-ports-memory_review",
        "evals/capri_comprehensive/artifacts/ports-live-v1-luna6-memory_review-2026-11-22",
        "--memory-review",
    ),
    (
        "luna-ports-memory_taint",
        "evals/capri_comprehensive/artifacts/ports-live-v1-luna6-memory_taint-2026-11-22",
        "--memory-taint",
    ),
    (
        "luna-ports-session_search",
        "evals/capri_comprehensive/artifacts/ports-live-v1-luna6-session_search-2026-11-22",
        "--session-search",
    ),
    (
        "luna-ports-memory_as_of",
        "evals/capri_comprehensive/artifacts/ports-live-v1-luna6-memory_as_of-2026-11-22",
        "--memory-as-of",
    ),
]


def log(msg: str) -> None:
    SCRATCH_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(UTC).astimezone().isoformat(timespec="seconds")
    line = f"{ts} {msg}\n"
    with RUNNER_LOG.open("a", encoding="utf-8") as f:
        f.write(line)
    print(line, end="", flush=True)


def write_status(state: dict) -> None:
    tmp = STATUS_JSON.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(STATUS_JSON)


def bridge_healthy() -> bool:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{BRIDGE_PORT}/api/version", timeout=2) as r:
            return r.status == 200
    except Exception:
        return False


def start_bridge() -> subprocess.Popen | None:
    if bridge_healthy():
        log(f"Reusing existing subscription_bridge on port {BRIDGE_PORT}")
        return None
    SCRATCH_DIR.mkdir(parents=True, exist_ok=True)
    flog = BRIDGE_LOG.open("a", encoding="utf-8")
    proc = subprocess.Popen(
        [
            str(EVAL_REPO / ".venv/bin/python"),
            str(Path(__file__).with_name("bridge_launcher.py")),
            "--backend",
            "codex",
            "--model",
            "gpt-6-luna",
            "--port",
            str(BRIDGE_PORT),
            "--upstream",
            "http://127.0.0.1:11434",
            "--timeout",
            "200",
        ],
        cwd=str(EVAL_REPO),
        stdin=subprocess.DEVNULL,
        stdout=flog,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )
    for _ in range(30):
        if bridge_healthy():
            log(
                f"Started subscription_bridge (codex / gpt-6-luna) on port {BRIDGE_PORT} PID={proc.pid}"
            )
            return proc
        if proc.poll() is not None:
            raise RuntimeError(f"subscription_bridge exited prematurely with rc={proc.returncode}")
        time.sleep(0.5)
    raise RuntimeError("subscription_bridge did not become ready within 15s")


def check_arm_records(out_dir: Path, scenarios: list[dict]) -> tuple[bool, list[str], list[str]]:
    """Return (done_in_log, broken_or_missing_sids, transient_error_sids)."""
    pilot_log = out_dir / "pilot.log"
    done_in_log = pilot_log.exists() and any(
        ln.endswith("DONE") or " DONE" in ln
        for ln in pilot_log.read_text(encoding="utf-8", errors="replace").splitlines()
    )
    missing_or_corrupt: list[str] = []
    transient: list[str] = []
    other_err: list[str] = []
    for row in scenarios:
        sid = row["scenario_id"]
        rec_path = out_dir / "r1" / f"{sid}.json"
        if not rec_path.exists() or rec_path.stat().st_size == 0:
            missing_or_corrupt.append(sid)
            continue
        try:
            rec = json.loads(rec_path.read_text(encoding="utf-8"))
        except Exception:
            rec_path.unlink(missing_ok=True)
            missing_or_corrupt.append(sid)
            continue
        err = rec.get("error_code")
        if err in TRANSIENT_ERRORS:
            transient.append(sid)
        elif rec.get("status") != "EXECUTED" or err is not None:
            other_err.append(f"{sid}:{rec.get('status')}/{err}")
    return (
        done_in_log and not missing_or_corrupt and not transient and not other_err,
        missing_or_corrupt + other_err,
        transient,
    )


def main() -> int:
    manifest = json.loads((EVAL_REPO / MANIFEST_REL).read_text(encoding="utf-8"))
    scenarios = manifest["scenarios"]
    bridge_proc = start_bridge()
    state: dict = {"state": "RUNNING", "completed": [], "results": {}, "error": None}
    write_status(state)

    try:
        for idx, (name, out_rel, extra_flag) in enumerate(ARMS, 1):
            extra = f"{CLOUD_BASE} {extra_flag}".strip()
            env = {
                **os.environ,
                "B12_EVAL_OLLAMA_URL": f"http://127.0.0.1:{BRIDGE_PORT}",
                "B12_EVAL_MODEL": "gemma4:12b",
                "B12_EVAL_VARIANT": "deployed",
                "NO_GPU_WAIT": "1",
                "EXTRA_RUNNER_ARGS": extra,
            }
            out_dir = EVAL_REPO / out_rel
            out_dir.mkdir(parents=True, exist_ok=True)
            state["current"] = f"{idx}/{len(ARMS)} {name}"
            write_status(state)

            clean, bad, transient = check_arm_records(out_dir, scenarios)
            if clean:
                log(f"SKIP {idx}/{len(ARMS)}: {name} already clean 16/16 (DONE)")
            else:
                log(
                    f"START {idx}/{len(ARMS)}: {name} ({extra_flag or 'control'}) "
                    f"[existing missing/other={len(bad)}, transient={transient}]"
                )
                for attempt in range(1, MAX_PILOT_ATTEMPTS + 1):
                    # Quarantine any transient-error JSONs (including deadline_exceeded) before retry
                    ts_q = int(time.time())
                    for t_sid in transient:
                        t_path = out_dir / "r1" / f"{t_sid}.json"
                        if t_path.exists():
                            t_path.rename(t_path.with_name(f"{t_sid}.json.broken.{ts_q}"))
                    if attempt > 1:
                        log(
                            f"RETRY {name} attempt {attempt}/{MAX_PILOT_ATTEMPTS} (transient={transient}, bad={bad})"
                        )
                    proc = subprocess.Popen(
                        [
                            "bash",
                            "evals/unified/run_locked_pilot.sh",
                            MANIFEST_REL,
                            out_rel,
                            "1",
                            "A0",
                        ],
                        cwd=str(EVAL_REPO),
                        env=env,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.STDOUT,
                        text=True,
                    )
                    last_cnt = -1
                    while proc.poll() is None:
                        r1 = out_dir / "r1"
                        cnt = len(list(r1.glob("M*.json"))) if r1.exists() else 0
                        if cnt != last_cnt:
                            last_cnt = cnt
                            log(f"{name} (try {attempt}): {cnt}/{len(scenarios)} recorded")
                            state["progress"] = f"{cnt}/{len(scenarios)} (try {attempt})"
                            write_status(state)
                        time.sleep(2)

                    if proc.returncode != 0:
                        out_tail = (proc.stdout.read() if proc.stdout else "")[-500:]
                        err = f"{name} exited with rc={proc.returncode}: {out_tail}"
                        log(f"ERROR: {err}")
                        state["state"] = "FAILED"
                        state["error"] = err
                        write_status(state)
                        return 1

                    clean, bad, transient = check_arm_records(out_dir, scenarios)
                    if clean:
                        break
                    if not transient and bad:
                        err = f"{name}: non-transient record issue after rc=0: {bad}"
                        log(f"ERROR: {err}")
                        state["state"] = "FAILED"
                        state["error"] = err
                        write_status(state)
                        return 1

                if not clean:
                    err = f"{name}: still not clean after {MAX_PILOT_ATTEMPTS} attempts (bad={bad}, transient={transient})"
                    log(f"ERROR: {err}")
                    state["state"] = "FAILED"
                    state["error"] = err
                    write_status(state)
                    return 1

            det_pass = 0
            per_fam: dict[str, list[str]] = {}
            for row in scenarios:
                sid = row["scenario_id"]
                fid = row["family_id"]
                rec_path = out_dir / "r1" / f"{sid}.json"
                rec = json.loads(rec_path.read_text(encoding="utf-8"))
                oracle = json.loads((EVAL_REPO / row["oracle_fixture"]).read_text(encoding="utf-8"))
                sc = score(rec, oracle)
                v = sc["verdict"]
                if v == "PASS_DETERMINISTIC":
                    det_pass += 1
                per_fam.setdefault(fid, []).append(v)

            state["completed"].append(name)
            state["results"][name] = {
                "out_dir": out_rel,
                "det_pass": f"{det_pass}/{len(scenarios)}",
                "per_family": {
                    k: f"{v.count('PASS_DETERMINISTIC')}/2" for k, v in sorted(per_fam.items())
                },
            }
            write_status(state)
            log(
                f"DONE {name}: det={det_pass}/{len(scenarios)} | {state['results'][name]['per_family']}"
            )

        state["state"] = "COMPLETED_ALL_6"
        state["current"] = None
        state["progress"] = None
        write_status(state)
        log("ALL 6 LUNA-6 DIAGNOSTIC ARMS COMPLETED")
        return 0
    finally:
        if bridge_proc is not None and bridge_proc.poll() is None:
            try:
                os.killpg(bridge_proc.pid, signal.SIGTERM)
                bridge_proc.wait(timeout=5)
            except Exception:
                pass
            log("Stopped subscription_bridge cleanly")


if __name__ == "__main__":
    raise SystemExit(main())
