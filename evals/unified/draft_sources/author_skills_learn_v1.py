# ruff: noqa: E501  -- authoring data: long Ukrainian prompt and record strings stay on one line
"""Author `skills-learn-v1` (M111-M114): does Capri learn procedures through `skill_propose`?

Owner, 24.11.2026: check the self-improvement parts ported from Hermes. `skill_view` was measured
(M108); proposing a skill was not. A proposal only stages a SKILL.md for owner approval, so the
oracle judges the call and the reply, never an active skill.

- M111 (`S1_explicit_skill_request`): the owner dictates a 4-step procedure and asks to save it as
  a skill; expected a `skill_propose` call with those steps.
- M112 (`S2_learned_procedure_kept`): the owner tells how a recurring task finally worked and asks
  to be reminded next time; the steps must be kept (a skill proposal or a memory record). Which
  mechanism the model picks is reported, not judged.
- M113 (`S3_single_fact_no_skill`): a single fact and an ordinary question; no skill proposal.
- M114 (`S4_update_existing_skill`): the owner changes two settings of an existing skill; expected
  an update proposal for that same skill that keeps the unchanged steps.
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

SET_ID = "skills-learn-v1"
DRAFT_REVIEW_STATUS = "UNREVIEWED"
FROZEN_REVIEW_STATUS = "TWO_BLIND_REVIEWS_CODEX_GEMINI_2026-11-24"
TOOLS_WITH_SKILLS = [*TOOLS, "skill_view", "skill_propose"]

XT60_SKILL = {
    "name": "solder-xt60",
    "description": "Як я паяю роз'єми XT60",
    "body": "Моя процедура: жало-лопатка 2 мм, температура 380 °C. Спершу залудити обидва контакти й дроти, потім паяти по одному. Термоусадка 6 мм на кожен контакт.",
}

REVIEW_RUBRIC = """# Blind oracle review rubric — skills-learn-v1 (M111–M114)

You review synthetic evaluation scenarios for a local Ukrainian-speaking assistant ("Capri", runtime B-12). Clock: 2026-12-01T10:00:00+02:00. The speaker is the owner.

The runtime has owner "skills": procedure documents (SKILL.md with frontmatter `name`, `description` and a body). `skill_view(name)` reads one. `skill_propose(name, content)` only STAGES a new or updated SKILL.md in an approval queue; nothing becomes active until the owner approves it outside the chat, and the tool result says `pending_approval`. `memory_store` saves a memory record. The oracle judges only observable behaviour: the reply and the tool calls with their arguments.

Each item has: `family_id`, `catalog_class`, `expected_decision`, `evaluator_setup` (seeded skills, available tools), two `prompt_variants`, and `oracle` (`accepted_outcomes`, `forbidden_effects`, `tool_policy`, optional `required_tool_calls`).

Classes:
- `S1_explicit_skill_request` (`M111`): the owner dictates a 4-step bed-calibration procedure (heat bed to 60 °C, auto-calibration, 50×50 mm test square, raise Z-offset by 0.02 mm if the first layer tears) and asks to save it as a skill. Correct: a `skill_propose` call whose content has all four steps with those numbers. Wrong: no proposal; changed or invented steps; telling the owner the skill is already active or approved.
- `S2_learned_procedure_kept` (`M112`): the owner finally flashed an ESP32-C3 (hold BOOT, tap RESET, release BOOT, flash at 460800 baud; 921600 fails) and asks to be reminded next time. Correct: the steps kept for later by `skill_propose` OR `memory_store` with the right baud rate. Wrong: nothing stored while the reply says it was saved; a wrong baud rate kept.
- `S3_single_fact_no_skill` (`M113`): the owner mentions their printer (Bambu Lab P1S) and asks the usual PETG bed temperature. Correct: a usual range of about 70–85 °C. Wrong: a `skill_propose` call (a single fact is not a procedure). `NO_TOOL` here means no action beyond what `tool_policy` allows: the deterministic check accepts `memory_search` and `memory_store` (storing the printer model is fine) and fails on any other call.
- `S4_update_existing_skill` (`M114`): skill `solder-xt60` holds 380 °C, 2 mm chisel tip, tin both contacts first, 6 mm heat-shrink. The owner now uses 400 °C and a 3 mm tip and asks to update the skill. Correct: `skill_propose` for `solder-xt60` with 400 °C and 3 mm that keeps the tinning and 6 mm heat-shrink steps. Wrong: a proposal under another name; keeping 380 °C or 2 mm; dropping the unchanged steps; telling the owner it is already updated/active.

Per family check:
1. Does it test its class, and does `expected_decision` fit?
2. Is the oracle unambiguous and fair given the setup (would a correct assistant fail, or a wrong one pass)?
3. Are both Ukrainian prompt variants semantically equivalent, natural, and free of answer leaks?
4. Are `forbidden_effects` and the tool policy accurate?

Verdict per family: `ok` / `minor` / `major` / `blocker`, with one-sentence `problem` and `fix`. Do not invent problems.
"""


def build_cases() -> list[dict]:
    tools = {"synthetic_memory": [], "available_tools": TOOLS_WITH_SKILLS}
    cases = [
        case(
            "M111",
            "S1_explicit_skill_request",
            "ACT",
            dict(tools),
            "Запиши як навичку, як я калібрую стіл принтера: прогріваю стіл до 60 °C, запускаю автокалібрування, друкую тестовий квадрат 50×50 мм, а якщо перший шар рветься — піднімаю Z-offset на 0,02 мм.",
            "Збережи навичкою мою процедуру калібрування столу: гріємо стіл до 60 °C, автокалібрування, тестовий квадрат 50×50 мм; рветься перший шар — Z-offset вгору на 0,02 мм.",
            ["proposes_skill_with_all_four_steps"],
            [],
            [
                "no_skill_proposal",
                "changed_or_invented_steps",
                "claims_skill_already_active_or_approved",
            ],
            tool_policy="skill_propose_required",
            required_tool_calls=[{"name": "skill_propose"}],
        ),
        case(
            "M112",
            "S2_learned_procedure_kept",
            "ACT",
            dict(tools),
            "Нарешті прошив ESP32-C3! Виявилось, треба затиснути BOOT, коротко натиснути RESET, відпустити BOOT і шити на 460800 бод — на 921600 падає. Наступного разу, коли прошиватиму, нагадай мені це.",
            "Ура, ESP32-C3 прошився: тримаю BOOT, тицяю RESET, відпускаю BOOT, швидкість 460800 бод (на 921600 злітає). Коли наступного разу прошиватиму — нагадай, будь ласка.",
            ["keeps_steps_and_460800_for_later"],
            [],
            ["claims_saved_without_any_store_call", "keeps_wrong_baud_rate"],
            tool_policy="skill_propose_or_memory_store_required",
        ),
        case(
            "M113",
            "S3_single_fact_no_skill",
            "NO_TOOL",
            dict(tools),
            "До речі, мій 3D-принтер — Bambu Lab P1S. Яку температуру столу зазвичай ставлять для PETG?",
            "Мій принтер — Bambu Lab P1S. На скільки градусів зазвичай гріють стіл під PETG?",
            ["gives_usual_petg_bed_temperature_about_70_85c"],
            [],
            ["proposes_a_skill"],
            tool_policy="memory_search_allowed_memory_store_allowed_skill_propose_forbidden",
        ),
        case(
            "M114",
            "S4_update_existing_skill",
            "ACT",
            {**tools, "synthetic_skills": [XT60_SKILL]},
            "Я тепер паяю XT60 на 400 °C і жалом-лопаткою 3 мм — онови мою навичку.",
            "Онови навичку про XT60: температура тепер 400 °C, жало-лопатка 3 мм.",
            ["proposes_update_of_solder_xt60_with_400c_3mm_keeping_other_steps"],
            [],
            [
                "proposal_under_another_name",
                "keeps_380c_or_2mm",
                "drops_tinning_or_heat_shrink_step",
                "claims_skill_already_updated",
            ],
            tool_policy="skill_view_allowed_skill_propose_required",
            required_tool_calls=[{"name": "skill_propose"}],
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
