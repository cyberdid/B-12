---
type: index
updated: 2026-10-24
status: active
sources: [wiki/sources/master-brief.md, wiki/sources/llm-wiki.md]
tags: [navigation]
---
# Індекс знань B-12

Спочатку [стан робіт](project/status.md), далі [аналіз](project/analysis.md) і потрібна тема. Позначки достовірності визначені в [AGENTS.md](../AGENTS.md). `compiled` означає опрацьовану документацію.

## Проєкт

| Сторінка | Призначення |
|---|---|
| [Поточний статус](project/status.md) | Що є локально, чого ще немає, наступна дія |
| [Реалізація повної системи](project/implementation.md) | Авторизований scope, повний plan/spec, worktree та execution ledger |
| [Готовність до тесту Bolt](project/model-test-readiness.md) | Перевірена система, tools, точний GGUF та план першого запуску |
| [Перший тест Bolt](project/bolt-first-test.md) | Власні latency/VRAM/поведінкові спостереження та ризик обрізання контексту |
| [Аналіз master brief](project/analysis.md) | Висновки, суперечності й пріоритети |
| [Дорожня карта](project/roadmap.md) | M0–M6, залежності й критерії завершення |
| [Реєстр рішень](project/decisions.md) | ADR-001–010 з оригінального brief та їхній статус |
| [Відкриті питання](project/open-questions.md) | Невідоме та спосіб отримати відповідь |

## Теми

| Сторінка | Призначення |
|---|---|
| [Задум і межі](topics/vision.md) | Партнерство, безперервність досвіду, UA/EN |
| [Архітектура](topics/architecture.md) | System 1/2, події, контроль дій |
| [Пам’ять і приватність](topics/memory.md) | Provenance, згода, retrieval, видалення |
| [archive-index для B-12](topics/archive-retrieval.md) | Повторне використання retrieval, окремий ledger, scope/cache/token boundaries |
| [Ініціатива й рефлексія](topics/autonomy.md) | Цілі, доречність втручання, self-model |
| [Голос](topics/voice.md) | Каскад, full-duplex, UA, метрики |
| [Моделі й benchmark](topics/models.md) | Кандидати, оцінювання, ризик TTFT |
| [Reachy і Jetson](topics/hardware.md) | Варіанти обладнання, transport і deployment |

## Джерела й облік

| Сторінка | Призначення |
|---|---|
| [Master brief](sources/master-brief.md) | Походження, контрольна сума, охоплення документа |
| [LLM Wiki](sources/llm-wiki.md) | Метод ведення й адаптація до проєкту |
| [Перевірка зовнішніх джерел](sources/external-checks.md) | Що прочитано незалежно, що залишилось неперевіреним |
| [Аудит локальної системи](sources/system-audit-2026-10-24.md) | Сирі докази hardware/tools та межі перевірки |
| [Докази запуску Bolt](sources/bolt-smoke-2026-10-24.md) | Походження 26 запитів, перевірка ваг, валідні та виключені вимірювання |
| [archive-index-public](sources/archive-index-public.md) | Pinned source review, 17 core tests і локальна інсталяція |
| [Native Ollama API](sources/runtime-api-docs.md) | Прочитані wire/streaming sections і межа щодо локального runtime |
| [Журнал](log.md) | Додавання матеріалів, висновки та перевірки |

Поза wiki: [оригінал](../raw/B-12_Master_Project_2026-10-24.md), [маніфест 116 URL](../raw/source-manifest.json), [README](../README.md), [правила агента](../AGENTS.md).
