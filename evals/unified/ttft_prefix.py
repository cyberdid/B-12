"""Measure TTFT on 20 cold and 20 warm Ollama turns for baseline vs stable_prefix (H5).

Intended for Colab/deployment measurement only — never run against the owner's local GPU.
Records TTFT P50/P95, host, OS, git commit, model digest, profile revision and num_ctx.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import platform
import statistics
import subprocess
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from b12.auth import owner_capabilities
from b12.config import Settings
from b12.model_profile import ModelProfile
from b12.runtime import open_runtime

_BASE_DAY = datetime(2026, 12, 1, 8, 0, tzinfo=UTC)


def _pct(values: list[float], q: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, round(q * (len(ordered) - 1))))
    return round(ordered[index], 3)


def _git_commit() -> str:
    try:
        done = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        return done.stdout.strip() or "unknown"
    except OSError:
        return "unknown"


def _summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    ttfts = [r["ttft_ms"] for r in rows if isinstance(r.get("ttft_ms"), (int, float))]
    cached = [
        r["prompt_eval_cached_count"]
        for r in rows
        if isinstance(r.get("prompt_eval_cached_count"), int)
    ]
    loads = [
        r["load_duration_ms"] for r in rows if isinstance(r.get("load_duration_ms"), (int, float))
    ]
    return {
        "count": len(rows),
        "completed": sum(1 for r in rows if r.get("state") == "completed"),
        "ttft_ms_p50": round(statistics.median(ttfts), 3) if ttfts else None,
        "ttft_ms_p95": _pct(ttfts, 0.95),
        "prompt_eval_cached_count_mean": round(statistics.mean(cached), 2) if cached else None,
        "load_duration_ms_p50": round(statistics.median(loads), 3) if loads else None,
    }


def _ns_to_ms(value: Any) -> float | None:
    if isinstance(value, (int, float)):
        return round(float(value) / 1_000_000.0, 3)
    return None


async def _run_series(
    settings: Settings,
    work_dir: Path,
    *,
    stable_prefix: bool,
    cache_state: str,
    turns: int,
) -> list[dict[str, Any]]:
    rt = open_runtime(
        settings.model_copy(
            update={
                "state_dir": work_dir,
                "stable_prefix": stable_prefix,
                "memory_temporal": True,
                "goals_in_context": True,
                "preference_rules": True,
                "host_access": "none",
                "memory_enrichment": False,
                "embedding_python": None,
            }
        )
    )
    rows: list[dict[str, Any]] = []
    try:
        actor = rt.control.create_actor(owner=True, consent=True)
        session = rt.control.create_session(actor.id)
        rt.memory.remember(
            "Пояснюй технічне коротко та без зайвих вступів.",
            actor,
            kind="preference",
            origin="explicit",
        )
        rt.goals.set_preference(actor.id, "reply_style", "concise", "ttft_prefix")

        if cache_state == "warm":
            # Prime residency and KV prefix before the 20 measured warm turns.
            rt.agent.clock = lambda: _BASE_DAY
            warm_task = rt.control.create_task(session)
            warm_grant = rt.control.issue_grant(
                actor.id, session, owner_capabilities(rt.settings), task_id=warm_task, ttl_s=600
            )
            await rt.agent.turn(
                session,
                warm_grant,
                "Прогрів моделі перед вимірюванням.",
                task_id=warm_task,
                timeout_s=300,
                companion_profile={"name": "Користувач", "style_note": "ділово"},
            )

        for idx in range(turns):
            if cache_state == "cold":
                await rt.agent.reset_provider()
                turn_session = rt.control.create_session(actor.id)
            else:
                turn_session = session
            rt.agent.clock = lambda i=idx: _BASE_DAY + timedelta(days=i % 5)
            rt.goals.set_preference(actor.id, "step", str(idx), "ttft_prefix")
            if idx % 4 == 0:
                rt.goals.create(actor.id, turn_session, f"Задача {idx}", "звіт")
            task = rt.control.create_task(turn_session)
            grant = rt.control.issue_grant(
                actor.id, turn_session, owner_capabilities(rt.settings), task_id=task, ttl_s=600
            )
            result = await rt.agent.turn(
                turn_session,
                grant,
                f"Крок вимірювання {idx}: дай коротку відповідь одним реченням.",
                task_id=task,
                timeout_s=300,
                companion_profile={"name": "Користувач", "style_note": f"нотатка {idx}"},
            )
            metric = result.model_metrics[0] if result.model_metrics else {}
            ttft_s = metric.get("ttft_s")
            elapsed_s = metric.get("elapsed_s")
            rows.append(
                {
                    "turn_index": idx,
                    "cache_state": cache_state,
                    "stable_prefix": stable_prefix,
                    "state": result.state,
                    "error_code": result.error_code,
                    "ttft_ms": round(ttft_s * 1000.0, 3) if ttft_s is not None else None,
                    "elapsed_ms": round(elapsed_s * 1000.0, 3) if elapsed_s is not None else None,
                    "prompt_eval_count": metric.get("prompt_eval_count"),
                    "prompt_eval_cached_count": metric.get("prompt_eval_cached_count"),
                    "prompt_eval_duration_ms": _ns_to_ms(metric.get("prompt_eval_duration")),
                    "load_duration_ms": _ns_to_ms(metric.get("load_duration")),
                    "eval_count": metric.get("eval_count"),
                    "eval_duration_ms": _ns_to_ms(metric.get("eval_duration")),
                    "total_duration_ms": _ns_to_ms(metric.get("total_duration")),
                }
            )
    finally:
        rt.close()
    return rows


async def measure_ttft_prefix(
    settings: Settings,
    *,
    turns: int = 20,
    stable_prefix_modes: tuple[bool, ...] = (False, True),
    label: str = "colab-only",
) -> dict[str, Any]:
    """Run warm and cold TTFT series across baseline/stable_prefix modes and return JSON report."""
    profile = ModelProfile(settings)
    runs: list[dict[str, Any]] = []
    summary: dict[str, dict[str, Any]] = {}

    with tempfile.TemporaryDirectory(prefix="b12-ttft-") as tmp:
        root = Path(tmp)
        for stable in stable_prefix_modes:
            mode_key = "stable_prefix" if stable else "baseline"
            summary[mode_key] = {}
            for cache_state in ("cold", "warm"):
                part = await _run_series(
                    settings,
                    root / f"{mode_key}-{cache_state}",
                    stable_prefix=stable,
                    cache_state=cache_state,
                    turns=turns,
                )
                runs.extend(part)
                summary[mode_key][cache_state] = _summarize(part)

    return {
        "host": platform.node() or "unknown",
        "os": platform.platform(),
        "git_commit": _git_commit(),
        "model": settings.model,
        "model_digest": profile.spec.manifest_digest,
        "profile_revision": profile.spec.revision,
        "num_ctx": settings.num_ctx,
        "output_tokens": settings.output_tokens,
        "turns_per_state": turns,
        "ollama_url": settings.ollama_url,
        "label": label,
        "summary": summary,
        "runs": runs,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--model", required=True)
    parser.add_argument("--ollama-url", default="http://127.0.0.1:11434")
    parser.add_argument("--model-profile", type=Path, required=True)
    parser.add_argument("--tokenizer-dir", type=Path, required=True)
    parser.add_argument("--num-ctx", type=int, default=8192)
    parser.add_argument("--output-tokens", type=int, default=512)
    parser.add_argument("--turns", type=int, default=20)
    parser.add_argument("--mode", choices=("both", "baseline", "stable_prefix"), default="both")
    parser.add_argument("--label", default="colab-only")
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args(argv)

    modes = {
        "both": (False, True),
        "baseline": (False,),
        "stable_prefix": (True,),
    }[args.mode]

    with tempfile.TemporaryDirectory(prefix="b12-ttft-cfg-") as cfg_dir:
        settings = Settings(
            state_dir=Path(cfg_dir) / "state",
            model=args.model,
            ollama_url=args.ollama_url,
            model_profile=args.model_profile,
            tokenizer_dir=args.tokenizer_dir,
            num_ctx=args.num_ctx,
            output_tokens=args.output_tokens,
        )
        report = asyncio.run(
            measure_ttft_prefix(
                settings,
                turns=args.turns,
                stable_prefix_modes=modes,
                label=args.label,
            )
        )

    encoded = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.out is not None:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(encoded, encoding="utf-8")
    else:
        print(encoded, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
