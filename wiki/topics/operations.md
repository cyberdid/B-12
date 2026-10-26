---
type: topic
updated: 2026-10-26
status: partially_implemented
sources: [src/b12/service.py, src/b12/telemetry.py, deploy/b12.service, scripts/install-user-service.sh, scripts/soak.py, scripts/load_memory.py, scripts/daily_check.py, tests/e2e/test_recovery.py, tests/performance/test_growth.py]
tags: [operations, backup, restore, soak, growth, long-horizon]
---
# Експлуатація: snapshots, restore, soak, ріст

## Snapshots і відновлення

**Перевірений факт:** `Operations` робить узгоджені SQLite-знімки (online backup API) із SHA-256 manifest та інвентарем. Токен API, логи й lock-файли не копіюються. Кожен глобальний purge спершу дописує payload-free запис у durable deletion ledger, потім застосовується всередині кожного керованого snapshot (purge store `snapshots`, manifest запечатується заново). `restore` тримає runtime lock, перевіряє manifest і `integrity_check`, робить pre-restore snapshot і відтворює ledger до того, як стан починає відповідати. Підроблений snapshot відхиляється. Невдала міграція відкочується відновленням snapshot. **Межа:** зовнішні копії та FS-snapshots поза керованим інвентарем не охоплені.

## Процес і сервіс

**Перевірений факт:** `b12 serve` тримає ексклюзивний runtime lock (другий сервер на тому самому state не стартує), пише rotating-логи, де форматер відкидає тексти винятків, і має обмежене graceful-завершення: відкриті стріми скасовуються, turn і дочірні process groups зупиняються. Після SIGKILL дочірній `shell_exec` помирає разом із сервером (PDEATHSIG), стан зберігає цілісність, а операції в стані `started` стають `unknown`. `/api/status` і `b12 status` дають uptime, затримки P50/P95, RSS, pending purges, розміри сховищ. Юніт `deploy/b12.service` рендериться інсталером без root і без автозапуску. **Відкрите:** справжнє `systemctl --user enable --now` класифікатор дозволів заблокував як постійну зміну системи — це робить власник.

## Soak і ріст (Task 15 — не завершено)

**Перевірений факт:** soak 26.10.2026 тривав 1 год 19 хв із запланованих 8 год і був зупинений за проханням власника. За цей час знайдено й виправлено:

| Дефект | Доказ | Виправлення |
|---|---|---|
| Кожна транзакція пам'яті перевіряла весь audit-ланцюжок | затримка turn P50 159 мс → 5.4 с за ~45 хв | інкрементальна перевірка від курсора; повна — при відкритті та коли `data_version` показує чужий commit |
| `recent()` брав усі рядки й різав у Python | 4.1 с на 200k записів | фільтр і LIMIT у SQL |
| Per-turn стан у `ControlStore._runtime` не звільнявся | 900 Event/deque після 900 turn | `release_turn` у `finally` |
| FTS5 secure-delete для швидшого purge | `integrity_check`: malformed inverted index (мінімальне відтворення на SQLite 3.45.1) | відкат, ремонт при відкритті, регресійний тест |

Purge залишається O(store) через повний FTS rebuild (~1 с на 200k) — свідомий компроміс заради фізичного стирання. Решта росту RSS (~7 МБ/хв у першому soak) — фрагментація arena glibc: `MALLOC_ARENA_MAX=2` дає 111 → 125 МБ за 2500 turn проти 108 → 153 МБ; налаштування внесено в юніт і soak. Growth-бенчмарк 200 → 200k записів — `artifacts/task15-growth-2026-10-26.json` (до виправлення `recent`); [графіки в README](../../README.md).

**Пауза 27.10.2026 00:06 EET (за проханням власника):** повний 8-годинний soak (старт 26.10 21:00 EET, seed 21) відпрацював 3 год 06 хв (11149 с активного часу), 7 циклів воркера, 7/7 перевірок `ok`, 36 забутих маркерів відсутні в байтах стану. Лишилось 17651 с (4 год 54 хв). Драйвер дістав чисту паузу за SIGTERM/SIGINT і `--resume`, що рахує накопичений активний час; фінальна подія вказує кількість сегментів і `continuous: false`, тому сегментований прогін не видається за безперервний. Перевірено на короткому прогоні (62 с + 46 с). Артефакти (локальні, поза git) не видаляти.

## Довгий горизонт (Task 19)

**Перевірений факт:** `scripts/daily_check.py seed|check` записує датовані якорі з відомою відповіддю, забуває один і щодня перевіряє recall, відсутність забутого маркера в байтах стану, цілісність, snapshots і повний audit. День 0 перевірено на тестовому стані. **Не доведено:** реальні день 1/7/30 на живому стані власника — потрібен справжній час і таймер, який встановлює власник.

Див. [agent loop і забуття](agent-loop.md), [стан](../project/status.md).
