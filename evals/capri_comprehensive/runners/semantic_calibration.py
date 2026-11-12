"""Calibrate the semantic recall threshold on the scenarios' own synthetic data.

For every scenario question the script scores (with the owner's embedding bridge):
- its own scenario memories: the best of them is a proxy for "the relevant record";
- the memories of all other scenarios: clearly unrelated pairs, an upper bound on noise
  (topics overlap across the B-12 stand, so this is conservative).

It prints, per threshold, the share of unrelated pairs that would pass (false positives)
and the share of questions whose best own memory would pass (recall proxy), and writes
artifacts/semantic_calibration.json. No owner data is read.

Usage (from the repository root):
    uv run python -m evals.capri_comprehensive.runners.semantic_calibration
"""

from __future__ import annotations

import asyncio
import json

import numpy as np

from evals.capri_comprehensive.evaluators.schema import ScenarioDefinition
from evals.capri_comprehensive.runners.live_components import SEMANTIC_PYTHON
from evals.capri_comprehensive.runners.run_live_suite import ARTIFACTS, SCENARIOS

THRESHOLDS = (0.55, 0.6, 0.62, 0.65, 0.68, 0.7, 0.72, 0.75)
# Known relevant pairs that lexical search misses (question, record).
LABELLED = (
    ("JOURNEY-04", "Нагадай, з яким редактором та яким кабелем на стенді ми працювали цього "
     "місяця?", "День 1: Власник налаштував робоче середовище Neovim для проекту B-12."),
    ("JOURNEY-04", "Нагадай, з яким редактором та яким кабелем на стенді ми працювали цього "
     "місяця?", "День 15: Власник замінив інтерфейсний кабель на стенді на екранований."),
)


async def calibrate() -> dict:
    from b12.semantic import BridgeEmbedder

    cases = []
    for path in sorted(SCENARIOS.glob("*/*.yaml")):
        sc = ScenarioDefinition.from_yaml_file(path)
        memories = [m.text for m in sc.pre_conditions.initial_state.memories]
        if memories:
            cases.append((sc.id, [t.input for t in sc.interactions], memories))
    texts = sorted({m for _, _, ms in cases for m in ms})
    index = {t: i for i, t in enumerate(texts)}
    embedder = BridgeEmbedder(SEMANTIC_PYTHON, backend="archive_index.embed:Embedder")
    try:
        docs = await embedder.documents(texts)
        unrelated, own_best = [], []
        for _sid, questions, memories in cases:
            own = {index[m] for m in memories}
            for question in questions:
                scores = docs @ await embedder.query(question)
                own_best.append(float(max(scores[i] for i in own)))
                unrelated.extend(float(scores[i]) for i in range(len(texts)) if i not in own)
        labelled = []
        for sid, question, record in LABELLED:
            q = await embedder.query(question)
            d = await embedder.documents([record])
            labelled.append({"scenario": sid, "record": record, "score": float(d[0] @ q)})
    finally:
        embedder.close()
    unrelated_arr, own_arr = np.array(unrelated), np.array(own_best)
    table = [
        {
            "threshold": t,
            "unrelated_pass_share": round(float((unrelated_arr >= t).mean()), 4),
            "own_best_pass_share": round(float((own_arr >= t).mean()), 4),
        }
        for t in THRESHOLDS
    ]
    return {
        "scenarios": len(cases),
        "questions": len(own_best),
        "unrelated_pairs": len(unrelated),
        "unrelated_percentiles": {
            p: round(float(np.percentile(unrelated_arr, p)), 4) for p in (50, 90, 95, 99, 99.9)
        },
        "unrelated_max": round(float(unrelated_arr.max()), 4),
        "own_best_percentiles": {
            p: round(float(np.percentile(own_arr, p)), 4) for p in (10, 25, 50)
        },
        "labelled": labelled,
        "table": table,
    }


def main() -> None:
    result = asyncio.run(calibrate())
    out = ARTIFACTS / "semantic_calibration.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
