---
type: log
updated: 2026-10-24
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
