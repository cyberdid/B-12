# Task 6 — scoped fix rereview (fix rounds 1–2)

Reviewer: coordinator (Claude Opus 5.5, Claude Code), продовження сесії після usage-limit Codex 26.10.2026.
Це **не** незалежний окремий агент: review виконано тим самим coordinator, що комітив fix round 2. Межу зафіксовано явно.

FIX ranges: `012f248..f0f8ea2` (I1), `f0f8ea2..7d7809e` (I2/M1). Package: `task-6-fix-review.diff`, `task-6-fix2-review.diff`.

## Findings status

- **I1 — ADDRESSED** (`f0f8ea2`). Resolver result валідовано як exact non-negative int до `remember`; None/bool/negative/float/string/exception → `failed/coordinator_unavailable`, без запису. 7 RED → GREEN regression на реальному MemoryStore.
- **I2 — ADDRESSED** (`7d7809e`). `capture`: fsync copy FD → fsync pinned `objects/` dirfd → `ready`; при помилці directory sync рядок лишається `deleting`, target не встановлюється (`os.replace` іде після `capture`). Purge/cleanup: спершу durable `deleting`, потім unlink через pinned dirfd, fsync каталогу, лише тоді `DELETE`/`complete`; помилка sync → `pending`, переживає reopen. Staging purge відкриває parent як fd і звіряє `(st_dev, st_ino)` перед unlink; parent swap не видаляє чужий sentinel. Тести: ordering observer, failed objects-dir sync, purge sync failure across reopen, staging purge/cleanup sync failure, pinned-parent swap.
- **M1 — ADDRESSED** (`7d7809e`). Каталог на depth cap дає `truncated=True`; regression depth 9.

## New issues

- Critical/Important: не виявлено.
- Observation (не блокує): staging-рядок, батьківський каталог якого видалено поза B-12, лишається `pending` при кожному purge (поведінка існувала до fix). Task7/13 purge coordinator має показувати такі receipts як pending із причиною, а не мовчки ретраїти.
- Observation: `BackupStore.close()` після часткової невдачі `__init__` може дати `AttributeError` (`_objects_fd` ще не встановлено). Косметичне.

## Verification (coordinator, exact HEAD 7d7809e)

`uv run --no-sync pytest -q` → **318 passed, 1 skipped in 9.37s**; `ruff check src tests` → All checks passed; `git diff --check` → clean. Тести — лише temp/local fixtures.

**Spec: PASS. Quality: Approved (coordinator rereview).** Task 6 gate закрито; Task 7 може стартувати.
