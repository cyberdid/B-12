# Task 2 — canonical persistent memory та забуття

Статус реалізації: **DONE**; незалежний spec/quality review виконує координатор окремо. Цей звіт не оголошує завершення загальної системи або R05.

- Дата завершення: 2026-10-25.
- Worktree: `/home/cyberdid/Projects/B-12/.worktrees/runtime`.
- Branch: `feat/b12-runtime`.
- BASE: `b16917b`.
- Виконавець завершення: `/root/task2_finish`; попередній handle після паузи недоступний.
- Наявний implementation збережено й перевірено, без повторної реалізації з нуля та без додаткових production змін під час завершення.
- Commit: `d18441c597adcabf1bc7d443daa2e7ebb5cf5cba` — `feat: add canonical memory and durable purge primitives`. Цей локальний SDD report ігнорується Git відповідно до `.gitignore`.

## Артефакти та поведінка

Commit охоплює лише `src/b12/contracts.py`, нові `src/b12/memory.py`, `src/b12/migrations.py`, `tests/unit/test_memory.py`, `tests/integration/test_memory_restart.py`, `tests/security/test_memory_isolation.py`.

**Перевірений факт:** `MemoryStore` реалізує всі методи Task 2: `remember`, `search`, `forget`, `audit_events`, `close`, `deletion_revision`, `begin_purge`, `acknowledge_purge`, `pending_purges`, `resume_purges`. `PurgeReceipt` — strict DTO з `schema_version=1`, UUID operation/target IDs, перевіреними state, pending stores та optional error code.

- `actor.id` є exact namespace; `owner` є роллю й не змінює namespace. Запис і пошук без `consent=True` заборонено також для owner. Actor надходить із довіреного контрольного шляху; authentication не реалізовується цим storage task.
- SQLite schema v1: payload, впорядковані evidence links, FTS5, per-actor deletion revision, purge outbox, store states, tombstones, payload-free append-only hash-chain audit і persisted head.
- Дозволена пам'ять зберігає text/source/ID/UTC timestamp після close/reopen; evidence може посилатися лише на live memory того самого actor. SQL параметризований, FTS query складається лише з literal Unicode alphanumeric terms.
- Нові state directories створюються з mode `0700`, database/sidecars мають `0600`; permissions уже наявних unrelated parent directories не змінюються. Future schema відхиляється до PRAGMA/schema/permission mutation.
- Purge спочатку окремо commit-ить payload-free closure/outbox, tombstones і revision. Відтак payload негайно недоступний через API, навіть якщо наступне фізичне видалення завершується SQL error. Closure охоплює transitive derived memories, зберігаючи unrelated parent/evidence.
- Cleanup видаляє payload/evidence, перебудовує FTS5, використовує `secure_delete` та WAL `TRUNCATE` checkpoint. Canonical complete встановлюється лише після успішного checkpoint; held WAL reader залишає pending. Реальний failing-delete trigger дає durable failed receipt без SQL exception text у persistent metadata.
- Pending/failed operations та IDs/revision переживають restart. `resume_purges` повторює canonical cleanup, а external stores завершуються лише через actor-scoped idempotent acknowledgements. Існуючу operation не можна мовчки доповнити новими store obligations.
- `expected_deletion_revision` перевіряється під write transaction; stale asynchronous writer відхиляється без запису його payload чи audit text. Незалежні SQLite connections/threads перевіряють serialization.
- Audit не містить text/source/path/arguments. SQL triggers забороняють update/delete; hash chain і persisted head виявляють зміну event та видалення tail. Corruption дає explicit failure під час роботи й reopen.

## TDD: походження доказів

**Історичне повідомлення попереднього виконавця, не повторно спостережений RED:** координатор передав, що початкові 17 tests були RED через відсутні `MemoryStore`/`PurgeReceipt`, потім GREEN. Далі повідомлено RED/GREEN для idempotent `forget` після `begin_purge`, а також перевірку реального SQLite failing-delete trigger: durable failed receipt, payload hidden by tombstones, cleanup після restart. У попередньому повідомленні наведено full suite `116 passed` (94 foundation + 22 memory). Сирого RED output у доступному task report не було; не приписуємо ці запуски поточному виконавцю й не відтворюємо RED шляхом видалення успадкованої реалізації.

**Перевірено поточним виконавцем:** у наявному стані Task 2 має 23 test cases, full suite — 117. Нових production змін або regressions під час завершення не додавалося, тому нового RED/GREEN циклу в цій фазі немає. Відмінність попереднього числа 22 від фактичного 23 зафіксована явно, без припущення про невідомий запуск.

## Свіжі команди перевірки

Середовище: CPython `3.12.3`, SQLite `3.45.1`, наявна `.venv` symlink; cache використовується поза repo. Усі наведені команди виконані поточним виконавцем на незміненому після них Task 2 code.

```bash
UV_CACHE_DIR=/home/cyberdid/Downloads/B-12-runtime/uv-cache uv run --no-sync pytest tests/unit/test_memory.py tests/integration/test_memory_restart.py tests/security/test_memory_isolation.py -q
```

Exit 0: **23 passed in 0.37s**.

```bash
UV_CACHE_DIR=/home/cyberdid/Downloads/B-12-runtime/uv-cache uv run --no-sync pytest -q
```

Exit 0: **117 passed in 0.37s** (94 foundation + 23 Task 2).

```bash
UV_CACHE_DIR=/home/cyberdid/Downloads/B-12-runtime/uv-cache uv run --no-sync ruff check src tests
git diff --check
git diff --cached --check
```

Exit 0 для кожної команди: `All checks passed!`; whitespace checks без output. Окремо focused Ruff для шести Task 2 paths також завершився exit 0.

## Self-review та межі

Self-review зіставив exact brief, public methods, SQL transactions, outbox/closure durability, actor scope, no-consent, WAL busy behavior, physical bytes/FTS cleanup, audit corruption і staged diff. У межах Task 2 невирішених дефектів не виявлено. Це self-review, не незалежний review.

Файлові та SQL тести працюють лише з synthetic temporary SQLite databases. Вони перевіряють durable bytes локальних DB/WAL/SHM files, реальні queries/vocabulary та independent connections/threads. Production data, GPU/model, зовнішній archive, аудіо, біометрія, historical `raw/` і unrelated filesystem permissions не змінювалися.

`forget` bool означає новостворений локальний canonical purge, а не глобальний receipt: `False` для невідомого/вже tombstoned запису. Для фізичного стану, pending/failed retries і external obligations слід використовувати `PurgeReceipt`. Begin/forget після наявної tombstone є idempotent; відновлення canonical cleanup виконує explicit `resume_purges`.

Global R05 coordinator для knowledge/sessions/goals/backups/active turns залишається downstream Tasks 7/9/13. `resume_purges` не виконує й не підтверджує external hooks. Revoked-consent actor може керувати видаленням і payload-free metadata; це не відкриває `remember`/`search` без згоди.

Audit є tamper-evident щодо наявного ledger/head та SQL append-only rules; це не зовнішньо підписаний або незалежно anchored ledger проти повного переписування DB власником filesystem. Physical cleanup tests не доводять стирання snapshots/backups, SSD remanence чи copies поза managed SQLite. Power-loss/OS-kill fault injection і великі latency/soak benchmarks не виконувались і не оголошені готовими.

Coordinator wiki зміни залишено поза staged Task 2 commit. Цей task не переходив до downstream implementation.
