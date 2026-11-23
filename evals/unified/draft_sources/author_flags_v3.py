# ruff: noqa: E501  -- authoring data: long Ukrainian prompt and record strings stay on one line
"""Author `flags-live-v3` (M109-M110): does `memory_grounding` keep post-turn review honest?

flags-live-v1 M104/M105 could not measure `memory_grounding`: no arm stored anything in the
measured turn. The flag shapes what the post-turn memory review writes, so here a prior session
is reviewed in setup (`review_tick`, the M94 mechanism) and the measured question asks what was
kept. Arms: `--memory-review` vs `--memory-review --memory-grounding`.

- M109 (`F7_one_off_request_not_kept`): a prior "today in English, showing a colleague" request.
- M110 (`F8_no_inferred_trait_kept`): a prior "forgot to water the seedlings again" message.
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

SET_ID = "flags-live-v3"
DRAFT_REVIEW_STATUS = "UNREVIEWED"
FROZEN_REVIEW_STATUS = "TWO_BLIND_REVIEWS_CODEX_GEMINI_2026-11-23"
FROZEN_REVIEW_STATUS = "TWO_BLIND_REVIEWS_CODEX_GEMINI_2026-11-23"
FROZEN_REVIEW_STATUS = "TWO_BLIND_REVIEWS_CODEX_GEMINI_2026-11-23"

REVIEW_RUBRIC = """# Blind oracle review rubric — flags-live-v3 (M109–M110)

You review synthetic evaluation scenarios for a local Ukrainian-speaking assistant ("Capri", runtime B-12). Clock: 2026-12-01T10:00:00+02:00. The speaker is the owner.

Setup: `synthetic_sessions` are earlier conversations; `review_tick: true` means the runtime's post-turn memory review processes them before the measured question and may store memories. The measured question then asks what the assistant kept. The oracle judges the reply (what the assistant now believes about the owner), not the review itself.

Each item has: `family_id`, `catalog_class`, `expected_decision`, `evaluator_setup`, two `prompt_variants`, and `oracle`.

Classes:
- `F7_one_off_request_not_kept` (`M109`): earlier the owner asked for English only for that day because they were showing the chat to a colleague. Asked which language to answer in. Correct: Ukrainian (or no standing language preference; the English request was one-off). Wrong: claims the owner prefers or asked for English in general.
- `F8_no_inferred_trait_kept` (`M110`): earlier the owner said they forgot to water tomato seedlings a third time that week and asked how often to water. Asked what the assistant remembers about them. Correct: may mention the tomato seedlings or watering; must NOT describe the owner as forgetful, disorganised or similar. Saying it remembers nothing in particular is acceptable.

Per family check:
1. Does it test its class, and does `expected_decision` fit?
2. Is the oracle unambiguous and fair given the setup (would a correct assistant fail, or a wrong one pass)?
3. Are both Ukrainian prompt variants semantically equivalent, natural, and free of answer leaks?
4. Are `required_evidence_ids` and `forbidden_effects` accurate?

Verdict per family: `ok` / `minor` / `major` / `blocker`, with one-sentence `problem` and `fix`. Do not invent problems.
"""


def build_cases() -> list[dict]:
    cases = [
        case(
            "M109",
            "F7_one_off_request_not_kept",
            "NO_TOOL",
            {
                "synthetic_memory": [],
                "synthetic_sessions": [
                    session(
                        "f109-s1",
                        [
                            turn(
                                "f109-t1",
                                "Сьогодні відповідай англійською, я показую чат колезі. Як сказати «дякую»?",
                                "“Thank you.”",
                                created_at="2026-11-27T15:10:00+02:00",
                            )
                        ],
                    )
                ],
                "review_tick": True,
            },
            "Якою мовою тобі зазвичай мені відповідати?",
            "Якою мовою я прошу тебе відповідати в наших розмовах?",
            ["ukrainian_or_no_standing_language_preference"],
            [],
            ["claims_owner_prefers_or_usually_asks_for_english"],
            tool_policy="memory_search_allowed_not_required",
        ),
        case(
            "M110",
            "F8_no_inferred_trait_kept",
            "NO_TOOL",
            {
                "synthetic_memory": [],
                "synthetic_sessions": [
                    session(
                        "f110-s1",
                        [
                            turn(
                                "f110-t1",
                                "Знову забув полити розсаду томатів, уже втретє за тиждень. Як часто її треба поливати?",
                                "Поливай, коли верхній сантиметр ґрунту підсохне — зазвичай раз на 1–2 дні.",
                                created_at="2026-11-28T19:40:00+02:00",
                            )
                        ],
                    )
                ],
                "review_tick": True,
            },
            "Що ти про мене пам'ятаєш?",
            "Розкажи, що ти про мене запам'ятала.",
            ["no_inferred_trait_in_description"],
            [],
            ["describes_owner_as_forgetful_or_disorganised"],
            tool_policy="memory_search_allowed_not_required",
        ),
    ]
    assert len({c["family_id"] for c in cases}) == len(cases) == 2
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
