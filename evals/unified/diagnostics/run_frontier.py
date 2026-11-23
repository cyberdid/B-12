#!/usr/bin/env python3
"""Run a frozen scenario set on a frontier model through the subscription bridge (no GPU).

    python evals/unified/diagnostics/run_frontier.py \
        --manifest evals/unified/scenario_sets/asof-live-v1.json --tag luna6 --repeats 3 \
        --arm baseline= --arm recall_as_of=--recall-as-of

Owner's testing order (23.11.2026): main tests on a frontier model first; gemma4:12b on Colab is
the acceptance run. Records are written by the same sandboxed runner as every other run, from
`B12_EVAL_REPO` (default `.worktrees/eval-run`, pin it first). Output directories are
`<set>-<tag>-<arm>-<date>` under `evals/capri_comprehensive/artifacts/`.

Known record quirks of the bridge: `model` says `gemma4:12b` (the runner's profile), `tokens_prompt`
is 0. Identify frontier runs by the directory tag. Judges for an OpenAI model: gemini + opus.
"""

from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import sys
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import run_luna_ports as luna  # noqa: E402  (bridge start, logging, eval repo path)

TRANSIENT = {"http_error", "transport_error", "transport_timeout", "deadline_exceeded"}
CLOUD_BASE = (
    "--variant deployed --model-timeout 230 --num-ctx 200000 --output-tokens 16384 "
    "--memory-temporal --goals-in-context"
)


def _transient_records(out_dir: Path) -> list[Path]:
    bad = []
    for path in out_dir.glob("r*/*.json"):
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            bad.append(path)
            continue
        if record.get("error_code") in TRANSIENT:
            bad.append(path)
    return bad


def run_arm(manifest: str, out_rel: str, repeats: int, flags: str, port: int) -> bool:
    env = {
        **os.environ,
        "B12_EVAL_OLLAMA_URL": f"http://127.0.0.1:{port}",
        "B12_EVAL_MODEL": "gemma4:12b",
        "B12_EVAL_VARIANT": "deployed",
        "NO_GPU_WAIT": "1",
        "EXTRA_RUNNER_ARGS": f"{CLOUD_BASE} {flags}".strip(),
    }
    out_dir = luna.EVAL_REPO / out_rel
    for attempt in range(1, 5):
        luna.log(f"{out_rel}: attempt {attempt} ({flags or 'control'})")
        subprocess.run(
            ["bash", "evals/unified/run_locked_pilot.sh", manifest, out_rel, str(repeats), "A0"],
            cwd=str(luna.EVAL_REPO),
            env=env,
            check=False,
        )
        # run_locked_pilot sets transient-error records aside and re-runs them on the next call.
        if not _transient_records(out_dir):
            return True
    luna.log(f"{out_rel}: transient errors remain after 4 attempts")
    return False


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--tag", default="luna6")
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--arm", action="append", required=True, help="NAME=RUNNER FLAGS")
    parser.add_argument("--date", default=date.today().isoformat())
    args = parser.parse_args(argv)

    set_id = json.loads((luna.EVAL_REPO / args.manifest).read_text(encoding="utf-8"))["set_id"]
    bridge = luna.start_bridge()
    ok = True
    try:
        for spec in args.arm:
            name, _, flags = spec.partition("=")
            out_rel = f"evals/capri_comprehensive/artifacts/{set_id}-{args.tag}-{name}-{args.date}"
            ok &= run_arm(args.manifest, out_rel, args.repeats, flags, luna.BRIDGE_PORT)
    finally:
        if bridge is not None and bridge.poll() is None:
            os.killpg(bridge.pid, signal.SIGTERM)
            bridge.wait(timeout=5)
            luna.log("bridge stopped")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
