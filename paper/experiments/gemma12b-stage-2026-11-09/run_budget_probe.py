"""Run four interleaved arms using existing pytest fixtures, offline and without inference."""
from pathlib import Path
import json
import os
import subprocess
import sys

OUT = Path(__file__).resolve().parent
ROOT = next((parent for parent in OUT.parents if (parent / "src/b12").is_dir() and (parent / "tests").is_dir()), None)
if ROOT is None:
    raise SystemExit("Reproduction requires the matching B-12 source snapshot.")
TEST = "tests/integration/test_agent_loop.py::test_long_persist_turn_keeps_the_window_within_a_fixed_budget"
results = []
for repetition in range(1, 4):
    for arm in ("current", "head", "removed", "neutral"):
        target = OUT / f"{arm}-{repetition}.json"
        environment = os.environ.copy()
        environment.update({
            "PYTHONPATH": str(OUT) + os.pathsep + str(ROOT / "src"),
            "CAPRI_PROBE_ARM": arm, "CAPRI_PROBE_OUTPUT": str(target),
        })
        command = [
            sys.executable, "-m", "pytest", "-q", "-p", "budget_probe", TEST,
            "--basetemp=/tmp/capri-paper-budget-probe", f"--junitxml={OUT / f'{arm}-{repetition}.xml'}",
        ]
        with (OUT / f"{arm}-{repetition}.txt").open("w") as log:
            result = subprocess.run(command, cwd=ROOT, env=environment, stdout=log, stderr=subprocess.STDOUT)
        if result.returncode not in (0, 1) or not target.exists():
            raise SystemExit(f"Probe failed to run: {arm}-{repetition}; inspect its log")
        observation = json.loads(target.read_text())
        assert (result.returncode == 0) == observation["observed_character_check"]
        results.append({
            "arm": arm, "repetition": repetition, "pytest_exit_code": result.returncode,
            "system_prompt_chars": observation["system_prompt_chars"],
            "prefix_chars": observation["prefix_chars"], "prefix_utf8_bytes": observation["prefix_utf8_bytes"],
            "request_count": len(observation["requests"]),
            "last_request": observation["requests"][-1],
        })
        print(arm, repetition, result.returncode, observation["requests"][-1]["total_message_chars"], flush=True)
(OUT / "budget-results.json").write_text(json.dumps(results, indent=2) + "\n")
