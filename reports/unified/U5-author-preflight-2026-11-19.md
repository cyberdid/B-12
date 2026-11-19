---
type: corpus_review
updated: 2026-11-19
status: internal_preflight_not_independent_review
sources:
  - reports/unified/ADR-016-scoped-memory-to-action.md
  - evals/unified/draft_sources/author_u5_application_v1.py
  - evals/unified/draft_sources/author_u5_application_v2.py
  - evals/unified/draft_sources/author_u5_application_v3.py
  - evals/unified/scenario_sets/u5-application-v1.json
  - evals/unified/scenario_sets/u5-application-v2.json
  - evals/unified/scenario_sets/u5-application-v3.json
  - reports/unified/oracle-review-u5-v2/README.md
  - reports/unified/oracle-review-u5-v3/README.md
  - evals/unified/setup_adapter.py
  - evals/unified/run_u2_u3.py
  - tests/unified/test_setup_adapter.py
  - tests/unified/test_run_u2_u3.py
tags: [U5, oracle, preflight, memory]
---

# U5 corpus author preflight

Це перевірка узгодженості автором корпусу з ADR-016 і runtime-політикою. Вона **не є незалежним сліпим review** і не замінює двох зовнішніх оцінок оракула.

## Висновки й виправлення

| Сімейство | Проблема у v1 | Зміна у v2 |
|---|---|---|
| M65 — explicit vs inferred | Корпус очікував перевагу прямої заяви власника, але системна інструкція лише вимагала уточнювати конфлікти. | Додано правило: актуальний запис із походженням `власник сказав прямо` має перевагу над суперечним `помічник вивів`; висновок позначається непідтвердженим. Промпт також каже, що `origin` — мітка моделі, не незалежне підтвердження. Додано інтеграційну перевірку інструкції та збереження уточнення для інших конфліктів. |
| M68 — reliability conflict | Оракул обирав 13 мм з manual і не вимагав згадати суперечний спогад 10 мм, хоча runtime каже не обирати переможця серед інших актуальних конфліктів. | Тепер потрібні обидва джерела, розкриття різної надійності й уточнення; рішення — `ASK`. Застосовувати загальне ранжування джерел runtime поки не вміє й не має підстав непомітно його вигадувати. |
| M83 — scope and validity | Загальне правило 07:45 мало `applies_when=null` (тобто без обмеження), тому одночасно діяло з правилом 06:30 у відрядженні. Це конфлікт, а не однозначна перевага вузького scope за поточною політикою. | Загальне правило тепер діє лише вдома; поїздкове — у відрядженні. У змодельованому стані застосовується лише 06:30. |
| M75 — cancelled resume | Формулювання «продовж» було прямою командою, тоді як оракул вимагав перепитати, чи відновити задачу. | Запити змінено на прохання поради («чи варто знову взятися…», «може, повернутися…»). Відповідь має назвати факт скасування та спитати перед будь-якою зміною стану. Це відповідає поточній межі: закриті цілі відновлює довірений owner control path, не вільний model text. |

## Артефакти й перевірки

- `u5-application-v1` збережено як `RETIRED`; він не проходив незалежного review і не запускався на моделі.
- На момент першого preflight `u5-application-v2` мав 24 сімейства / 48 варіантів і статус `DRAFT`; після action-language preflight його позначено `RETIRED`, див. розділ v3 нижче. Джерело — `author_u5_application_v2.py`.
- `evals.unified.validate_scenarios` підтвердив схему, унікальні ID, безпечні fixture paths та SHA-256 v2. Валідатор прямо обмежує свою гарантію структурою; він не оцінює семантичну якість.
- Підготовлено `reports/unified/oracle-review-u5-v2/` із рубрикою, prompt, JSON sheet, схемою відповіді та SHA-256 сумами. У пакеті немає model outputs або arm labels.
- Новий інтеграційний тест перевіряє, що runtime prompt містить explicit-vs-inferred правило, його caveat і уточнення для інших конфліктів.

## Evaluator setup preflight

Перевірка runner-підготовки виявила окрему технічну прогалину: adapter раніше викидав `applies_when` і `origin`, не переносив revoked-стан та не передавав прапорець scoped memory під час seed. Це виправлено в `evals/unified/setup_adapter.py` та `run_u2_u3.py`. Замінені й відкликані записи тепер проходять штатний memory lifecycle; цілі створюються до цих переходів, щоб сценарій міг відтворити ціль, що була досягнута на чинному доказі, який пізніше застарів.

No-model перевірки: **49 passed** у п'яти evaluator-модулях; із них 35 тестів — setup adapter і scripted runner. Усі 24 P1 setups активного на момент цих тестів набору засіялися без відкидання непорожніх полів пам'яті; scripted Ollama підтвердив, що scope metadata доходить до контексту. Перевірка runner та fixtures не є модельним результатом або незалежним review oracle.

## Метрики та criterion-level judgments

Статичний аудит scorer знайшов, що попередній combined.json зберігав лише загальний semantic verdict і список спорів; одностайні мітки окремих критеріїв відкидалися. Це не дозволяло достовірно розділити stale_use, overapplication і resurrection, а deterministic FAIL міг прибрати judge item, потрібний для метрики.

Додано збереження per-criterion labels/votes, optional criterion-level owner adjudication, збереження metric-tagged criteria у blind sheet навіть при сторонньому deterministic FAIL, та evals/unified/analyze_u5_metrics.py. Аналізатор трактує met на tagged forbidden effect як adverse event; not_met — як його відсутність; disputed/unclear/missing/run-failed outcome лишається unknown. Звіт показує pooled counts/rate, macro rate лише для повністю визначених сімейств і paired family-cluster bootstrap для B0 проти U5. Ці компоненти перевірено synthetic/no-model тестами; це протокол обробки майбутніх міток, не результат на фактичних відповідях Capri.

## Межі

Власний preflight може пропустити семантичну помилку або розділяти упередження автора з oracle. До завершення двох справді незалежних сліпих reviews активного корпусу його не заморожувати й модельні arms не запускати. Setup adapter тепер перевірений; scorer compatibility має бути перевірений після затвердження oracle semantics.

## Internal action-language preflight: v3 (19.11.2026)

Під час повторного проходу по сімействам M61–M84 знайдено неоднозначність у трьох сімействах: формулювання M61/M62 про «надіслати/нагадати» могло виглядати як прохання запланувати дію, а M83 — як прохання встановити будильник, хоча всі три очікують `NO_TOOL` і перевіряють лише застосування пам'яті. Prompt variants переписано як питання про прийнятний/чинний час, не як доручення виконати дію.

Збережено артефакти окремою версією: `u5-application-v2` і її review pack переведено в `RETIRED` до будь-якого незалежного review; `u5-application-v3` має 24 сімейства / 48 варіантів і лишається `DRAFT`. Створено новий pack `reports/unified/oracle-review-u5-v3/` з manifest SHA-256 та checksums для файлів pack. Це внутрішня авторська перевірка; два незалежні blind reviews ще не отримані, модельного запуску не було.

Validation: v1/v2/v3 manifests проходять структурну/hash-валідацію, старий v2 pack і новий v3 pack проходять `sha256sum -c SHA256SUMS`. Це підтверджує цілісність артефактів, не семантичну коректність оракулів.
