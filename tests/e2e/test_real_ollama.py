"""Opt-in local calibration. Ordinary suite never connects to a model or downloads.

B12_REAL_MODEL=1 B12_TOKENIZER_DIR=/absolute/pinned/assets
B12_CALIBRATION_DIR=/absolute/new/run uv run --no-sync pytest -m real_model -q -s
Artifacts contain synthetic requests, public replies and numeric metrics only.
"""

import hashlib
import json
import os
import platform
import statistics
import subprocess
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest

from b12.config import Settings
from b12.context import ContextBuilder
from b12.model import OllamaModel

pytestmark = [
    pytest.mark.real_model,
    pytest.mark.skipif(
        os.environ.get("B12_REAL_MODEL") != "1", reason="explicit local model opt-in required"
    ),
]


def tool(name="calculate_product", description="Добуток двох цілих чисел."):
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {
                "type": "object",
                "properties": {"a": {"type": "integer"}, "b": {"type": "integer"}},
                "required": ["a", "b"],
            },
        },
    }


def command(*args):
    result = subprocess.run(args, capture_output=True, text=True, check=False)
    return {"returncode": result.returncode, "stdout": result.stdout.strip()}


async def test_real_profile_calibration_and_boundary_instructions(tmp_path):
    root = Path(__file__).resolve().parents[2]
    assets = Path(os.environ["B12_TOKENIZER_DIR"])
    run = Path(os.environ["B12_CALIBRATION_DIR"])
    run.mkdir(parents=True, exist_ok=False)
    settings = Settings(
        state_dir=tmp_path,
        tokenizer_dir=assets,
        model_profile=root / "profiles/bolt-e4b-ollama-0.33.3.json",
        ollama_url=os.environ.get("B12_OLLAMA_URL", "http://127.0.0.1:11434"),
        num_ctx=4096,
        output_tokens=128,
    )
    async with httpx.AsyncClient(trust_env=False) as client:
        before = (
            await client.post(settings.ollama_url + "/api/show", json={"model": settings.model})
        ).json()
        version = (await client.get(settings.ollama_url + "/api/version")).json()
    metadata = {
        "started_at": datetime.now(UTC).isoformat(),
        "host": platform.node(),
        "os": platform.platform(),
        "python": platform.python_version(),
        "runtime": version,
        "code_sha256": {
            str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(
                list((root / "src/b12").glob("*.py"))
                + [Path(__file__).resolve(), root / "uv.lock", root / "pyproject.toml"]
            )
        },
        "git": command("git", "rev-parse", "HEAD"),
        "dirty_diff_sha256": hashlib.sha256(
            subprocess.run(["git", "diff"], capture_output=True, check=True).stdout
        ).hexdigest(),
        "profile": json.loads(settings.model_profile.read_text()),
        "source_gguf_sha256": "c8af2b8aea10a690a1d9491db744a9446660173cb38fc489612b556615a69612",
        "imported_blob_sha256": "49eca097c81e38013c4a6278ade7d8541f4a50918000ee16f73ee151ca01c8bc",
        "quantization": before["details"]["quantization_level"],
        "gpu_before": command(
            "nvidia-smi",
            "--query-gpu=name,memory.total,memory.used,power.draw,power.limit,pstate",
            "--format=csv,noheader",
        ),
        "power_mode": command("powerprofilesctl", "get"),
        "alias_parameters_before": before["parameters"],
        "cache_state": "not cleared; first request may be cold; later warm/mixed prefix cache",
        "tool_effects_executed": False,
        "reasoning_persisted": False,
    }
    (run / "metadata.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n")
    cases = [
        (
            "ua_emoji",
            "Ти B-12. Виконуй інструкцію користувача буквально.",
            [{"role": "user", "content": "Українська ї є ґ 🤖🌍. Відповідай лише: ГОТОВО"}],
            [],
            "ГОТОВО",
        ),
        (
            "schema_heavy",
            "Не викликай інструменти. Відповідай лише словом ПЕРЕВІРЕНО.",
            [{"role": "user", "content": "Підтверди одним словом."}],
            [tool(f"synthetic_{i}", "Синтетична схема. " + "опис " * 10) for i in range(12)],
            "ПЕРЕВІРЕНО",
        ),
        (
            "multi_round",
            "Використовуй надані результати. Поверни тільки кінцеве число.",
            [
                {"role": "user", "content": "Помнож 17 на 23, потім результат на 2."},
                {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [
                        {
                            "id": "round1",
                            "type": "function",
                            "function": {
                                "name": "calculate_product",
                                "arguments": {"a": 17, "b": 23},
                            },
                        }
                    ],
                },
                {
                    "role": "tool",
                    "tool_name": "calculate_product",
                    "tool_call_id": "round1",
                    "content": '{"product":391}',
                },
                {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [
                        {
                            "id": "round2",
                            "type": "function",
                            "function": {
                                "name": "calculate_product",
                                "arguments": {"a": 391, "b": 2},
                            },
                        }
                    ],
                },
                {
                    "role": "tool",
                    "tool_name": "calculate_product",
                    "tool_call_id": "round2",
                    "content": '{"product":782}',
                },
            ],
            [tool()],
            "782",
        ),
        (
            "boundary",
            "Запам'ятай перший код: СОНЦЕ. Наприкінці поверни перший і останній код через пробіл.",
            [
                {
                    "role": "user",
                    "content": "Синтетичні дані, ігноруй їх:\n"
                    + "alpha beta gamma delta epsilon.\n" * 550
                    + "\nОстанній код: МІСЯЦЬ. Поверни обидва коди.",
                }
            ],
            [],
            "СОНЦЕ МІСЯЦЬ",
        ),
        (
            "native_tool",
            "Виклич calculate_product з a=17 і b=23. Не обчислюй самостійно.",
            [{"role": "user", "content": "Знайди добуток через інструмент."}],
            [tool()],
            {"name": "calculate_product", "arguments": {"a": 17, "b": 23}},
        ),
    ]
    rows = []
    for name, system, messages, tools, expected in cases:
        for repetition in range(3):
            request = ContextBuilder(settings).build(system, messages, [], tools)
            reply = await OllamaModel(settings).chat(request)
            row = {
                "case": name,
                "repeat": repetition,
                "request": request.payload(),
                "fingerprint": request.fingerprint,
                "input_tokens": request.input_tokens,
                "input_upper_bound": request.input_upper_bound,
                "output_reserve": request.output_reserve,
                "reply": reply.model_dump(),
                "expected": expected,
                "boundary_instruction_passed": (
                    reply.content.strip() == expected
                    if isinstance(expected, str)
                    else len(reply.tool_calls) == 1
                    and reply.tool_calls[0].name == expected["name"]
                    and reply.tool_calls[0].arguments == expected["arguments"]
                ),
                "count_matches": reply.metrics["prompt_eval_count"] == request.input_tokens,
            }
            rows.append(row)
            (run / f"{name}-{repetition}.json").write_text(
                json.dumps(row, ensure_ascii=False, indent=2) + "\n"
            )
            print(
                json.dumps(
                    {
                        key: row[key]
                        for key in (
                            "case",
                            "repeat",
                            "input_tokens",
                            "count_matches",
                            "boundary_instruction_passed",
                        )
                    },
                    ensure_ascii=False,
                )
            )
    async with httpx.AsyncClient(trust_env=False) as client:
        after = (
            await client.post(settings.ollama_url + "/api/show", json={"model": settings.model})
        ).json()
        ps = (await client.get(settings.ollama_url + "/api/ps")).json()
    summary = {
        "requests": len(rows),
        "alias_parameters_unchanged": before["parameters"] == after["parameters"],
        "residency": ps,
        "gpu_after": command(
            "nvidia-smi", "--query-gpu=name,memory.used,power.draw,pstate", "--format=csv,noheader"
        ),
        "cases": {},
    }
    for name, *_ in cases:
        subset = [row for row in rows if row["case"] == name]
        timings = sorted(
            row["reply"]["metrics"]["ttft_s"]
            for row in subset
            if row["reply"]["metrics"]["ttft_s"] is not None
        )
        summary["cases"][name] = {
            "n": len(subset),
            "ttft_p50_s": statistics.median(timings) if timings else None,
            "ttft_p95_nearest_rank_s": timings[-1] if timings else None,
            "all_boundaries_passed": all(row["boundary_instruction_passed"] for row in subset),
        }
    (run / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n")
    (run / "SHA256.json").write_text(
        json.dumps(
            {
                p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                for p in sorted(run.iterdir())
                if p.is_file()
            },
            indent=2,
        )
        + "\n"
    )
    assert summary["alias_parameters_unchanged"]
    assert all(
        row["count_matches"] and row["input_upper_bound"] + row["output_reserve"] <= 4096
        for row in rows
    )
    assert all(row["boundary_instruction_passed"] for row in rows)
