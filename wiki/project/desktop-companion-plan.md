---
type: project-plan
updated: 2026-11-07
status: implemented-needs-host-validation
sources: [docs/superpowers/specs/2026-11-07-b12-desktop-companion-design.md, docs/superpowers/plans/2026-11-07-b12-desktop-companion.md, docs/desktop-companion.md, wiki/topics/desktop-companion.md, wiki/sources/capri-desktop-companions-2026-11-07.md, src/b12/api.py, src/b12/tui/client.py]
tags: [desktop, companion, cybercat, plan]
---
# Desktop-компаньйон B-12 — план

**Вимога власника (07.11.2026):** уважно вивчити чотири Capricorn-репозиторії, спланувати й реалізувати найбільш корисний desktop-компаньйон B-12; надано широку згоду на роботу.

**Обраний дизайн:** необов’язковий Qt desktop shell із власним cybercat, системним треєм і компактним чатом, який використовує тільки існуючий owner-authenticated API. Деталі: [design](../../docs/superpowers/specs/2026-11-07-b12-desktop-companion-design.md), [implementation plan](../../docs/superpowers/plans/2026-11-07-b12-desktop-companion.md), [research](../sources/capri-desktop-companions-2026-11-07.md).

## Межі

- Не копіювати Capri code/assets; використовується B-12 asset із власним provenance.
- API/runtime лишається єдиним власником стану, моделі, tools, grants і approval.
- Нових host actions чи прихованих browser/window/screen listeners не додавати.
- Не запускати сервер, модель, мікрофон чи audio playback при старті desktop UI.
- PySide6 додається як окремий optional dependency; CLI/TUI без нього працездатні.
- Перший target — поточний Linux/X11 desktop; Wayland та інші ОС окремо не підтверджені.

## Етапи

1. **Дослідження й дизайн — зроблено.** Pinned 4 джерела, порівняно функції/права, визначено B-12 reuse межі.
2. **API client і CLI command — реалізовано.** Loopback-only bearer client, NDJSON-стрім, сталі коди помилок, кодування ID у URL-шляху й optional `b12 desktop`. Команда не бере runtime lock; Qt імпортується лише для desktop.
3. **Кіберкіт і tray — реалізовано, host validation очікує.** Прозорий topmost QWidget, пози, погляд за pointer, drag, QSettings position, menu, tray notifications і sleep/wake без tray.
4. **UI контур — реалізовано.** Sessions/history, streaming, cancel/resume, exact-operation approval/deny, memory CRUD, consent/persist, connectivity та лише voice mute/status. API не передає аргументи approvals; UI це показує. Markdown images і memory labels рендеряться як безпечний текст.
5. **Локальна перевірка — пройдена.** 51 desktop перевірка входить до повного suite; повний результат — 718 passed, 4 skipped. `ruff check src tests`, `uv lock --check`, wheel/sdist build і `git diff --check` пройшли. Змінені wiki-сторінки та manifest ще проходять фінальну перевірку після перенесення гілки на актуальний `main`. Фізичний X11/Wayland, чиста системна інсталяція та живий model stream ще не перевірені. Для цієї роботи не запускали service, desktop client, voice чи GPU процес.

**Перевірений baseline:** у новій гілці feat/b12-desktop-companion на commit 3e7fb07 цільові TUI integration tests до змін: 22 passed (uv run --locked --extra dev --extra tui pytest tests/integration/test_tui.py -q).

Підсумок реалізації та обмежень наведено у [тематичній сторінці](../topics/desktop-companion.md); хронологію перевірок — у [журналі](../log.md). Робоча гілка ще потребує перенесення на актуальний `main` і фінальної wiki-перевірки.
