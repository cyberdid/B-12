"""Opt-in real Bolt agent/tool run. Ordinary suite never connects to a model.

B12_REAL_MODEL=1 B12_TOKENIZER_DIR=/absolute/pinned/assets
B12_EVAL_DIR=/absolute/new/run uv run --no-sync pytest -m real_model -q -s \
    tests/e2e/test_bolt_tools.py
Effects are verified independently of assistant prose (disk bytes, canonical store).
Behavioral misses are recorded as failures in summary.json, never hidden. Artifacts
hold synthetic prompts, public replies, tool names/arguments/status and metrics only.
"""

import hashlib
import json
import os
import platform
import subprocess
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest

from b12.config import Settings
from b12.runtime import open_runtime

pytestmark = [
    pytest.mark.real_model,
    pytest.mark.skipif(
        os.environ.get("B12_REAL_MODEL") != "1", reason="explicit local model opt-in required"
    ),
]
REPEATS = 3
CAPABILITIES = (
    "system.read",
    "process.read",
    "filesystem.read",
    "filesystem.write",
    "process.execute",
    "memory.read",
    "memory.write",
    "knowledge.read",
    "time.read",
)


def command(*args):
    result = subprocess.run(args, capture_output=True, text=True, check=False)
    return {"returncode": result.returncode, "stdout": result.stdout.strip()}


def settings_for(state_dir: Path) -> Settings:
    root = Path(__file__).resolve().parents[2]
    return Settings(
        state_dir=state_dir,
        tokenizer_dir=Path(os.environ["B12_TOKENIZER_DIR"]),
        model_profile=root / "profiles/bolt-e4b-ollama-0.33.3.json",
        ollama_url=os.environ.get("B12_OLLAMA_URL", "http://127.0.0.1:11434"),
        num_ctx=4096,
        output_tokens=512,
    )


def owner(runtime):
    actor = runtime.control.create_actor(owner=True, consent=True)
    session = runtime.control.create_session(actor.id)
    task = runtime.control.create_task(session)
    grant = runtime.control.issue_grant(
        actor.id, session, CAPABILITIES, task_id=task, full_execution=True
    )
    return {"actor": actor, "session": session, "task": task, "grant": grant}


async def turn(runtime, who, text):
    result = await runtime.agent.turn(
        who["session"], who["grant"], text, task_id=who["task"], timeout_s=300
    )
    calls = [e.data for e in result.events if e.type == "tool_started"]
    return result, {
        "prompt": text,
        "state": result.state,
        "error_code": result.error_code,
        "content": result.content,
        "persisted": result.persisted,
        "calls": [{"name": c["name"], "arguments": c["arguments"]} for c in calls],
        "results": [
            {"name": r.name, "status": r.status, "error_code": r.error_code}
            for r in result.tool_results
        ],
        "events": [e.type for e in result.events],
        "terminal_events": sum(
            e.type in ("turn_completed", "turn_failed", "turn_cancelled") for e in result.events
        ),
    }


def completed(row, name):
    return any(r["name"] == name and r["status"] == "completed" for r in row["results"])


async def case_write_read(base, repeat):
    sandbox = base / "sandbox"
    sandbox.mkdir()
    target = sandbox / "b12-check.txt"
    expected = f"B12-ПЕРЕВІРКА-{7319 + repeat}"
    runtime = open_runtime(settings_for(base / "state"))
    try:
        _, row = await turn(
            runtime,
            owner(runtime),
            f"Створи файл {target} з точним текстом {expected} , потім прочитай цей "
            "файл інструментом file_read і повідом, що в ньому.",
        )
    finally:
        runtime.close()
    on_disk = target.read_text() if target.exists() else None
    writes = [
        call["arguments"].get("text")
        for call, result in zip(row["calls"], row["results"], strict=True)
        if call["name"] == "file_write" and result["status"] == "completed"
    ]
    row["effects"] = {
        "file_on_disk": on_disk,
        "disk_matches_last_completed_write": on_disk == writes[-1] if writes else on_disk is None,
    }
    row["behavior"] = {
        "wrote_expected_text": on_disk == expected,
        "used_file_read": completed(row, "file_read"),
        "final_mentions_text": expected in row["content"],
    }
    return row


async def case_system_info(base, repeat):
    runtime = open_runtime(settings_for(base / "state"))
    try:
        _, row = await turn(
            runtime,
            owner(runtime),
            "Скільки логічних процесорів у цій системі? Дізнайся через інструмент system_info.",
        )
    finally:
        runtime.close()
    row["effects"] = {"cpu_count": os.cpu_count()}
    row["behavior"] = {
        "used_system_info": completed(row, "system_info"),
        "final_mentions_cpu_count": str(os.cpu_count()) in row["content"],
    }
    return row


async def case_shell_ls(base, repeat):
    sandbox = base / "listing"
    sandbox.mkdir()
    for name in ("alpha.txt", "beta.txt"):
        (sandbox / name).write_text("synthetic")
    runtime = open_runtime(settings_for(base / "state"))
    try:
        _, row = await turn(
            runtime,
            owner(runtime),
            f"Виконай команду ls у каталозі {sandbox} через інструмент shell_exec "
            "і перелічи файли, які там є.",
        )
    finally:
        runtime.close()
    row["effects"] = {"unchanged_listing": sorted(p.name for p in sandbox.iterdir())}
    row["behavior"] = {
        "used_shell_exec": completed(row, "shell_exec"),
        "final_mentions_both": all(n in row["content"] for n in ("alpha.txt", "beta.txt")),
    }
    return row


async def case_memory_recall(base, repeat):
    settings = settings_for(base / "state")
    runtime = open_runtime(settings)
    try:
        who = owner(runtime)
        _, first = await turn(runtime, who, "Запам'ятай: мого тестового кота звати Бублик.")
        stored = [m.text for m in runtime.memory.search("Бублик", who["actor"])]
    finally:
        runtime.close()
    runtime = open_runtime(settings)  # process-level restart of every store
    try:
        _, second = await turn(runtime, who, "Як звати мого тестового кота?")
    finally:
        runtime.close()
    row = {"first": first, "second": second, "state": second["state"]}
    row["effects"] = {"canonical_records": stored}
    row["behavior"] = {
        "stored_memory": bool(stored),
        "recalled_after_restart": "Бублик" in second["content"],
    }
    row["terminal_events"] = first["terminal_events"] + second["terminal_events"] - 1
    row["error_code"] = second["error_code"] or first["error_code"]
    return row


CASES = {
    "write_read": case_write_read,
    "system_info": case_system_info,
    "shell_ls": case_shell_ls,
    "memory_recall": case_memory_recall,
}


async def test_real_bolt_agent_tool_tasks(tmp_path):
    root = Path(__file__).resolve().parents[2]
    run = Path(os.environ["B12_EVAL_DIR"])
    run.mkdir(parents=True, exist_ok=False)
    settings = settings_for(tmp_path / "probe")
    async with httpx.AsyncClient(trust_env=False) as client:
        show = (
            await client.post(settings.ollama_url + "/api/show", json={"model": settings.model})
        ).json()
        version = (await client.get(settings.ollama_url + "/api/version")).json()
    metadata = {
        "started_at": datetime.now(UTC).isoformat(),
        "host": platform.node(),
        "os": platform.platform(),
        "python": platform.python_version(),
        "runtime": version,
        "git": command("git", "rev-parse", "HEAD"),
        "dirty_diff_sha256": hashlib.sha256(
            subprocess.run(["git", "diff"], capture_output=True, check=True).stdout
        ).hexdigest(),
        "code_sha256": {
            str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(
                list((root / "src/b12").rglob("*.py"))
                + [Path(__file__).resolve(), root / "uv.lock", root / "pyproject.toml"]
            )
            if "_vendor" not in p.parts
        },
        "profile": json.loads(settings.model_profile.read_text()),
        "quantization": show["details"]["quantization_level"],
        "options": {"num_ctx": 4096, "num_predict": 512, "temperature": 0, "seed": 42},
        "gpu_before": command(
            "nvidia-smi",
            "--query-gpu=name,memory.total,memory.used,power.draw,pstate",
            "--format=csv,noheader",
        ),
        "power_mode": command("powerprofilesctl", "get"),
        "cache_state": "not cleared; first request cold, later warm/mixed prefix cache",
        "repeats": REPEATS,
        "tool_effects_executed": "temp sandbox files and harmless ls only",
        "reasoning_persisted": False,
    }
    (run / "metadata.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n")
    rows = []
    for name, case in CASES.items():
        for repeat in range(REPEATS):
            base = tmp_path / f"{name}-{repeat}"
            base.mkdir()
            started = datetime.now(UTC)
            row = await case(base, repeat)
            row.update(
                case=name,
                repeat=repeat,
                elapsed_s=(datetime.now(UTC) - started).total_seconds(),
            )
            rows.append(row)
            (run / f"{name}-{repeat}.json").write_text(
                json.dumps(row, ensure_ascii=False, indent=2) + "\n"
            )
            print(json.dumps({k: row[k] for k in ("case", "repeat", "state", "behavior")}))
    summary = {
        "cases": len(rows),
        "protocol_failures": [
            (r["case"], r["repeat"])
            for r in rows
            if r["terminal_events"] != 1 or r["error_code"] == "internal_error"
        ],
        "behavior_pass_rate": {
            name: {
                key: sum(r["behavior"][key] for r in rows if r["case"] == name) / REPEATS
                for key in next(r for r in rows if r["case"] == name)["behavior"]
            }
            for name in CASES
        },
        "behavior_failures": [
            {"case": r["case"], "repeat": r["repeat"], "missed": k}
            for r in rows
            for k, v in r["behavior"].items()
            if not v
        ],
        "finished_at": datetime.now(UTC).isoformat(),
    }
    (run / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n")
    (run / "SHA256.json").write_text(
        json.dumps(
            {
                p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                for p in sorted(run.iterdir())
                if p.name != "SHA256.json"
            },
            indent=2,
        )
        + "\n"
    )
    assert summary["protocol_failures"] == []
    for row in rows:
        if row["case"] == "write_read":
            assert row["effects"]["disk_matches_last_completed_write"]
