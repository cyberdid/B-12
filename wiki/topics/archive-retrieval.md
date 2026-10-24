---
type: integration-proposal
updated: 2026-10-24
status: proposed_not_integrated
sources: [wiki/sources/archive-index-public.md, raw/archive-index-public-7ad80dcdc7e3/REVIEW.json]
tags: [retrieval, memory, integration]
---
# Повторне використання archive-index у B-12

**Висновок review:** можемо повторно використати готовий пошук, не починаючи retrieval layer з нуля. Це уточнює план текстового B-12; runtime integration ще не виконано. [Докази та pinned source](../sources/archive-index-public.md).

## Розподіл відповідальності

| Частина | Призначення |
|---|---|
| B-12 canonical memory | Дозволені події, speaker/consent, evidence IDs, lifecycle/forget і історія виправлень |
| archive-index | Перебудовуваний lexical/semantic індекс дозволеного змісту, provenance та пошук |
| B-12 retrieval adapter | Перевірка доступу, exact scope, свіжість, selection, token budget і формування evidence context |
| Bolt | Інтерпретація наданого контексту, відповідь або пропозиція дії |
| Runtime policy | Дозволи перед записом/дією; їх не встановлює відповідь моделі |

Пропонований потік: control/consent → дозволений canonical event → derived B-12 index → authorized retrieval → короткий evidence context → Bolt. Обидва SQLite сховища можуть бути окремими файлами; межі важливіші за вибір формату. Документаційна wiki проєкту залишається окремою від runtime пам’яті.

## Що використати спочатку

Почати з lexical retrieval без embedding GPU load. Система вже має потрібне середовище для перевірених core модулів. Source paths, locators і hashes придатні для посилань на докази; canonical event IDs слід передавати явно. Для semantic stage потрібен окремий joint benchmark з Bolt на 8GB VRAM.

Не направляти робота за замовчуванням у весь персональний archive DB. Для першого PoC — окрема B-12 DB і синтетичні або явно дозволені матеріали. Існування приватного документа в глобальному індексі не створює дозволу використовувати його у відповіді гостю.

## Виявлені інтеграційні нюанси

1. **Canonical/derived.** `replace_document`, chunk trimming і видалення джерел означають, що index не append-only ledger. Підстави збереження й deletion propagation залишаються обов’язком [memory policy](memory.md).
2. **Scope.** Публічний project filter використовує prefix (`startswith` / SQL `LIKE prefix%`). Для доступу до даних потрібен exact allowlist у довіреному шарі; цей фільтр призначений для пошуку, а не авторизації.
3. **Свіжість.** Synthetic probe підтвердив, що VectorCache не включає нові вектори без refresh. Постійний адаптер має invalidation після запису/видалення. У переглянутому MCP service cache створюється на час життя сервісу; автоматичного refresh у search path не виявлено.
4. **Ресурси.** `VectorCache` спочатку читає всі вектори в RAM, потім фільтрує. Default Embedder lazily обирає CUDA. У публічному MCP використано `Embedder()` напряму; CLI використовує `make_embedder()`, тому не припускати однакової обробки backend env settings. Local installed source відрізняється й потребує окремого review перед використанням.
5. **Релевантність.** Rank/score не є confidence факту; semantic top-k може містити слабкі збіги. Потрібні relevance/unknown tests і відповідь «не знаю» за недостатніх доказів.
6. **Контекст.** Кількість і довжина hits визначаються token budget, а не тільки `k`. [Перший Bolt test](../project/bolt-first-test.md) уже показав втрату instructions при переповненні 2048. Бюджет має врахувати system, tools, evidence, user і output.
7. **Read path.** MCP API відкриває search/stats, але `Store()` під час ініціалізації створює schema/migrations і встановлює WAL. Для обіцянки file-level read-only потрібен окремий режим; не запускати його конструктор на production DB лише для огляду.

## Перший інтеграційний тест — пропозиція

Створити окремий тестовий B-12 index з кількома дозволеними синтетичними подіями. Запит має повернути event ID/джерело, Bolt — відповідь із відповідним evidence. Після додавання/видалення події пошук відображає зміни; відсутню подію модель не вигадує; неавторизований запис не потрапляє ані до canonical store, ані до index. Перевірити exact scope й збереження instructions при короткому context budget.

Цей тест використовує вже перевірений model alias і відокремлює retrieval якість від personality prompt. [Наступний стан робіт](../project/status.md). Автобіографічна пам’ять, [ініціатива](autonomy.md) та consent enforcement не виникають автоматично від підключення archive MCP.
