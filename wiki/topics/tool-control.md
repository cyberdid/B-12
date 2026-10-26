---
type: topic
updated: 2026-10-26
status: compiled
sources: [docs/superpowers/specs/2026-10-24-b12-system-design.md, src/b12/control.py, src/b12/tools/registry.py, src/b12/tools/outcomes.py, src/b12/tools/filesystem.py, src/b12/tools/process.py, src/b12/tools/network.py, src/b12/tools/memory.py, tests/security/test_tool_policy.py, tests/unit/test_registry.py, tests/integration/test_host_tools.py, tests/security/test_host_boundaries.py]
tags: [tools, control, approval, provenance]
---
# Контроль і результати інструментів

## Межа дозволів

**Перевірений факт:** `ControlStore` — довірений серверний шлях для actor/session/task/turn identity та grants. `Actor` DTO і поля запиту самі собою не дають дозволу. Незмінний `ExecutionContext` посилається на виданий control credential; перед dispatch та побічним ефектом перевіряються точні прив’язки, consent, revision, grant expiry/revocation, capability, cancellation і monotonic deadline.

**Перевірений факт:** tool registry приймає strict typed arguments і handler-и з trusted catalog. Model arguments не можуть задавати approval, actor/grant або operation identity. `Risk.ARBITRARY` вимагає task-scoped full-execution grant або exact one-shot approval; argv не є sandbox, а blacklist не гарантує безпеку. Для зовнішніх повідомлень чи публікацій потрібен окремий capability.

Approval атомарно прив’язаний до actor/session/turn/call, digest аргументів, capability, revision та expiry. Виконання має persistent lifecycle. Прострочене approval переводить незавершену операцію в `failed/approval_expired`, очищує приватний digest і додає payload-free audit event в одній транзакції. Після можливого ефекту timeout/cancel/restart дає `unknown`; автоматичного повтору немає.

## Контракт результату для host tools

**Перевірений факт:** handlers повертають `b12.tools.outcomes.HandlerOutcome`; registry повторно валідує snapshot після `await` і сам задає call/name IDs, duration та operation provenance. Фінальна серіалізована відповідь обмежена 64 KiB JSON; handler також має обмежувати buffers під час читання/збору.

| Статус | Значення |
|---|---|
| `completed` | Ефект(и) підтверджено; помилки немає |
| `failed` | Trusted handler засвідчує, що жодного ефекту не відбулося; `side_effects` порожній |
| `unknown` | Ефект міг відбутися частково або результат невідомий; зберігається лише bounded content/evidence |

`SideEffect` має фіксований `kind`, стан `completed|possible` та UUID evidence/artifact references. Шляхи, stdout, секрети й display names не записуються в lifecycle/audit. При timeout або cancellation handler може завершити прибирання вже запущених ресурсів і повернути `unknown`; це не дозволяє запускати нові дії чи перетворює запізнілий результат на успіх.

## Реальні host tools (Task 6)

**Перевірений факт:** commits `012f248`, `f0f8ea2`, `7d7809e` реєструють 13 tools: `current_time`, `system_info`, `process_list`, `file_list`, `file_read`, `file_search`, `file_write`, `shell_exec`, `http_fetch`, `memory_search`, `memory_store`, `memory_forget`, `knowledge_search`. Усі проходять Task 5 registry зі strict schemas і capabilities; `shell_exec` — `Risk.ARBITRARY`, `memory_forget` — `Risk.DESTRUCTIVE` через injected coordinator. Full suite на `7d7809e`: 318 passed / 1 skipped.

- **Файли:** pinned parent dirfd, відмова для leaf symlink/non-regular target, новий inode з mode/owner/xattrs/POSIX ACL до install. Overwrite спершу робить приватну managed backup copy: fsync copy → fsync `objects/` → стан `ready` → `os.replace` → fsync parent. Purge/cleanup durably фіксує `deleting` до unlink і підтверджує `complete` лише після fsync каталогу; інакше `pending`, що переживає restart. `file_search` має depth cap 8 і позначає неповне охоплення `truncated`.
- **Процеси:** argv без shell-інтерпретації; stdout/stderr дренуються паралельно з bounded prefixes; timeout/cancel — TERM→KILL усієї process group, перевірено на child/grandchild. `setsid`-escape не є sandbox guarantee.
- **HTTP:** без proxy/auth з environment, без redirects, ліміт на raw wire bytes; `Content-Encoding` повертається окремо.
- **Memory:** `memory_store` вимагає exact non-negative int deletion revision від trusted resolver; None/невалідне/виняток → `coordinator_unavailable` без запису (закриває stale-turn resurrection).

Review: перший незалежний review знайшов I1 (resolver None), I2 (directory durability ordering), M1 (depth truncation); scoped rereview `task-6-rereview.md` — усі ADDRESSED. Rereview виконав coordinator, а не окремий агент; межа зафіксована в артефакті.

## API і автентифікація

**Перевірений факт:** Task 9 (`9632cdc`) відкриває host tools через API лише після автентифікації. Owner bearer token лежить у `state_dir/api/owner.token` (0600); ControlStore зберігає тільки HMAC digest. Токен приймається лише з заголовка, не з URL. Гостьові токени видає owner, з typed capabilities без filesystem/process/network/forget і без full execution. Guard відхиляє чужий Host (DNS rebinding), чужий Origin для змін стану і тіла понад 64 KiB. Поля actor/consent/grant у тілі дають 422. Розрив NDJSON-стріму скасовує turn. Не реалізовано: TLS (лише loopback), rate limiting, UI.

## Межі та наступний крок

Реальні effects перевірено лише на temp/local fixtures; production файли користувача не змінювались. **Не реалізовано:** global `PurgeCoordinator` і original-revision lookup (Task 7), agent/session loop (Task 7), загальний service backup (Task 13). Blocking OS/Python I/O не має hard preemption. Staging, батьківський каталог якого видалено поза B-12, лишається `pending` — coordinator має показувати причину. Код і тести не доводять 24/7 або physical hardware acceptance.

Див. [план усієї реалізації](../project/implementation.md), [стан](../project/status.md), [пам’ять і приватність](memory.md) та [архітектуру](architecture.md).
