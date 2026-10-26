---
type: execution
updated: 2026-10-26
status: active
sources: [docs/superpowers/specs/2026-10-24-b12-system-design.md, docs/superpowers/plans/2026-10-24-b12-full-system.md]
tags: [implementation, plan, acceptance]
---
# Реалізація повної системи B-12

Власник прямо доручив: великий план → реалізація → звичайні й великі тести → реальні tool calls; надано дозвіл на повний доступ до системи для цієї роботи. Самого початку реалізації повторно погоджувати не потрібно.

- [Специфікація](../../docs/superpowers/specs/2026-10-24-b12-system-design.md) — архітектура та 17 acceptance requirements R01–R17.
- [Повний implementation plan](../../docs/superpowers/plans/2026-10-24-b12-full-system.md) — 20 завдань, interfaces, files, RED/GREEN/review gates і великі перевірки.
- Розробка виконується в ізольованому worktree `.worktrees/runtime`, branch `feat/b12-runtime`; дослідницький baseline залишається на `main`.
- Task progress ledger: `.worktrees/runtime/.superpowers/sdd/2026-10-24-b12-full-system/progress.md`; фактичний шлях підтверджується output `sdd-workspace` і `git worktree list`.

Поточна послідовність: contracts/config/package → canonical memory → retrieval → model/context → tools → agent loop → CLI/API/Web → autonomy/MCP/service → великі evals/soak → voice/duplex → hardware/long-horizon evidence.

## Перевірений checkpoint

**Перевірений факт:** Task 1 реалізовано в `4cf5e79`, URL edge cases виправлено в `4c455b5`; незалежні spec/quality review пройдені, coordinator повторив 94 passing tests. Є package `b12`, strict versioned contracts і перевірювані Settings. Це foundation, не готовий agent.

**Перевірений факт:** Task 2 canonical memory збережено в `d18441c`; незалежні spec/quality review пройдені, coordinator повторив 117 tests і Ruff без помилок. Є consent/actor isolation, restart, transitive forget, tombstones/outbox, deletion revision, payload-free audit і checkpoint-aware receipts. Локальний `forget` не означає global R05: coordinator та hooks для sessions/goals/backups ще попереду.

**Перевірений факт:** Task 3 (`e33b926`) реалізує lexical derived retrieval із pinned archive components, окремими actor stores та revision-aware UUID evidence. 15 нових integration tests, full suite 132 passed, independent review пройдено; wheel містить exact upstream modules та LICENSE/NOTICE. Update/delete мають durable invalidation receipts і чесний pending/failed cleanup. [Подробиці й межі](../topics/archive-retrieval.md).

**Перевірений факт:** Task 4 завершено після fix review: commit `46b374c`, run4 із 15/15 реальними Bolt-запитами, full suite 208 passed / 1 real-model skip, fix re-review пройдено. Snapshot validation тепер спільна для builder і send; callbacks awaitable-only; malformed terminal дає typed error. [Докази та обмеження](../topics/model-transport.md).

**Перевірений факт:** Task 5 пройшов fix re-review (`task-5-rereview.md`): commit `bc07196` додає strict `HandlerOutcome` із bounded content, typed effects/truncation/unknown lifecycle та транзакційне завершення expired approvals. Fix round закрив Important handler-interface gap і Minor expiry lifecycle gap. Coordinator повторив suite: 274 passed / 1 skipped; Ruff і whitespace clean. [Поточний контрольний контракт і межі](../topics/tool-control.md).

**Перевірений факт:** Task 6 (`012f248`, fixes `f0f8ea2`, `7d7809e`) додає 13 реальних host tools через `HandlerOutcome`/`EffectGuard`. Review знайшов I1/I2/M1; усі закрито, scoped rereview — coordinator (Claude Code), не окремий агент. Full suite 318 passed / 1 skipped; Ruff clean. [Деталі й межі](../topics/tool-control.md).

**Наступний крок:** Task 7 об’єднує sessions, original-revision lookup, global purge coordination і спільний agent loop.

**Вимога:** уточнення architecture review у §15 специфікації та binding amendments плану обов’язкові: server-owned control, global purge hooks, revision-aware evidence, immutable admitted request і чесні unknown tool outcomes. Наявність цих контрактів у плані не доводить їхньої реалізації.

Goal залишається active до перевірки всього scope. Mock hardware, короткий smoke test або наявність плану не закривають фізичні/тривалі вимоги. Доступність відсутнього обладнання фіксується як dependency, не як привід зупинити desktop реалізацію.
