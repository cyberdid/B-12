"""Small current-code end-to-end pilot; not the historical 109-case benchmark."""
import asyncio
import hashlib
import json
from pathlib import Path
import platform
import subprocess
import sys
import time

OUT = Path(__file__).resolve().parent
ROOT = next((parent for parent in OUT.parents if (parent / "src/b12").is_dir() and (parent / "tests").is_dir()), None)
if ROOT is None:
    raise SystemExit("Reproduction requires the matching B-12 source snapshot.")
sys.path.insert(0, str(ROOT / "evals"))
import runner
from b12.config import Settings
from b12.model import OllamaModel

IDS = ("ua-fact-0", "tool-write-read-0", "memory-store-recall-0")


async def main():
    calibration = json.loads((OUT / "gemma-calibration-results.json").read_text())
    assert len(calibration) == 8 and all(row.get("exact_prompt_count") for row in calibration)
    assets = json.loads((OUT / "gemma-assets-preflight.json").read_text())
    cases = {case["id"]: case for case in runner.load_cases(set()) if case["id"] in IDS}
    assert len(cases) == 3
    (OUT / "pilot-cases.json").write_text(json.dumps(cases, ensure_ascii=False, indent=2) + "\n")
    settings = Settings(
        state_dir=OUT / "pilot-work/base", model="gemma4:12b",
        model_profile=OUT / "gemma4-12b-candidate-profile.json",
        tokenizer_dir=Path(assets["assets"]["tokenizer.json"]["local_path"]).parent,
        num_ctx=4096, output_tokens=128, temperature=0, top_p=1.0, seed=42,
        model_timeout_s=45, max_rounds=8, max_tool_calls=12,
        quiet_start="00:00", quiet_end="00:00",
    )
    meta = {
        "head": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        "host": platform.node(), "platform": platform.platform(), "python": sys.version,
        "model": settings.model, "profile": json.loads(settings.model_profile.read_text()),
        "case_ids": IDS, "repeats": 2, "contexts": [4096, 8192],
        "options": {"output_tokens": 128, "temperature": 0, "top_p": 1.0, "seed": 42,
                    "max_rounds": 8, "max_tool_calls": 12, "total_deadline_s": 240},
        "corpus_files_sha256": {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
                                for p in (ROOT / "evals/cases").glob("*.jsonl")},
        "scorer_sha256": hashlib.sha256((ROOT / "evals/scoring.py").read_bytes()).hexdigest(),
        "selection": "three hand-selected smoke scenarios; not representative or statistically independent",
        "historical_comparability": "different model, code, output budget and small selected corpus; do not compare aggregate scores",
        "cache": "first model call cold after calibration unload; subsequent requests may reuse caches; uncontrolled",
        "power_mode": "not measured", "operator_load": "ordinary desktop session, not controlled",
    }
    (OUT / "gemma-pilot-metadata.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n")
    observed = []
    deadline = time.monotonic() + 240
    model = OllamaModel(settings)
    try:
        for repeat in range(2):
            for identifier in IDS:
                for context in (4096, 8192):
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        return
                    active = settings.model_copy(update={"num_ctx": context})
                    try:
                        row = await asyncio.wait_for(
                            runner.run_case(cases[identifier], repeat, active, OUT / "pilot-work"),
                            timeout=remaining,
                        )
                    except asyncio.TimeoutError:
                        observed.append({"case": identifier, "repeat": repeat, "num_ctx": context,
                                         "status": "experiment-deadline", "passed": False})
                        return
                    observed.append(row)
                    (OUT / "gemma-pilot-results.json").write_text(json.dumps(observed, ensure_ascii=False, indent=2) + "\n")
                    print(identifier, context, repeat, row["passed"],
                          [(turn["state"], turn["error_code"]) for turn in row["turns"]], flush=True)
    finally:
        (OUT / "gemma-pilot-results.json").write_text(json.dumps(observed, ensure_ascii=False, indent=2) + "\n")
        (OUT / "gemma-pilot-cleanup.json").write_text(json.dumps({"unload_acknowledged": await model.unload(timeout_s=10)}, indent=2) + "\n")


if __name__ == "__main__":
    asyncio.run(main())
