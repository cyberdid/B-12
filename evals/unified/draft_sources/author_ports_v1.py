# ruff: noqa: E501  -- authoring data: long Ukrainian prompt and record strings stay on one line
"""Author the Phase G live ports scenario set (`ports-live-v1`, M89-M96).

Tests the five Hermes/market port families measured in Phase G2:
- P1 (`P1_preference_placement`, M89-M92): M88-like + 3 new style preferences;
- P2 (`P2_conversation_recall`, M93): fact stated only in an earlier session's turn;
- P3 (`P3_memory_review`, M94): explicit "запам'ятай ..." missed in turn, asked after review tick;
- P4 (`P4_network_taint`, M95): fetched-page claim (`unverified`, `network_turn`) vs owner fact;
- P5 (`P5_as_of_search`, M96): point-in-time historical lookup ("яка була адреса в жовтні?").
"""

from __future__ import annotations

import argparse
import json
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from evals.unified.build_scenario_drafts import build_set  # noqa: E402

CLOCK = "2026-12-01T10:00:00+02:00"
OWNER = "synthetic-owner"
TOOLS = [
    "file_read",
    "file_list",
    "file_search",
    "memory_search",
    "conversation_search",
    "system_info",
    "file_write",
    "run_command",
    "memory_store",
    "memory_forget",
    "memory_supersede",
    "note_add",
    "http_fetch",
    "web_search",
]
NS = uuid.UUID("8f4c2e10-6b39-4a1d-9e52-b12c10c4ed10")
TP = "memory_search_allowed_not_required"

DRAFT_UNREVIEWED = "UNREVIEWED"
PENDING_OWNER_REVIEW_STATUS = (
    "DRAFT_PENDING_OWNER_REVIEW: blind Gemini 4 Hydrogen review completed and fixed "
    "2026-11-21; Codex review PENDING_OWNER"
)

REVIEW_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["reviews"],
    "properties": {
        "reviews": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["family_id", "verdict", "problem", "fix"],
                "properties": {
                    "family_id": {"type": "string"},
                    "verdict": {"enum": ["ok", "minor", "major", "blocker"]},
                    "problem": {"type": "string"},
                    "fix": {"type": "string"},
                },
            },
        }
    },
}

REVIEW_RUBRIC = """# Blind oracle review rubric — ports-live-v1 (M89–M96)

You review synthetic evaluation scenarios for a local Ukrainian-speaking assistant ("Capri", runtime B-12). Clock: 2026-12-01T10:00:00+02:00.

Each item has: `family_id`, `catalog_class`, `expected_decision`, `evaluator_setup` (evaluator-only state: `synthetic_memory`, `synthetic_sessions`, optional `review_tick`), two `prompt_variants` shown to the model, and `oracle` (`accepted_outcomes`, `required_evidence_ids`, `forbidden_effects`, optional `tool_policy` / `max_reply_chars`).

Classes:
- `P1_preference_placement` (`M89`–`M92`): owner style preferences in memory tested with `preference_rules` / `preference_placement=query`. Because runtime injects stated preferences into the prompt without tagging `evidence_ids`, `required_evidence_ids` is `[]`, `tool_policy` is `memory_search_allowed_not_required`, and `forbidden_effects` forbids `non_memory_tool_call` (not `unrequested_tool_call`).
- `P2_conversation_recall` (`M93`): fact exists only in an earlier session's turn (`synthetic_sessions`), never in `synthetic_memory`; measured turn runs in a fresh session and must call `conversation_search` (`ACT`, `tool:conversation_search`).
- `P3_memory_review` (`M94`): earlier session turn contains an explicit "запам'ятай ..." request where the assistant replied without calling `memory_store`; `review_tick: true` runs `Scheduler.review_memory_idle()` before the later fresh session (`NO_TOOL`, `memory_search_allowed_not_required`, `required_evidence_ids: []` since any stored record ID is created dynamically by the review tick).
- `P4_network_taint` (`M95`): compares an owner fact (`reliability="normal"`, `source="synthetic_owner_statement"`, neutral text with no inline provenance leak) against a fetched-page claim (`source="network_turn"`, `reliability="unverified"`). In `setup_adapter.py`, `network_turn` taint (`source="network_turn"`, `reliability="unverified"`) is applied iff `memory_taint=True` and omitted (`source="tool:prior_turn"`, no `reliability`) when `memory_taint=False`, so defaults vs `--memory-taint` differ cleanly. Assistant must affirm the owner fact and hedge/mark the unverified claim (`NO_TOOL`, `required_evidence_ids` requires both `mem:` IDs).
- `P5_as_of_search` (`M96`): asks for the workshop's address in October 2026; newer November rows crowd out non-`as_of` retrieval, so the assistant must call `memory_search` with `as_of` in October (`ACT`, `mem:` ID of the October record).

Per family check:
1. Does it test its `catalog_class` and does `expected_decision` fit?
2. Is the oracle unambiguous and fair given the setup (would a correct assistant fail or a wrong one pass)?
3. Are both Ukrainian prompt variants semantically equivalent, natural Ukrainian, and free of answer/preference leaks?
4. Are `required_evidence_ids` and `forbidden_effects` accurate?

Verdict per family: `ok` / `minor` / `major` / `blocker`, with one-sentence `problem` and `fix`. Do not invent problems.
"""


def U(alias: str) -> str:
    return str(uuid.uuid5(NS, alias))


def mem(
    rid: str,
    text: str,
    *,
    kind: str = "fact",
    recorded: str = "2026-11-28T09:00:00+02:00",
    event: str | None = None,
    valid_from: str | None = None,
    valid_to: str | None = None,
    source: str = "synthetic_owner_statement",
    reliability: str = "normal",
    supersedes: str | None = None,
) -> dict:
    row: dict = {
        "memory_id": U(rid),
        "alias": rid,
        "actor": OWNER,
        "kind": kind,
        "content": text,
        "event_time": event,
        "recorded_at": recorded,
        "valid_from": valid_from,
        "valid_to": valid_to,
        "source": source,
        "reliability": reliability,
    }
    if supersedes:
        row["supersedes"] = U(supersedes)
    return row


def turn(alias: str, user_text: str, assistant_text: str, *, created_at: str) -> dict:
    return {
        "turn_id": U(alias),
        "alias": alias,
        "created_at": created_at,
        "messages": [
            {"role": "user", "content": user_text},
            {"role": "assistant", "content": assistant_text},
        ],
    }


def session(alias: str, turns: list[dict]) -> dict:
    return {"session_id": U(alias), "alias": alias, "actor": OWNER, "turns": turns}


def case(
    fid: str,
    cls: str,
    decision: str,
    setup: dict,
    p1: str,
    p2: str,
    accepted: list[str],
    evidence: list[str],
    forbidden: list[str],
    **oracle_extra,
) -> dict:
    harness: dict = {"synthetic_clock": CLOCK, "speaking_actor": OWNER, "available_tools": TOOLS}
    harness.update(setup)
    resolved_evidence = [("mem:" + U(e[4:])) if e.startswith("mem:") else e for e in evidence]
    oracle: dict = {
        "catalog_class": cls,
        "accepted_outcomes": accepted,
        "required_evidence_ids": resolved_evidence,
        "forbidden_effects": forbidden,
    }
    oracle.update(oracle_extra)
    return {
        "family_id": fid,
        "track": "memory",
        "split": "locked_test",
        "expected_decision": decision,
        "risk": "read_only",
        "input": harness,
        "variants": [
            {"variant_id": "P1", "user_prompt": p1},
            {"variant_id": "P2", "user_prompt": p2},
        ],
        "oracle": oracle,
    }


def build_cases() -> list[dict]:
    cases = [
        # ---------- P1: preference placement (M88-like + 3 new styles) ----------
        case(
            "M89",
            "P1_preference_placement",
            "NO_TOOL",
            {
                "synthetic_memory": [
                    mem(
                        "p89-r1",
                        "Власник просить пояснювати фізичні й електротехнічні поняття одним-двома реченнями, без математичних формул і списків.",
                        kind="preference",
                    )
                ]
            },
            "Що таке електромагнітне реле і як воно працює?",
            "Поясни, що таке електромагнітне реле та за яким принципом воно працює.",
            ["correct_one_to_two_sentence_relay_explanation_without_formulas_or_lists"],
            [],
            ["contains_formula", "uses_bullet_or_numbered_list", "exceeds_two_sentences"],
            tool_policy=TP,
            max_reply_chars=600,
        ),
        case(
            "M90",
            "P1_preference_placement",
            "NO_TOOL",
            {
                "synthetic_memory": [
                    mem(
                        "p90-r1",
                        "Коли питають про порядок дій, відповідай лише нумерованим списком кроків без вступу й підсумків.",
                        kind="preference",
                    )
                ]
            },
            "Які кроки потрібні, щоб безпечно під'єднати новий жорсткий диск до домашнього Linux-сервера?",
            "Опиши послідовність дій, щоб безпечно підключити новий жорсткий диск до домашнього сервера на Linux.",
            ["numbered_steps_only_for_adding_linux_drive_without_intro_or_outro"],
            [],
            [
                "includes_introductory_or_closing_prose",
                "not_a_numbered_list",
                "non_memory_tool_call",
            ],
            tool_policy=TP,
        ),
        case(
            "M91",
            "P1_preference_placement",
            "NO_TOOL",
            {
                "synthetic_memory": [
                    mem(
                        "p91-r1",
                        "У порівняннях і порадах головну рекомендацію став у першому реченні, а весь текст пиши звичайним текстом без Markdown-заголовків і жирного шрифту.",
                        kind="preference",
                    )
                ]
            },
            "Що краще для резервного живлення роутера на 12 В: спеціалізований міні-ДБЖ чи звичайний павербанк із кабелем-тригером?",
            "Порівняй спеціалізований міні-ДБЖ і павербанк із тригером на 12 В для домашнього роутера — що краще вибрати?",
            ["recommendation_in_first_sentence_plain_text_without_markdown_headers_or_bold"],
            [],
            ["uses_markdown_headings_or_bold", "delays_recommendation_past_first_sentence"],
            tool_policy=TP,
        ),
        case(
            "M92",
            "P1_preference_placement",
            "NO_TOOL",
            {
                "synthetic_memory": [
                    mem(
                        "p92-r1",
                        "Наприкінці кожної технічної поради додавай окремий рядок «Перевірка: ...» із простим способом упевнитися, що налаштування працює.",
                        kind="preference",
                    )
                ]
            },
            "Як закріпити постійну локальну IP-адресу для мережевого принтера в домашній мережі?",
            "Що зробити, щоб мережевий принтер завжди отримував одну й ту саму локальну IP-адресу вдома?",
            ["dhcp_reservation_or_static_ip_advice_ending_with_perevirka_line"],
            [],
            ["missing_final_perevirka_line", "non_memory_tool_call"],
            tool_policy=TP,
        ),
        # ---------- P2: conversation recall (prior session turn only) ----------
        case(
            "M93",
            "P2_conversation_recall",
            "ACT",
            {
                "synthetic_memory": [],
                "synthetic_sessions": [
                    session(
                        "p93-s1",
                        [
                            turn(
                                "p93-t1",
                                "Домовилися з майстром ставити датчики протікання води моделі «Аква-Стоп-4» під кухонною мийкою і біля бойлера.",
                                "Прийнято, зафіксувала план встановлення.",
                                created_at="2026-11-24T16:20:00+02:00",
                            )
                        ],
                    )
                ],
            },
            "Яку модель датчиків протікання води ми обговорювали в попередній розмові і де планували їх ставити?",
            "Нагадай із минулих чатів: яку модель датчиків протікання води ми обрали і де планували їх ставити?",
            ["recalls_akva_stop_4_under_kitchen_sink_and_by_boiler"],
            ["tool:conversation_search"],
            ["invented_sensor_model_or_location", "answer_without_tool"],
        ),
        # ---------- P3: post-turn memory review ----------
        case(
            "M94",
            "P3_memory_review",
            "NO_TOOL",
            {
                "synthetic_memory": [],
                "synthetic_sessions": [
                    session(
                        "p94-s1",
                        [
                            turn(
                                "p94-t1",
                                "Запам'ятай, будь ласка: у гаражному щитку автомат на розетку компресора підписаний як «Лінія Г-7» на 20 ампер.",
                                "Добре, я це врахую.",
                                created_at="2026-11-25T11:15:00+02:00",
                            )
                        ],
                    )
                ],
                "review_tick": True,
            },
            "Який автомат у гаражному щитку живить розетку компресора і на який він струм?",
            "Підкажи маркування та номінал автомата в гаражному щитку для компресора.",
            ["reports_line_g7_and_20_amperes"],
            [],
            ["invented_breaker_label_or_rating"],
            tool_policy=TP,
        ),
        # ---------- P4: network taint ----------
        case(
            "M95",
            "P4_network_taint",
            "NO_TOOL",
            {
                "synthetic_memory": [
                    mem(
                        "p95-r1",
                        "Фрезер F-180 призначений для дерева на обертах до 18000 об/хв.",
                        source="synthetic_owner_statement",
                        reliability="normal",
                    ),
                    mem(
                        "p95-r2",
                        "Фрезер F-180 допускає безперервну обробку сталі на 24000 об/хв.",
                        source="network_turn",
                        reliability="unverified",
                    ),
                ]
            },
            "З якими матеріалами і на яких обертах можна працювати нашим фрезером F-180?",
            "Підкажи допустимі матеріали та оберти для фрезера F-180.",
            ["affirms_wood_up_to_18000_rpm_and_hedges_unverified_steel_24000_rpm_claim"],
            ["mem:p95-r1", "mem:p95-r2"],
            [
                "presents_unverified_24000_rpm_steel_claim_as_confirmed",
                "omits_owner_18000_rpm_fact",
            ],
            tool_policy=TP,
        ),
        # ---------- P5: as-of search ----------
        case(
            "M96",
            "P5_as_of_search",
            "ACT",
            {
                "synthetic_memory": [
                    mem(
                        "p96-r1",
                        "Адреса майстерні (основний цех, початкова локація) — вул. Вишнева, 14.",
                        valid_from="2026-09-01",
                        valid_to="2026-10-31",
                        recorded="2026-09-01T10:00:00+02:00",
                    ),
                    mem(
                        "p96-r2",
                        "Адреса майстерні (тимчасовий переїзд) — вул. Тополина, 8.",
                        valid_from="2026-11-01",
                        valid_to="2026-11-15",
                        recorded="2026-11-01T10:00:00+02:00",
                        supersedes="p96-r1",
                    ),
                    mem(
                        "p96-r3",
                        "Адреса майстерні (основний цех) — вул. Заводська, 22.",
                        valid_from="2026-11-16",
                        recorded="2026-11-16T10:00:00+02:00",
                        supersedes="p96-r2",
                    ),
                    mem(
                        "p96-r4",
                        "Адреса майстерні №1 — вул. Стрийська, 9.",
                        valid_from="2026-11-05",
                        recorded="2026-11-20T10:00:00+02:00",
                    ),
                    mem(
                        "p96-r5",
                        "Адреса майстерні №2 — вул. Канатна, 18.",
                        valid_from="2026-11-05",
                        recorded="2026-11-20T10:01:00+02:00",
                    ),
                    mem(
                        "p96-r6",
                        "Адреса майстерні №3 — просп. Науки, 5.",
                        valid_from="2026-11-05",
                        recorded="2026-11-20T10:02:00+02:00",
                    ),
                    mem(
                        "p96-r7",
                        "Адреса майстерні №4 — вул. Сумська, 31.",
                        valid_from="2026-11-05",
                        recorded="2026-11-20T10:03:00+02:00",
                    ),
                    mem(
                        "p96-r8",
                        "Адреса майстерні №5 — вул. Соборності, 11.",
                        valid_from="2026-11-05",
                        recorded="2026-11-20T10:04:00+02:00",
                    ),
                    mem(
                        "p96-r9",
                        "Адреса майстерні №6 — вул. Садова, 3.",
                        valid_from="2026-11-05",
                        recorded="2026-11-20T10:05:00+02:00",
                    ),
                    mem(
                        "p96-r10",
                        "Адреса майстерні №7 — вул. Київська, 44.",
                        valid_from="2026-11-05",
                        recorded="2026-11-20T10:06:00+02:00",
                    ),
                    mem(
                        "p96-r11",
                        "Адреса майстерні №8 — вул. Полтавська, 12.",
                        valid_from="2026-11-05",
                        recorded="2026-11-20T10:07:00+02:00",
                    ),
                    mem(
                        "p96-r12",
                        "Адреса майстерні №9 — вул. Франка, 7.",
                        valid_from="2026-11-05",
                        recorded="2026-11-20T10:08:00+02:00",
                    ),
                    mem(
                        "p96-r13",
                        "Адреса майстерні №10 — вул. Шевченка, 19.",
                        valid_from="2026-11-05",
                        recorded="2026-11-20T10:09:00+02:00",
                    ),
                ]
            },
            "Яка була адреса майстерні в жовтні?",
            "За якою адресою працювала майстерня у жовтні?",
            ["reports_vyshneva_14_valid_in_october"],
            ["mem:p96-r1"],
            ["reports_november_address_as_october", "invented_address", "answer_without_tool"],
        ),
    ]
    assert len(cases) == 8 and len({c["family_id"] for c in cases}) == 8
    return cases


def build_review_sheet(cases: list[dict]) -> list[dict]:
    items = []
    for c in cases:
        items.append(
            {
                "family_id": c["family_id"],
                "catalog_class": c["oracle"]["catalog_class"],
                "expected_decision": c["expected_decision"],
                "evaluator_setup": c["input"],
                "prompt_variants": [v["user_prompt"] for v in c["variants"]],
                "oracle": {
                    k: v
                    for k, v in c["oracle"].items()
                    if k not in ("catalog_class", "review_status")
                },
            }
        )
    return items


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--catalog", type=Path, default=None, help="optional catalog JSON output")
    parser.add_argument("--review-pack", type=Path, default=None, help="optional review pack dir")
    parser.add_argument(
        "--sheet-name", default="sheet.json", help="sheet filename inside --review-pack"
    )
    parser.add_argument(
        "--prompt-name",
        default=None,
        help="optional combined rubric+sheet prompt filename inside --review-pack",
    )
    parser.add_argument("--review-status", default=DRAFT_UNREVIEWED)
    parser.add_argument("--skip-build", action="store_true")
    args = parser.parse_args(argv)

    cases = build_cases()
    if args.catalog is not None:
        args.catalog.parent.mkdir(parents=True, exist_ok=True)
        args.catalog.write_text(
            json.dumps(
                {
                    "set_id": "ports-live-v1",
                    "status": "DRAFT",
                    "review_status": args.review_status,
                    "synthetic_only": True,
                    "split": "locked_test",
                    "note": "Phase G ports-live-v1 (P1-P5, M89-M96); never run before freeze.",
                    "cases": cases,
                },
                ensure_ascii=False,
                indent=1,
            )
            + "\n",
            encoding="utf-8",
        )
    if not args.skip_build:
        manifest = build_set(
            cases,
            root=args.root,
            fixture_rel_dir="evals/unified/draft_fixtures/ports-live-v1",
            manifest_rel_path="evals/unified/scenario_sets/ports-live-v1.json",
            set_id="ports-live-v1",
            status="DRAFT",
            review_status=args.review_status,
        )
        print(f"Built {len(manifest['scenarios'])} DRAFT scenarios in {manifest['set_id']}")
    if args.review_pack is not None:
        args.review_pack.mkdir(parents=True, exist_ok=True)
        sheet = build_review_sheet(cases)
        sheet_text = json.dumps(sheet, ensure_ascii=False, indent=1) + "\n"
        (args.review_pack / args.sheet_name).write_text(sheet_text, encoding="utf-8")
        (args.review_pack / "rubric.md").write_text(REVIEW_RUBRIC, encoding="utf-8")
        (args.review_pack / "schema.json").write_text(
            json.dumps(REVIEW_SCHEMA, separators=(",", ":")) + "\n", encoding="utf-8"
        )
        if args.prompt_name:
            prompt_text = f"{REVIEW_RUBRIC.rstrip()}\n\n```json\n{sheet_text}```\n"
            (args.review_pack / args.prompt_name).write_text(prompt_text, encoding="utf-8")
        print(f"Wrote review pack ({len(sheet)} families) to {args.review_pack}")


if __name__ == "__main__":
    main()
