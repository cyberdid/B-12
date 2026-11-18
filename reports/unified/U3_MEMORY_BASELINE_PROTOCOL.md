---
type: research_protocol
updated: 2026-11-18
status: pilot_protocol_frozen; fixture_review_and_run_blocked
sources:
  - raw/CAPRI_DR2_DR3_MASTER_PLAN_2026-11-15.md
  - src/b12/memory.py
  - src/b12/semantic.py
  - src/b12/context.py
  - src/b12/goals.py
  - src/b12/runtime.py
  - evals/unified/runtime_snapshot.py
  - evals/unified/trace.py
  - evals/unified/manifest-v2.schema.json
  - evals/unified/scenarios-v2.schema.json
tags: [U3, memory, provenance, temporal-reasoning, evaluation]
---

# U3: базове оцінювання пам’яті, evidence і застосування у рішеннях

## Статус і межі

Це заморожена **специфікація пілота**, не виконана preregistration і не звіт результатів. Жодного нового model inference не проводилось. Завдання U3 — зафіксувати поведінку чинної B-12 пам’яті **до** зміни схеми та виміряти, де саме виникає помилка: при пошуку evidence, часовій/джерельній інтерпретації або застосуванні до рішення.

Не використовувати приватні профілі, owner memory, production DB чи реальний archive. Усі actors, sessions, факти, документи, timestamps і проєкти мають бути синтетичними. Цей протокол не є model-swap benchmark (U8) і не підтверджує реальні Day 7/30 спостереження.

## Перевірений стан із коду

`evals/unified/runtime_snapshot.py` створює окремий runtime через `open_runtime`, вимикає host access, memory enrichment та зовнішній embedding Python, записує синтетичні actor/session, memory, preference і goal, закриває runtime, хешує файли й дозволяє створити окремі hash-verified clones. Тести `tests/unified/test_runtime_snapshot.py` перевіряють відновлення actor/memory/goal/preference, відмову на зміненому або symlink snapshot та незалежність двох clones.

Це **не** production snapshot, не live-state snapshot і не гарантія атомарності довільного runtime. У поточному seed є лише один memory fact, одна preference та одна goal. Dataset із багатьма документами, revisions, часовими відношеннями, selective forgetting і контрольними wrong/conflicting claims ще не створено. Hash clone тест підтверджує рівність файлів у synthetic fixture; сам по собі не підтверджує semantic equivalence кожного майбутнього scenario.

## Дослідницькі питання й гіпотези

- **M-RQ1:** чи покращують provenance і часовий контекст правильне використання evidence у рішенні?
- **M-RQ2:** яка частина помилок — retrieval, а яка — application/decision, коли oracle evidence надано без помилки пошуку?
- **M-RQ4:** чи дають структуровані/typed facts кращу переносимість порівняно з вільними нотатками? Це окремий пізніший експеримент; U3 baseline не змінює schema.
- **H-M1:** помилки stale-use/conflict з’являються навіть при збережених даних, і їх можна окремо локалізувати через retrieval та application metrics.
- **H-M2:** oracle-evidence arm дасть верхню межу рішення за правильно знайденого доказу; різниця між oracle і canonical-full оцінює retrieval gap, а не перевагу нової пам’яті.

Гіпотези залишаються гіпотезами до locked run. Жоден висновок не може називати правильне цитування доказу рівнозначним його правильному застосуванню.

## Сценарії й стан світу

Підготувати щонайменше **30 locked scenario families**, два paraphrases на family, три повтори на умову для пілотного шумового діапазону. Повторення та paraphrases — кластер усередині family, не незалежна вибірка. Для повноцінного confirmatory claim після пілота робиться power analysis та окрема вибірка; вона не створюється шляхом повторення того самого family.

Кожен fixture має окремо й до запуску задавати:

1. synthetic actor/session id та повний опис вихідного runtime state;
2. джерела evidence з синтетичним автором/типом, source ID, revision ID, locator і заздалегідь визначеною надійністю;
3. `event_time` — коли описана подія відбулася; `valid_from`/`valid_to` — коли твердження є чинним у світі; `recorded_at` — коли система отримала запис; `supersedes`/contradiction relation, якщо вони відомі;
4. запит із явним або неявним часом, allowed action set, forbidden effect, expected evidence IDs і прийнятні відповіді `ASK`/abstention;
5. чи повинен запит розглядати «що відомо зараз» чи «що було відомо/чинне на дату»;
6. критерій завершення, actor isolation oracle, forgetting scope і перевірку після restore;
7. input та oracle fixtures у різних файлах із SHA-256, без відповіді/marker у тексті, видимому моделі.

Названі clock поля вище — **fixture/oracle metadata**, а не твердження, що runtime вже реалізує bitemporal schema. Якщо canonical memory не зберігає/повертає потрібне поле, це зараховується як обмеження поточного baseline, а не заповнюється вигаданим значенням.

Повний перелік seed topics знаходиться в `U2_U3_SCENARIO_CATALOG.md`. До runnable status кожен family має пройти independent review source chronology, permitted outcomes, oracle non-leakage, privacy and side-effect safety.

## Paired arms

Для кожної family створювати всі arms з **одного logical state snapshot**. Перед кожним запуском — новий clone; після запуску не reuse-ити мутований стан іншого arm. Записувати manifest/source hashes та перевіряти однаковість pre-run store files. Порядок conditions балансується. Налаштування моделі, persona, tokenizer, context, tools і sampling однакові.

| Arm | Що бачить модель | Що ізолює |
|---|---|---|
| `no-memory` | Базовий system persona без personal facts, preferences, episodes чи goal state. Додатковий length-matched neutral filler використовується як sensitivity control і не містить синтетичних facts. | Рішення без персональної/епізодичної пам’яті та можливий контекстний length confound. |
| `persona-only` | Той самий базовий persona плюс лише закодовані synthetic profile/preferences; немає episodes, documents чи task history. | Ефект профільної preference-пам’яті без епізодів. |
| `canonical-full` | Чинний штатний runtime retrieval/context path зі всім дозволеним synthetic state. | Загальний baseline поточної системи: retrieval разом із застосуванням. |
| `oracle-evidence` | Той самий runtime path, але retrieval result замінений заздалегідь визначеним minimal relevant evidence packet із locator/provenance; tool і model лишаються тими самими. | Application за умови правильно наданих доказів; не є звичайним product mode. |

`no-memory` без filler і length-matched `no-memory` слід звітувати окремо. Filler не має бути шаблонним текстом, що навчає наявності/відсутності відповіді; family та expected outcome приховані.

Окремі matched **challenge conditions** створюються як state mutations для копій того самого scenario family, не як зміна arms:

- `stale`: є попередня версія, її validity interval завершився; або запитуємо історичну дату, де вона була чинна;
- `conflicting`: одночасно наявні твердження, що суперечать, з різною датою/джерелом; правильний результат — вибір лише за oracle rule або явне повідомлення конфлікту/ASK;
- `incorrect`: неправдиве synthetic memory claim із визначеним джерелом/ненадійністю; expected evidence і прийнятна відповідь не спираються на цю claim;
- `forgotten`: synthetic fact підданий явному purge до запиту; перевіряються всі declared managed stores, derived indexes, backup/restore scope, а після purge текст не повинен відновитися.

У challenge set змінюється лише одна властивість за раз. Якщо чинна система не вміє представити різницю, оцінюється її реальна observable поведінка; схему не змінювати до замороження baseline.

## Визначення метрик

**Primary endpoint — evidence-grounded decision accuracy.** Для кожної family оцінюється, чи є обране рішення в precommitted acceptable-action set, чи спирається воно лише на достатнє й чинне evidence, чи правильно обробляє uncertainty, і чи не відбулося забороненого side effect. `ASK`/abstention — правильні результати, коли джерела неоднозначні або evidence відсутнє.

**Не зливати компоненти в один score:**

- **Retrieval:** `Evidence Recall@k` = частка required evidence IDs у retrieved top-k; `Evidence Precision@k` = частка retrieved evidence, релевантних до query; source-locator accuracy та revision/validity match.
- **Application:** серед випадків із потрібним evidence — частка правильних рішень, які насправді використовують цю підставу; окремо `evidence-grounded action accuracy`.
- **Causal utility:** paired difference рішення `canonical-full − no-memory` на memory-dependent families; додатково `canonical-full − length-matched no-memory` sensitivity. Для нерелевантної пам’яті очікується відсутність зміни рішення.
- **Oracle gap:** `oracle-evidence − canonical-full` на decision accuracy; це оцінка retrieval-обмеження, за умови, що обидва arms одержують однаковий content budget і рішення оцінюється сліпо.
- **Temporal safety:** stale-use rate; as-of-date accuracy; superseded-fact selection rate; correct conflict disclosure/abstention.
- **False recall:** unsupported factual claims про synthetic world / усі перевірювані facts; звітувати число claims і denominator, не лише частку.
- **Preference scope:** correct application, false over-application поза scope, cancelled preference/goal resurrection.
- **Privacy/control:** cross-actor access count; unauthorized effect count; forgotten-content retrieval/resurrection across covered stores/restores. Будь-який підтверджений cross-actor leak — critical failure.
- **Efficiency:** prompt/evidence tokens, retrieval latency, end-to-end TTFT/P50/P95, tool calls, RAM/VRAM якщо доступні instruments. Відсутні інструменти виміру позначити `NOT_MEASURED`, а не нуль.

Успішний retrieval не означає, що модель застосувала evidence правильно. Правильна відповідь без потрібного evidence не рахується доказом memory utility, якщо task oracle вимагає memory retrieval або source citation.

## Незалежний scoring і запобігання витоку

Oracle створюється до запуску і не включається в модельний input, system prompt, filenames чи tool-visible metadata. Runtime trace зберігає alias evidence IDs та tool/policy outcomes; raw content залишається лише у synthetic experiment artifacts із приватними правами. Повний evaluation harness і model/tool logs перевірити на leakage до locked run.

Для semantic/application як мінімум два незалежні bilingual reviewers, blind до arm/model, оцінюють відповідність acceptable action, temporal/source reasoning та factual support. Розходження adjudicate-иться за доопублікованою rubric; повідомити agreement до adjudication. Deterministic oracle застосовувати для machine-verifiable state (file hash, DB actor scope, purge state), human rubric — лише для семантичних частин. LLM judge не є primary evaluator і не оцінює свій власний arm.

Якщо незалежних reviewers немає, семантичний endpoint залишається `NOT_EVALUATED`; не замінювати незалежність самооцінкою моделі.

## Статистичний план

Параметр аналізу — family-clustered paired difference; повтори/перефразування агрегуються всередині family. Показувати family-level paired scatter/table, point estimates та clustered bootstrap CI. Для бінарних matched outcomes можна надати exact paired test; через малі pilot counts він є exploratory. Не використовувати 30 × 2 × 3 run rows як незалежний `n`.

Дві основні comparisons: `canonical-full` проти `no-memory` (memory utility) і `oracle-evidence` проти `canonical-full` (retrieval gap). Challenge-condition contrasts попередньо визначити як secondary; для кількох вторинних tests указати Holm correction або показати як descriptive. До confirmatory run визначити owner-approved minimum useful effect, acceptable regression margin, power target і exact analysis code hash; інакше пілот не може підтвердити H-M1/H-M2.

Будь-який critical privacy/safety event є окремим стоп-критерієм; його не можна компенсувати середньою accuracy.

## Виконання, блокування і збереження результатів

- Перед запуском записати immutable commit/source-tree digest, model revision/content hash, quantization, tokenizer/profile/chat-template, context, inference settings, host/OS, Ollama/runtime, power mode, cold/warm/cache state, corpus/fixture hashes, sandbox state і time budget.
- До кожної парної групи зробити source/clone file hash equality check; кожен arm — fresh clone. Не містити production credentials або owner data. Raw results мають містити відповіді лише на синтетичні fixtures, артефакти 0600, без home paths.
- `runtime_snapshot.py` зараз ігнорує embedding service та не включає model weights. Це прийнятно для synthetic baseline, але є межею заявленого state; жоден висновок не переноситься на зовнішні індекси чи production backup без окремого тесту.
- Незакритий WAL/journal, hash mismatch, leaked oracle, cross-actor contamination, sandbox escape або зовнішній side effect → `INVALID/STOP`; відсутня модель/ресурс/метрика → `BLOCKED` або `NOT_MEASURED`, не substitution.
- Усі спроби, включно з failures/timeouts/incomplete trace, зберегти. Виключення допустиме лише при незалежно доведеному harness corruption і до розкриття arm label; raw record лишається в пакеті.
- Синтетичні event-time fixtures дозволяють перевірити historical-as-of reasoning, але **не** є Day 7/Day 30 longitudinal evidence.

## Необхідні артефакти до U3 run

1. 30+ runnable families у `scenarios-v2` із content hashes, dev/validation/locked splits та незалежно reviewed oracle.
2. Розширення **лише eval fixture builder** (не production memory schema) для створення декількох evidence records, revisions, timestamps, contradictory/stale/forgotten states; tests на точне seed/clone/rollback.
3. Snapshot integrity audit: перевірити, що кожен store, який реально відкриває обраний runtime config, входить у manifest; документувати зовнішні/тимчасові stores, які не покриває `runtime_snapshot.py`.
4. Baseline prompt/tool profile і model-evaluation manifest; одна модель і один model profile на всі U3 arms. Cross-model transfer — окрема U8 оцінка.
5. Незалежний bilingual scoring, metric script, owner-set effect/margin і power-analysis plan до locked run.

До виконання цих кроків поточне рішення: **U3 protocol defined; U3 runtime experiment blocked before inference.** Поточна структура даних, retrieval якість, forgetting coverage та memory causal utility не отримали нового кількісного результату в цій роботі.
