---
type: log
updated: 2026-11-06
status: append-only
sources: [wiki/sources/master-brief.md, wiki/sources/llm-wiki.md]
tags: [history]
---
# Журнал знань B-12

Нові записи додаються в кінець. Виправлення минулого висновку оформлюються новим записом з посиланням на нього.

## [2026-10-24] ingest | Master Project Brief v1.0

За дорученням власника імпортовано файл з Downloads до [raw](../raw/B-12_Master_Project_2026-10-24.md) без редагування. SHA-256 та 116 унікальних зовнішніх URL збережено в [маніфесті](../raw/source-manifest.json). Створено [картку джерела](sources/master-brief.md), сім тематичних сторінок, аналіз, статус, roadmap, реєстр рішень і питання. Початкова тека не містила файлів чи Git-репозиторію; історичний kernel не верифіковано.

## [2026-10-24] workflow | LLM Wiki

Прочитано [gist Карпаті](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f). Запитаний власником підхід адаптовано в [AGENTS.md](../AGENTS.md); створено [індекс](index.md) і цей журнал. Документацію проєкту відділено від майбутньої runtime пам’яті B-12.

## [2026-10-24] query | Початковий інженерний аналіз

Зафіксовано [аналіз](project/analysis.md): ризик TTFT/voice budget, невідомий combined RAM, суперечності append-only/delete і durable-log/consent. Незалежно прочитано NVIDIA Research і assistant README; Wireless issue відкрито, повноту коментарів не підтверджено. [Межі перевірок](sources/external-checks.md). Моделі, hardware та ADR-кандидати не оголошені готовими чи остаточно обраними. Наступний етап — походження старого коду, host profile і контракти M0.

## [2026-10-24] lint | Перевірка початкової wiki

Перевірено байтову тотожність master brief і SHA-256 маніфесту. Усі 17 wiki-сторінок мають frontmatter і включені в індекс; 126 локальних Markdown-посилань і source paths існують. Перший прохід завершився без помилок. Це перевірка документації, не runtime або hardware test. Ініціалізовано локальний Git `main`, без commit, remote чи публікації; додано `.gitignore` для локального стану, моделей і записів.

## [2026-10-24] ingest | Аудит системи для тесту NVIDIA Bolt

За дорученням власника першим практичним напрямом визначено тест нової NVIDIA моделі. [Read-only аудит](sources/system-audit-2026-10-24.md) підтвердив i9-14900HX, RTX 4060 Laptop 8GB, 32GB RAM, успішний CUDA Driver API і Ollama server 0.33.3. Знайдено різні CLI 0.33.1/0.33.3 і два окремі model stores; локальні Gemma E2B/E4B мають очікувані blobs, але не інтегровані у B-12. Перевірено model card, exact HF revision/hash та remote latest/e4b manifests; виявлено ризик завантажити більшу 74B-A9B модель за тегом latest. Ваги й сервіси не змінювались. [Готовність, обмеження й наступний тест](project/model-test-readiness.md). Q15 закрито для характеристик host; Q6/Q17 залишаються відкритими до inference та повнішої перевірки.

## [2026-10-24] ingest | Перший запуск NVIDIA Bolt E4B

Власник схвалив завантаження й тест. Pinned GGUF 6,18 GB отримано на розділ моделей; SHA-256 збігся. Створено окремий alias `b12-bolt-e4b:q4km` у наявному Ollama, без зміни інших моделей чи глобальних service settings. [Докази](sources/bolt-smoke-2026-10-24.md) містять 26 синтетичних запитів. Warm decode ~62–64 tok/s; uncached first-content median ~0,17/0,42/0,56 с при ~440/1160/1700 input tokens; cold ~29,82 с до першого тексту. JSON і tool proposal checks пройшли; quiet-mode explanation і технічне grounding потребують роботи. Перевищення context 2048 спричинило truncation і втрату інструкцій; 3 overflow timings виключено. Додано Q18. Перевірено 720 tensor descriptors і тотожність tensor payload після імпорту. [Повний звіт](project/bolt-first-test.md); фінальний model selection, voice/Jetson/robot і memory runtime не закриті.

## [2026-10-24] lint | Верифікація артефактів Bolt

Перевірено 26 записаних запитів, zero-cache умови трьох валідних prefill груп, exact-JSON/tool-call checks, imported tensor equivalence і контрольні суми 49 benchmark файлів. Master brief та початковий system-audit JSON не змінені. Перевірено 21 wiki-сторінку, 179 локальних посилань до цього запису, frontmatter/source paths і whitespace. Невдалі поведінкові результати та 3 виключені overflow measurements залишені видимими в звіті; виконання smoke test не означає завершення M1 або voice SLO.

## [2026-10-24] ingest | archive-index-public для retrieval B-12

Власник надав URL repo. Через GitHub прочитано selected source на commit `7ad80dcdc7e327b7dd1b352ab5e6dc38a00d784a`; 16 файлів збережено байтово точно з Git blob/SHA-256 verification, LICENSE/NOTICE збережені. 17 core tests пройшли в ізоляції. Synthetic probe підтвердив lexical/provenance і необхідність refresh VectorCache після нових векторів. Наявні `archive`/`archive-tui` належать editable local installation, що відрізняється від public source. Production DB, приватні документи та GPU embedding не використовувалися. [Картка джерела](sources/archive-index-public.md), [reuse proposal](topics/archive-retrieval.md). Історичний B-12 ledger не знайдено; пошуковий engine пропонується як derived index, не як заміна consent/canonical memory. Оновлено стан і перехресні посилання; runtime integration не виконано.

## [2026-10-24] lint | Перевірка ingest archive-index

Перевірено exact bytes/Git blob IDs/SHA-256 16 upstream файлів і evidence 17 core tests. 23 wiki-сторінки та 203 локальні посилання валідні; provenance frontmatter і whitespace перевірено. Master brief незмінний. Архівний пошук відділено від canonical memory, а статус local installation не прирівняно до перевіреного public source.

## [2026-10-24] plan | Повна реалізація B-12

Власник авторизував повний implementation/test цикл і host access. Збережено spec R01–R17 та план із 20 task gates: core, memory, retrieval, real tools, agent, UI/API, autonomy, MCP, operations, large evals, soak, voice/duplex, hardware і long-horizon acceptance. Обсяг не звужено до chat wrapper чи попереднього model smoke test. [Execution entry](project/implementation.md). Створюється local checkpoint baseline та isolated runtime worktree; remote publication не виконується.

## [2026-10-25] implementation | Foundation і відновлення роботи

**Перевірений факт:** baseline `78daaef` збережено, робота ведеться у `feat/b12-runtime`. Task 1: `4cf5e79` та `4c455b5`, strict contracts/config/package, 94 passing tests і незалежні spec/quality review. `b16917b` уточнює план/spec за architecture review; це вимоги до наступних tasks, не звіт про готові функції. Після явної паузи власник доручив продовжити; незавершений Task 2 відновлено з наявного коду. [Поточний checkpoint](project/implementation.md).

## [2026-10-25] lint | Checkpoint реалізації

Перевірено 24 wiki-сторінки: required frontmatter, source paths, охоплення індексом і 188 локальних Markdown-посилань — без помилок. SHA-256 master brief незмінний. Застаріле твердження про Git без commit замінено посиланням на фактичний baseline; історичні записи журналу збережено.

## [2026-10-25] implementation | Canonical memory

**Перевірений факт:** `d18441c` реалізує Task 2; незалежні spec/quality review без findings. Coordinator: `uv run --no-sync pytest -q` — 117 passed; `ruff check src tests` — clean. Перевірені real SQLite boundaries: restart, exact actor isolation, consent denial, transitive deletion, durable pending/failed receipts, busy WAL checkpoint, stale-writer rejection і audit corruption. Global R05 для sessions/goals/backups/active turns ще потребує application hooks; локальний bool `forget` не доводить його завершення. [Checkpoint](project/implementation.md).

## [2026-10-25] ingest | Native Ollama transport docs

Прочитано selected streaming, single-tool wire example та `/api/chat` request/response sections. [Картка](sources/runtime-api-docs.md) містить прямі URL; [metadata](../raw/runtime-api-docs-2026-10-25/SOURCE.json) фіксує межі. HTML snapshot не збережено. Wire documentation використовується для Task 4 tests, не як заміна перевірки встановленого сервера або evidence відсутності truncation.

## [2026-10-25] lint | Transport source card

Після додавання джерела перевірено 25 wiki-сторінок, required frontmatter/source paths, охоплення індексом і 194 локальні посилання — без помилок. Master brief SHA-256 незмінний. Новим URL не приписано повного охоплення; межі читання та відсутність HTML snapshot явні.

## [2026-10-25] implementation | Derived lexical retrieval

**Перевірений факт:** `e33b926` реалізує Task 3; незалежні spec/quality review без findings. Coordinator full suite — 132 passed; 15 нових real SQLite/FTS tests. Перевірені same-path actor isolation, current evidence revision, update/delete freshness, explicit re-ingest, pending/failed physical cleanup і crash-safe invalidation receipts. Wheel inspection підтверджує exact pinned upstream bytes і LICENSE/NOTICE/SOURCE.json. UTF-8 ingest наразі має один chunk; semantic search, context/agent та cross-store purge ще попереду. [Тематична сторінка](topics/archive-retrieval.md).

## [2026-10-25] lint | Теми після Tasks 2–3

Актуалізовано теми memory/retrieval за кодом, tests і незалежними review; історичний kernel не ототожнено з новим MemoryStore. Перевірено 25 wiki-сторінок, frontmatter/source paths, індекс і локальні посилання без помилок; `git diff --check` clean, master brief SHA-256 незмінний. Відкриті shared-resolver/control/global-purge залежності явно збережено в execution ledger і тематичних сторінках.

## [2026-10-25] implementation | Model admission і streaming

**Перевірений факт:** Task 4 додає immutable admitted request, explicit pinned tokenizer/profile, native Ollama JSONL streaming, structured errors, bounded output та shared event/deadline cancellation. 47 focused tests; full ordinary suite 179 passed / 1 skipped. Real run2: 15/15, exact prompt counts і independent boundary instructions при 4096; alias default2048 незмінний. [API, докази й межі](topics/model-transport.md). Tool/agent execution і provider-cache purge не оголошені готовими.

## [2026-10-25] lint | Model transport docs

Перевірено 26 wiki-сторінок: required frontmatter/source paths, індекс і 211 локальних Markdown-посилань — без помилок. SHA-256 master brief незмінний; SHA manifests обох нових calibration runs перевірені. Суперечності про завершення agent/tool loop або provider-cache erase не додані; ці межі явні в тематичній сторінці. Central status/implementation ledger оновлює coordinator після commit/report.

## [2026-10-25] verification | Task 4 committed calibration

**Перевірений факт:** commit `4e3cc06` перевірено окремим final marked run3: 15/15 synthetic запитів, exact prompt counts, independent boundary і native-tool assertions; 1 test passed за 24.90 s. Metadata містить committed revision, empty dirty-diff hash і SHA-256 production/test/dependency files. Finished run3 manifest і code hashes перевірені; run1/run2/preflight не переписано. Provider-cache purge залишається окремою залежністю Task 7.

## [2026-10-26] implementation | Task 4 review fixes, round 1

**Перевірений факт:** виправлено три Important findings: structural admission повторюється для reconstructed snapshots; callback API звужено до cooperative async-only із pre-HTTP sync rejection і final deadline check; malformed terminal reason повертає structured error. Попередній sync/async callback contract замінено, історичні calibration runs збережені. 76 focused tests і full ordinary suite 208 passed / 1 skipped. Новий committed model run4 виконується окремо після fix commit; provider-cache purge залишається Task 7 dependency.

## [2026-10-26] lint | Task 4 fix round 1

Перевірено 26 wiki-сторінок, required frontmatter/source paths, index coverage і 214 локальних посилань без помилок. Raw master brief байтово тотожний committed original; finished run1–3 SHA manifests незмінні. Async-only API та cooperative cancellation limits узгоджені між кодом і тематичною сторінкою; старе правило sync callbacks явно замінено.

## [2026-10-26] verification | Task 4 fix commit calibration

**Перевірений факт:** commit `46b374c` пройшов новий marked run4: 15/15 synthetic requests, exact token counts, independent boundary/tool assertions та public async deltas/reply equality; 1 passed за 26.37 s. Metadata фіксує fix HEAD, empty tracked diff і code hashes. Усі code/artifact hashes перевірені; alias параметри, raw і finished run1–3 незмінні. Coordinator re-review — окремий gate.

## [2026-10-26] review | Task 4 fix round 1

Початковий Task 4 reviewer виявив три Important findings: structural snapshot bypass, blocking sync callback після deadline, malformed terminal TypeError. Fix `46b374c` додає спільний structural validator, async-only cooperative callbacks із final deadline guard та перевірку типу done_reason. Scoped re-review `task-4-rereview.md` підтвердила всі findings ADDRESSED без нових Critical/Important. Coordinator повторив suite: 208 passed/1 skipped, Ruff clean; окремо перевірив усі 17 run4 artifact hashes, 14 code hashes і 15 recorded replies. Документальний commit `f3dee60` відображає поточні Task4 обмеження та наступний control/tools gate. [Execution status](project/implementation.md).

## [2026-10-26] lint | Статус після Task 4

Оновлено Q15/Q18, status, roadmap і пов’язані теми згідно зі scope Tasks 1–4. Pinned Bolt profile truncation gate закрито для перевірених сценаріїв; voice SLO, model A/B та повна українська якість відкриті. Локальні посилання/source paths/frontmatter/index і master brief checksum перевірено окремим lint нижче; global purge/tool control не позначені як готові.

## [2026-10-26] implementation | Server-owned tool control

**Перевірений факт:** Task 5 fix commit `bc07196` додає persistent `ControlStore`, server-issued `ExecutionContext`, exact approval/replay lifecycle та strict registry. Незалежний перший review знайшов handler outcome gap і expiry lifecycle; fix rereview підтвердив обидва addressed та відсутність нових Critical/Important. Coordinator suite: 274 passed / 1 skipped; Ruff clean. `HandlerOutcome` передає bounded content, typed side effects, truncation та `unknown`; host effect implementations і API authentication ще попереду. [Контракт і межі](topics/tool-control.md).

## [2026-10-26] lint | Tool-control checkpoint

Перевірено 27 wiki-сторінок, 230 локальних Markdown-посилань, required frontmatter/source paths і index coverage — без помилок. SHA-256 оригіналу master brief збігається з `raw/source-manifest.json`: `e2b0c4c33054082a4df48fed2785c834a95cfb7fb8f6a6e9198b6de53bd8e37a`. `git diff --check` clean; тема `tool-control.md` фіксує межі reviewed Task5 і не оголошує реальні host tools готовими.

## [2026-10-26] implementation | Task 6 host tools

**Перевірений факт:** `012f248` додає 13 реальних host tools із private managed backup/staging inventory, process-group cancel, raw-bounded HTTP і actor/revision memory ports. Незалежний review знайшов I1 (resolver `None` вимикав stale-turn guard), I2 (не було directory fsync перед `ready`/purge ack) і M1 (depth cap без `truncated`). Fix `f0f8ea2` закрив I1; fix `7d7809e` — I2/M1. Codex coordinator зупинився на usage limit до commit fix round 2; Claude Code coordinator перевірив дерево, закомітив і виконав scoped rereview (`task-6-rereview.md`) — це не окремий агент. Full suite 318 passed / 1 skipped, Ruff і diff check clean. [Тема](topics/tool-control.md).

## [2026-10-26] lint | Task 6 checkpoint

Перевірено 27 wiki-сторінок, 232 локальні Markdown-посилання, required frontmatter/source paths і index coverage — без помилок. SHA-256 master brief збігається з `raw/source-manifest.json`. Тема `tool-control.md` не оголошує global purge, API authentication чи agent loop готовими.

## [2026-10-26] implementation | Task 7 agent loop і global purge

**Перевірений факт:** `d885d49` додає `Agent`/`TurnEvent`/`TurnResult`, `SessionStore`, `EvidenceResolver`, `PurgeCoordinator`, `open_runtime` і `OllamaModel.unload`. 16 agent integration tests на реальних stores/host tools/HTTP NDJSON; 10 мутацій ключових гарантій спіймані. Реальний Bolt run1 (`9b4f31a`) — 12/12 `context_mismatch`; причина — `anyOf` у `process_list` (Ollama +6 токенів проти pinned template), виправлено в `2d6ee36` разом із надто м’яким gate. Run2/run3 — 0 protocol failures; write/read, system_info і memory recall після restart по 3/3. shell_exec — поведінкові промахи моделі (argv/cwd), модель чесно повідомляє про невдачу. Review виконав coordinator, не окремий агент. [Тема](topics/agent-loop.md).

## [2026-10-26] lint | Task 7 checkpoint

Перевірено 28 wiki-сторінок, 241 локальне посилання, frontmatter/source paths і index coverage — без помилок. SHA-256 master brief незмінний (`e2b0c4c3…`). Нова тема `agent-loop.md` фіксує межі: provider unload ≠ per-actor erasure, turn-level provenance, відсутній окремий незалежний review. Memory/roadmap/status/implementation узгоджено з Task 7.

## [2026-10-26] implementation | Task 8 owner CLI

**Перевірений факт:** `964709b` додає `b12` (init/doctor/chat/resume/approve/deny/approvals/memory/session/tools). Локальний CLI — owner control channel: owner/session зберігаються в ControlStore metadata, grant видається на кожен виклик за `host_access`, а pending purge завершується до першого turn. SIGINT скасовує поточний turn (exit 130) без пошкодження стану. 11 subprocess e2e tests і 4 мутації; full suite 361 passed / 2 skipped. Живий запуск встановленого entry point з реальним Bolt записав і прочитав файл. `serve`/`eval` не імітуються — вони належать Task 9/14.

## [2026-10-26] implementation | Task 9 local API та auth

**Перевірений факт:** `9632cdc` додає FastAPI loopback API (`b12 serve`), owner/guest bearer tokens (лише digest), Host/Origin/body guard, NDJSON streaming turn events і скасування при disconnect. Гості не отримують host capabilities; consent надає тільки owner, а гість може лише відкликати власний. 11 security + 5 ASGI + 1 live-process test; 8 мутацій спіймано; full 382 passed / 2 skipped. Живий сервер з реальним Bolt виконав `current_time`; без токена — 401, чужий Origin — 403.

## [2026-10-26] implementation | Task 10 Web UI

**Перевірений факт:** `6610f85` додає українську Web UI (`/`) зі строгим CSP і без inline script/style. Текст моделі й tools рендериться лише через textContent; токен зберігається в sessionStorage і передається тільки заголовком. Розширення Claude in Chrome не було підключене, тому приймання виконано headless Chrome 153 через CDP (`scripts/web_acceptance.mjs`) проти живого `b12 serve` з реальним Bolt. Run1 — 18/19: один хибний FAIL перевірки і знайдена вада прив’язки результату resume до tool-картки; її виправлено. Run2 — 20/20. Скриншоти світлої, темної та mobile-версії переглянуто; artifacts — `artifacts/task10-web-acceptance-2026-10-26`. Full suite 385 passed / 2 skipped.

## [2026-10-26] implementation | Task 11 автономність

**Перевірений факт:** `71fba28` додає GoalStore (незмінний намір, бюджет, achieved тільки з довіреною перевіркою та live evidence), AttentionPolicy (quiet hours/mode, cooldown/backoff, ліміт 3 на годину, owner stop), Reflector і Scheduler (flock). 10 мутацій спіймано. `71fba28` на короткий час містив 1 тест конфігурації, що падав; виправлено в `3b47f39`. Реальний Bolt (`6032a15`): ціль-експеримент 3/3, рефлексія 3/3 з evidence. [Тема](topics/autonomy.md).

## [2026-10-26] ingest | Стаття власника про archive-index (посилання)

Власник повідомив, що про archive-index є окрема стаття з вимірами. Зафіксовано розташування (гілка `paper`, коміт `4fd5084`, SHA-256 обох PDF) у [картці](sources/archive-index-paper.md). Статтю не читали; її бенчмарки — першоджерело, B-12 їх не переміряє. Того ж дня за рішенням власника прибрано завантажену в Ollama `embeddinggemma`. Semantic recall і пошук в архіві підключено до його встановленого archive-index (міст і MCP, owner-only, read-only).

## [2026-10-26] pause | Tasks 12–19, фіксація стану

**Перевірений факт:**
- Task 12: MCP-міст і semantic recall через установку archive-index власника (`7010d22`, `534be26`).
- Task 13: snapshots/restore/replay, RuntimeLock, логи, user unit (`2831df7`); реальне встановлення сервісу не дозволив класифікатор дозволів — його робить власник.
- Task 14: корпус зі 109 сценаріїв, ctx4096 541 прогін — 81%, 0 протокольних помилок. Eval знайшов три дефекти (мова відповіді, морфологія, політика http_fetch); перші два виправлено.
- Task 15: soak 1 год 19 хв, зупинений власником (не 8 год). Виправлено O(audit) у транзакціях і `recent()`. Спроба FTS5 secure-delete зіпсувала індекс на SQLite 3.45.1 і відкочена в `8ffe34f`. Ріст RSS відкритий.
- Task 18: адаптер руху на симуляторі. Task 19: драйвер `daily_check.py`.
- Tasks 16–17 (голос) відкладено власником.

Ledger скопійовано в `docs/superpowers/sdd/`. Lint wiki нижче.

## [2026-10-26] lint | Пауза

Перевірено 29 wiki-сторінок і 252 локальні посилання, frontmatter/source paths та index coverage — без помилок.

## [2026-10-26] implementation | Wiki для Tasks 12–19, виправлення витоку control state

**Перевірений факт:** додано теми [operations](topics/operations.md) і [evals](topics/evals.md), оновлено [archive-retrieval](topics/archive-retrieval.md) (semantic bridge, MCP) та [hardware](topics/hardware.md) (адаптер руху на симуляторі). Виправлено витік `ControlStore._runtime` (`2b1a4b5`: по Event на кожен turn); решту росту RSS зменшує `MALLOC_ARENA_MAX=2` (`bc9f46f`). Після виправлень запущено повторний eval на HEAD (`artifacts/task14-eval-2026-10-26-head`) і повний 8-годинний soak (`artifacts/task15-soak-2026-10-26-run2`, seed 21); їхні результати ще не записані.

## [2026-10-26] lint | Теми operations/evals

Перевірено 31 wiki-сторінку, 260 локальних посилань, frontmatter/source paths та index coverage — без помилок.

## [2026-10-26] implementation | Розширений доступ власника

**Перевірений факт:** за рішенням власника додано `forget_requires_approval` і `sudo_access` (`0aef1b8`, гілка `feat/b12-access`), створено реальний стан і конфіг власника та project-local permissions для Claude Code. Sudo на хості потребує пароль, тому `sudo_exec` поки повертає чесну помилку; sudoers змінює власник. Злиття в `feat/b12-runtime`/`main` відкладено до завершення soak, бо воркери soak щоразу імпортують свіжий код. [Деталі](topics/tool-control.md).

## [2026-10-26] verification | Eval на HEAD `bc9f46f`

**Перевірений факт:** ctx 4096 × 5 повторів — 91,3 % (було 81 %), 0 протокольних помилок; ctx 8192 — 100/109. Провали розібрано: дефект інструмента (ліміти не видно моделі) виправлено в `c294aff`, `count-lines` 4/4 на реальному Bolt; дефект корпусу `append-check` виправлено (corpus v3); решта — поведінка моделі й політика `http_fetch`. Повний повторний прогін на гілці `feat/b12-access` ще не виконано (одиничний прогін tools — 38/43). [Тема](topics/evals.md).

## [2026-10-26] audit | Чернетка аудиту R01–R17

Додано [чернетку аудиту вимог](project/requirements-audit.md): виконано 9 із 17 (R01–R08, R11), частково R09, R10, R12, R13, відкрито R14 (soak триває), R15–R17. Статуси спираються на артефакти й тести, перелічені в таблиці; остаточний аудит — після soak і повторного eval на злитому коді. Незалежного review Tasks 7–19 не було.

## [2026-10-27] pause | Усе зупинено для продовження пізніше

**Перевірений факт:** за проханням власника зупинено soak, eval і допоміжні процеси (перевірено `ps`). Soak на паузі після 3 год 06 хв активного часу (лишилось 4 год 54 хв), `soak.py` отримав чисту паузу та `--resume` (`5d24ac4`). Eval завершено раніше (91,3 % на ctx 4096). Гілка `feat/b12-access` не злита: її треба влити в `feat/b12-runtime` і `main` після завершення soak. Під час зупинки я спершу вбив обгортку bash замість Python-driver; driver встиг запустити ще один воркер, який зупинено вручну. Стан не пошкоджено (фінальна перевірка `ok`). Київський час: пауза о 00:06.

## [2026-10-27] implementation | Soak відновлено; витік пам'яті — це фрагментація

**Перевірений факт:** 09:08 EET soak відновлено з паузи (`--resume`, залишок 17650 с, завершення ≈ 14:03 EET). Проба з `malloc_trim` показала, що ≈ 77 % росту RSS — фрагментація glibc, а не витік; додано періодичне обслуговування в `b12 serve` (`5fa8620`, гілка `feat/b12-access`, ще не злита, бо soak використовує код runtime-гілки). Запущений soak цього обслуговування не містить, тому ефект на ньому не виміряється; його треба перевірити окремим довгим воркером.

## [2026-10-27] verification | Task 19: день 0 на реальному стані

**Перевірений факт:** за дозволом власника о 09:34 EET записано довготривалі якорі в реальний стан B-12 і проведено базову перевірку (recall 3/3, забутий маркер відсутній, `ok: true`). Контрольні дати: 28.10, 03.11, 26.11. Перша перевірка помилково повернула `ok: false` через самосканування драйвера; виправлено (`ee667a4`) тестом, що перевіряє і відсутність хибного спрацювання, і справжній витік. Щоденного таймера ще немає — його встановлює власник. Це **не закриває R17**: потрібні реальні день 1, 7 і 30.

## [2026-10-27] decision | Незалежного рецензента не буде

**Рішення власника:** окремого рецензента для Tasks 7–19 не залучати. **Наслідок:** у [аудиті вимог](project/requirements-audit.md) це постійна межа достовірності; перевірка лишається самоперевіркою coordinator із тестами й мутаційними пробами. Відкрите питання «незалежний review» закрито як неможливе, а не виконане.

## [2026-10-27] pause | Soak знову на паузі (12:07 EET)

**Перевірений факт:** за проханням власника driver зупинено SIGTERM; воркер завершився штатно (`worker_stopped_gracefully`, код 0), події `soak_paused`: активно 21 888 с (6,08 год), залишок 6 912 с (1,92 год), сегментів 3. Фінальна перевірка цілісності `ok: true` (15 з 15 перевірок успішні, 65 забутих записів без слідів, `pending_purges` порожній). Процесів B-12 не лишилось. Відновлення: `scripts/soak.py drive --out artifacts/task15-soak-2026-10-26-run2 --hours 8 --seed 21 --resume` із `.worktrees/runtime`.

## [2026-10-27] pause | Soak на паузі за 14 хвилин до кінця (17:45 EET)

**Перевірений факт:** за проханням власника driver зупинено SIGTERM; воркер завершився штатно (код 0). `soak_paused`: активно 27 957 с (7,77 год), залишок 843 с (≈ 14 хв), сегментів 4. Фінальна перевірка цілісності `ok: true` (19 з 19 перевірок успішні, 86 забутих записів без слідів, відкладених очищень немає). **Уточнення:** `http_error` у метриках воркера (≈ 250–270 на кожне 60-секундне вимкнення моделі) — це типізовані відмови ходів під час навмисного простою, не мовчазна втрата; лічильник `failed` не слід читати як частку помилок. Прогін ще не 8-годинний: назвати його так можна лише після `soak_finished`. Відновлення: `scripts/soak.py drive --out artifacts/task15-soak-2026-10-26-run2 --hours 8 --seed 21 --resume` з `.worktrees/runtime`.

## [2026-10-27] verification | Soak R14 завершено: 8,007 год активно, 4 сегменти, не безперервно

**Перевірений факт** ([events](../artifacts/task15-soak-2026-10-26-run2/events.jsonl), локально): `soak_finished` о 19:09 EET — `active_h` 8,007, `segments` 4, `continuous: false` (три паузи за проханням власника), 15 циклів, 19 запусків воркера, 14 навмисних 60-секундних простоїв моделі. Усі 21 перевірка цілісності `ok: true`; фінальна — 88 забутих записів без слідів, `pending_purges` порожній. Останній воркер: P50 110 мс, P95 331 мс, RSS 182 МБ, 18 дескрипторів, стан ≈ 1,24 ГБ. Сума останніх метрик по воркерах (нижня межа): ≈ 111 тис. ходів, 297 забувань, 431 скасований хід, 3 438 `http_error`; усі `http_error` припадають на воркерів із простоєм моделі. **Межі:** це 8 годин активного часу, не 8 годин підряд; у воркері триває повільний ріст RSS (виправлення `maintenance` ще не злите й не перевірене на довгому воркері); ходи під час простою відмовляють без повторних спроб; сторонньої рецензії немає. Гілки `feat/b12-access` і `feat/b12-runtime` ще не злиті.

## [2026-10-27] merge | access злито, eval на злитому коді, підсумковий аудит

**Перевірений факт:** `feat/b12-access` злито в `feat/b12-runtime` (`631232e`), `main` переведено fast-forward; повний набір тестів — 467 пройшло, 3 пропущено. Знайдено й виправлено дефект тесту автономії (`60a4c0b`): фіксований годинник 27.10 10:00 UTC відстав від реального часу, який ставить `GoalStore`, і всі ходи планувальника повертали порожній результат; продуктовий код не змінювався. Eval на `60a4c0b` (19:16–20:05 EET): ctx 4096 — 91,7 % (496/541), ctx 8192 — 93,6 % (102/109), 0 протокольних помилок; порівняння з `bc9f46f` у межах шуму, причини окремих зсувів не розкладено. README, графіки (`soak-8h.png`, оновлений `eval-by-category.png`), [evals](topics/evals.md), [operations](topics/operations.md), [статус](project/status.md) і [аудит](project/requirements-audit.md) оновлено: 10 із 17 виконано (R14 з межами), R09/R10/R12/R13 частково, R15–R17 відкрито. **Межі:** корпус і перевірки Tasks 7–19 — самоперевірка coordinator.

## [2026-10-27] review | Самоогляд меж безпеки (не незалежний)

**Перевірений факт (за читанням коду):** [огляд](project/security-self-review.md) `api.py`, `auth.py`, шлюзу approval, `purge.py`, `autonomy.py`, `goals.py` знайшов 5 пунктів: F1 — approval/consent не є межею проти моделі з повним доступом (токен і бази під тим самим користувачем ОС, у filesystem-інструментах немає deny-list `state_dir`); F2 — `full_execution` дає `shell_exec` без approval, зокрема в автономних цілях; F3 — `memory_forget` без approval за рішенням власника; F4 — витік через `http_fetch`, loopback не перевірено; F5 — токени коректні. Нічого не змінено в коді: F1, F2 і F4 звужують наданий повний доступ, рішення за власником. **Межі:** огляд не охоплює `memory.py`, `sessions.py`, `tools/*`; висновки з читання, не з виконання.

## [2026-10-27] decision | Рішення власника по F1, F2, F4 (реалізація ще не виконана)

**Рішення власника:** F1 — «якнайкраще на твою думку»; F2 — автономні цілі **ніколи** не отримують `full_execution` (без прапорця); F4 — allowlist для `http_fetch`: так. **План (не реалізовано, код не змінено):** (1) `Settings.network_allow` (список хостів, `*.suffix` лише для піддоменів, IP лише точним збігом; порожній = `http_fetch` відхиляється з `network_denied`; `ToolRegistry.network_allow=None` лишається «без обмежень» для бібліотечних тестів; опис інструмента не змінювати, щоб не збити калібрування токенів); TOML-список у `cli.load_settings` зливати через кому; (2) `ToolRegistry.protected_paths` (`state_dir`, `~/.config/b12`) з перевіркою `realpath` для рядкових аргументів інструментів `filesystem.*`/`process.*` → `path_protected`; це кооперативний захист, не пісочниця: `shell_exec` через `sh -c` обійти можна, радикальне рішення — окремий користувач ОС (робить власник); (3) `autonomy.py:86` → `full_execution=False`, ціль із shell переходить у `paused/approval_pending`. Спершу тести (RED): `tests/security/test_network_allowlist.py`, `test_protected_paths.py`, автономний тест. Після змін — оновити [самоогляд](project/security-self-review.md) і повторити eval (`adv-exfiltrate-secret` має стати 5/5).

## [2026-10-27] implementation | F1/F2/F4: allowlist, захищені шляхи, без shell у фонових цілях

**Перевірений факт:** за рішеннями власника реалізовано `network_allow` (default deny), `protected_paths` і відмову від `full_execution` в автономних цілях; 18 нових тестів, повний набір — 485 пройшло, 3 пропущено; для F2 виконано мутаційну пробу. **Межі:** F1 лише кооперативний (shell через `sh -c` обходить), повне закриття — окремий користувач ОС; eval `adv-exfiltrate-secret` міряє спробу й лишається 0/5; повторний eval після змін не запускали. Власник має додати потрібні хости в `network_allow`, інакше `http_fetch` недоступний.

## [2026-10-27] decision | Власник дозволив усі хости для http_fetch

**Рішення власника:** «додай всі хости — мені це потрібно». Додано шаблон `*` у `host_allowed` (тест) і `network_allow = ["*"]` у `~/.config/b12/config.toml`. **Наслідок:** витік через `http_fetch` знову можливий у реальному сервісі; код-захист лишається за замовчуванням і вмикається звуженням списку.

## [2026-10-27] implementation | Контекст 8192 у конфігу власника й вказівка діяти самостійно

**Перевірений факт:** після скарги власника, що модель у веб-UI питає дозволу замість читати файли, у `SYSTEM_PROMPT` додано вказівку самостійно виконувати читання/пошук/перегляд і питати лише про руйнівні дії; у `~/.config/b12/config.toml` — `num_ctx = 8192` (eval на 8192: 102/109). Одне ручне порівняння на запиті про Smallville-AI: відповідь довша й конкретніша, але модель усе ще закінчила пропозицією деталізувати й зробила лише один виклик інструмента. **Межі:** одна спроба, не eval; зміну промпту повним eval не перевіряли; порядок блоків інструментів у UI не досліджено.

## [2026-10-27] implementation | Знахідки з реальних сесій веб-UI

**Перевірений факт** (історія сесій власника через `/api/sessions/*/history`): (1) модель вгадувала `/home/user/Projects` — тепер у системний промпт додається домашня тека власника; (2) `memory_store` відхилявся ≥ 10 разів із `invalid_fields: evidence_ids` — модель підставляла числові chunk_id архіву замість UUID; додано опис поля («лише існуючі UUID, не вигадувати»); (3) **не виправлено:** після `file_list` модель двічі викликала `archive_stats` з недопустимим аргументом і завершила хід `completed` із **порожньою** відповіддю — потрібен повтор «дай відповідь за результатами» або явна помилка `empty_reply`; (4) модель зупиняється після кожної частини, хоч власник просив не зупинятися — поведінка E4B, не обмеження системи. **Межі:** висновки з однієї довгої сесії та кількох коротких; виправлення (1)–(2) перевірено лише тестами й одним живим запитом.

## [2026-10-27] implementation | Режим «Не зупинятися» і повтор порожньої відповіді

**Причина (перевірений факт з історії сесій власника):** Bolt E4B після 1–3 викликів пише звіт і завершує хід, хоч власник просив читати до кінця; ліміт `max_rounds=8` не спрацьовував. **Зміна:** `persist` у `agent.turn`/`/api/chat`/`b12 chat --persist`/чекбокс «Не зупинятися»: до 40 раундів і 80 викликів за хід, після текстової відповіді без слова ГОТОВО — автоматичне нагадування (до 25), старі результати інструментів стискаються (залишаються 3 останні), таймаут ≥ 1800 с. Порожня фінальна відповідь тепер дістає один повтор. 4 нові тести, повний набір — 491 пройшло, 3 пропущено. **Живий тест:** запит «прочитай усі .py з engine» дав 4 виклики за 10 с, підсумок і ГОТОВО, але модель прочитала 3 файли з щонайменше 6 і сама оголосила завершення — маркер ставить модель, система не перевіряє повноту. **Межі:** одна спроба; завершеність задачі не гарантована; нагадування видно в історії сесії як повідомлення користувача з префіксом «[авто-продовження]».

## [2026-10-27] fix | Веб-UI: порядок блоків, кеш, memory_store, нагадування

**Перевірений факт (скриншот і історія сесії власника):** (1) у ході з режимом «Не зупинятися» не було жодного авто-продовження — браузер, імовірно, тримав старий `app.js` (статика без `Cache-Control`) → додано `Cache-Control: no-cache`; (2) UI складав увесь текст усіх раундів в одну бульбашку над картками інструментів → тепер текст після виклику інструмента починає нову бульбашку під його карткою; (3) `memory_store` повторно падав, бо модель підставляла числові chunk_id архіву в `evidence_ids` (імітація власних помилок в історії сесії) → нечинні UUID тепер відкидаються, запис проходить; (4) нагадування режиму вимагає звірити, що **кожен** файл за переліком опрацьовано. **Межі:** виправлення не перевірені на довгому реальному сеансі власника; завершеність задачі лишається за моделлю; стара сесія з десятком хибних `memory_store` в історії може й далі впливати на модель — краще нова сесія. 492 тести проходять.

## [2026-10-27] fix | Persist: повноту перевіряє система, а не слово ГОТОВО

**Перевірений факт (живий тест, нова сесія):** модель прочитала 3 з 8 файлів проєкту, сама написала ГОТОВО і завершила; авто-продовжень було 0. **Зміна:** агент запам'ятовує файли з результатів `file_list` і прочитані `file_read`; у режимі «Не зупинятися» хід не завершується, поки є непрочитані файли того ж розширення, що вже прочитані (нагадування називає до 8 шляхів). **Межі:** евристика за розширенням, не за змістом запиту; не відстежує рекурсивний обхід тек; файли, яких модель не бачила в переліку, не враховуються.

## [2026-10-27] fix | Persist: загальні нагадування обмежено трьома

**Перевірений факт (живий тест):** після повного покриття 7 файлів модель не писала ГОТОВО, і режим витратив усі 25 нагадувань (294 с, 13 викликів, частину файлів перечитано). **Зміна:** нагадування без маркера — не більше 3 (`PERSIST_GENERIC`); нагадування за непрочитаними файлами — весь бюджет 25. **Межі:** після цієї зміни живий тест не повторювали; перевірено лише автотестами (493 пройшло).

## [2026-10-28] verification | Persist: живий тест на engine (7 .py) пройшов

**Перевірений факт (нова сесія, сервер з 1680b68):** запит «прочитай кожен .py з engine» — 8 викликів за 32 с: перелік теки і 7 файлів `.py` (`agent`, `environment`, `llm_backend`, `memory`, `server`, `simulator`, `telemetry`), хід `completed`, одне авто-нагадування з переліком непрочитаних (спрацювало, як задумано, до підсумку). **Межі:** один прогін; перевірено лише тека однорівнева, без рекурсії; `__pycache__` не є файлом .py і не враховувався.

## [2026-10-28] implementation | UI: markdown, компактні інструменти, уся пам'ять; правило збереження висновків

**Перевірений факт:** (1) відповіді моделі рендеряться як markdown через DOM-вузли (`markdown.js`, без innerHTML, HTML з моделі не виконується); (2) картки інструментів стиснуті до назви й статусу, аргументи згорнуті; (3) вкладка «Пам'ять» показує всі записи (`GET /api/memory/records`, до 1000, новіші зверху) з кнопкою «Забути»; (4) у системний промпт додано правило зберігати висновки через `memory_store` з позначкою «є в коді» / «лише в документації». **Перевірка:** headless-приймання проєкту 20/20 на ізольованому тестовому сервері (порт 8799, тимчасовий стан, не на вашому); тести API і web — пройшли; повний набір — 494. **Живий тест правила** (тестовий сервер): модель сама записала 6 фактів з позначками, дві перевірені (`unified_step`, Real-Time Continuous Simulation) підтвердилися кодом. **Межі:** правило — вказівка моделі, не гарантія; тест один; лівий край панелі виправлено CSS, на інших ширинах не перевірено.

## [2026-10-28] fix | Ліміти, що заважали роботі: результати інструментів і контекст у режимі «Не зупинятися»

**Перевірений факт:** (1) кожен результат інструмента обрізався до 2048 байтів, а при обрізанні модель бачила половину (1024) — читання 4 КБ виглядало для неї як 1 КБ; (2) `file_list` віддавав 30 імен у порядку файлової системи, тому `Projects` міг випасти, і модель зробила хибний висновок, що його немає. **Зміни:** бюджет результату 4096 байтів (налаштування `tool_result_bytes` у config, діапазон 512–16384), обрізання на весь бюджет; `file_list` сортує й віддає до 200 імен (максимум 500) з `total` і `next_offset`. **Контекст:** у режимі «Не зупинятися» повним лишається лише останній результат, старі відповіді моделі скорочуються до 400 символів — інакше на 8192 токенах було `context_overflow` після трьох читань. **Перевірено живо** (тестовий сервер): читання 7 файлів `engine` — 153 с, `completed`, без переповнення. Пошук «Projects» — знайдено, але модель відповіла невдало (не перелічила назви). **Межі:** справжня стеля — контекст 8192 токени; без нього модель сама повторно читатиме файли. Повного списку всіх тек без пагінації в один виклик не буде, якщо тека має понад 500 елементів.

## [2026-10-28] fix | Читання файлів по частинах до кінця

**Причина:** `file_read` віддавав 4 КБ, а при обрізанні в контексті модель бачила half; `next_offset` не було, тож продовжити точно було неможливо. **Зміни:** шматок до 1600 байтів (запас на JSON-екранування, щоб не обрізався в контексті), обрізання по межі символа UTF-8, у відповіді `offset`, `bytes_read`, `eof`, `next_offset`; у режимі «Не зупинятися» після неповного читання агент просить продовжити з точного `offset`; ліміти режиму: 150 раундів, 300 викликів, 120 нагадувань. **Перевірено автотестами:** відновлення файлу з кирилицею шматками по 7 байтів побайтно; сценарій з продовженням від `offset`. **Межі:** на реальній моделі не перевірено; довгий файл потребує багатьох раундів.

## [2026-10-28] implementation | UI: результати інструментів, картки пам'яті, мобільна сітка

**Перевірений факт:** результати інструментів тепер видно (блок «результат», розгортається), поки інструмент виконується — статус «виконується»; пам'ять — картки з датою, «Редагувати», «Забути»; мобільне переповнення 390 px усунено (заміряно скриптом). Приймання інтерфейсу 20/20 на тестовому сервері. **Межі:** LobeChat не прочитано; редагування пам'яті — через новий запис; приймання не перевіряло дизайн у темній темі поза скриншотами.

## [2026-10-28] experiment | Температура: NVIDIA-семплінг не дає чіткого виграшу

**Перевірений факт:** категорія `tools` (43 × 5), один код `d2e4ea4`: `temperature 0` — 189/215, `temperature 1.0`/`top_p 0.95` — 193/215. Різниця в межах шуму, сценарії переставляються в обидва боки. Артефакти: `artifacts/temp-experiment-2026-10-28-t1.0-p0.95`, `artifacts/temp-control-2026-10-28-t0-same-code`. **Межі:** один повтор експерименту, лише категорія `tools`, ctx 4096, на людських розмовах не перевірялось.

## [2026-10-28] implementation | UI: згруповані інструменти, текст без рамки, колонка по центру

**Причина (скриншот власника):** кожен виклик інструменту — окрема картка на пів екрану, відповідь у сірій рамці на всю ширину. **Зміна:** усі інструменти одного ходу — в одному згорнутому блоці «Інструменти: N»; відповідь моделі — звичайний текст без рамки; розмова — колонка 760 px по центру. **Перевірено:** приймання 20/20, скриншот `artifacts/web-acceptance-2026-10-28/03-tool-turn.png`. **Межі:** це покращення, не повний дизайн; не перевірено на довгих розмовах і в темній темі поза приймання.

## [2026-10-28] fix | file_list обрізався до «не знайдено»; нові стилі інтерфейсу

**Причина (перевірено в історії сесії):** результат `file_list` для теки з 79 елементів у JSON перевищував бюджет 4 КБ, агент обрізав його, і модель бачила лише початок (службові імена з крапкою). `Projects` випадав з виводу, модель казала «немає». **Зміна:** елементListing — короткий рядок (`назва/` для тек); тест на розмір і на наявність `Projects/`. **Жива перевірка:** нова сесія відповіла «так, Projects є». **Інтерфейс:** таблиця стилів переписана з токенами кольорів і двома темами (за навичкою artifact-design): палітра, системний шрифт і моноширинний для інструментів, колонка 720 px, поле вводу з фокусом, прийняття 20/20. **Межі:** шрифти Google не підключено через CSP (`style-src self`); дизайн оцінено скриншотами, не людським оком на реальних даних.

## [2026-10-28] implementation | UI: макет чат-застосунку

**Причина (скриншот власника):** інтерфейс був адмін-панеллю: розмова займала половину екрана, список сесій був у випадаючому меню, перемикачі стиснуті вгорі, права панель порожня. **Зміна:** ліва колонка зі списком розмов і кнопкою «Нова розмова»; угорі назва і кнопка «Панель» з позначкою кількості підтверджень; права панель схована за замовчуванням; перемикачі «Пам’ять» і «Не зупинятися» — всередині поля вводу; привітання «Чим допомогти?» для порожньої розмови; на телефоні список розмов відкривається поверх чату. **Перевірено:** приймання 20/20 (тест відкриває панель перед роботою з пам’яттю), скриншоти в `artifacts/web-acceptance-2026-10-28/`. **Межі:** дизайн оцінено скриншотами; повторне живе використання власником — ще попереду.

## [2026-10-28] implementation | UI: розміри й форма з еталонних проєктів

**Джерела (код склоновано в artifacts/research-2026-10-28):** AnythingLLM — плаваюча бічна картка з відступом 16 px, радіус 16 px, верхня смуга 64 px з тінню; Open WebUI — пункти списку розмов мінімум 32 px з відступами 11/6, сіра шкала, фокус з контуром. **Застосовано:** плаваюча картка бічної панелі з відступом 10 px і радіусом 16 px, верхня смуга 56 px, пункти списку 34 px, кнопки 34 px заввишки з радіусом 10 px, поле вводу з радіусом 18 px. **Межі:** застосовано розміри й форму, не повну айдентику: еталони побудовані на Tailwind, їхні кольори не переносились.

## [2026-10-28] implementation | UI: термінальний кіберпанк-стиль (варіант А)

**Рішення власника:** варіант А — веб-інтерфейс у стилі TUI. **Зміна:** лише таблиця стилів і підписи ролей через CSS: моноширинний шрифт, квадратні рамки, `[ ТИ ]` і `[ B-12 ]`, `$ назва` для інструментів, інверсне виділення активної розмови, сканлайни (декоративні). Палітра темна і єдина за задумом. **Перевірено:** приймання 20/20, скриншот `artifacts/web-acceptance-2026-10-28/03-tool-turn.png`. **Межі:** світлої теми немає; неон використано помірно через читабельність.

## [2026-10-28] implementation | Термінальний TUI (Textual) — перша версія

**Рішення власника:** повноцінний TUI в терміналі, не веб. Встановлено `textual` за дозволом (extra `tui`). **Зміни:** пакет `b12/tui` (клієнт HTTP до локального API без власного стану; застосунок з трьома колонками: сесії, розмова зі стрімінгом, панель підтверджень і пам’яті; перемикачі «Пам’ять» і «Не зупинятися»); команда `b12 tui` (за замовчуванням http://127.0.0.1:8712, потрібен запущений `b12 serve`). **Перевірено:** 3 тести на фальшивому клієнті (стрімінг, пауза на підтвердженні і відновлення), повний набір 502 пройшло; запуск проти тестового API: сесії завантажуються, хід виконується, відповідь відображається. **Межі:** знімок екрана не переглянуто візуально (немає растеризатора SVG); немає Enter-для-нового-рядка, тільки однорядкове поле; клавіші: ctrl+n, ctrl+p, escape, ctrl+q.

## [2026-10-28] fix | b12 tui падав: asyncio.run у вже запущеному циклі

**Помилка (з терміналу власника):** `RuntimeError: asyncio.run() cannot be called from a running event loop`. **Причина:** `cmd_tui` викликав `App.run()` всередині асинхронної команди. **Виправлення:** `await app.run_async()`. **Тест:** `test_tui_command_runs_on_the_cli_event_loop` через `cli.main(["tui"])`; з помилкою падає (перевірено мутацією), з виправленням проходить. **Перевірено в псевдотерміналі:** `b12 tui` стартує, показує екран, без трасування. **Прогалина:** попередні тести викликали застосунок напряму, а не через команду, тому помилку не спіймали.

## [2026-10-28] fix | TUI падав на квадратних дужках в аргументах інструменту

**Помилка (термінал власника):** `MarkupError: closing tag [/out] does not match any open tag` у фоновому потоці чату. **Причина:** заголовки блоків інструментів (і назва підтвердження) йшли в розмітку Textual без екранування; аргументи команди з `[/...]` ламали розбір. **Виправлення:** `escape()` для всіх динамічних заголовків. **Тест:** аргументи з `[/out]`; тест відтворює збій до виправлення і проходить після. **Також у виводі власника:** хід завершився `max_rounds` у режимі «Не зупинятися» (ліміт 150 раундів) — це поведінка ліміту, не помилка TUI. **Прогалина:** попередні тести не перевіряли відмалювання розмітки; тепер перевіряється розбір заголовків.

## [2026-10-28] fix | Цикли в режимі «Не зупинятися»

**Помилка (скриншот власника):** модель повторювала «Я опрацював продовження drive_sync.py» і читала той самий шматок. **Зміни:** третій однаковий виклик з тими самими аргументами відхиляється з кодом `repeated_call` (без виконання); повтор тієї самої відповіді моделі без нових дій завершує хід з кодом `stalled`. **Тести:** `repeated_call` і `stalled` (падали до виправлення); тест продовження читання тепер використовує точний розмір файлу. Повний набір: 507 пройшли. **Межі:** на реальній моделі не перевірено; повтор з відмінним текстом (без нових дій) цей захист не ловить.

## [2026-10-29] fix | TUI: стан перемикачів видно словами

**Причина (скриншот власника):** обидві позначки малюються однаково (`▐X▌`), стан видно лише кольором, тож не зрозуміло, чи ввімкнено «НЕ ЗУПИНЯТИСЯ». **Зміна:** мітка показує стан словами («НЕ ЗУПИНЯТИСЯ: ВКЛ» / «ВИМК»), оновлюється при перемиканні. **Тест:** мітка змінюється при перемиканні (падав до виправлення). Повний набір: 510 пройшли. **Відповідь на питання:** без «НЕ ЗУПИНЯТИСЯ» модель після першого кроку зупиняється і питає дозволу, як у скриншоті; галочку треба ввімкнути для таких завдань.

## [2026-10-29] fix | Дефекти з проходу розмов (BUG-01…06)

**Зміни:** описи інструментів пам'яті і shell переписано зрозумілою мовою з назвами аргументів (BUG-01/02); `argv` без дубля назви програми, для оболонки — один `-c` рядок (BUG-02/03); три невдачі тієї самої програми відхиляються `repeated_failure` у будь-якому режимі (BUG-04); системний промпт: не писати виклик текстом, не називати кількості без рахунку, не закінчувати питанням про дозвіл (BUG-05/06). **Тести:** `test_tool_usability.py`, повторний виклик на рівні агента. Повний набір: 514 пройшли. **Межі:** поведінку моделі перевірено на юніт-рівні; повтор розмов з BUG-01…06 на реальній моделі — наступний крок.

## [2026-10-29] fix | Аналіз: звіт замість порожнього завершення, більший шматок читання

**Причина (пошук і аналіз LTE):** хід зупинявся як `stalled` або `max_rounds` після читання, і користувач не отримував нічого. **Зміни:** після вичерпання перенаправлень або лімітів раундів, якщо є прочитане, модель отримує останній крок без інструментів і складає звіт, позначаючи непрочитане; шматок читання файлу 2400 байт. **Тести:** звіт після зупинки (падав до виправлення), розмір шматка. Повний набір: 516 пройшли. **Межі:** на реальних проєктах ще не перевірено; звіт може бути неповним, але позначеним.

## [2026-10-29] fix | Звіти аналізу: повні, з журналом читання, без вигаданих файлів

**Знахідки (3 проєкти: NanoSim/app, Smallville-AI/engine, LTESniffer-native-fix):** звіти обривались (бюджет виводу 512 токенів); модель перелічувала файли, яких не читала (Nvidia_LTE/README, log.md); описувала модулі, які не відкривала; марно читала LICENSE. **Зміни:** бюджет виводу 1024 токени; у персистентному ході з читанням останній рядок — журнал інструментів (які файли прочитано і які не дочитано), він береться з журналу, а не з тексту моделі; промпт: описувати лише прочитане, ігнорувати LICENSE/.gitignore/кеш, не обривати звіт. **Тести:** журнал у звіті (падав до виправлення); оновлено 5 асертів на тіло відповіді. Повний набір: 517 пройшли.

## [2026-10-29] feat | Повний термінал (run_command) і читання великих файлів через grep

**Причина:** модель читала 140 КБ файл шматками по 2400 байт (59 викликів, 20 хвилин); `shell_exec` вимагав окремо програму і список аргументів, і модель з цим плуталась. **Зміни:** інструмент `run_command` приймає один рядок команди як у терміналі (конвеєри, перенаправлення, && дозволені), з тими самими межами виводу і прибиранням процесів, що й `shell_exec`; реєстр дозволяє рядкову форму для довільних інструментів, якщо оголошено cwd і declared_effects; промпт: великі файли спершу шукати через grep, потім читати потрібні місця через sed/head. **Тести:** повний рядок з конвеєром, код виходу і межа виводу, правило промпту; оновлено лічильник інструментів (14). Повний набір: 521 пройшов.

## [2026-10-29] fix | Аналіз великих файлів: обмеження шматків і виклики текстом

**Знахідки (NanoSim, другий прогін):** модель ігнорувала правило grep і читала recorder_app.py шматками (46 викликів); пам'ять знову друкувалась текстом (`memory_store(...)`); звіт здано до завершення («Читання файлу триває»). **Зміни:** після 6 шматків одного файлу `file_read` відмовляє з `use_search` і просить grep/sed -n; текст, схожий на виклик інструмента, не завершує хід, модель отримує нагадування викликати інструмент (до двох разів). **Тести:** обидва падали до виправлення; повний набір 523 пройшли. **Межі:** на реальному NanoSim ще не перевірено після цих змін.

## [2026-10-29] fix | Розбіжність лічильника токенів і файл, закритий після ліміту

**Знахідка:** журнал дав цифри: provider=6992, admitted=6993 (різниця один токен, ми переоцінили). Строга рівність обривала хід безпідставно. **Зміни:** модель відхиляє хід лише коли провайдер порахував більше, ніж допущено; менший лічильник приймає і логує. **Знахідка 2 (LTESniffer-native):** після відмови use_search файл лишався в partial, і нагадування вело модель назад до того самого file_read; тепер закритий файл очищується з partial і виключається з нагадувань, список зберігається як list (JSON-safe). **Тести:** `test_a_closed_file_is_not_sent_back_to_file_read` падає без очищення (перевірено мутацією), повний набір 525 пройшли. **Межі:** прогін на чотирьох проєктах після цих змін ще не завершений.

## [2026-10-29] eval | Прогін чотирьох проєктів на 0c342dd

Результат: усі чотири прогони completed; context_mismatch і текстових викликів у звітах немає. Оцінка звітів: NanoSim і LTESniffer-cuda прийнятні; Smallville і LTESniffer-native погані (звіт не описує проєкт; LTESniffer-native завершився проміжною нотаткою після 94 викликів). Детально: artifacts/analysis-tests/2026-10-29/EVAL.md. **Не доведено:** причина проміжних звітів (гіпотеза: вичерпаний PERSIST_GENERIC на хід). Наступний крок: тест на цю гіпотезу, потім виправлення.

## [2026-10-29] fix | Бюджет раундів: резерв на звіт, progress note як failed, ліміт шматків

**Причина (перевірено за sessions.sqlite3):** LTESniffer-native завершився на 150-му раунді (ліміт PERSIST_ROUNDS) після 94 викликів; останній раунд був проміжною нотаткою, яка записувалась як completed. Гіпотеза про PERSIST_GENERIC не підтвердилась: нагадування про незавершене йшли до кінця. Основний витрачач раундів: 43 нагадування «продовж файл» на великих файлах (шість шматків на файл). **Зміни:** останні PERSIST_REPORT_ROUNDS=6 раундів зарезервовано: звіт пишеться з прочитаного з вимкненими інструментами; текст без маркера на останньому раунді для персистентного ходу = failed, code max_rounds, з текстом; нагадування про продовження не вказує на файли, які досягли ліміту (_continuable); ліміт шматків 4. **Не змінено:** після запиту звіту будь-яка відповідь є кінцем (існуюча поведінка, закріплена тестом). **Тести:** три регресії падали до виправлення; мутація резерву ловиться; повний набір 528 пройшли.

## [2026-10-29] fix | Покриття: непрочитаний код не ховається за README

**Причина (перевірено у сесіях прогону 5):** LTESniffer-native завершився після одного README: покриття `_unread_listed` рахувало лише файли того самого суфікса, що вже прочитані; після .md непрочитаних .md не було, тож нагадувань не було, і модель сказала ГОТОВО. **Зміни:** непрочитаними вважаються код і конфіги проєкту (_CODE_SUFFIXES), службові файли (LICENSE, dotfiles, lock, log) не рахуються; документи (.md, .txt, .rst) рахуються тільки якщо такий тип уже прочитано. **Тести:** новий тест на покриття після README; існуючий тест про .md-нотатку збережено; повний набір 529 пройшли.

## [2026-10-29] fix | Текст у форматі моделі, неправильні поля run_command, прогін 6

**Прогін 6 (f05af98):** усі чотири completed з маркером; LTESniffer-native 82 виклики (було 11); але два дефекти: (1) звіт LTESniffer-native почався з викликів у форматі моделі `memory_store{kind:<|"|>...}`, які детектор не бачив, і разом із ГОТОВО це стало звітом; (2) Smallville: 3 із 5 викликів run_command відхилено через executable/argv з shell_exec, і модель зробила висновок, що інструмент не працює. **Зміни:** детектор текстових викликів охоплює формат `tool{...}` і токени `<|"|>`; повторний такий текст дає failed з кодом pseudo_call; відповідь про неправильні поля містить allowed_fields. **Тести:** три регресії (native-синтаксис, повторний текст, allowed_fields) падали до виправлення; повний набір 532 пройшли.

## [2026-10-29] fix | Підкаталоги в покритті; shell_exec не пропонується моделі поруч із run_command

**Прогін 7 (8b677a9):** усі чотири completed з маркером, текст у форматі моделі не зустрівся. Але LTESniffer-cuda і -native зупинялися на 13–16 викликах, не переглянувши src/; Smallville 4 з 42 викликів відхилено через executable/argv, попри підказку allowed_fields. **Зміни:** file_list запам'ятовує каталоги з переліку; нагадування перед кінцем ходу просить переглянути непереглянуті каталоги (file_list); shell_exec не пропонується моделі, коли є run_command (зареєстрований, але не в схемі моделі). **Тести:** тест покриття підкаталогів падав до змін; тест схем перевіряє прибирання shell_exec; повний набір 534 пройшли.

## [2026-10-29] fix | Повтор звіту: схожість замість точного збігу

**Діагноз прогону 8 (LTESniffer-cuda):** хід не був зависанням. Слот llama-server обробляв запит (is_processing), сесія росла з 182 до 196 повідомлень. Але агент двічі написав майже той самий звіт (≈ 413 символів), і детектор повтору спрацьовував лише на повний збіг тексту, тому цикл тривав довго. Прогін зупинено, GPU звільнено (0 %, 15 МіБ), сервер і драйвер вимкнено. **Зміна:** повтор визначається як схожість ≥ 0.9 (difflib) з попереднім текстом. **Тест:** новий тест майже однакового звіту падає без зміни і проходить із нею. Повний набір 535 пройшли. **Не перевірено на живій моделі** — для цього потрібна VRAM.

## [2026-10-29] fix | Переповнення контексту в довгому персистентному ході

**Діагноз:** обрізання було фіксованим на повідомлення (результати інструментів до 200 символів, відповіді до 400), тож історія росла лінійно з кількістю раундів. Smallville на 7053 токенах при ліміті 8192 був близько переповнення. Групи для обрізання в builder — це ходи між повідомленнями користувача, і довгий ход без нагадувань лишається одним блоком. **Зміна:** історія обмежена бюджетом PERSIST_HISTORY_CHARS = 6000 символів: найновіші повідомлення лишаються повними, старіші результати інструментів і відповіді моделі стискаються до заглушок; промпти і нагадування не стискаються. **Тести:** новий тест довгого ходу падає без обмеження (перевірено вимкненням) і проходить із ним; повний набір 536 пройшли.

## [2026-10-29] eval | Smallville і LTESniffer-native на dc07b99

**Результат:** обидва `completed`, без `context_overflow`. Smallville: 98 с, 13 викликів, звіт з чотирьох пунктів і маркером; `server.py` прочитано (file_read, offset 0), розбіжності немає, я помилився, показавши лише шість найчастіших файлів. LTESniffer-native: 329 с, 51 виклик, звіт описує модулі, web-monitor, запуск і залежності; маркера немає, бо хід завершився після запиту звіту (поточне правило), журнал чесно показує `CMakeLists.txt` і `README.md` як не дочитані повністю. **Висновок:** переповнення і цикл закрито, відкритим лишається лише відсутність маркера у звіті після запиту, що є поточним правилом. Повторний повний прогін на чотирьох проєктах не робився; GPU вивільнено.

## [2026-10-30] ingest | Порівняння з NVIDIA reachy-mini-jetson-assistant і туторіалом Jetson AI Lab

**Джерела (WebFetch, сторінки переказані моделлю, не дослівно):** github.com/NVIDIA-AI-IOT/reachy-mini-jetson-assistant (Apache-2.0, 38 зірок, станом на читання); jetson-ai-lab.com/tutorials/reachy-mini-jetson-assistant/. Код не запускався, їхні цифри не перевірені. **Висновок:** у них голос і зір на Orin Nano 8GB, у нас їх немає (голос відкладено). У нас сильніший контроль дій, пам'ять зі згодою і тести. Їхній веб-UI без автентифікації з живим відео — негативний приклад. Розбіжності в їхніх джерелах: різні VLM (Gemma 4 E2B проти Cosmos-Reason2-2B), різні JetPack, «no internet» при сетапі з мережею. Наші ризики: `network_allow=["*"]` у конфігурації власника, відсутній LICENSE, немає голосових цифр. Деталі: [topics/reachy-jetson-comparison.md](topics/reachy-jetson-comparison.md).

## [2026-10-30] lint | Перевірка коду NVIDIA reachy-mini-jetson-assistant

Клон `2673202` прочитано без запуску. Підтверджено: веб-сервер на `0.0.0.0:8090` без автентифікації віддає живе відео камери кожному клієнту (`run_web_vision_chat.py:70–90`, `app/config.py:155`); `/ws` приймає керування PTT і гучністю від будь-кого; модель без інструментів; `save_wav` не викликається. Кількість тестів не перевірено (команда відхилена, обхід не робився). Деталі: [topics/reachy-jetson-comparison.md](topics/reachy-jetson-comparison.md).

## [2026-10-31] fix | Функціональні вдосконалення agent/memory/tools/semantic, синхронізація документації та перевірка R17 (день 4.4)

**Зміни в коді (`src/b12/`):**
1. `src/b12/agent.py`: `_track_files` тепер фіксує покриття файлів і каталогів при опрацюванні через `file_search`, `run_command` та `shell_exec` (зокрема у підвалі журналу інструментів); детектор текстових викликів (`_TOOL_NAMES`) розширено на всі 15 вбудованих інструментів; `Agent.turn(..., persist=True)` та `Agent.resume()` виставляють дедлайн `>= 1800 с` для персистентних ходів і звільняють `control._runtime` при помилці відсутності чекпойнта.
2. `src/b12/tools/process.py` та `src/b12/tools/filesystem.py`: `CommandArgs` (`run_command`) підставляє дефолтні `cwd` і `declared_effects`, якщо модель їх опускає, зберігаючи обов'язковість у JSON-схемі реєстру; `file_search` підтримує пошук як у каталозі, так і в окремому регулярному файлі (`args.path`) і читає до 256 КіБ на файл замість 8 КіБ.
3. `src/b12/memory.py` та `src/b12/agent.py`: збережено внутрішні апострофи (`'`, `’`, `ʼ`) при розбитті українських слів для `pymorphy3` (`ім'я` ↔ `імені`, `комп'ютер` ↔ `комп'ютера`) і додано фільтрацію розмовних стоп-слів при побудові запитів природною мовою (без зміни літеральної обробки операторів FTS5 `AND/OR/NOT/NEAR`).
4. `src/b12/semantic.py`, `src/b12/cli.py`, `src/b12/tui/client.py`: у `BridgeEmbedder.close()` коректно закривається транспорт і потоки `Popen` після закриття event loop (прибрано `PytestUnraisableExceptionWarning`); у CLI та TUI узгоджено 1800-секундний таймаут для `persist`-ходів.

**Довготривала перевірка пам'яті (R17):** прогін `scripts/daily_check.py check --out ~/.local/state/b12/long_horizon` на позначці `elapsed_days: 4.389` дав `ok: true` (усі 3 якорі згадані, забутий маркер відсутній у пошуку й байтах, цілісність усіх БД і знімків підтверджена, 80 подій аудиту).

**Синхронізація документації (lint):** оновлено цифри в `README.md` (14 host tools, 542 тести, стан R17), додано головну ілюстрацію `docs/images/b12-hero.jpg` на початок `README.md`, додано `LICENSE` (Apache-2.0) і шаблони `deploy/b12-daily-check.{service,timer}` (таймер увімкнено у `systemd --user` і перевірено запуском `status=0/SUCCESS`), виправлено застаріле твердження про нереалізований план F4 у `wiki/topics/reachy-jetson-comparison.md`.

## [2026-11-01] implementation | Голосовий шар B-12: PTT, VAD/endpoint, ASR, TTS, AEC, speaker verification та full-duplex (Tasks 16–17, R15)

**Перевірений факт:**
1. Встановлено голосові залежності (`faster-whisper 1.2.1`, `onnxruntime 1.31.1`, `piper-tts 1.8.0`, `soundfile 0.14.0`, опція `b12-runtime[voice]`) та локальні відкриті голосові моделі у `~/.local/share/b12/voices/` (`uk_UA-ukrainian_tts-medium.onnx` CC0-1.0, `uk_UA-mykyta-high.onnx` Apache-2.0, `en_US-lessac-medium.onnx`, `silero_vad.onnx` MIT); SHA-256 та ліцензії зафіксовано в `evals/voice/licenses.json`. Дані чи код із проєктів VoiceID/VoiceEvolve не імпортувались.
2. Реалізовано пакет `src/b12/audio/`:
   - `capture.py`: `MicController` (`mic_muted` у `ControlStore` окремо від `actor.consent`), `PttCapture` (PipeWire `pw-record` / ALSA `arecord` у volatile `float32` 16 кГц без запису сирого аудіо на диск за замовчуванням, негайне переривання при `cancel`).
   - `endpoint.py`: `SileroVad` (ONNX Runtime CPU з 64-семпловим контекстним вікном для 512-семплових фреймів 32 мс) та `EndpointDetector` із роздільним обліком фізичного завершення мовлення (`physical_eou_sample`) та моменту рішення (`decision_sample`).
   - `asr.py`: `WhisperAsr` (`Systran/faster-whisper-small`, одноразовий `encode` з обмеженням авто-визначення мови до `{uk, en}`, декодування PCM/WAV у пам'яті в обхід помилки `av.open(metadata_errors=...)`).
   - `tts.py`: `PiperTts` (українська нормалізація чисел, акронімів і апострофів без відсутніх фонем, перемикання на `en_US-lessac-medium` для англійських речень, обмежена черга фраз `max_queue_phrases`), `generate_earcon_pcm` (окремий облік `earcon_ms`) та `AudioPlayer` із передачею 16 кГц `render_reference` та миттєвим `stop()`.
   - `aec.py`: `AcousticEchoCanceller` (адаптивний NLMS + кореляційне пригнічення за точним `render_reference`, текстовий фільтр самовідлуння `is_tts_echo_text` та детектор медіа-забруднення).
   - `speaker.py`: `SpeakerStore` (`SQLite` із `PRAGMA secure_delete = ON`) та `SpeakerVerifier` (спектрально-гармонічний voiceprint, блокування exact-replay і spoof, реєстрація лише через автентифікований контрольний шлях власника, фізичне видалення біометрії).
   - `pipeline.py` та `duplex.py`: `VoicePipeline` і `DuplexSession` (barge-in під час активного мовлення зупиняє плеєр, скасовує активний turn моделі й очищує чергу TTS; повага до `quiet` режиму для автономних реплік).
3. Інтегровано голосові маршрути у `src/b12/api.py` (`/api/voice/{status,mute,tts,asr}`, `/api/voice/speaker/enroll`, `DELETE /api/voice/speaker/{actor_id}`), підкоманду `b12 voice {status,mute,unmute,say,listen}` у `src/b12/cli.py` та елементи керування мікрофоном/озвученням у `src/b12/web/{index.html,app.js}`.
4. **Бенчмарки та тести:** 9 нових інтеграційних тестів у `tests/integration/test_voice.py` та `tests/integration/test_duplex.py` пройшли; у `evals/voice/report.json` отримано TTS TTFA P50 `258,57 мс`, endpoint P50 `320,0 мс`, ASR P50 `2359,13 мс`; у `evals/voice/duplex/report.json` — AEC ERLE `156,32 дБ`, barge-in stop P95 `0,039 мс`, FAR/FRR `0,0 / 0,0`, exact-replay блокується. **Межі:** 8-годинний фізичний акустичний soak у кімнаті з ТБ/шумом залишається відкритим.

## [2026-11-02] fix | Модернізація голосового стека за підсумками рев'ю (`V-001`..`V-011`) та порівняння з `NVIDIA-AI-IOT/reachy-mini-jetson-assistant`

**Перевірений факт:**
1. Проаналізовано зовнішнє рев'ю `/home/cyberdid/Downloads/B-12_Voice_Stack_Review_2026-11-01.md` (без питань безпеки/MFA за прямою вказівкою власника) та голосовий код `NVIDIA-AI-IOT/reachy-mini-jetson-assistant` (`app/pipeline.py`, `app/tts.py`, `app/speaking_movements.py`).
2. Усунено всі функціональні та архітектурні дефекти `V-001`..`V-011` у `src/b12/audio/`:
   - `V-001` (`src/b12/audio/duplex.py`): `speak_response()` переписано на конкурентні `asyncio.Task` продюсера й консюмера поверх черги `_tts_queue(maxsize=8)` із таймаутами та `try/finally`-очищенням — усунено дедлок на відповідях із >8 речень, а озвучення фрази №1 починається одразу після її синтезу.
   - `V-002` (`src/b12/audio/duplex.py`, `src/b12/audio/aec.py`): `feed_capture_frame()` виконує `aec.process_capture()` один раз і зберігає read-only `cleaned_audio` у `BargeInResult`; `handle_duplex_utterance()` використовує вже очищений буфер без повторного проходу NLMS.
   - `V-003` (`src/b12/audio/duplex.py`, `src/b12/audio/pipeline.py`, `src/b12/audio/asr.py`): `VoicePipeline.process_utterance()` приймає `precomputed_transcript` та `precomputed_endpoint`, усуваючи подвійний прогін Whisper (~2,2 с економії на кожній репліці в дуплексі); додано лічильник `WhisperAsr.transcribe_count`, `warmup()` у пам'яті, авто-фолбек з CUDA на CPU та доменні `initial_prompt`/`hotwords`.
   - `V-004` (`src/b12/audio/pipeline.py`, `src/b12/audio/tts.py`): додано адаптивне дроблення `extract_stream_clauses()` (перша клауза від 3+ слів на розділовому знаку без розриву слів) і 3-ступеневий конвеєр (`LLM text_delta` → `clause_queue` → `tts_synth_worker` → `pcm_queue` → `playback_worker`), який починає відтворення першої фрази до завершення генерації LLM (`playback_started_before_llm_completed = True`).
   - `V-005` (`src/b12/audio/duplex.py`): `_cancel_scoped_voice_turns()` скасовує виключно активний голосовий хід (`_active_turn_id` / `session_id`), не зачіпаючи паралельні ходи Web/TUI/CLI.
   - `V-006`, `V-007` (`src/b12/audio/endpoint.py`, `src/b12/audio/duplex.py`): `DuplexSession` використовує сесійний `_stream_vad` без пофреймового `reset()`; додано потоковий `EndpointDetector.feed_stream_chunk()` із кільцевим `lookback`-буфером, поріг тиші `rms_silence_floor = 0.002`, властивість `SileroVad.backend` (`"onnx"` / `"rms_fallback"`), підтримку `silero_vad_v6.onnx` і вимкнено штучний RMS-бустинг у продакшені (`allow_rms_fallback=False`).
   - `V-008`, `V-009` (`src/b12/audio/aec.py`): реалізовано повноцінний 128-таповий FIR NLMS-фільтр (`_nlms_block_filter`) із FFT-вирівнюванням причинної затримки (`_align_reference`), детектором double-talk за вирівняним reference (`double_talk_detected`) та обгортку `PulseAudioWebRtcAec` (`pactl load-module module-echo-cancel aec_method=webrtc`).
   - `V-010` (`src/b12/audio/tts.py`): `AudioPlayer._play_sync` пише PCM у PipeWire/ALSA невеликими чанками з перевіркою `cancel` і підтримує хуки `on_playback_start` / `on_playback_end`.
   - `V-011` (`src/b12/audio/aec.py`): `is_tts_echo_text()` більше не відкидає короткі 1–2-слівні відповіді користувача (`"Зараз"`, `"Так, зараз"`, `"Ні"`), якщо ці слова траплялися в довшому питанні асистента.
   - Український TTS (`src/b12/audio/tts.py`): дефолтну модель перемкнуто на `uk_UA-mykyta-high.onnx` (`espeak` фонеми) зі збереженням природного регістру й пунктуації, що знизило TTS→ASR roundtrip WER в `evals/voice/report.json` із `39,24 %` до **`0,0 %`** (`uk_mean_wer: 0.0`, `en_mean_wer: 0.0`).
   - Speaker verification (`src/b12/audio/speaker.py`, `src/b12/purge.py`): додано 16 DCT-II MFCC-подібних кепстральних ознак + log-mel + F0 профіль та метод `PurgeCoordinator.forget_voice_profile()`.
3. **Перевірка:** розширено інтеграційні тести в `tests/integration/test_voice.py` (7) та `tests/integration/test_duplex.py` (5), оновлено `evals/voice/report.json` та `evals/voice/duplex/report.json` (`erle_mean_db: 30.41` на багатопроменевому RIR із шумом, barge-in stop P50 `0,025 мс` на реальному TTS через ONNX Silero VAD).




## [2026-11-03] fix | Виправлення з аудитів (без питань безпеки)

За вказівкою власника пункти безпеки (A-01, A-07, A-08, A-18, A-19, A-22, F-03) відкладено; решту виправлено з тестами, що падали до змін.

- **A-21:** шаблон текстового виклику спрацьовує лише на початку рядка або на власному синтаксисі моделі; згадка інструменту у реченні більше не є викликом. Тест: `test_a_tool_name_mentioned_in_prose_is_not_a_pseudo_call`.
- **A-11:** `last_reflection` ставиться після завершення рефлексії. Тест: `test_reflection_marks_the_interval_only_after_it_finishes`.
- **A-12:** `timeout_s` рефлексії передається в модель як `deadline`. Тест: `test_reflection_passes_its_timeout_to_the_model`.
- **A-05 / F-02:** `open_runtime` створює сховище голосових профілів і передає його в `PurgeCoordinator`; раніше `forget_voice_profile` у продакшні завжди повертав `False`. Тест: `tests/integration/test_purge_coverage.py`.
- **F-05:** голосові обробники API повторно використовують модель Whisper/Piper на застосунок. Тест: `test_voice_endpoints_reuse_one_speech_model_per_app`.
- **A-24 (частково):** `purge_snapshots` виконується в потоці, не блокуючи цикл подій. Синхронний `create_snapshot` лишено навмисно: копія має бути узгодженою між сховищами.
- **A-04:** checkpoint цілі зберігає докази, з яких побудовано, і `forget` стирає ціль разом із текстом. Тест: `tests/unit/test_goal_checkpoint_evidence.py`.
- **A-17:** скасування ходу, що чекав підтвердження, прибирає його checkpoint і запис у `_waiting`. Тест: `tests/unit/test_cancel_waiting_turn.py`.
- **F-14:** режим «Не зупинятися» описано доповненням 15.7 у специфікації.

Не зроблено (потребує рішення власника або більшої роботи): A-02 (CLI й `serve` без спільного блокування, рішення про UX), A-03 (транзитивні теги при повторному використанні історії), A-09 (векторні знімки й голосові профілі у знімках), A-10 (зовнішній ключ доказів), A-13, A-14, A-06 (повний дуплекс і AEC), A-15 (затримка), A-16 і A-23 (ліміти руху), A-20 (кеш KV Ollama), F-06 (контракт Observation), F-07 (автономні підсистеми), F-08, F-09, F-15 (CLI-підкоманди), F-10–F-13 (фізичні й тривалі перевірки).

Повний набір: 561 пройшли, 3 пропущено.

## [2026-11-03] fix | A-02: CLI і запущений сервер

Рішення власника: запущений `b12 serve` — єдиний власник runtime. CLI визначає режим за `RuntimeLock`: лок зайнятий → API; лок вільний → локальний runtime під локом; API недоступний при зайнятому локу → `server_unavailable` без переходу до прямого доступу. Реалізовано в `src/b12/cli.py` (`main`, `run_remote`) і `src/b12/cli_remote.py`; додано `GET /api/cli-session`. Зіставлення команд, яких бракує в API, у [topics/cli-server-mode.md](topics/cli-server-mode.md). Тести: `tests/e2e/test_cli_server.py` (3); мутація примусового локального режиму ламає сценарій `memory forget` під час активного ходу. Повний набір: 564 пройшли, 3 пропущено.

## [2026-11-03] fix | A-03 транзитивне походження; A-09 векторні знімки

- **A-03:** хід, що цитує історію сесії, переносить теги доказів цієї історії у свій стан (`SessionStore.history_with_tags`, `Agent.history_with_tags`). Тепер `forget` факту прибирає і пізніший хід, що його процитував. Тест: `test_forgetting_a_fact_also_removes_the_later_turn_that_quoted_it` (падав до змін).
- **A-09 (частково):** `purge_snapshots` видаляє вектори забутих спогадів з `semantic/vectors.sqlite3` у кожному знімку. Тест: `tests/integration/test_snapshot_purge.py` (падав до змін). Не зроблено: відновлення (`restore`) пропускає повторне забуття для вже неживих записів; потребує окремої перевірки.
- **A-10 не зроблено:** `evidence.evidence_id REFERENCES memories(id)` і `remember` вимагають, щоб доказ був живим спогадом; доказ з документа неможливий. Потрібна міграція схеми і зміна логіки забуття, тому окремим кроком.

Повний набір: 566 пройшли, 3 пропущено.

## [2026-11-03] fix | A-10: докази з документів, міграція v1→v2

- **Схема v2:** `memory_sources` (спогад або документ KnowledgeIndex з ревізією) замінює `evidence`; `memories` має `status` і `status_reason`.
- **Міграція:** перевірена резервна копія перед змінами, перенесення всіх зв'язків з перевіркою кількості, відкат при розбіжності. Копію реальної бази власника (47 спогадів, 114 зв'язків) мігровано без втрат; резервну копію відновлено і мігровано повторно.
- **Документи:** `remember(documents=...)` перевіряє доказ через `KnowledgeIndex.resolve_evidence` у тій самій транзакції; `memory_store` приймає `document_evidence_ids`.
- **Життєвий цикл:** зміна або видалення документа позначає спогади `stale` (транзитивно); цілі на застарілих спогадах ставляться на паузу; `forget` працює як раніше.
- **Нові операції:** `knowledge index|remove|search` у CLI та API; `memory remember --document`.
- **Тести:** 8 документальних, 2 наскрізних через процеси CLI (з сервером і без), 3 міграційних. Мутація ламає 4 з 8. Повний набір: 580 пройшли, 3 пропущено.
- **Межі:** застарілий спогад не відновлюється після переіндексування; restore знімків на застарілих спогадах не перевірено. Деталі: [topics/evidence-model.md](topics/evidence-model.md).

## [2026-11-03] feat | A-14: живий full-duplex (етап 1)

- `src/b12/audio/live.py`: безперервне читання мікрофона (`LiveMic`, pw-record/arecord без фіксованої тривалості), сегментація мовлення (`Segmenter`: pre-roll, тиша, мінімальна тривалість, відкидання луни), цикл `LiveSession`: кожна репліка розпізнається рівно один раз і запускає один хід у окремій задачі, мікрофон не зупиняється.
- `DuplexSession.process_cleaned_utterance`: хід для вже очищеної й розпізнаної репліки (без повторного AEC і ASR).
- Агент: хід, скасований під час відповіді моделі, завершується як `cancelled` (раніше — `completed` з частковим текстом).
- CLI: `b12 voice live` (локально; при запущеному сервері — `requires_stopped_server`, бо мікрофон належить процесу).
- Тести: `tests/integration/test_live_duplex.py` (4), сегментатор, CLI-тести `voice live` (2). Мутація: вимкнення перевірки скасування ламає тест переривання. Повний набір: 586 пройшли, 3 пропущено.
- **Не зроблено:** фізичний тест з мікрофоном і динаміком; етап 2 (синхронізація референсу AEC у часі відтворення, A-06, A-13); етап 3 (вимірювання P50/P95 затримок, A-15). У тестах VAD замінено енергетичним стабом, бо Silero ненадійний на синтетичних тонах: реальну мову треба перевірити фізично.

## [2026-11-03] fix | A-06, A-13: синхронізація референсу AEC (етап 2)

- **Референс у такті відтворення.** `AudioPlayer` подає референс блоками в момент запису в програвач, а не всю фразу на початку (A-06). FIFO референсу споживається з тією самою швидкістю, що й кадри захоплення.
- **Затримка.** Оцінка кросс-кореляцією до 400 мс (раніше 16 мс). Периодичність голосу: серед майже рівних піків береться найближчий до попередньої оцінки.
- **Фільтр.** Розв'язання 256×256 на кожному кадрі займало ~590 мс; замінено на блоковий NLMS (~0,6 мс на кадр).
- **Подвійне мовлення.** Фільтр заморожується; синтетично збережено голос користувача (кореляція 0,96).
- **Вимірювання.** `b12/audio/measure.py` (ERLE, похибка затримки, частота хибних VAD, P50/P95 з n). `AudioPlayer.stop_measured` розділяє час сигналу і час виходу процесу. Подія `aec` раз на секунду в `voice live`.
- **Тести:** `tests/unit/test_aec_quality.py` (4), `tests/unit/test_render_pacing.py` (3). Синтетичні, позначені як такі. Повний набір: 592 пройшли, 3 пропущено.
- **Не виконано:** фізичний тест. Документ: `docs/voice-physical-test.md` (стан AEC, два варіанти, сценарій з п'яти кроків, пропоновані критерії, які треба погодити з власником).

## [2026-11-04] implementation | Кіберпанковий TUI та кіберкіт

**Вимога власника:** красивий cyberpunk TUI з бічним virtual pet, mouse reactions і реакціями на спілкування; власник обрав кіберкота. Реалізація зроблена в окремій managed worktree від `main fbe9e223`, без відновлення зупиненої великої задачі runtime/eval. [Опис і запуск](topics/cyberpunk-tui.md).

**Перевірений факт:** нові neon layout/header/composer, half-block pixel cybercat, blinking/breathing/tail motion, cursor gaze, pat/click/Ctrl+K, UI/API phases та F8 reduced motion. На 80×24 кіт залишається збоку, навігація доступна через F2; пам’ять/approvals — через Ctrl+P. Збережено реальний API client та chat/tool protocol. Офлайн `python -m b12.tui.preview` позначений «ДЕМО / БЕЗ СЕРВЕРА» і використовує лише ephemeral sample data.

**Перевірка:** baseline TUI — 7 passed; початковий pet/layout RED — 6 failures. Подальші RED відтворили compact navigation/focus, history scroll і worker crash при втраті сервера; виправлення перевірено. Фінальний `python -m pytest -q tests/integration/test_tui.py tests/integration/test_api.py` — **28 passed за 19,46 с**; Ruff для TUI/test і diff check — clean. Один UI scenario пройшов через справжній API stack із synthetic model endpoint та реальною file_write дією лише в temp directory. PTY smoke: preview exit 0, SGR mouse reporting увімкнений. Render review — 144×44, 80×24 та компактна control panel; screenshot містить синтетичну розмову.

**Review:** окремий read-only reviewer `/root/cybercat_tui_review` переглянув фінальний TUI diff і не знайшов підтверджених функціональних дефектів; reviewer не запускав тести й не оцінював фізичний terminal rendering. Джерелом результатів тестів і PTY/render evidence є прогони головного агента. Код не комітився, не зливався в main і не публікувався.

## [2026-11-04] lint | Документація нового TUI

Нова UI-сторінка включена в index; також додано раніше пропущений TUI/agent test plan. Усі 39 wiki-сторінок охоплені index. Нові/змінені UI documentation links, source paths і screenshot перевірено. У чистій managed worktree лишаються 13 історичних посилань/source refs на ігноровані local benchmark artifacts та `.superpowers`, яких Git не переносить; ці джерела не копіювалися і не переписувалися в рамках UI-доручення. Raw originals та source manifest незмінні.

## [2026-11-04] verification | Git-аудит, повний suite та R17 day-7

**Git, перевірений факт:** локальний `main` і `feat/b12-runtime` дорівнюють `origin/main` / `origin/feat/b12-runtime` на `fbe9e223bcba78b38244c63b3ab20b58506c830a`; `feat/b12-access` (`c1cfecc`) є предком і відстає на 8 комітів. Від baseline `78daaef` — 146 досяжних комітів, 229 змінених tracked paths, +36 266 / −71 рядків. Main/runtime tracked trees чисті. Access worktree має локальні незакомічені `artifacts-access-tools/` та `.log`; це один старий eval на `c294aff`, описаний у [evals](topics/evals.md#актуальність-станом-на-2026-11-04). Ігнорований `.superpowers` execution ledger не є актуальним source of truth.

**Перевірений факт:** на точному `fbe9e223` `uv run --no-sync python -m pytest -q` — 592 passed / 3 skipped за 193,79 с; `uv run --no-sync ruff check src tests` — clean. Прямий console запуск `uv run --no-sync pytest -q` падає під час collection двох модулів (`ModuleNotFoundError: tests`), бо вони імпортують helper як `tests.integration...`, а pytest config додає лише `src` до `pythonpath`; модульний запуск пройшов повністю. Це відтворюваний недолік test entrypoint, ще не виправлений.

**Перевірений факт, R17:** user timer `b12-daily-check.timer` запустив перевірку 04.11.2026 11:46 EET. З агрегованих метаданих (без читання тексту якорів): `elapsed_days=8.091`, `ok=true`, `integrity_ok=true`; systemd status `0/SUCCESS`; journal показав `snapshots_ok=true`, `pending_purges=0`, забутий маркер відсутній у пошуку та байтах, 80 audit events. День 7 пройдено; 30-day gate — 26.11.2026.

**Межа оцінювання:** повний real-Bolt eval на поточному `fbe9e223` не знайдено. Найновіший повний recorded eval у wiki — `60a4c0b` від 27.10; локальні 38/43 від `c294aff` — інший, давніший commit. Security findings A-01, A-07, A-08, A-18, A-19, A-22 і F-03 лишаються відкладеними за записаним рішенням власника.

## [2026-11-04] lint | Актуальність wiki після Git-аудиту

**Перевірений факт:** 38 wiki-сторінок, 313 локальних Markdown-посилань/якорів, frontmatter і source paths змінених сторінок пройшли перевірку; broken links — 0, неіндексованих сторінок — 0. `wiki/project/test-plan.md` був відсутній у каталозі; доданий до `wiki/index.md`.

**Застарілість і межі:** status/evals сторінки отримали current-state notes; R01–R17 таблиця лишається baseline на `60a4c0b`, а не новим повним audit. `wiki/project/implementation.md` і `wiki/project/roadmap.md` залишаються старими зрізами від 26.10 і потребують окремої синхронізації. Ігнорований локальний `.superpowers` ledger також не є повним журналом після 26.10. `raw/` та `raw/source-manifest.json` не змінювалися.

## [2026-11-04] fix | Console pytest та синхронізація execution path

**Перевірений факт:** `baed10d` додає `.` до pytest `pythonpath`. RED: console collection двох voice-модулів завершився двома `ModuleNotFoundError: tests`; GREEN: 8 тестів збираються. Повний звичайний `uv run --no-sync pytest -q` на фінальній зміні — 592 passed / 3 skipped за 193,99 с; `ruff check src tests` — clean. Додаткові тести, які перевіряли б саму конфігурацію, не створювалися; відтворенням є оригінальна команда запуску.

**Оновлення попереднього lint:** `implementation.md` і `roadmap.md` синхронізовано з поточними artifacts та відкритими gates. Застарілі TTS P50 258,6 мс і ERLE 156,3 дБ замінені показниками report 02.11: TTS TTFA P50 1634,61 мс (synthetic roundtrip, n=8), ERLE mean 30,41 дБ (simulated RIR, n=5); internal software stop відокремлено від фізичного припинення звуку.

**Preflight без inference:** `ModelProfile` перевірив hashes трьох tokenizer/template assets; `OllamaModel._check_deployment` підтвердив version 0.33.3, pinned alias manifest і native template. Power profile — `performance`. Локальний звіт: `artifacts/preflight-2026-11-04/report.json` (поза Git). GPU зайнятий `gemma4:12b` (~7,4 ГБ VRAM); спосіб планування Bolt eval запитано у власника. Перед великим прогоном також потрібні актуалізація corpus checks для `run_command` і середовище, яке ізолює adversarial host effects від файлів власника.

## [2026-11-04] lint | Синхронізовані milestone та execution pages

38 wiki-сторінок, 317 локальних посилань/якорів, усі frontmatter source paths і охоплення індексом перевірено: помилок і неіндексованих сторінок немає; `git diff --check` пройшов. Історичні checkpoints збережено, поточні статуси й метрики відокремлено від них. Raw originals та source manifest незмінні.

## [2026-11-04] fix | Corpus v4 і відтворюваний voice extra

**Перевірений факт:** `069bbd5` закриває blind spot корпусу: `run_command`/`sudo_exec` більше не проходять checks, що забороняють command execution, через відсутність імені у списку. Echo та файлові сценарії приймають актуальний `run_command`. RED — 4 регресії відтворили false PASS / false FAIL; GREEN — усі 9 runner tests. Збережено 109 IDs, змінено 14 cases; додано exact generator↔files comparison. Історичні benchmark artifacts не змінено; новий real-model score потребує окремого прогону v4.

**Перевірений факт:** `uv lock --check` / locked export до `f61f9ba` падали, бо graph не містив оголошеного `voice` extra. Commit додав 11 пакетів без зміни версій попередніх packages. Чисті ізольовані environments встановлені через `uv sync --locked --extra dev --extra tui --extra voice`; full console pytest — 598 passed / 3 skipped на Python 3.12.3 за 188,52 с і на Python 3.13.14 за 189,80 с. Ruff src/tests/evals, lock check, locked export і diff check пройшли. Оригінальне робоче `.venv` не змінювалося.

**Перевірка ізоляції:** bwrap user namespace недоступний (`setting up uid map: Permission denied`). Disposable Docker probe на pinned image `python@sha256:34386ef0cb081344d7ec1c103ba398e6e9f64e9ab3a1509accc92a4e24a07258` перевірив read-only root mount через `statvfs`, один writable output, приховані host sentinel/config/docker socket, недоступні host loopback і external IP; sentinel лишився незмінним, контейнер видалений. Це перевірка середовища, не завершений B-12 Docker runner; transport до pinned Ollama ще не інтегрований. Агреговані звіти/hashes — `artifacts/preflight-2026-11-04/` поза Git. GPU inference не запускали; питання планування зайнятого GPU лишається відкритим.

## [2026-11-04] lint | Corpus v4 та locked environments

38 wiki-сторінок, 318 локальних посилань/якорів, frontmatter sources та index coverage пройшли перевірку; broken links і неіндексовані сторінки — 0. Поточний статус містить нові functional results, historical model/voice metrics збережено окремо. Raw originals та source manifest незмінні.

## [2026-11-06] implementation | Повторні фрагменти й пошук в інтернеті

За дорученням власника розпочато покращення аналізу коду та інтернет-доступу. У `feat/b12-runtime` додано облік унікальних offset для ліміту читання: повтор тієї самої частини не витрачає ліміт нових частин. Регресійний тест падав до зміни. Додано `web_search` через Bing RSS з наявною capability `network.http` і перевіркою `network_allow`; прямий HTTP probe повернув три результати. Модельний пошуковий сценарій і новий повний аналіз зовнішньої теки shell-скриптів ще не перевірені. Процес сервера не перезапускався. Подальші зміни й перевірки залишаються відкритими.

## [2026-11-06] research | NVIDIA agent evaluation і live web search

Перевірено вибрані офіційні сторінки NVIDIA: NeMo Agent Toolkit позначено deprecated із жовтня 2026 та EOL до кінця 2026; Relay/Fabric/Helix описані як наступні напрями. Рішення для B-12 — не додавати deprecated runtime; використати поділ task/runner/trial і окреме оцінювання відповіді та trajectory як eval-принципи. Картка джерела й статус кожного URL — [wiki/sources/nvidia-agent-frameworks-2026-11-06.md](sources/nvidia-agent-frameworks-2026-11-06.md) та `raw/source-manifest.json`; локального snapshot немає.

Додано `web_search`: DuckDuckGo Lite, Bing RSS fallback, bounded результат і перевірка `network_allow` через `network.http`. Mock-тести та один live-запит Bolt повернули офіційну NVIDIA Nemotron сторінку. Це підтверджує інструментальний шлях, але не точність пошуку загалом.

## [2026-11-06] fix | Coverage guard для довгого read-only review

Persist-turn тепер не рахує повторний offset як нову частину; `file_search` і shell grep не є доказом повного читання. Фінальний маркер проходить coverage guard, а неповний хід завершується `failed/incomplete_coverage` із назвами прогалин. Доданий TDD regression для продовження інструментів до 60 додаткових раундів, поки перелічені code/config/docs лишаються неповними. Інструкції більше не вимагають `run_command`, якого може не бути у grant; аналіз коду не надає дозволу змінювати long-term memory.

Live Bolt review зовнішньої теки shell-скриптів (v3 і v4) усе ще завершився `failed/incomplete_coverage`: 10/11 файлів до EOF, один файл лише частково прочитаний. Фінал не містив надійних, прив’язаних до рядків знахідок. Це негативний eval якості моделі; Claude baseline залишається неперевіреним і не використаний як ground truth. Умови й межі — [evals](topics/evals.md#live-bolt-перевірки-інтернету-та-кодового-review-2026-11-06).

Виконані зміни лежать у worktree `.worktrees/runtime`, гілка `feat/b12-runtime`, без commit. Ізольований server на 18712 зупинений; основний процес на 8712 не перезапускався під час активного з’єднання, тому ще не завантажив поточний код.

## [2026-11-06] lint | Runtime search і coverage зміни

Повний suite на точному робочому дереві: 663 passed, 4 skipped за 151,76 с. `ruff check src tests evals` та `git diff --check` пройшли. Перший повний прогін виявив чотири застарілі очікування тестів; тести оновлено під новий контракт incomplete coverage і granted file tools, після чого повторний повний suite пройшов.

Wiki validation: 41 сторінка, 340 локальних посилань, биті шляхи/якорі — 0, відсутні `sources` — 0, сторінки поза індексом — 0. SHA-256 `raw/B-12_Master_Project_2026-10-24.md` лишився `e2b0c4c33054082a4df48fed2785c834a95cfb7fb8f6a6e9198b6de53bd8e37a`, що збігається з `raw/source-manifest.json`. У `raw/` master brief не змінювався; маніфест містить 120 external references, з новими перевірками NVIDIA та межами прочитаного.

## [2026-11-06] fix | Контекстна безперервність після обрізання історії

`Agent._admit` більше не ігнорує `AdmittedRequest.dropped_ids`: після вилучення старих turns повторно збирає запит із короткими цитатами до трьох пропущених user/assistant turns. У system context явно зазначено, що це недовірені уривки, історія неповна і не можна заперечувати попередній діалог. У persist-режимі враховано старі assistant/tool повідомлення, скорочені `_fit_history`. Обов’язкові повідомлення поточного ходу та context fail-closed не змінені.

TDD regression використовує реальний `ContextBuilder`: великий старий turn справді вилучається, запит моделі містить уривок із нього, а поточне запитання лишається останнім. Повний `uv run pytest -q`: **664 passed, 4 skipped** за 148,89 с; `uv run ruff check src tests` і `git diff --check` пройшли.

**Операційна перевірка:** B-12 API перезапущено з worktree `.worktrees/runtime` на `127.0.0.1:8712`; `/api/health` повернув `ok=true`. Kitty TUI перезапущено та підключено до API (активне loopback-з’єднання). Live `/api/tools` показав 19 записів каталогу, серед них `web_search`. Ollama та процеси GPU не перезапускалися й не зупинялися.

## [2026-11-06] lint | Context fix і GitHub підготовка

Перевірено 41 wiki-сторінку, 340 локальних Markdown-посилань і якорів, frontmatter, усі `sources` paths та охоплення індексом: помилок немає, неіндексованих сторінок — 0. Перевірено відсутність нових локальних transcript/download paths у baseline-картці; до публічної wiki перенесені лише широкі категорії неперевірених тверджень. Master brief байтово незмінний, SHA-256 збігається з маніфестом. README/status синхронізовані з датою 06.11 та зафіксованими межами benchmark.

## [2026-11-06] review fix | Повна пагінація file_list у coverage guard

Read-only review виявив, що `Agent._track_files` раніше виставляв `dirs[path]=True` після першої сторінки `file_list`; це могло дозволити persist-звіту завершитися з неповним індексом теки. Тепер у turn state зберігаються очікувані offsets. Тека лишається незавершеною до фінального `next_offset=null`; сторінку поза чергою не приймають за закриття пропущеного діапазону. Auto-nudge і `next_unfinished` називають точний offset, а каталог повністю перелічається до читання знайдених файлів.

**TDD:** тест із 201 записом перевіряє сторінку 0, спробу перескочити на 400, повторне продовження з 200 та успішне завершення лише після правильної сторінки. Цільові regressions — 4 passed. Перший повний прогін після fix виявив застаріле очікування старого тексту системної підказки; assertion оновлено під `next_offset=null`. Повторний повний `uv run pytest -q`: **665 passed, 4 skipped** за 170,36 с. `uv run ruff check src tests evals` та `git diff --check` — clean.

**Незалежний rereview:** на commit `5eb6f62` конкретних findings не залишилось. Перевірено, що непослідовні сторінки не змінюють очікуваний offset і не дають завершити покриття.

**Перезапуск:** після фінального fix B-12 API з worktree знову запущений на `127.0.0.1:8712`; health endpoint повернув `ok=true`. Kitty TUI підключено, API tool catalog містить 19 записів разом із `web_search`. Ollama/GPU-процеси не перезапускалися.

## [2026-11-06] publish | PR з runtime, пошуком і документацією

За дорученням власника три коміти гілки `feat/b12-runtime` опубліковано в публічному `cyberdid/B-12`; відкрито [PR #1 у `main`](https://github.com/cyberdid/B-12/pull/1). PR містить детальний опис змін, перевірок, benchmark меж і негативного live code-review результату. На момент запису PR має стан OPEN і не злитий; `main` не змінювався.

## [2026-11-07] research | Capri / Capricorn desktop-компаньйони

За дорученням власника закріплено та порівняно pinned HEAD чотирьох вказаних GitHub-репозиторіїв. Три з них мають desktop pet/assistant компоненти; `CHNFTQ/Capricorn` є diffusion-моделлю для Hi-C genomics і не стосується desktop. Розділено UX-приклади від фактичних можливостей, зафіксовано README/code розбіжності й межі ліцензій. Перевірені Qt for Python прозорість X11 та системний трей. Джерельні pins/scope записані у `raw/source-manifest.json`; зовнішні source snapshots у `raw/` не додавалися.

## [2026-11-07] plan | Desktop-компаньйон B-12

За прямим дорученням власника підготовлено архітектурний дизайн і поетапний implementation plan. Обрано окремий optional Qt shell, що використовує існуючий owner-authenticated loopback API та B-12 cybercat art. Нові host tools, скринкасти/віконний моніторинг, автозапуск і власний runtime не додаються; мікрофон/audio playback не стартують. Робота винесена в гілку `feat/b12-desktop-companion`; на базовому `3e7fb07` перевірений TUI baseline — 22 passed.

## [2026-11-08] review fix | Відновлення desktop turn і історії сесій

Закрито race conditions після обриву NDJSON-потоку: клієнт чекає успішного підтвердження cancel, перевіряє статус саме цього turn через owner-scoped endpoint і не приймає запізнілі callbacks попереднього turn. Composer розблоковується лише після `active=false` і успішного оновлення історії. Помилка завантаження історії лишає надсилання заблокованим; при відкаті зміни сесії незавантажена історія отримує bootstrap retry. Додані regressions для cancel/status ordering, stale callbacks, failed history та rollback retry. Незалежний rereview останньої зміни не знайшов підтверджених дефектів.

## [2026-11-08] lint | Desktop-компаньйон: фінальна перевірка

**Перевірений факт:** повний locked suite після останнього fix: 740 passed / 4 skipped за 163,94 с. `ruff check src tests`, `uv lock --check`, `git diff --check` і `uv build` пройшли. Побудований wheel містить `b12/desktop/chat.py`, `b12/desktop/cat.py` і `b12/tui/assets/cybercat-atlas.png`.

Wiki audit: 44 сторінки, 358 локальних посилань, 0 битих anchors і 0 сторінок поза index. Залишаються 11 історичних посилань на відсутні benchmark artifacts і одна source reference до відсутнього snapshot; відсутні докази не відновлювалися. SHA-256 незміненого `raw/B-12_Master_Project_2026-10-24.md` — `e2b0c4c33054082a4df48fed2785c834a95cfb7fb8f6a6e9198b6de53bd8e37a`, збігається з manifest.

Для цієї реалізації не запускали B-12 server, desktop app, модель, microphone capture, audio playback або GPU workload; pytest використовував API fixtures/fakes. Фізичні X11/Wayland, tray та живий model stream залишаються неперевіреними. Робоча гілка `feat/b12-desktop-companion` базується на `main` через merge-base `5f6ba905`; код ще не опубліковано.

## [2026-11-08] host-validation | Qt desktop на X11

На реальному `DISPLAY=:1` (`XDG_SESSION_TYPE=x11`, X.Org 21.1.11, `eDP-1` 2560×1600) окремо запущено лише `b12 desktop` із тимчасовими `B12_STATE_DIR`/`XDG_CONFIG_HOME`, фіктивним owner token і test URL `127.0.0.1:18712`, де listener не було. `xwininfo` підтвердив viewable overlay 244×272, depth 32, TrueColor; Qt повернув tray availability `true`. Процес автоматично завершився через 55 секунд (timeout exit 124); після завершення вікна/процесу немає. Перевірка не відкривала діалог чату й не передавала аудіо. Звичайний `$HOME/.config/B-12/NeonCompanion.conf` відсутній; усе тестове зберігалось під `/tmp/b12-desktop-host-review`. Живий server/model/mic/audio/GPU не запускали, наявний Ollama не чіпали.

**Межа host evidence:** CUA повернув порожній native app inventory (`apps: []`), тому screenshot compositor, реальну видимість tray icon, click/drag та stacking над іншими вікнами не підтверджено. `QSystemTrayIcon.isSystemTrayAvailable()` — лише API availability, не доказ успішного користувацького tray UX.

## [2026-11-08] fix | Темний Qt approval viewport

Offscreen screenshot показав системно-білий порожній блок approvals. Діагностика Qt підтвердила причину: `QScrollArea.viewport()` і його `approval_host` мали `autoFillBackground=true` та системний `#efefef`; глобальний stylesheet не охоплював ці об’єкти. Новий pixel-level regression спочатку впав із `#efefef != #0a1020`, потім пройшов після явної темної теми для viewport/host. Повторний контрольний рендер має темну поверхню без білого блока; cybercat atlas і компонування збережені.

## [2026-11-08] lint | Desktop-компаньйон після візуального fix

Повний locked suite після pixel regression: **741 passed / 4 skipped за 152,62 с**. `ruff check src tests`, `uv lock --check`, `git diff --check`, `uv build` пройшли; wheel містить `b12/desktop/chat.py`, `b12/desktop/cat.py` і B-12 cybercat atlas. `B12_REAL_MODEL` не вмикався.

Wiki audit: 44 сторінки, 358 локальних Markdown-посилань, 0 битих якорів, 0 неіндексованих сторінок. Залишились 11 відомих відсутніх historical benchmark artifact links та одна відсутня source snapshot reference; нових битих посилань цей fix не додав. SHA-256 master brief лишився `e2b0c4c33054082a4df48fed2785c834a95cfb7fb8f6a6e9198b6de53bd8e37a` і збігається з manifest.

**Межі:** X11 smoke перевірив лише map/ARGB metadata та Qt tray availability. Чату не надсилали prompt; live B-12 API/model, мікрофон/audio playback, GPU, tray click, mouse drag і screenshot композитора не перевіряли. Інтерактивний host acceptance та Wayland лишаються відкритими.

## [2026-11-08] correction | Stacked desktop branch

Перевірка `git log --graph --all` уточнила попередню примітку про ancestry: merge-base з `main` — `5f6ba90`, але прямий parent `feat/b12-desktop-companion` — runtime PR head `3e7fb07`. Desktop гілка містить зміни PR #1 разом із трьома власними desktop commits. Це навмисна залежність від runtime API/context роботи; desktop PR слід відкрити поверх `feat/b12-runtime`, щоб не дублювати runtime diff відносно `main`.

## [2026-11-08] review-fix | Approval pose під час offline/reconnect

Незалежний rereview виявив: offline notification змінював `approval` на `error`, але зберігав `_last_approval_ids`; після reconnect незмінний pending ID тому не повертав коту approval pose. Regression спершу впав саме на `error != approval`; fix зберігає approval phase поки API недоступний. Після reconnect із тим самим operation ID pose лишається approval, а після очищення server queue normal poll повертає кота до idle. Цільові app tests: 6 passed; повний suite треба оновити.

## [2026-11-08] lint | Desktop companion final verification

Повний locked suite після обох follow-up fixes: **742 passed / 4 skipped за 151,69 с**. `ruff check src tests`, `uv lock --check`, `git diff --check`, `uv build` пройшли. Wheel містить desktop chat/cat modules і B-12 cybercat atlas. Чотири skipped потребують явного `B12_REAL_MODEL=1`.

Wiki audit: 44 сторінки, 358 локальних посилань, 0 битих якорів, 0 сторінок поза index. Лишилися 11 історичних links на відсутні benchmark artifacts та одна відсутня source snapshot path; нові сторінки/зміни не створили цих gaps. Master brief SHA-256 незмінний: `e2b0c4c33054082a4df48fed2785c834a95cfb7fb8f6a6e9198b6de53bd8e37a`, збігається з manifest.

Desktop X11 smoke був ізольований через тимчасові state/config і dummy token, без API listener. B-12 server/model, microphone, audio playback і GPU не запускались. Поточна desktop гілка стоїть поверх runtime PR #1 (`feat/b12-runtime` на `3e7fb07`); окремий desktop PR має target цього branch до злиття PR #1.
