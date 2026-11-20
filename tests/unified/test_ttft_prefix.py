"""Tests for evals/unified/ttft_prefix.py using scripted_ollama (no GPU needed)."""

import json

from evals.unified.ttft_prefix import main, measure_ttft_prefix


async def test_ttft_prefix_measures_20_warm_and_cold_turns_and_metadata(scripted_ollama, tmp_path):
    state, base = scripted_ollama
    state["script"] = [{"content": "Добре."} for _ in range(200)]

    report = await measure_ttft_prefix(base, turns=20, label="colab-only")

    assert report["host"]
    assert report["num_ctx"] == base.num_ctx
    assert report["model"] == base.model
    assert report["model_digest"] == "a" * 64
    assert report["turns_per_state"] == 20
    assert report["label"] == "colab-only"

    for mode in ("baseline", "stable_prefix"):
        for cache_state in ("cold", "warm"):
            bucket = report["summary"][mode][cache_state]
            assert bucket["count"] == 20
            assert bucket["completed"] == 20
            assert isinstance(bucket["ttft_ms_p50"], float)
            assert isinstance(bucket["ttft_ms_p95"], float)
            assert bucket["ttft_ms_p95"] >= bucket["ttft_ms_p50"]

    assert len(report["runs"]) == 80  # 20 cold + 20 warm for baseline and stable_prefix
    assert state["unloads"] >= 40  # 20 cold turns unloaded per mode

    # CLI entry writes JSON output cleanly
    out_file = tmp_path / "ttft_report.json"
    state["script"] = [{"content": "Добре."} for _ in range(100)]
    rc = await __import__("asyncio").to_thread(
        main,
        [
            "--model",
            base.model,
            "--ollama-url",
            base.ollama_url,
            "--model-profile",
            str(base.model_profile),
            "--tokenizer-dir",
            str(base.tokenizer_dir),
            "--num-ctx",
            str(base.num_ctx),
            "--output-tokens",
            str(base.output_tokens),
            "--turns",
            "4",
            "--mode",
            "stable_prefix",
            "--out",
            str(out_file),
        ],
    )
    assert rc == 0
    written = json.loads(out_file.read_text(encoding="utf-8"))
    assert written["turns_per_state"] == 4
    assert "stable_prefix" in written["summary"]
    assert len(written["runs"]) == 8
