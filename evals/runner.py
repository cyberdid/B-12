"""Resumable B-12 eval runner against the real local model.

  python evals/runner.py --out /abs/run --profile /abs/profile.json --tokenizer /abs/assets \
      [--repeats 5] [--num-ctx 4096] [--categories ua,tools] [--latency]
Each (case, repeat, num_ctx) runs in a fresh state directory with its own sandbox;
results.jsonl is appended per run and skipped on resume. Failures stay in the report.
"""

import argparse
import asyncio
import hashlib
import json
import os
import platform
import shutil
import statistics
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from scoring import evaluate, substitute  # noqa: E402

from b12.auth import HOST_CAPABILITIES  # noqa: E402
from b12.config import Settings  # noqa: E402
from b12.runtime import open_runtime  # noqa: E402

CASES = Path(__file__).parent / "cases"


def load_cases(categories):
    items = []
    for path in sorted(CASES.glob("*.jsonl")):
        for line in path.read_text().splitlines():
            item = json.loads(line)
            if not categories or item["category"] in categories:
                items.append(item)
    return items


def control_state(runtime, granted):
    rows = runtime.control.db.execute("SELECT id, owner, consent, revision FROM actors").fetchall()
    grants = runtime.control.db.execute("SELECT id, capabilities, revoked FROM grants").fetchall()
    return {
        "actors": sorted(tuple(r) for r in rows),
        "grants": sorted(tuple(g) for g in grants if g[0] not in granted),
    }


async def run_case(case, repeat, settings_base, work):
    root = work / f"{case['id']}-{repeat}-{settings_base.num_ctx}"
    shutil.rmtree(root, ignore_errors=True)
    sandbox = root / "sandbox"
    sandbox.mkdir(parents=True)
    mapping = {"sandbox": sandbox, "cpu_count": os.cpu_count(), "year": datetime.now(UTC).year}
    case = substitute(case, mapping)
    settings = settings_base.model_copy(update={"state_dir": root / "state"})
    runtime = open_runtime(settings)
    granted = set()
    try:
        actor = runtime.control.create_actor(owner=True, consent=case.get("consent", True))
        if case.get("other_actor_memories"):
            other = runtime.control.create_actor(consent=True)
            for text in case["other_actor_memories"]:
                runtime.memory.remember(text, other)
        for text in case.get("memories", []):
            runtime.memory.remember(text, actor)
        for name, content in case.get("files", {}).items():
            (sandbox / name).write_text(content)
        for name, content in case.get("documents", {}).items():
            doc = sandbox / "docs" / name
            doc.parent.mkdir(exist_ok=True)
            doc.write_text(content)
            runtime.knowledge.index_document(doc, actor)
        before = control_state(runtime, granted)
        session = runtime.control.create_session(actor.id)
        turns = []
        for text in case["turns"]:
            if case.get("new_session_each_turn"):
                session = runtime.control.create_session(actor.id)
            task = runtime.control.create_task(session)
            grant = runtime.control.issue_grant(
                actor.id, session, HOST_CAPABILITIES["full"], task_id=task, full_execution=True
            )
            granted.add(grant)
            started = time.monotonic()
            result = await runtime.agent.turn(session, grant, text, task_id=task, timeout_s=240)
            calls = [e.data for e in result.events if e.type == "tool_started"]
            turns.append(
                {
                    "prompt": text,
                    "state": result.state,
                    "error_code": result.error_code,
                    "content": result.content,
                    "calls": [{"name": c["name"], "arguments": c["arguments"]} for c in calls],
                    "results": [
                        {"name": r.name, "status": r.status, "error_code": r.error_code}
                        for r in result.tool_results
                    ],
                    "model_metrics": [dict(m) for m in result.model_metrics],
                    "elapsed_s": time.monotonic() - started,
                }
            )
        memories = []
        if actor.consent:
            memories = [r.text for r in runtime.memory.recent(actor, limit=200)]
        world = {
            "memories": memories,
            "memory_count": runtime.memory._connection.execute(
                "SELECT COUNT(*) FROM memories WHERE actor_id=?", (actor.id,)
            ).fetchone()[0],
            "control_before": before,
            "control_after": control_state(runtime, granted),
        }
        checks = []
        for check in case["checks"]:
            passed, detail = evaluate(check, turns, world)
            checks.append({"check": check, "passed": passed, "detail": detail})
    finally:
        runtime.close()
    passed = all(c["passed"] for c in checks)
    if passed:
        shutil.rmtree(root, ignore_errors=True)
    return {
        "case": case["id"],
        "category": case["category"],
        "repeat": repeat,
        "num_ctx": settings_base.num_ctx,
        "multi_step": bool(case.get("multi_step")),
        "passed": passed,
        "checks": checks,
        "turns": turns,
        "human_rubric": {"naturalness": None, "helpfulness": None, "notes": None},
    }


async def latency_suite(settings_base, work, out):
    from b12.model import OllamaModel

    await OllamaModel(settings_base).unload()
    runtime = open_runtime(settings_base.model_copy(update={"state_dir": work / "latency"}))
    rows = []
    try:
        actor = runtime.control.create_actor(owner=True, consent=True)
        session = runtime.control.create_session(actor.id)
        for index in range(6):
            task = runtime.control.create_task(session)
            grant = runtime.control.issue_grant(actor.id, session, ("time.read",), task_id=task)
            result = await runtime.agent.turn(
                session, grant, f"Скажи одне слово: привіт {index}", task_id=task
            )
            metrics = result.model_metrics[0] if result.model_metrics else {}
            rows.append(
                {
                    "index": index,
                    "cache": "cold" if index == 0 else "warm",
                    "state": result.state,
                    "ttft_s": metrics.get("ttft_s"),
                    "load_duration_ns": metrics.get("load_duration"),
                    "prompt_eval_count": metrics.get("prompt_eval_count"),
                    "prompt_eval_cached_count": metrics.get("prompt_eval_cached_count"),
                    "elapsed_s": metrics.get("elapsed_s"),
                }
            )
    finally:
        runtime.close()
    (out / f"latency-ctx{settings_base.num_ctx}.json").write_text(json.dumps(rows, indent=2))
    return rows


def summarize(out: Path):
    rows = [json.loads(line) for line in (out / "results.jsonl").read_text().splitlines()]
    summary = {"runs": len(rows), "by_ctx": {}}
    for ctx in sorted({r["num_ctx"] for r in rows}):
        selected = [r for r in rows if r["num_ctx"] == ctx]
        categories = {}
        for row in selected:
            bucket = categories.setdefault(row["category"], {"runs": 0, "passed": 0})
            bucket["runs"] += 1
            bucket["passed"] += row["passed"]
        ttft = [
            t["model_metrics"][0]["ttft_s"]
            for r in selected
            for t in r["turns"]
            if t["model_metrics"] and t["model_metrics"][0].get("ttft_s") is not None
        ]
        elapsed = [t["elapsed_s"] for r in selected for t in r["turns"]]
        multi = [r for r in selected if r["multi_step"]]
        summary["by_ctx"][str(ctx)] = {
            "runs": len(selected),
            "cases": len({r["case"] for r in selected}),
            "passed": sum(r["passed"] for r in selected),
            "pass_rate": sum(r["passed"] for r in selected) / len(selected),
            "by_category": categories,
            "multi_step_tool_runs": len(multi),
            "multi_step_passed": sum(r["passed"] for r in multi),
            "protocol_errors": sorted(
                {
                    t["error_code"]
                    for r in selected
                    for t in r["turns"]
                    if t["error_code"] and t["state"] == "failed"
                }
            ),
            "ttft_s": {
                "p50": statistics.median(ttft) if ttft else None,
                "p95": sorted(ttft)[int(len(ttft) * 0.95)] if ttft else None,
            },
            "turn_elapsed_s": {
                "p50": statistics.median(elapsed) if elapsed else None,
                "p95": sorted(elapsed)[int(len(elapsed) * 0.95)] if elapsed else None,
            },
            "failed": [
                {
                    "case": r["case"],
                    "repeat": r["repeat"],
                    "failed_checks": [
                        c["check"]["type"] + ":" + c["detail"]
                        for c in r["checks"]
                        if not c["passed"]
                    ],
                }
                for r in selected
                if not r["passed"]
            ],
        }
    (out / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2))
    return summary


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True)
    parser.add_argument("--profile", required=True)
    parser.add_argument("--tokenizer", required=True)
    parser.add_argument("--repeats", type=int, default=5)
    parser.add_argument("--num-ctx", type=int, default=4096)
    parser.add_argument("--categories", default="")
    parser.add_argument("--latency", action="store_true")
    args = parser.parse_args()
    out = Path(args.out).absolute()
    out.mkdir(parents=True, exist_ok=True)
    work = out / "work"
    settings = Settings(
        state_dir=work / "base",
        model_profile=Path(args.profile),
        tokenizer_dir=Path(args.tokenizer),
        num_ctx=args.num_ctx,
        output_tokens=512,
        quiet_start="00:00",
        quiet_end="00:00",
    )
    root = Path(__file__).resolve().parents[1]
    meta = out / f"metadata-ctx{args.num_ctx}.json"
    if not meta.exists():
        meta.write_text(
            json.dumps(
                {
                    "started_at": datetime.now(UTC).isoformat(),
                    "host": platform.node(),
                    "os": platform.platform(),
                    "git": subprocess.run(
                        ["git", "rev-parse", "HEAD"], capture_output=True, text=True, cwd=root
                    ).stdout.strip(),
                    "dirty_diff_sha256": hashlib.sha256(
                        subprocess.run(["git", "diff"], capture_output=True, cwd=root).stdout
                    ).hexdigest(),
                    "cases_sha256": {
                        p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                        for p in sorted(CASES.glob("*.jsonl"))
                    },
                    "profile": json.loads(Path(args.profile).read_text()),
                    "options": {
                        "num_ctx": args.num_ctx,
                        "num_predict": 512,
                        "temperature": 0,
                        "seed": 42,
                    },
                    "repeats": args.repeats,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    if args.latency:
        print(json.dumps(await latency_suite(settings, work, out), indent=2))
        return
    results = out / "results.jsonl"
    done = set()
    if results.exists():
        for line in results.read_text().splitlines():
            row = json.loads(line)
            done.add((row["case"], row["repeat"], row["num_ctx"]))
    categories = {c for c in args.categories.split(",") if c}
    for case in load_cases(categories):
        for repeat in range(min(args.repeats, case.get("repeats", args.repeats))):
            if (case["id"], repeat, args.num_ctx) in done:
                continue
            row = await run_case(case, repeat, settings, work)
            with results.open("a") as handle:
                handle.write(json.dumps(row, ensure_ascii=False) + "\n")
            print(
                f"{row['case']} r{repeat} ctx{args.num_ctx}: {'PASS' if row['passed'] else 'FAIL'}",
                flush=True,
            )
    print(
        json.dumps(summarize(out)["by_ctx"][str(args.num_ctx)], ensure_ascii=False, indent=2)[:3000]
    )


if __name__ == "__main__":
    asyncio.run(main())
