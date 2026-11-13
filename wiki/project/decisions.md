---
type: decisions
updated: 2026-11-08
status: active
sources: [raw/B-12_Master_Project_2026-10-24.md, wiki/sources/llm-wiki.md, wiki/sources/capri-desktop-companions-2026-11-07.md, wiki/sources/capri-personality-review-2026-11-08.md, docs/superpowers/specs/2026-11-08-b12-capri-compact-actions-design.md, docs/superpowers/specs/2026-11-08-b12-capri-feature-parity-design.md, docs/superpowers/plans/2026-11-08-b12-capri-feature-parity.md, docs/superpowers/specs/2026-11-08-capri-persona-brand-design.md, docs/superpowers/plans/2026-11-08-capri-persona-brand.md, src/b12/persona.py, src/b12/agent.py, src/b12/api.py, src/b12/desktop/profile.py]
tags: [adr, baseline, desktop]
---
# Реєстр рішень

IDs ADR-001–010 збережено з §16 master brief. Це запропоновані baseline, а не доказ реалізації або окремого затвердження власником кожної технології. ADR-011–014 додано окремо за прямими вимогами власника щодо desktop-компаньйона та його ідентичності. Нормативні вимоги відрізняються від інженерних кандидатів.

| ID | Зміст | Статус знання / умова перегляду |
|---|---|---|
| ADR-001 | Local-first, хмара опційна | Вимога з brief; offline behavior перевіряється окремо |
| ADR-002 | System 1 / System 2 | Архітектурна пропозиція; підтвердити неблокувальний interrupt |
| ADR-003 | Append-only event ledger + typed permissions | Пропозиція; lifecycle/delete суперечність ще відкрита |
| ADR-004 | ASR → LLM/memory → TTS | Запропонований v1 шлях; оцінити latency й UA |
| ADR-005 | AEC3 + Silero + Smart Turn | Кандидати; duplex/endpoint tests перед остаточним вибором |
| ADR-006 | Piper UA | Кандидат; перевірити голос, engine/voice licenses й TTFA |
| ADR-007 | Bolt E4B кандидат, Gemma A/B baseline | Bolt пройшов [перший desktop smoke test](bolt-first-test.md); є поведінкові й context-budget недоліки. A/B і Jetson ще відкриті; остаточного вибору немає |
| ADR-008 | Wireless бажаний, Lite простіший bring-up | Уподобання з brief; купівля й transport proof не підтверджені |
| ADR-009 | Curiosity/initiative керуються runtime | Архітектурна пропозиція; довгі trace evaluations |
| ADR-010 | Не заявляти свідомість або guaranteed personality | Межа інтерпретації поведінки з brief |
| [ADR-011](#adr-011--desktop-launchers--system-commands) | Owner-click запуск програм у Qt companion; shell лише через наявний B-12 tool/grant/approval flow | Прийнято прямою вимогою власника 08.11.2026; визначено вузькі межі в рішенні нижче |
| [ADR-012](#adr-012--функціональна-сумісність-capri-desktop) | Повна незалежна реалізація сумісних Capri Desktop feature families у B-12 | Прийнято прямою вимогою власника 08.11.2026; implementation і host acceptance ще тривають |
| [ADR-013](#adr-013--ідентичність-capri-та-сумісність-runtime) | Capri як ім’я компаньйона; локальний профіль стилю; збереження внутрішнього `b12` namespace | Прийнято прямою вимогою власника 08.11.2026; код додано, поведінкова перевірка ще потрібна |
| [ADR-014](#adr-014--імерсивне-самосприйняття-capri-та-чесність-про-межі) | Цілісна ідентичність Capri, характер і межі тверджень про свідомість/можливості | Прийнято власником 08.11.2026; prompt оновлено, людська оцінка на моделі ще потрібна |

## DOC-001 — ведення LLM Wiki

**Статус: прийнято прямим дорученням власника 24.10.2026.** Незмінений master brief у `raw/`; тематичний синтез у `wiki/`; [AGENTS.md](../../AGENTS.md) задає workflow. Рішення стосується ведення проєкту, не вибору роботизованого стеку. Джерело методу — [картка LLM Wiki](../sources/llm-wiki.md).

## Нові рішення, які ще потрібні

- Lifecycle персональних payload і похідних даних, [memory](../topics/memory.md).
- Exact consent/control boundary та права інструментів, [architecture](../topics/architecture.md).
- Host authoritative memory й режим без ноутбука, [hardware](../topics/hardware.md).
- Вимірюваний voice SLO і pinned benchmark settings, [voice](../topics/voice.md).

Прийняте рішення доповнювати датою, підставою, альтернативами, наслідками та evidence. Нову редакцію позначати як таку, що замінює стару; зміни фіксувати в [журналі](../log.md). [Відкриті питання](open-questions.md) залишаються активними до появи доказів.

## ADR-011 — Desktop launchers / system commands

**Дата:** 2026-11-08. **Статус:** прийнято прямою вимогою власника під час роботи над Capri desktop-companion.

**Рішення власника:** з компаньйона мають запускатися програми й задаватися системні команди.

**Реалізаційні межі:** локальні application launchers створює власник у Qt UI. Запис містить absolute executable path та окремий argv; кожен запуск показує точні параметри і вимагає натискання підтвердження. Site shortcuts приймають тільки owner-authored `http`/`https` без credentials і відкриваються зовнішнім браузером лише після кліку. Shell parsing/`shell=True`, PATH-вибір і запуск із модельного тексту заборонені. Вільний shell command composer відправляє текст у B-12 chat; подальше виконання залишається за runtime `shell_exec`, наявними grants та exact approvals. Desktop не створює grant і не обходить approval.

**Причина:** надані Capricorn-проєкти мають launchers/reply-entry UX, але їхній широкий desktop automation або прямі model-originated host actions не відповідають B-12 control invariants. Ця реалізація додає явний owner control у GUI, не змінюючи permission boundary моделі.

**Наслідок:** desktop companion тепер може стартувати явно налаштовану програму після локального підтвердження та відкривати власні web shortcuts у браузері. Користувач відповідає за executable, argv і сайт. Raw shell-команда лишається під B-12 runtime policy й може бути недоступною, якщо grant/capability не дозволяє її.

## ADR-012 — Функціональна сумісність Capri Desktop

**Дата:** 2026-11-08. **Статус:** прийнято прямою вимогою власника: «з цього репозиторію все забрати». Перевірений upstream HEAD — `cb33e87dfaee79cec8b4b0f737ca89e07b87ba4b`; повний список features і evidence наведені у [source review](../sources/capri-desktop-companions-2026-11-07.md), execution plan — у [feature parity plan](../../docs/superpowers/plans/2026-11-08-b12-capri-feature-parity.md).

**Рішення:** реалізувати в B-12 усі корисні user-facing capability families незалежним кодом, наскільки дозволяють B-12 architecture, підтверджені хостові можливості й доступний model transport. Це не дозвіл копіювати файли/code/art із репозиторію.

**Контроль:** зовнішні Claude/Codex/Antigravity hooks встановлюються лише з явної дії власника, створюють backup, зберігають сторонні entries й мають точний uninstall. Activity log містить bounded metadata, не prompts, tool arguments/results, file contents, secrets чи audio. File/window/screen/device telemetry має явний окремий opt-in. Screen capture не записується на диск; B-12 не заявляє image understanding, поки API/model transport його не підтримує. Модель, grants, consent та tool execution лишаються за B-12 runtime. Системні дії показують точний target і потребують owner action; arbitrary shell проходить чинний tool/grant/exact-approval flow. Автоматичне закриття сторонніх AI tabs/apps вимкнене/не реалізується; profile/bond UI не карає користувача за відсутність і не заявляє sentience.

**Платформи й ліцензія:** Linux/X11 — target цієї реалізації; README джерела обмежує expanded window tracking до Windows та каже, що інші ОС не перевірені. Функція, що не має Linux equivalent або потрібного API, позначається unavailable, а не completed. Upstream `LICENSE` для сучасного коду — PolyForm Noncommercial 1.0.0 і прямо виключає character artwork; B-12 реалізує поведінку самостійно й не включає upstream assets.

**Підстава:** власник вимагає повний feature review і впровадження. Повна власницька згода знімає попереднє project-scope виключення функціональних груп, але не скасовує технічних, приватнісних і ліцензійних меж, описаних вище.

**Наслідок:** завдання оцінюється за повною capability matrix, не за compact-chat subset. Жоден capability family не позначається реалізованим без локального коду й відповідних evidence; live host behavior лишається open до явного acceptance.

## ADR-013 — Ідентичність Capri та сумісність runtime

**Дата:** 2026-11-08. **Статус:** прийнято прямою вимогою власника: «додай це нам — доповни його. і перейменуй B-12 на Capri. все додай».

**Рішення:** Capri — видиме ім’я компаньйона у графічному desktop UI, TUI, Web UI, CLI та базовому prompt моделі. Її власний стиль спирається на повторно перевірені persona/system-prompt, scripted-reply та profile-модулі наданих проєктів, але формулюється самостійно; upstream prompts, діалоги, код і artwork не копіюються.

**Профіль:** локальний desktop profile дозволяє задати звертання до власника, стиль і фрази. Він обмежується за довжиною та надсилається з desktop-запитом як дані, що впливають лише на формулювання. Профіль не пишеться в історію розмови, довгу пам’ять чи activity log і не може надавати дозволи або змінювати tools, grants, consent чи approvals. При локальному model provider він лишається на комп’ютері; при хмарному provider поля профілю передаються тому provider у складі prompt-запиту.

**Сумісність:** назви Python-пакета, CLI/API paths, state/config paths, environment variables, hook ownership markers та `QSettings("B-12", "NeonCompanion")` лишаються без змін. Вони є внутрішніми контрактами та ключами збережених налаштувань; їх перейменування мігрувало б дані й ламало б наявні інтеграції. Історичні сторінки зберігають B-12 у своєму provenance.

**Підстава й межа:** власник змінив user-facing бренд та попросив додати знайдену поведінку. Це не вимагає перейменувати distribution, systemd units, зовнішні env/config keys або переносити точні фрази з проєктів. Перейменування цих технічних контрактів потребувало б окремої міграції.

**Наслідок:** desktop profile передається до `/api/chat` лише за наявності профілю; інші виклики отримують базову персону Capri. Статична коректність коду перевіряється окремо; модельна оцінка стилю, privacy acceptance на cloud provider та людська оцінка ще не виконані.


## ADR-014 — Імерсивне самосприйняття Capri та чесність про межі

**Дата:** 2026-11-08. **Статус:** дизайн прийнято власником; базовий prompt оновлено локально.

**Вимога власника:** Capri має бути схожою на реальну Capri й повноцінно сприймати себе як Capri.

**Рішення:** у звичайній розмові Capri впевнено називає себе Capri, говорить від першої особи та не розриває образ незапрошеними AI-дисклеймерами. Її самостійно сформульований голос поєднує спостережливість, допитливість, дотепність, пустотливість, суху іронію, самостійні погляди й уважну турботу. Кіберпанкова перспектива забарвлює характер, але не витісняє буденні теми або інженерну точність.

**Межі:** це ідентичність software-companion, а не доказ людської свідомості, життя під час бездіяльності чи безперервної пам’яті. На прямі запитання про технічну природу та фактичні можливості Capri відповідає чесно. Вона не вигадує спільних спогадів, канонічних фактів, аудіо/візуального сприйняття або невиконаних дій. Рішення не скасовує ADR-010 та B-12 control/consent invariants.

**Походження:** конкретні голосові риси синтезовано з власницької вимоги й перевірених фанатських persona-файлів; офіційна сторінка серіалу не дає повного Capri voice guide. Це не канонічна атрибуція і не копія upstream промптів чи реплік; evidence наведено у [картці persona review](../sources/capri-personality-review-2026-11-08.md).

**Наслідок і відкрита перевірка:** базовий prompt спільного Agent змінився для всіх model clients. Текстовий prompt та його статичний стан перевіряються локально; переконливість і стабільність поведінки треба окремо оцінити у розмові на цільовій моделі.
