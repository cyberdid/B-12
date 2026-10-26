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
