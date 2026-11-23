# ruff: noqa: E501  -- authoring data: long Ukrainian prompt and record strings stay on one line
"""Author `asof-live-v1` (M97-M99): does Capri answer a question about a past period correctly?

ports-live-v1 M96 required the model to call memory_search(as_of=...); both gemma4:12b and
gpt-6-luna answered from the current records instead. The runtime flag `recall_as_of` makes
recall apply the period itself. M96's oracle checks the tool call, so it cannot measure that
fix; this set judges the answer, and a tool call is allowed but not required.

- M97 (`A1_period_recall_m96`): the M96 setup and prompts unchanged, answer-based oracle.
- M98 (`A2_period_recall_supplier`): another domain; the September supplier is crowded out by
  suppliers valid from October.
- M99 (`A3_day_precision`): a single day in November, when two addresses were valid in turn.
The "current state" control is not a family here (only M97-M99 are free two-digit IDs): it is
the full ports-live-v1 run with --recall-as-of, whose M89-M95 ask about the present.
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
    TP,
    case,
    mem,
)

SET_ID = "asof-live-v1"
DRAFT_REVIEW_STATUS = "UNREVIEWED"
FROZEN_REVIEW_STATUS = (
    "REVIEWED 2026-11-23: blind Codex (M97-M99 ok) and blind Gemini 4 Hydrogen "
    "(M97, M98 ok; M99 minor: accepted outcome named the move 'temporary' - renamed) "
    "- fixed before any run; FROZEN 2026-11-23"
)

REVIEW_RUBRIC = """# Blind oracle review rubric — asof-live-v1 (M97–M99)

You review synthetic evaluation scenarios for a local Ukrainian-speaking assistant ("Capri", runtime B-12). Clock: 2026-12-01T10:00:00+02:00. Memory records carry validity windows (`valid_from`, `valid_to`).

The set measures whether the assistant answers a question about a PAST period with the record that was valid then, not with today's records. A tool call (`memory_search`, optionally with `as_of`) is allowed but NOT required: the runtime may already offer the right records. Judge the answer.

Each item has: `family_id`, `catalog_class`, `expected_decision`, `evaluator_setup` (evaluator-only memory), two `prompt_variants` shown to the assistant, and `oracle` (`accepted_outcomes`, `required_evidence_ids`, `forbidden_effects`, `tool_policy`).

Classes:
- `A1_period_recall_m96` (`M97`): the ports-live-v1 M96 setup (October main address, a temporary November address, the current address, ten numbered workshops valid from 5 November). Asked for October; correct: вул. Вишнева, 14.
- `A2_period_recall_supplier` (`M98`): plywood supplier in September; later suppliers of other materials and the October plywood supplier crowd it out. Correct: ТОВ «Ліс-Пром».
- `A3_day_precision` (`M99`): the address on 10 November, between the end of the October address and the start of the current one. Correct: вул. Тополина, 8 (mentioning that the move was temporary is optional). Warehouse addresses valid from 5 November are other entities.

Per family check:
1. Does it test its class, and does `expected_decision` fit?
2. Is the oracle unambiguous and fair given the setup (would a correct assistant fail, or a wrong one pass)?
3. Are both Ukrainian prompt variants semantically equivalent, natural, and free of answer leaks?
4. Are `required_evidence_ids` and `forbidden_effects` accurate?

Verdict per family: `ok` / `minor` / `major` / `blocker`, with one-sentence `problem` and `fix`. Do not invent problems.
"""


def _m96_memory(prefix: str) -> list[dict]:
    rows = [
        mem(f"{prefix}-r1", "Адреса майстерні (основний цех, початкова локація) — вул. Вишнева, 14.", valid_from="2026-09-01", valid_to="2026-10-31", recorded="2026-09-01T10:00:00+02:00"),
        mem(f"{prefix}-r2", "Адреса майстерні (тимчасовий переїзд) — вул. Тополина, 8.", valid_from="2026-11-01", valid_to="2026-11-15", recorded="2026-11-01T10:00:00+02:00", supersedes=f"{prefix}-r1"),
        mem(f"{prefix}-r3", "Адреса майстерні (основний цех) — вул. Заводська, 22.", valid_from="2026-11-16", recorded="2026-11-16T10:00:00+02:00", supersedes=f"{prefix}-r2"),
    ]
    streets = ["вул. Стрийська, 9", "вул. Канатна, 18", "просп. Науки, 5", "вул. Сумська, 31", "вул. Соборності, 11", "вул. Садова, 3", "вул. Київська, 44", "вул. Полтавська, 12", "вул. Франка, 7", "вул. Шевченка, 19"]
    for n, street in enumerate(streets, start=1):
        rows.append(mem(f"{prefix}-r{n + 3}", f"Адреса майстерні №{n} — {street}.", valid_from="2026-11-05", recorded=f"2026-11-20T10:{n - 1:02d}:00+02:00"))
    return rows


def _moves_memory(prefix: str) -> list[dict]:
    """Main address history plus warehouses (other entities) valid from 5 November."""
    rows = [
        mem(f"{prefix}-r1", "Адреса майстерні (основний цех) — вул. Вишнева, 14.", valid_from="2026-09-01", valid_to="2026-10-31", recorded="2026-09-01T10:00:00+02:00"),
        mem(f"{prefix}-r2", "Адреса майстерні (тимчасовий переїзд на час ремонту) — вул. Тополина, 8.", valid_from="2026-11-01", valid_to="2026-11-15", recorded="2026-11-01T10:00:00+02:00", supersedes=f"{prefix}-r1"),
        mem(f"{prefix}-r3", "Адреса майстерні (основний цех після ремонту) — вул. Заводська, 22.", valid_from="2026-11-16", recorded="2026-11-16T10:00:00+02:00", supersedes=f"{prefix}-r2"),
    ]
    for n, street in enumerate(["вул. Лугова, 3", "вул. Річна, 17", "вул. Польова, 40", "вул. Гірська, 6", "вул. Озерна, 21", "вул. Липова, 12"], start=1):
        rows.append(mem(f"{prefix}-w{n}", f"Адреса складу №{n} — {street}.", valid_from="2026-11-05", recorded=f"2026-11-20T11:{n:02d}:00+02:00"))
    return rows


def _supplier_memory(prefix: str) -> list[dict]:
    rows = [
        mem(f"{prefix}-r1", "Постачальник фанери — ТОВ «Ліс-Пром».", valid_from="2026-07-01", valid_to="2026-09-30", recorded="2026-07-01T10:00:00+02:00"),
        mem(f"{prefix}-r2", "Постачальник фанери — ФОП Гнатюк.", valid_from="2026-10-01", recorded="2026-10-01T10:00:00+02:00", supersedes=f"{prefix}-r1"),
    ]
    others = [("фарби", "ТОВ «Колір-Плюс»"), ("клею", "ФОП Мельник"), ("метизів", "ТОВ «Кріп-Сервіс»"), ("лаку", "ТОВ «Лак-Майстер»"), ("шліфшкурки", "ФОП Дорош"), ("кромки", "ТОВ «Кромка-Юа»"), ("фурнітури", "ТОВ «Фурна»"), ("ДСП", "ТОВ «Плита-Центр»")]
    for n, (what, who) in enumerate(others, start=1):
        rows.append(mem(f"{prefix}-o{n}", f"Постачальник {what} — {who}.", valid_from="2026-10-10", recorded=f"2026-10-10T10:{n:02d}:00+02:00"))
    return rows


def build_cases() -> list[dict]:
    cases = [
        case(
            "M97", "A1_period_recall_m96", "NO_TOOL",
            {"synthetic_memory": _m96_memory("a97")},
            "Яка була адреса майстерні в жовтні?",
            "За якою адресою працювала майстерня у жовтні?",
            ["reports_vyshneva_14_valid_in_october"],
            ["mem:a97-r1"],
            ["reports_november_address_as_october", "invented_address"],
            tool_policy=TP,
        ),
        case(
            "M98", "A2_period_recall_supplier", "NO_TOOL",
            {"synthetic_memory": _supplier_memory("a98")},
            "Хто постачав нам фанеру у вересні?",
            "Від кого ми брали фанеру у вересні?",
            ["names_lis_prom_as_september_plywood_supplier"],
            ["mem:a98-r1"],
            ["names_gnatiuk_as_september_supplier", "names_other_material_supplier", "invented_supplier"],
            tool_policy=TP,
        ),
        case(
            "M99", "A3_day_precision", "NO_TOOL",
            {"synthetic_memory": _moves_memory("a99")},
            "Де працювала майстерня 10 листопада?",
            "За якою адресою була майстерня 10 листопада?",
            ["reports_topolyna_8_on_november_10"],
            ["mem:a99-r2"],
            ["reports_vyshneva_or_zavodska_for_november_10", "reports_warehouse_as_workshop", "invented_address"],
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
            "oracle": {k: v for k, v in c["oracle"].items() if k not in ("catalog_class", "review_status")},
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
        (args.review_pack / "schema.json").write_text(json.dumps(REVIEW_SCHEMA, separators=(",", ":")) + "\n", encoding="utf-8")
        (args.review_pack / "prompt.txt").write_text(f"{REVIEW_RUBRIC.rstrip()}\n\n```json\n{sheet_text}```\n", encoding="utf-8")
        print(f"Wrote review pack to {args.review_pack}")


if __name__ == "__main__":
    main()
