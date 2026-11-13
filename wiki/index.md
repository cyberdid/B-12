---
type: index
updated: 2026-11-12
status: active
sources: [wiki/sources/master-brief.md, wiki/sources/llm-wiki.md]
tags: [navigation]
---
# Індекс знань Capri / B-12 runtime

Спочатку [стан робіт](project/status.md), далі [аналіз](project/analysis.md) і потрібна тема. Позначки достовірності визначені в [AGENTS.md](../AGENTS.md). `compiled` означає опрацьовану документацію.

## Проєкт

| Сторінка | Призначення |
|---|---|
| [Поточний статус](project/status.md) | Що є локально, чого ще немає, наступна дія |
| [План desktop-компаньйона](project/desktop-companion-plan.md) | Загальний стан Qt companion, його scope і host acceptance |
| [Capri feature parity](../docs/superpowers/plans/2026-11-08-b12-capri-feature-parity.md) | Повний capability audit Capri Desktop і план незалежної реалізації у B-12 |
| [Capri persona та brand](../docs/superpowers/plans/2026-11-08-capri-persona-brand.md) | Базовий характер Capri, desktop profile context і межа сумісності `b12` |
| [Реалізація повної системи](project/implementation.md) | Авторизований scope, повний plan/spec, worktree та execution ledger |
| [План тестування](project/test-plan.md) | Рівні перевірки для CLI/TUI, агента, моделі та релізу |
| [Готовність до тесту Bolt](project/model-test-readiness.md) | Перевірена система, tools, точний GGUF та план першого запуску |
| [Перший тест Bolt](project/bolt-first-test.md) | Власні latency/VRAM/поведінкові спостереження та ризик обрізання контексту |
| [Комплексна оцінка Capri, 12.11.2026](project/capri-comprehensive-evaluation.md) | 92 сценарії через рантайм на злитому `main`: 48 пройдено, 32 провалено, 12 заблоковано обладнанням (60,0%); gemma — 43/80; класифікація «гібридна модель-центрична система», не повний компаньйон |
| [Звіт про роботу, 10–11.11.2026](project/work-report-2026-11-11.md) | Що зроблено в оцінці Capri, довгостроковій пам'яті й git; відкриті питання; PDF-версія |
| [Звіт про роботу, 12.11.2026](project/work-report-2026-11-12.md) | Оцінка через рантайм (47/80), закрита дірка з мережевими командами, пріоритети цілей, PR готові до злиття; PDF |
| [Аналіз master brief](project/analysis.md) | Висновки, суперечності й пріоритети |
| [Дорожня карта](project/roadmap.md) | M0–M6, залежності й критерії завершення |
| [Аудит вимог R01–R17](project/requirements-audit.md) | Статус кожної вимоги з доказами й межами; відкриті рішення |
| [Подібні проєкти та моделі, 28.10.2026](sources/ai-assistant-projects-2026-10-28.md) | Перевірений огляд коду й UI конкурентів, що переносимо, і даних про Nemotron Bolt E4B |
| [Самоогляд меж безпеки](project/security-self-review.md) | Знахідки F1–F5 за читанням API, control, purge; не незалежний |
| [Реєстр рішень](project/decisions.md) | ADR-001–010 з оригінального brief, ADR-011–014 для desktop-компаньйона, Capri та стилю |
| [Відкриті питання](project/open-questions.md) | Невідоме та спосіб отримати відповідь |

## Теми

| Сторінка | Призначення |
|---|---|
| [Задум і межі](topics/vision.md) | Партнерство, безперервність досвіду, UA/EN |
| [Архітектура](topics/architecture.md) | System 1/2, події, контроль дій |
| [Пам’ять і приватність](topics/memory.md) | Provenance, згода, retrieval, видалення |
| [archive-index для B-12](topics/archive-retrieval.md) | Повторне використання retrieval, окремий ledger, scope/cache/token boundaries |
| [Ініціатива й рефлексія](topics/autonomy.md) | Цілі, доречність втручання, self-model |
| [Порівняння з NVIDIA Reachy Jetson](topics/reachy-jetson-comparison.md) | Їхній голос і зір, наш контроль дій і пам'ять; ризики й розбіжності у джерелах |
| [CLI і запущений сервер](topics/cli-server-mode.md) | Один власник runtime: API при запущеному сервері, лок без нього; зіставлення команд і ендпоінтів |
| [Кіберпанковий TUI та кіберкіт](topics/cyberpunk-tui.md) | Анімований companion, local activity/hooks, task reports, explicit voice та опційні зовнішні skins |
| [Desktop-компаньйон](topics/desktop-companion.md) | Qt Capri/Кіберкіт, компактний чат, інтеграції агентів, локальні дії й функціональні межі |
| [Модель доказів (A-10)](topics/evidence-model.md) | Спогади з посиланням на документи, міграція v1→v2 з резервною копією, застарілість і життєвий цикл |
| [Голос](topics/voice.md) | Каскад, full-duplex, UA, метрики |
| [Admission і model transport](topics/model-transport.md) | Immutable budget, pinned profile, streaming, cancellation і real calibration |
| [Контроль і результати інструментів](topics/tool-control.md) | Server-owned grants, exact approval, lifecycle, bounded effects і unknown outcomes |
| [NVIDIA AI Factory Operations Agent](topics/nvidia-ai-factory-operations-agent.md) | Порівняння кластерного operations агента з local-first архітектурою B-12 |
| [Agent loop і глобальне забуття](topics/agent-loop.md) | Model→tools→results, events, sessions/provenance, PurgeCoordinator, реальний Bolt |
| [Експлуатація: snapshots, soak, ріст](topics/operations.md) | Backup/restore, deletion replay, сервіс, знайдені деградації, long-horizon драйвер |
| [Eval: корпус і результати](topics/evals.md) | 109 сценаріїв, runner, результати Bolt і знайдені дефекти |
| [Моделі й benchmark](topics/models.md) | Кандидати, оцінювання, ризик TTFT |
| [Reachy і Jetson](topics/hardware.md) | Варіанти обладнання, transport і deployment |

## Джерела й облік

| Сторінка | Призначення |
|---|---|
| [Огляд Capri-подібних desktop companions](sources/capri-desktop-companions-2026-11-07.md) | Чотири pinned репозиторії, придатні ідеї та ліцензійні межі |
| [Lifecycle hooks для coding agents](sources/agent-hooks-2026-11-08.md) | Офіційні hooks Claude Code, Codex та Antigravity; schema boundaries і межі інтеграції |
| [Master brief](sources/master-brief.md) | Походження, контрольна сума, охоплення документа |
| [LLM Wiki](sources/llm-wiki.md) | Метод ведення й адаптація до проєкту |
| [Перевірка зовнішніх джерел](sources/external-checks.md) | Що прочитано незалежно, що залишилось неперевіреним |
| [Аудит локальної системи](sources/system-audit-2026-10-24.md) | Сирі докази hardware/tools та межі перевірки |
| [Докази запуску Bolt](sources/bolt-smoke-2026-10-24.md) | Походження 26 запитів, перевірка ваг, валідні та виключені вимірювання |
| [archive-index-public](sources/archive-index-public.md) | Pinned source review, 17 core tests і локальна інсталяція |
| [Стаття власника про archive-index](sources/archive-index-paper.md) | Першоджерело бенчмарків пошуку/EmbeddingGemma 2; B-12 посилається, не переміряє |
| [Native Ollama API](sources/runtime-api-docs.md) | Прочитані wire/streaming sections і межа щодо локального runtime |
| [Оригінальна обкладинка Capri](sources/capri-original-hero-2026-11-08.md) | Походження hero/social preview, prompt і межі використання локального art pack |
| [NVIDIA agent frameworks](sources/nvidia-agent-frameworks-2026-11-06.md) | Перевірений статус NeMo Agent Toolkit та локальна оцінка Helix для B-12 |
| [Capri / Capricorn desktop-компаньйони](sources/capri-desktop-companions-2026-11-07.md) | Чотири задані repositories й окремий Linux art fork, Qt UX та межі ліцензії |
| [Особистість і самосприйняття Capri](sources/capri-personality-review-2026-11-08.md) | Вимога власника, відмінність канону від fan-made personality prompts і межі імерсивної ідентичності |
| [Scribe і двомовний препринт](sources/scribe-paper-2026-11-08.md) | Джерело редактора, версія й межі рукописів B-12 / Capri |
| [Capri запущено на Gemma 12B](sources/gemma12b-desktop-launch-2026-11-09.md) | Постійна конфігурація, API/Qt startup, тестова відповідь і виміряний CPU/GPU offload |
| [Gemma 12B: експериментальний етап](sources/gemma12b-followup-2026-11-09.md) | 8 exact counts, 12 вибраних task runs і порівняння чотирьох префіксів на CPU |
| [Академічне оформлення Capri](sources/capri-academic-formatting-2026-11-09.md) | Чотири локальні PDF, авторський шаблон A4/CMU, прописані норми та виправлення верстки |
| [Наукова редакція Capri, 09.11](sources/capri-scientific-revision-2026-11-09.md) | RQ, матриця доказів, нові CPU-перевірки та межі відтворюваності |
| [Суміжні джерела препринту](sources/preprint-related-work-2026-11-08.md) | Перевірені abstracts, DOI та межі використання результатів інших робіт |
| [Оригінальна обкладинка Capri](sources/capri-original-hero-2026-11-08.md) | Походження hero/social preview, prompt і межі використання локального art pack |
| [NVIDIA AI Factory Operations Agent](sources/nvidia-ai-factory-operations-agent-2026-11-07.md) | Вибірковий code/docs огляд кластерного operations blueprint і його меж для B-12 |
| [Claude password-policy baseline](sources/claude-password-policy-baseline-2026-11-04.md) | Десять неперевірених категорій із попереднього review; використані лише для оцінки охоплення B-12 |
| [Журнал](log.md) | Додавання матеріалів, висновки та перевірки |

Поза wiki: [оригінал](../raw/B-12_Master_Project_2026-10-24.md), [маніфест 128 зовнішніх джерел](../raw/source-manifest.json), [README](../README.md), [правила агента](../AGENTS.md).
