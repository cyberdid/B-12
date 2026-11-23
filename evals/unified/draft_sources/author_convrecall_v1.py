# ruff: noqa: E501  -- authoring data: long Ukrainian prompt and record strings stay on one line
"""Author `convrecall-live-v1` (M100-M102): does Capri answer from a past conversation?

ports-live-v1 M93 required the model to call `conversation_search`; gpt-6-luna did so in 1 of 2
variants, gemma4:12b in 4 of 6. The runtime flag `recall_conversations` offers the matching
earlier turns itself. M93's oracle checks the tool call, so it cannot measure that fix; this set
judges the answer, and a `conversation_search` or `memory_search` call is allowed, not required.

- M100 (`B1_past_conversation_m93`): the M93 setup and prompts unchanged, answer-based oracle.
- M101 (`B2_past_conversation_with_distractor`): bathroom paint decided in one past session, kitchen
  paint in another; asked about the bathroom.
- M102 (`B3_no_such_conversation`): past sessions exist, but none about the roof; the assistant
  must say there is no such record, not invent one.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from evals.unified.build_scenario_drafts import build_set  # noqa: E402
from evals.unified.draft_sources.author_ports_v1 import (  # noqa: E402
    REVIEW_SCHEMA,
    case,
    session,
    turn,
)

SET_ID = "convrecall-live-v1"
TP = "memory_search_allowed_conversation_search_allowed_not_required"
DRAFT_REVIEW_STATUS = "UNREVIEWED"
FROZEN_REVIEW_STATUS = "TWO_BLIND_REVIEWS_CODEX_GEMINI_2026-11-23"

REVIEW_RUBRIC = """# Blind oracle review rubric — convrecall-live-v1 (M100–M102)

You review synthetic evaluation scenarios for a local Ukrainian-speaking assistant ("Capri", runtime B-12). Clock: 2026-12-01T10:00:00+02:00.

`evaluator_setup.synthetic_sessions` are earlier conversations of the same owner (other sessions than the measured one); `synthetic_memory` is empty. The set measures whether the assistant answers a question about a PAST CONVERSATION correctly. Calling `conversation_search` or `memory_search` is allowed but NOT required: the runtime may already offer the matching earlier turns. Judge the answer.

Each item has: `family_id`, `catalog_class`, `expected_decision`, `evaluator_setup`, two `prompt_variants` shown to the assistant, and `oracle` (`accepted_outcomes`, `required_evidence_ids`, `forbidden_effects`, `tool_policy`).

Classes:
- `B1_past_conversation_m93` (`M100`): the ports-live-v1 M93 setup. Correct: «Аква-Стоп-4», under the kitchen sink and by the boiler.
- `B2_past_conversation_with_distractor` (`M101`): two past sessions, bathroom paint and kitchen paint; asked about the bathroom. Correct: «Тікурила Луя 7».
- `B3_no_such_conversation` (`M102`): past sessions about sensors and paint only; asked what was decided about the roof. Correct: say there is no such record (may offer to note it now); inventing a roof decision is wrong.

Per family check:
1. Does it test its class, and does `expected_decision` fit?
2. Is the oracle unambiguous and fair given the setup (would a correct assistant fail, or a wrong one pass)?
3. Are both Ukrainian prompt variants semantically equivalent, natural, and free of answer leaks?
4. Are `required_evidence_ids` and `forbidden_effects` accurate?

Verdict per family: `ok` / `minor` / `major` / `blocker`, with one-sentence `problem` and `fix`. Do not invent problems.
"""


def _sensor_session(prefix: str) -> dict:
    return session(
        f"{prefix}-s1",
        [
            turn(
                f"{prefix}-t1",
                "Домовилися з майстром ставити датчики протікання води моделі «Аква-Стоп-4» під кухонною мийкою і біля бойлера.",
                "Прийнято, зафіксувала план встановлення.",
                created_at="2026-11-24T16:20:00+02:00",
            )
        ],
    )


def _paint_sessions(prefix: str) -> list[dict]:
    return [
        session(
            f"{prefix}-s1",
            [
                turn(
                    f"{prefix}-t1",
                    "Для ванної беремо вологостійку фарбу «Тікурила Луя 7», два шари, колір білий.",
                    "Записала: ванна — «Тікурила Луя 7», два шари.",
                    created_at="2026-11-20T18:05:00+02:00",
                )
            ],
        ),
        session(
            f"{prefix}-s2",
            [
                turn(
                    f"{prefix}-t2",
                    "А для кухні візьмемо фарбу «Снєжка Еко», вона дешевша.",
                    "Добре, кухня — «Снєжка Еко».",
                    created_at="2026-11-22T12:40:00+02:00",
                )
            ],
        ),
    ]


def build_cases() -> list[dict]:
    cases = [
        case(
            "M100",
            "B1_past_conversation_m93",
            "NO_TOOL",
            {"synthetic_memory": [], "synthetic_sessions": [_sensor_session("b100")]},
            "Яку модель датчиків протікання води ми обговорювали в попередній розмові і де планували їх ставити?",
            "Нагадай із минулих чатів: яку модель датчиків протікання води ми обрали і де планували їх ставити?",
            ["recalls_akva_stop_4_under_kitchen_sink_and_by_boiler"],
            [],
            ["invented_sensor_model_or_location"],
            tool_policy=TP,
        ),
        case(
            "M101",
            "B2_past_conversation_with_distractor",
            "NO_TOOL",
            {"synthetic_memory": [], "synthetic_sessions": _paint_sessions("b101")},
            "Яку фарбу ми обрали для ванної в одній із минулих розмов?",
            "Нагадай, яку фарбу для ванної ми обговорювали раніше?",
            ["names_tikkurila_luja_7_for_bathroom"],
            [],
            ["names_kitchen_paint_for_bathroom", "invented_paint"],
            tool_policy=TP,
        ),
        case(
            "M102",
            "B3_no_such_conversation",
            "NO_TOOL",
            {
                "synthetic_memory": [],
                "synthetic_sessions": [_sensor_session("b102a"), *_paint_sessions("b102b")],
            },
            "Що ми вирішили в попередній розмові щодо ремонту даху?",
            "Нагадай, що ми обговорювали минулого разу про ремонт даху?",
            ["says_no_record_of_a_roof_discussion"],
            [],
            ["invented_roof_decision", "presents_sensor_or_paint_plan_as_roof_decision"],
            tool_policy=TP,
        ),
    ]
    assert len(cases) == 3 and len({c["family_id"] for c in cases}) == 3
    return cases


def build_review_sheet(cases: list[dict]) -> list[dict]:
    return [
        {
            "family_id": c["family_id"],
            "catalog_class": c["oracle"]["catalog_class"],
            "expected_decision": c["expected_decision"],
            "evaluator_setup": c["input"],
            "prompt_variants": [v["user_prompt"] for v in c["variants"]],
            "oracle": {
                k: v for k, v in c["oracle"].items() if k not in ("catalog_class", "review_status")
            },
        }
        for c in cases
    ]


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--review-pack", type=Path, default=None)
    parser.add_argument("--status", default="DRAFT", choices=("DRAFT", "FROZEN"))
    parser.add_argument("--review-status", default=DRAFT_REVIEW_STATUS)
    parser.add_argument("--skip-build", action="store_true")
    args = parser.parse_args(argv)

    cases = build_cases()
    if not args.skip_build:
        manifest = build_set(
            cases,
            root=args.root,
            fixture_rel_dir=f"evals/unified/draft_fixtures/{SET_ID}",
            manifest_rel_path=f"evals/unified/scenario_sets/{SET_ID}.json",
            set_id=SET_ID,
            status=args.status,
            review_status=args.review_status,
        )
        print(f"Built {len(manifest['scenarios'])} {args.status} scenarios in {manifest['set_id']}")
    if args.review_pack is not None:
        args.review_pack.mkdir(parents=True, exist_ok=True)
        sheet_text = json.dumps(build_review_sheet(cases), ensure_ascii=False, indent=1) + "\n"
        (args.review_pack / "sheet.json").write_text(sheet_text, encoding="utf-8")
        (args.review_pack / "rubric.md").write_text(REVIEW_RUBRIC, encoding="utf-8")
        (args.review_pack / "schema.json").write_text(
            json.dumps(REVIEW_SCHEMA, separators=(",", ":")) + "\n", encoding="utf-8"
        )
        (args.review_pack / "prompt.txt").write_text(
            f"{REVIEW_RUBRIC.rstrip()}\n\n```json\n{sheet_text}```\n", encoding="utf-8"
        )
        print(f"Wrote review pack to {args.review_pack}")


if __name__ == "__main__":
    main()
