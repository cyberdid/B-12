# ruff: noqa: E501  -- authoring data: long Ukrainian prompt and record strings stay on one line
"""Author `flags-live-v2` (M107-M108): answer-level checks for `standing_intents` and `skills`.

Item 8 of the owner's list (23.11.2026), the two flags whose state the runner could not seed
before `2b37a05`.

- M107 (`F5_standing_intent_fires`, flag `standing_intents`): the owner set an intent "before
  buying paint: the bathroom needs primer Ceresit CT 17"; the question mentions buying paint.
  Intents match whole words, so the keyword list carries the inflected forms used in the prompts.
- M108 (`F6_owner_skill_used`, flag `skills`): an owner skill holds a personal XT60 soldering
  procedure (380 °C, 2 mm tip, 6 mm heat-shrink); asked how to solder XT60, the assistant should
  follow it (via `skill_view`).
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
    TOOLS,
    case,
)

SET_ID = "flags-live-v2"
DRAFT_REVIEW_STATUS = "UNREVIEWED"
FROZEN_REVIEW_STATUS = "TWO_BLIND_REVIEWS_CODEX_GEMINI_2026-11-23"
TOOLS_WITH_SKILLS = [*TOOLS, "skill_view"]

REVIEW_RUBRIC = """# Blind oracle review rubric — flags-live-v2 (M107–M108)

You review synthetic evaluation scenarios for a local Ukrainian-speaking assistant ("Capri", runtime B-12). Clock: 2026-12-01T10:00:00+02:00. The speaker is the owner.

Each family targets one runtime feature; the oracle judges only observable behaviour (reply and tool calls). The runtime may inject owner state as data beside the question: standing intents (keyword-triggered owner notes) and a skills index (names and descriptions; the body is read with `skill_view`).

Each item has: `family_id`, `catalog_class`, `expected_decision`, `evaluator_setup` (`synthetic_intents` with keywords and text, `synthetic_skills` with name, description, body), two `prompt_variants`, and `oracle`.

Classes:
- `F5_standing_intent_fires` (`M107`): the owner's intent says that before buying paint the bathroom needs primer «Церезит CT 17». The owner says they are going to buy paint for the bathroom and asks what not to forget. Correct: mentions the primer Ceresit CT 17. Generic advice without the primer is not enough.
- `F6_owner_skill_used` (`M108`): the owner skill `solder-xt60` says: 380 °C, 2 mm chisel tip, tin both contacts first, 6 mm heat-shrink. Asked how to solder XT60 and at what temperature. Correct: 380 °C as the owner's setting (other details welcome). A different temperature presented as the owner's setting is wrong.

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
            "M107",
            "F5_standing_intent_fires",
            "NO_TOOL",
            {
                "synthetic_memory": [],
                "synthetic_intents": [
                    {
                        "alias": "f107-i1",
                        "keywords": ["фарба", "фарби", "фарбу", "фарбою"],
                        "text": "Перед покупкою фарби для ванної: потрібна ґрунтовка «Церезит CT 17».",
                    }
                ],
            },
            "Їду в будівельний за фарбою для ванної. Що ще не забути купити?",
            "Збираюся купувати фарбу для ванної — що ще треба не забути взяти?",
            ["mentions_primer_ceresit_ct17"],
            [],
            ["invented_owner_note"],
            tool_policy="memory_search_allowed_not_required",
        ),
        case(
            "M108",
            "F6_owner_skill_used",
            "NO_TOOL",
            {
                "synthetic_memory": [],
                "available_tools": TOOLS_WITH_SKILLS,
                "synthetic_skills": [
                    {
                        "name": "solder-xt60",
                        "description": "Як я паяю роз'єми XT60",
                        "body": "Моя процедура: жало-лопатка 2 мм, температура 380 °C. Спершу залудити обидва контакти й дроти, потім паяти по одному. Термоусадка 6 мм на кожен контакт.",
                    }
                ],
            },
            "Як мені паяти роз'єм XT60 — яку температуру ставити?",
            "Нагадай, як я паяю XT60 і на яку температуру ставлю паяльник?",
            ["owner_setting_380c"],
            [],
            ["other_temperature_as_owner_setting"],
            tool_policy="memory_search_allowed_skill_view_allowed_not_required",
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
