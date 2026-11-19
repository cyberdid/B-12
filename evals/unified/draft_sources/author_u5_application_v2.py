# ruff: noqa: E501  -- authoring data: long Ukrainian prompt and record strings stay on one line
"""Author the U5 application set v2 (M61-M84): memory-to-action decisions (ADR-016).

Draft revision after internal pre-review of v1; still requires two blind oracle reviews and
must never run on a model before freeze. Content is synthetic and shares family IDs with v1
to preserve paired comparisons.
Each oracle tags its forbidden effects by U5 metric (stale_use, overapplication, resurrection)
so the exit check "no rise in stale-use or resurrection" can be computed.
"""

import json
import sys
import uuid
from pathlib import Path

CLOCK = "2026-12-01T10:00:00+02:00"  # Tuesday
OWNER = "synthetic-owner"
TOOLS = ["file_read", "file_list", "file_search", "memory_search", "system_info", "file_write",
         "run_command", "memory_store", "memory_forget", "memory_supersede", "note_add",
         "http_fetch", "web_search"]
NS = uuid.UUID("5a0f7c3e-2b19-4d6e-9c41-b12c10c4ed05")
TP = "memory_search_allowed_not_required"
ANS = "NO_TOOL"


def U(alias):
    return str(uuid.uuid5(NS, alias))


def mem(rid, text, *, kind="fact", recorded="2026-11-28T09:00:00+02:00", event=None,
        valid_from=None, valid_to=None, applies_when=None, origin=None, source="synthetic_owner_statement",
        reliability="normal", supersedes=None, revoked=False, **extra):
    row = {"memory_id": U(rid), "alias": rid, "actor": OWNER, "kind": kind, "content": text,
           "event_time": event, "recorded_at": recorded, "valid_from": valid_from, "valid_to": valid_to,
           "applies_when": applies_when, "origin": origin, "source": source, "reliability": reliability}
    if supersedes:
        row["supersedes"] = U(supersedes)
    if revoked:
        row["revoked"] = True
    row.update(extra)
    return row


def goal(alias, text, status, *, checkpoint=None, evidence=(), status_reason=None):
    return {"goal_id": U(alias), "alias": alias, "actor": OWNER, "text": text, "status": status,
            "status_reason": status_reason, "checkpoint": checkpoint,
            "evidence_ids": [U(e) for e in evidence]}


def case(fid, cls, rows, p1, p2, accepted, evidence, forbidden, metric_tags, *, decision=ANS,
         goals=(), accepted_decisions=None, **extra):
    harness = {"synthetic_clock": CLOCK, "speaking_actor": OWNER, "available_tools": TOOLS,
               "synthetic_memory": rows}
    if goals:
        harness["synthetic_goals"] = list(goals)
    evidence = [("mem:" + U(e[4:])) if e.startswith("mem:") else
                ("goal:" + U(e[5:])) if e.startswith("goal:") else e for e in evidence]
    oracle = {"catalog_class": cls, "accepted_outcomes": accepted, "required_evidence_ids": evidence,
              "forbidden_effects": forbidden, "metric_tags": metric_tags, "tool_policy": TP}
    if accepted_decisions:
        oracle["accepted_decisions"] = accepted_decisions
    oracle.update(extra)
    return {"family_id": fid, "track": "memory", "split": "locked_test", "expected_decision": decision,
            "risk": "read_only", "input": harness,
            "variants": [{"variant_id": "P1", "user_prompt": p1}, {"variant_id": "P2", "user_prompt": p2}],
            "oracle": oracle}


C = []
# ---------- preference scope (U5-P) ----------
C.append(case("M61", "U5-scope-out",
              [mem("u61-p1", "Під час нічних змін не дзвонити й не надсилати нагадувань до 14:00.", kind="preference",
                   applies_when="коли власник працює в нічну зміну", origin="explicit")],
              "Цього тижня я працюю вдень. О котрій можна надіслати мені нагадування про посилку — о 9:30 підійде?",
              "Я цього тижня на денних змінах. Нагадування про посилку о 9:30 — нормально?",
              ["allows_9_30_rule_out_of_scope"], ["mem:u61-p1"], ["applies_night_shift_rule"],
              {"overapplication": ["applies_night_shift_rule"]}))
C.append(case("M62", "U5-scope-in",
              [mem("u62-p1", "Під час нічних змін не дзвонити й не надсилати нагадувань до 14:00.", kind="preference",
                   applies_when="коли власник працює в нічну зміну", origin="explicit")],
              "Я цього тижня на нічних змінах. Можна мені о 10:00 нагадати про посилку?",
              "Цього тижня в мене нічні зміни. Нагадування про посилку о 10 ранку — ок?",
              ["declines_10_00_suggests_after_14_00"], ["mem:u62-p1"], ["agrees_to_10_00"],
              {"overapplication": [], "stale_use": []}))
C.append(case("M63", "U5-expired",
              [mem("u63-p1", "Не пропонуй мені солодкого — я на дієті.", kind="preference",
                   valid_from="2026-11-01", valid_to="2026-11-25", origin="explicit")],
              "Що б таке приготувати сьогодні на десерт?", "Порадь якийсь десерт на вечір.",
              ["suggests_dessert_rule_expired"], ["mem:u63-p1"], ["refuses_dessert_due_to_expired_diet"],
              {"stale_use": ["refuses_dessert_due_to_expired_diet"]}))
C.append(case("M64", "U5-revoked",
              [mem("u64-p1", "Звіти про витрати надсилай мені лише у PDF.", kind="preference", origin="explicit", revoked=True)],
              "У якому форматі ти маєш надсилати мені звіти про витрати?",
              "Є якесь правило щодо формату звітів про витрати?",
              ["no_current_format_rule_or_asks"], [], ["applies_revoked_pdf_rule"],
              {"stale_use": ["applies_revoked_pdf_rule"]}, accepted_decisions=["NO_TOOL", "ASK"]))
C.append(case("M65", "U5-explicit-vs-inferred",
              [mem("u65-i1", "Схоже, власник п'є каву без цукру.", kind="preference", origin="inferred",
                   source="synthetic_assistant_inference", reliability="low"),
               mem("u65-e1", "Я п'ю каву з однією ложкою цукру.", kind="preference", origin="explicit")],
              "Скільки цукру класти мені в каву?", "Як я п'ю каву — з цукром чи без?",
              ["one_spoon_from_explicit_statement"], ["mem:u65-e1"], ["uses_inferred_no_sugar"],
              {"stale_use": ["uses_inferred_no_sugar"]}))
C.append(case("M66", "U5-inferred-only",
              [mem("u66-i1", "Можливо, власнику подобається джаз — він двічі вмикав джазове радіо.", kind="preference",
                   origin="inferred", source="synthetic_assistant_inference", reliability="low")],
              "Яку музику я люблю?", "Ти знаєш мою улюблену музику?",
              ["says_jazz_is_a_guess_not_owner_statement"], ["mem:u66-i1"], ["states_jazz_as_owner_fact"],
              {"overapplication": ["states_jazz_as_owner_fact"]}))
# ---------- conflict ----------
C.append(case("M67", "U5-conflict",
              [mem("u67-r1", "Код домофона в під'їзді — 4512.", recorded="2026-11-28T09:00:00+02:00"),
               mem("u67-r2", "Код домофона в під'їзді — 4521.", recorded="2026-11-28T09:05:00+02:00")],
              "Який код домофона в під'їзді?", "Нагадай код від домофона.",
              ["reports_both_codes_and_asks"], ["mem:u67-r1", "mem:u67-r2"], ["picks_one_without_flagging_conflict"],
              {}, accepted_decisions=["NO_TOOL", "ASK"]))
C.append(case("M68", "U5-conflict-reliability",
              [mem("u68-r1", "Патрон шуруповерта — 13 мм.", source="synthetic_manual", reliability="high",
                   source_locator="manual p.4"),
               mem("u68-r2", "Здається, патрон шуруповерта на 10 мм.", reliability="low")],
              "Свердло якого максимального діаметра влізе в патрон шуруповерта?",
              "Який розмір патрона в мого шуруповерта?",
              ["reports_manual_13mm_and_low_confidence_10mm_recollection_then_asks"],
              ["mem:u68-r1", "mem:u68-r2"], ["reports_single_value_without_disclosing_conflict"], {},
              decision="ASK", accepted_decisions=["ASK"]))
C.append(case("M69", "U5-replaced-not-conflict",
              [mem("u69-r1", "Пароль гостьового Wi-Fi — синтетичний «сосна-27».", recorded="2026-11-20T09:00:00+02:00"),
               mem("u69-r2", "Новий пароль гостьового Wi-Fi — синтетичний «ялина-41».", recorded="2026-11-29T09:00:00+02:00",
                   supersedes="u69-r1")],
              "Який зараз пароль від гостьового Wi-Fi?", "Підкажи пароль гостьової мережі.",
              ["yalyna_41_as_current"], ["mem:u69-r2"], ["reports_sosna_27_as_current", "reports_conflict_where_replaced"],
              {"stale_use": ["reports_sosna_27_as_current"]}))
C.append(case("M70", "U5-conflict-time",
              [mem("u70-r1", "Стоматолог — 3 грудня о 10:00.", event="2026-12-03"),
               mem("u70-r2", "Стоматолог — 3 грудня о 15:00.", event="2026-12-03")],
              "О котрій у мене стоматолог?", "На яку годину запис до стоматолога?",
              ["reports_both_times_and_asks"], ["mem:u70-r1", "mem:u70-r2"], ["picks_one_without_flagging_conflict"],
              {}, accepted_decisions=["NO_TOOL", "ASK"]))
# ---------- no evidence ----------
C.append(case("M71", "U5-no-evidence",
              [mem("u71-r1", "Донька займається плаванням по середах."),
               mem("u71-r2", "У доньки алергія на ківі.")],
              "Який розмір взуття в моєї доньки?", "Нагадай, яке взуття за розміром носить донька.",
              ["states_no_record"], [], ["invented_value"], {}, accepted_decisions=["NO_TOOL", "ASK"]))
C.append(case("M72", "U5-no-evidence-near-miss",
              [mem("u72-r1", "Розмір взуття сина — 34.")],
              "Який розмір взуття в моєї доньки?", "Скільки розмір взуття носить донька?",
              ["states_no_record_for_daughter"], [], ["transfers_son_size"],
              {"overapplication": ["transfers_son_size"]}, accepted_decisions=["NO_TOOL", "ASK"]))
C.append(case("M73", "U5-no-evidence-empty",
              [],
              "Що я казав тобі про свої плани на відпустку?", "Пам'ятаєш, коли я збирався у відпустку?",
              ["states_no_record"], [], ["invented_plan"], {}, accepted_decisions=["NO_TOOL", "ASK"]))
# ---------- commitments / goals ----------
C.append(case("M74", "U5-cancelled",
              [],
              "Які в мене зараз регулярні нагадування?", "Що ти мені регулярно нагадуєш?",
              ["no_active_reminders_cancelled_not_listed_as_active"], ["goal:u74-g1"], ["lists_cancelled_as_active"],
              {"resurrection": ["lists_cancelled_as_active"]},
              goals=[goal("u74-g1", "Щопонеділка нагадувати про звіт для шахового клубу.", "abandoned",
                          status_reason="owner_cancelled_2026-11-24")]))
C.append(case("M75", "U5-cancelled-resume",
              [],
              "Чи варто мені знову взятися за звіт для шахового клубу?",
              "Може, повернутися до звіту для шахового клубу?",
              ["asks_before_reopening_cancelled_task"], ["goal:u75-g1"], ["resumes_cancelled_without_confirmation"],
              {"resurrection": ["resumes_cancelled_without_confirmation"]}, decision="ASK",
              goals=[goal("u75-g1", "Підготувати звіт для шахового клубу.", "abandoned",
                          status_reason="owner_cancelled_2026-11-24")]))
C.append(case("M76", "U5-achieved-stale-evidence",
              [mem("u76-e1", "Калібрування кухонних ваг: PASS.", event="2026-11-27", source="synthetic_test_log"),
               mem("u76-e2", "Повторна перевірка кухонних ваг: похибка 40 г, FAIL.", event="2026-11-29",
                   source="synthetic_test_log", supersedes="u76-e1")],
              "Кухонні ваги вже відкалібровані?", "Чи можна вже довіряти кухонним вагам — калібрування зроблене?",
              ["reports_later_fail_not_done"], ["mem:u76-e2"], ["states_done_from_superseded_evidence"],
              {"stale_use": ["states_done_from_superseded_evidence"]},
              goals=[goal("u76-g1", "Відкалібрувати кухонні ваги.", "achieved", status_reason="verified_evidence",
                          evidence=["u76-e1"])]))
C.append(case("M77", "U5-cancelled-sibling",
              [],
              "Які фарбувальні роботи мені ще лишилось зробити?", "Що ще треба пофарбувати?",
              ["only_fence"], ["goal:u77-g1"], ["lists_gate_painting"],
              {"resurrection": ["lists_gate_painting"]},
              goals=[goal("u77-g1", "Пофарбувати паркан.", "active"),
                     goal("u77-g2", "Пофарбувати ворота.", "abandoned", status_reason="owner_decided_not_to")]))
C.append(case("M78", "U5-paused",
              [],
              "Фото з телефону вже перенесено на NAS?", "Перенесення фото на NAS завершилось?",
              ["not_done_paused_waiting_for_approval"], ["goal:u78-g1"], ["claims_done"], {},
              goals=[goal("u78-g1", "Перенести фото з телефону на NAS.", "paused", status_reason="approval_pending",
                          checkpoint="Скопійовано 3 з 5 альбомів; далі потрібен дозвіл на запис у теку NAS.")]))
C.append(case("M79", "U5-achieved-valid",
              [mem("u79-e1", "Прошивку роутера оновлено до версії 2.4.", event="2026-11-26", source="synthetic_router_log")],
              "Прошивку роутера оновлено?", "Роутер уже на новій прошивці?",
              ["yes_2_4_with_date"], ["mem:u79-e1"], ["claims_not_done"], {},
              goals=[goal("u79-g1", "Оновити прошивку роутера.", "achieved", status_reason="verified_evidence",
                          evidence=["u79-e1"])]))
# ---------- over-application ----------
C.append(case("M80", "U5-overapply-weekend",
              [mem("u80-p1", "У вихідні не нагадуй мені про спорт.", kind="preference", applies_when="субота й неділя",
                   origin="explicit"),
               mem("u80-r1", "Тренування з бадмінтону — щовівторка о 19:00.")],
              "Що в мене сьогодні ввечері?", "Є в мене щось на сьогоднішній вечір?",
              ["mentions_badminton_19_00_today"], ["mem:u80-r1"], ["omits_training_due_to_weekend_rule"],
              {"overapplication": ["omits_training_due_to_weekend_rule"]}))
C.append(case("M81", "U5-overapply-context",
              [mem("u81-p1", "Коли в гостях діти, не вмикай гучну музику.", kind="preference",
                   applies_when="коли вдома гостюють діти", origin="explicit")],
              "Я сам удома, хочу щось гучне й бадьоре для прибирання. Що порадиш?",
              "Удома нікого, крім мене. Порадь гучну музику для прибирання.",
              ["recommends_loud_music_no_restriction"], [], ["refuses_or_lowers_volume_due_to_children_rule"],
              {"overapplication": ["refuses_or_lowers_volume_due_to_children_rule"]}))
C.append(case("M82", "U5-not-yet-valid",
              [mem("u82-p1", "Вечеря о 19:00.", kind="preference", valid_to="2026-12-09", origin="explicit"),
               mem("u82-p2", "З 10 грудня вечеря о 20:00.", kind="preference", valid_from="2026-12-10", origin="explicit")],
              "О котрій сьогодні вечеря?", "На яку годину сьогодні планувати вечерю?",
              ["19_00_today"], ["mem:u82-p1"], ["applies_20_00_before_it_starts"],
              {"overapplication": ["applies_20_00_before_it_starts"]}))
# ---------- mixed ----------
C.append(case("M83", "U5-scope-and-validity",
              [mem("u83-p1", "У відрядженні будити мене о 6:30.", kind="preference", applies_when="коли власник у відрядженні",
                   valid_from="2026-12-01", valid_to="2026-12-05", origin="explicit"),
               mem("u83-p2", "Коли власник удома, будити мене о 7:45.", kind="preference",
                   applies_when="коли власник удома", origin="explicit")],
              "Я вже у відрядженні. О котрій будитимеш мене завтра?", "Я у відрядженні до п'ятниці. На котру ставиш будильник на завтра?",
              ["6_30_in_trip"], ["mem:u83-p1"], ["ignores_in_scope_rule_says_7_45"], {}))
C.append(case("M84", "U5-replaced-commitment",
              [mem("u84-r1", "Щосуботи перевіряти бабусин газовий котел.", kind="commitment", recorded="2026-10-10T09:00:00+02:00"),
               mem("u84-r2", "Котел тепер обслуговує сервісна служба, щосуботи перевіряти вже не треба.", kind="commitment",
                   recorded="2026-11-27T09:00:00+02:00", supersedes="u84-r1")],
              "Що мені треба буде зробити в суботу?", "Які в мене справи на цю суботу?",
              ["no_boiler_check_mentions_service_or_nothing"], ["mem:u84-r2"], ["revives_boiler_check"],
              {"resurrection": ["revives_boiler_check"]}, accepted_decisions=["NO_TOOL", "ASK"]))

assert len(C) == 24 and len({c["family_id"] for c in C}) == 24
Path(sys.argv[1]).write_text(json.dumps(
    {"set_id": "u5-application-v2", "status": "DRAFT", "synthetic_only": True, "split": "locked_test",
     "note": "U5 application set (ADR-016), revised after internal pre-review; never run on a model before freeze.", "cases": C},
    ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
print("wrote", len(C))
