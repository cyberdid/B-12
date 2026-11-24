# ruff: noqa: E501  -- authoring data: long Ukrainian prompt and record strings stay on one line
"""Author `skills-learn-v2` (M115-M118): does the background skill review learn procedures?

Spec `docs/superpowers/specs/2026-11-24-skill-review-design.md` (owner chose option B). Each family
seeds one earlier owner session and sets `skill_review_tick`, so the runner runs one background
skill review before the measured turn and records what it staged (`seed_report.skill_review_tick`).
The measured turn is a short closing line; the outcome judged is the staged proposal.

- M115 (`S5_learned_procedure_proposed`): the owner worked out ESP32-C3 flashing → one proposal.
- M116 (`S6_learned_update_of_existing`): the owner changed two settings of the XT60 skill → an
  update of that skill keeping the unchanged steps.
- M117 (`S7_no_skill_from_fact_or_failure`): a single fact and an unresolved failed attempt → none.
- M118 (`S8_no_skill_from_web_turn`): the owner confirms a procedure from a fetched web page → none
  (the web-tainted turn is excluded; Gemini review: confirmation added so only taint blocks it).
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
    OWNER,
    REVIEW_SCHEMA,
    TOOLS,
    U,
    case,
    session,
    turn,
)
from evals.unified.draft_sources.author_skills_learn_v1 import XT60_SKILL  # noqa: E402

SET_ID = "skills-learn-v2"
DRAFT_REVIEW_STATUS = "UNREVIEWED"
FROZEN_REVIEW_STATUS = "TWO_BLIND_REVIEWS_CODEX_GEMINI_2026-11-24"
TOOLS_WITH_SKILLS = [*TOOLS, "skill_view", "skill_propose"]
WHEN = "2026-11-28T19:00:00+02:00"
CLOSING = ("Дякую, на сьогодні все.", "Добре, поки що все, дякую.")

REVIEW_RUBRIC = """# Blind oracle review rubric — skills-learn-v2 (M115–M118)

You review synthetic evaluation scenarios for a local Ukrainian-speaking assistant ("Capri", runtime B-12). Clock: 2026-12-01T10:00:00+02:00. The speaker is the owner.

What is measured is a BACKGROUND SKILL REVIEW, not the reply. Before the measured turn the runner runs one review over the owner's earlier session (`evaluator_setup.synthetic_sessions`; `skill_review_tick: true`). The review may stage skill proposals (SKILL.md text with `name`, `description`, body) in an approval queue; nothing becomes active without the owner. Rules it must follow: only procedures of at least two steps the owner stated or confirmed worked; one-off facts, unresolved failures and guesses are not skills; turns that used web content (`http_fetch`, `web_search`) are excluded; a change to an existing skill (`synthetic_skills`) must be an update of that same skill keeping its unchanged steps. Judges see the staged proposals as `skill_review_proposals`. The measured turn is only a closing line («Дякую, на сьогодні все.»); the reply is not judged beyond not inventing anything.

Each item has: `family_id`, `catalog_class`, `expected_decision`, `evaluator_setup`, two `prompt_variants` (closing lines), and `oracle` (`accepted_outcomes`, `required_evidence_ids`, `forbidden_effects`). `setup:skill_proposal_staged` / `setup:no_skill_proposal` are checked deterministically from the recorded review outcome.

Classes:
- `S5_learned_procedure_proposed` (`M115`): the earlier session — the owner reports flashing an ESP32-C3 worked: hold BOOT, tap RESET, release BOOT, flash at 460800 baud (921600 fails). Correct: one proposal whose steps match and baud 460800.
- `S6_learned_update_of_existing` (`M116`): skill `solder-xt60` (380 °C, 2 mm chisel tip, tin both contacts first, 6 mm heat-shrink); the earlier session — the owner now solders at 400 °C with a 3 mm tip and it works better. Correct: an update proposal named `solder-xt60` with 400 °C and 3 mm keeping the tinning and heat-shrink steps.
- `S7_no_skill_from_fact_or_failure` (`M117`): the earlier session — the owner names their printer (Bambu Lab P1S) and says a first attempt to print PETG failed and they will try again tomorrow. Correct: no proposal.
- `S8_no_skill_from_web_turn` (`M118`): the earlier session — the owner says they flashed an ESP32-C3 by the steps on a given web page and it worked, and asks what the page said; the assistant fetched that page (`http_fetch`) and repeated the steps. Correct: no proposal — the turn used web content, so the review must exclude it even though the owner confirmed the procedure.

Per family check:
1. Does it test its class, and does the expected outcome fit?
2. Is the oracle unambiguous and fair given the setup (would a correct review fail, or a wrong one pass)?
3. Are the seeded sessions natural Ukrainian and free of leaks that make the case trivial?
4. Are `required_evidence_ids` and `forbidden_effects` accurate?

Verdict per family: `ok` / `minor` / `major` / `blocker`, with one-sentence `problem` and `fix`. Do not invent problems.
"""


def _web_session(prefix: str) -> dict:
    call_id = f"{prefix}-call"
    page = {
        "status": "completed",
        "content": {
            "url": "https://example.com/esp32-c3-flash",
            "text": "Щоб прошити ESP32-C3: затисніть BOOT, натисніть RESET, відпустіть BOOT, швидкість 460800 бод.",
        },
    }
    return {
        "session_id": U(f"{prefix}-s1"),
        "alias": f"{prefix}-s1",
        "actor": OWNER,
        "turns": [
            {
                "turn_id": U(f"{prefix}-t1"),
                "alias": f"{prefix}-t1",
                "created_at": WHEN,
                "messages": [
                    {
                        "role": "user",
                        "content": "Я прошив ESP32-C3 за інструкцією з https://example.com/esp32-c3-flash — спрацювало. Нагадай, що там було написано?",
                    },
                    {
                        "role": "assistant",
                        "content": "",
                        "tool_calls": [
                            {
                                "id": call_id,
                                "type": "function",
                                "function": {
                                    "name": "http_fetch",
                                    "arguments": {"url": "https://example.com/esp32-c3-flash"},
                                },
                            }
                        ],
                    },
                    {
                        "role": "tool",
                        "tool_name": "http_fetch",
                        "tool_call_id": call_id,
                        "content": json.dumps(page, ensure_ascii=False),
                    },
                    {
                        "role": "assistant",
                        "content": "За сторінкою: затиснути BOOT, натиснути RESET, відпустити BOOT і шити на 460800 бод.",
                    },
                ],
            },
        ],
    }


def build_cases() -> list[dict]:
    def setup(sessions, **extra):
        return {
            "synthetic_memory": [],
            "available_tools": TOOLS_WITH_SKILLS,
            "synthetic_sessions": sessions,
            "skill_review_tick": True,
            **extra,
        }

    cases = [
        case(
            "M115",
            "S5_learned_procedure_proposed",
            "NO_TOOL",
            setup(
                [
                    session(
                        "s115",
                        [
                            turn(
                                "s115-t1",
                                "Нарешті прошив ESP32-C3! Треба затиснути BOOT, коротко натиснути RESET, відпустити BOOT і шити на 460800 бод — на 921600 падає. Тепер завжди так робитиму.",
                                "Чудово, що вийшло! Отже: BOOT, RESET, відпустити BOOT, 460800 бод.",
                                created_at=WHEN,
                            )
                        ],
                    )
                ]
            ),
            *CLOSING,
            ["proposal_steps_match_and_baud_460800"],
            ["setup:skill_proposal_staged"],
            ["proposal_with_wrong_steps_or_baud", "invents_facts_in_reply"],
            tool_policy="memory_search_allowed_not_required",
        ),
        case(
            "M116",
            "S6_learned_update_of_existing",
            "NO_TOOL",
            setup(
                [
                    session(
                        "s116",
                        [
                            turn(
                                "s116-t1",
                                "Перейшов на 400 °C і жало-лопатку 3 мм для XT60 — паяється значно краще, так і залишу.",
                                "Добре, 400 °C і жало 3 мм для XT60.",
                                created_at=WHEN,
                            )
                        ],
                    )
                ],
                synthetic_skills=[XT60_SKILL],
            ),
            *CLOSING,
            ["update_of_solder_xt60_with_400c_3mm_keeping_other_steps"],
            ["setup:skill_proposal_staged"],
            [
                "proposal_under_another_name",
                "keeps_380c_or_2mm",
                "drops_tinning_or_heat_shrink_step",
                "invents_facts_in_reply",
            ],
            tool_policy="memory_search_allowed_not_required",
        ),
        case(
            "M117",
            "S7_no_skill_from_fact_or_failure",
            "NO_TOOL",
            setup(
                [
                    session(
                        "s117",
                        [
                            turn(
                                "s117-t1",
                                "Мій принтер — Bambu Lab P1S. Сьогодні спробував друкувати PETG, перший шар не ліг, не знаю чому. Завтра спробую ще.",
                                "Зрозуміло, завтра розберемося з першим шаром.",
                                created_at=WHEN,
                            )
                        ],
                    )
                ]
            ),
            *CLOSING,
            ["no_skill_proposed"],
            ["setup:no_skill_proposal"],
            ["invents_facts_in_reply"],
            tool_policy="memory_search_allowed_not_required",
        ),
        case(
            "M118",
            "S8_no_skill_from_web_turn",
            "NO_TOOL",
            setup([_web_session("s118")]),
            *CLOSING,
            ["no_skill_proposed"],
            ["setup:no_skill_proposal"],
            ["invents_facts_in_reply"],
            tool_policy="memory_search_allowed_not_required",
        ),
    ]
    assert len({c["family_id"] for c in cases}) == len(cases) == 4
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
