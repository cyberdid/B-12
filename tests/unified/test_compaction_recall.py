"""Tests for evals/unified/compaction_recall.py using scripted_ollama (no real model)."""

from __future__ import annotations

import json
import re

import pytest

from evals.unified.compaction_recall import (
    PLANTED_FACTS,
    POLICIES,
    build_synthetic_conversation,
    main,
    measure_compaction_recall,
    score_exact_match,
)


def test_synthetic_conversation_places_12_facts_in_the_middle():
    turns = build_synthetic_conversation()
    assert len(PLANTED_FACTS) == 12
    fact_positions = [i for i, turn in enumerate(turns) if turn["fact_id"] is not None]
    assert len(fact_positions) == 12
    # Strictly in the middle: filler turns exist both before the first fact and after the last.
    assert fact_positions[0] >= 4
    assert len(turns) - 1 - fact_positions[-1] >= 20
    # Planted values never leak into head or tail filler turns.
    filler_text = "\n".join(
        f"{t['user']}\n{t['assistant']}" for t in turns if t["fact_id"] is None
    ).lower()
    for fact in PLANTED_FACTS:
        assert fact.expected_value.lower() not in filler_text


def test_exact_match_scorer_handles_present_and_absent_values():
    assert score_exact_match("8443", "8443") == 1.0
    assert score_exact_match("  kestrel-9. ", "Kestrel-9") == 1.0
    assert score_exact_match("«Івано-Франківськ»", "Івано-Франківськ") == 1.0
    assert score_exact_match("НЕМАЄ В КОНТЕКСТІ", "8443") == 0.0
    assert score_exact_match("84430", "8443") == 0.0
    assert score_exact_match("", "8443") == 0.0


def test_summary_policy_is_rejected_in_track_h():
    assert POLICIES == ("trim", "trim+memory")
    with pytest.raises(ValueError, match="summary"):
        import asyncio

        asyncio.run(measure_compaction_recall(None, policies=("summary",)))  # type: ignore[arg-type]


def _scripted_context_reader():
    """Return a scripted Ollama handler answering strictly from post-admission messages."""

    def respond(body: dict) -> dict:
        messages = body.get("messages") or []
        user_msgs = [m["content"] for m in messages if m.get("role") == "user"]
        question = user_msgs[-1] if user_msgs else ""
        # Inspect all post-admission messages except the current user question (history + evidence).
        last_user_idx = max(
            (i for i, m in enumerate(messages) if m.get("role") == "user"),
            default=-1,
        )
        context_blob = "\n".join(
            m.get("content", "") for i, m in enumerate(messages) if i != last_user_idx
        )
        matched_fact = next(
            (fact for fact in PLANTED_FACTS if fact.question in question),
            None,
        )
        if matched_fact is not None:
            pattern = r"(?<!\w)" + re.escape(matched_fact.expected_value) + r"(?!\w)"
            if re.search(pattern, context_blob, flags=re.IGNORECASE):
                return {"content": matched_fact.expected_value}
        return {"content": "НЕМАЄ В КОНТЕКСТІ"}

    return respond


async def test_compaction_recall_end_to_end_with_scripted_model(scripted_ollama, tmp_path):
    state, base = scripted_ollama
    reader = _scripted_context_reader()
    state["script"] = [reader for _ in range(len(PLANTED_FACTS) * 2)]

    report = await measure_compaction_recall(base)

    assert report["facts_count"] == 12
    assert set(report["policies"]) == {"trim", "trim+memory"}

    trim_res = report["policies"]["trim"]
    mem_res = report["policies"]["trim+memory"]

    assert trim_res["total"] == 12
    assert trim_res["correct"] == 0
    assert trim_res["recall"] == 0.0
    assert trim_res["prompt_tokens"] > 0
    assert all(item["score"] == 0.0 for item in trim_res["per_question"])
    assert all(not item["value_in_post_admission_context"] for item in trim_res["per_question"])

    assert mem_res["total"] == 12
    assert mem_res["correct"] == 12
    assert mem_res["recall"] == 1.0
    assert mem_res["prompt_tokens"] > trim_res["prompt_tokens"]
    assert all(item["score"] == 1.0 for item in mem_res["per_question"])
    assert all(item["value_in_post_admission_context"] for item in mem_res["per_question"])

    # CLI entry writes valid JSON with recall and prompt tokens per policy.
    out_file = tmp_path / "compaction_recall.json"
    state["script"] = [reader for _ in range(len(PLANTED_FACTS) * 2)]
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
            "--out",
            str(out_file),
        ],
    )
    assert rc == 0
    written = json.loads(out_file.read_text(encoding="utf-8"))
    assert written["policies"]["trim"]["recall"] == 0.0
    assert written["policies"]["trim+memory"]["recall"] == 1.0
    assert written["policies"]["trim+memory"]["prompt_tokens"] > 0


async def test_compaction_recall_evicts_middle_facts_under_tight_num_ctx(scripted_ollama):
    state, base = scripted_ollama
    reader = _scripted_context_reader()
    state["script"] = [reader for _ in range(len(PLANTED_FACTS) * 2)]
    # Even when history_turns covers the whole 40-turn conversation, ContextBuilder evicts
    # oldest groups to fit the synthetic byte-tokenizer window (16384); only the tail survives
    # trim (system prompt alone is ~11k byte-tokens in the synthetic BPE fixture), while memory
    # preserves all 12 facts.
    tight = base.model_copy(update={"num_ctx": 16384, "output_tokens": 512})
    report = await measure_compaction_recall(tight, history_turns=60)
    assert report["policies"]["trim"]["recall"] == 0.0
    assert report["policies"]["trim+memory"]["recall"] == 1.0
