"""Controlled A/B: the persona's brevity sentence (control) vs an explicit length rule (treatment).

Same code, model (Bolt), scenarios and seeds; only one persona sentence differs. Runs through
the real runtime (RuntimeTurnExecutor) and must run inside the bubblewrap sandbox.
Usage: python brevity_ab.py OUT_DIR REPEATS
"""
import json
import os
import re
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.getcwd())
from b12 import agent as agent_module  # noqa: E402
from evals.capri_comprehensive.evaluators.schema import ScenarioDefinition  # noqa: E402
from evals.capri_comprehensive.runners.runner import ScenarioRunner  # noqa: E402
from evals.capri_comprehensive.runners.runtime_executor import RuntimeTurnExecutor  # noqa: E402

CONTROL = "У побуті будь лаконічною; складні й технічні відповіді давай точно та повно. "
TREATMENT = (
    "У побуті будь лаконічною: на привітання, питання про тебе, втому чи емоції "
    "відповідай 1–3 короткими реченнями (до ~300 символів), без списків і заголовків. "
    "Складні й технічні відповіді, звіти та аналіз давай точно та повно. "
)
assert CONTROL in agent_module.SYSTEM_PROMPT
ARMS = {"control": agent_module.SYSTEM_PROMPT,
        "treatment": agent_module.SYSTEM_PROMPT.replace(CONTROL, TREATMENT)}
SCENARIOS = ["INT-01", "INT-02", "INT-03", "INT-04", "INT-05", "INT-06", "INT-07", "INT-08",
             "VOI-01", "VOI-03", "LT-08", "RE-01", "RE-04", "RE-07", "AUT-02", "MEM-01", "MEM-07"]
ROOT = Path("evals/capri_comprehensive/scenarios")


class ArmExecutor(RuntimeTurnExecutor):
    def __init__(self, base, system_prompt):
        super().__init__(base)
        self.system_prompt = system_prompt

    def run_turn(self, turn, turn_index, world_state):
        self.runtime.agent.system_prompt = self.system_prompt
        return super().run_turn(turn, turn_index, world_state)


def cyrillic_share(text):
    letters = re.findall(r"[^\W\d_]", text)
    return sum("а" <= c.lower() <= "я" or c.lower() in "іїєґ" for c in letters) / max(1, len(letters))


def main(out, repeats):
    out.mkdir(parents=True, exist_ok=True)
    rows = []
    for rep in range(repeats):
        for arm, prompt in ARMS.items():
            base = Path(tempfile.mkdtemp(prefix=f"ab-{arm}-"))
            runner = ScenarioRunner(artifacts_dir=out / "artifacts" / f"{arm}-{rep}",
                                    turn_executor=ArmExecutor(base, prompt))
            for sid in SCENARIOS:
                sc = ScenarioDefinition.from_yaml_file(next(ROOT.glob(f"*/{sid}.yaml")))
                report = runner.run(sc)
                for t in report.turn_results:
                    text = t.response_content or ""
                    rows.append({
                        "repeat": rep, "arm": arm, "scenario": sid, "turn": t.turn_index,
                        "passed_scenario": report.all_passed, "chars": len(text),
                        "tool_calls": len(t.tool_calls), "cyrillic_share": round(cyrillic_share(text), 3),
                        "failed": [a.detail[:160] for a in t.failed_assertions],
                    })
                print(rep, arm, sid, "PASS" if report.all_passed else "FAIL", flush=True)
    text = json.dumps(rows, ensure_ascii=False, indent=1).replace(str(Path.home()), "~")
    (out / "brevity_ab_rows.json").write_text(text, encoding="utf-8")


if __name__ == "__main__":
    os.environ["B12_EVAL_SANDBOX"] = "1"
    main(Path(sys.argv[1]), int(sys.argv[2]))
