---
type: topic
updated: 2026-10-26
status: compiled
sources: [docs/superpowers/specs/2026-10-24-b12-system-design.md, src/b12/control.py, src/b12/tools/registry.py, src/b12/tools/outcomes.py, tests/security/test_tool_policy.py, tests/unit/test_registry.py]
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

## Межі та наступний крок

Task 5 реалізував registry і серверний control layer, але **не** реальні OS handlers, API authentication або UI owner review. Task 6 має додати filesystem/process/network handlers, process-group cleanup, output bounds та реальні effects лише у temp/local fixtures. `memory_forget` чекає на global `PurgeCoordinator` Task 7; backup copies мають бути зареєстровані для purge. API authentication лишається Task 9. Код і тести не доводять 24/7 або physical hardware acceptance.

Див. [план усієї реалізації](../project/implementation.md), [стан](../project/status.md), [пам’ять і приватність](memory.md) та [архітектуру](architecture.md).
