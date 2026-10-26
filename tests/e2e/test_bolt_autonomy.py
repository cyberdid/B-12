"""Opt-in real Bolt autonomy: bounded synthetic goal experiment and reflection.

B12_REAL_MODEL=1 B12_TOKENIZER_DIR=/abs/assets B12_EVAL_DIR=/abs/new/run \
    uv run --no-sync pytest -m real_model -q -s tests/e2e/test_bolt_autonomy.py
Goal completion is decided only by the trusted file check; reflection outcomes are
recorded as they are (recorded / rejected), never forced.
"""

import hashlib
import json
import os
import subprocess
from datetime import UTC, datetime
from pathlib import Path

import pytest

from b12.config import Settings

pytestmark = [
    pytest.mark.real_model,
    pytest.mark.skipif(
        os.environ.get("B12_REAL_MODEL") != "1", reason="explicit local model opt-in required"
    ),
]
REPEATS = 3


def settings_for(state_dir: Path) -> Settings:
    root = Path(__file__).resolve().parents[2]
    return Settings(
        state_dir=state_dir,
        tokenizer_dir=Path(os.environ["B12_TOKENIZER_DIR"]),
        model_profile=root / "profiles/bolt-e4b-ollama-0.33.3.json",
        num_ctx=4096,
        output_tokens=512,
        quiet_start="00:00",
        quiet_end="00:00",
    )


async def run_case(base: Path, repeat: int) -> dict:
    from b12.autonomy import Scheduler
    from b12.reflection import Reflector
    from b12.runtime import open_runtime

    runtime = open_runtime(settings_for(base / "state"))
    scheduler = Scheduler(runtime)
    try:
        actor = runtime.control.create_actor(owner=True, consent=True)
        target = base / "sandbox" / "experiment.txt"
        target.parent.mkdir()
        expected = f"температура={20 + repeat}"
        goal = runtime.goals.create(
            actor.id,
            runtime.control.create_session(actor.id),
            f"Синтетичний експеримент: запиши у файл {target} рядок '{expected}'.",
            "Файл існує і містить точний рядок.",
            allowed_tools=("filesystem.read", "filesystem.write", "time.read"),
            budget_turns=2,
            review_interval_s=30,
            check={"kind": "file_contains", "path": str(target), "text": expected},
        )
        outcomes = await scheduler.tick()
        after = runtime.goals.get(goal["id"], actor.id)
        for text in (
            "Власник щоранку о 7:30 перевіряє логи сервера.",
            "Власник просить короткі звіти без води.",
            "Власник двічі відклав довгі звіти на вечір.",
        ):
            runtime.memory.remember(text, actor)
        reflection = await Reflector(runtime).reflect(actor)
        reflected = None
        if reflection["state"] == "recorded":
            [record] = [r for r in runtime.memory.recent(actor) if r.kind == "reflection"]
            reflected = {"text": record.text, "evidence_ids": list(record.evidence_ids)}
        return {
            "repeat": repeat,
            "goal_outcomes": outcomes,
            "goal_status": after["status"],
            "consumed_turns": after["consumed_turns"],
            "checkpoint": after["checkpoint"],
            "file_on_disk": target.read_text() if target.exists() else None,
            "check_passes_independently": target.exists() and expected in target.read_text(),
            "reflection": reflection,
            "reflection_record": reflected,
            "proposals": runtime.goals.proposals(actor.id),
        }
    finally:
        scheduler.close()
        runtime.close()


async def test_real_bolt_bounded_experiment_and_reflection(tmp_path):
    root = Path(__file__).resolve().parents[2]
    run = Path(os.environ["B12_EVAL_DIR"])
    run.mkdir(parents=True, exist_ok=False)
    git = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True).stdout
    dirty = subprocess.run(["git", "diff"], capture_output=True, check=True).stdout
    metadata = {
        "started_at": datetime.now(UTC).isoformat(),
        "git": git.strip(),
        "dirty_diff_sha256": hashlib.sha256(dirty).hexdigest(),
        "profile": json.loads((root / "profiles/bolt-e4b-ollama-0.33.3.json").read_text()),
        "options": {"num_ctx": 4096, "num_predict": 512, "temperature": 0, "seed": 42},
        "repeats": REPEATS,
    }
    (run / "metadata.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n")
    rows = []
    for repeat in range(REPEATS):
        base = tmp_path / str(repeat)
        base.mkdir()
        row = await run_case(base, repeat)
        rows.append(row)
        (run / f"case-{repeat}.json").write_text(
            json.dumps(row, ensure_ascii=False, indent=2) + "\n"
        )
        print(json.dumps({k: row[k] for k in ("repeat", "goal_status")} | row["reflection"]))
    summary = {
        "achieved": sum(r["goal_status"] == "achieved" for r in rows),
        "achieved_without_check": sum(
            r["goal_status"] == "achieved" and not r["check_passes_independently"] for r in rows
        ),
        "reflections_recorded": sum(r["reflection"]["state"] == "recorded" for r in rows),
        "reflection_outcomes": [r["reflection"] for r in rows],
        "finished_at": datetime.now(UTC).isoformat(),
    }
    (run / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n")
    assert summary["achieved_without_check"] == 0
    for row in rows:
        assert row["consumed_turns"] <= 2
