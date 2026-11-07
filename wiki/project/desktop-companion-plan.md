---
type: project-plan
updated: 2026-11-08
status: implemented-needs-host-validation
sources: [docs/superpowers/specs/2026-11-07-b12-desktop-companion-design.md, docs/superpowers/plans/2026-11-07-b12-desktop-companion.md, docs/desktop-companion.md, wiki/topics/desktop-companion.md, wiki/sources/capri-desktop-companions-2026-11-07.md, src/b12/api.py, src/b12/desktop/client.py, src/b12/desktop/chat.py, src/b12/tui/client.py, tests/desktop/, tests/integration/test_api.py]
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
5. **Документація та локальна перевірка — виконано.** Locked full suite: 740 passed / 4 skipped за 163,94 с; Ruff `src tests`, lock check, `git diff --check`, wheel/sdist build пройшли. Wheel містить desktop chat/cat modules і власний cybercat atlas. Wiki audit: 44 сторінки, 358 локальних links, 0 broken anchors, 0 неіндексованих сторінок; залишилися 11 історичних missing artifact links та одна відсутня snapshot source reference. Незалежний rereview після останнього recovery fix не знайшов підтверджених дефектів. `main` є предком цієї гілки (`5f6ba90`), перенос не потрібен. Фізичний X11/Wayland, чиста системна інсталяція та живий model stream не перевірялись. Для цієї роботи не запускали service, desktop client, voice чи GPU процес.

**Перевірений baseline:** у новій гілці feat/b12-desktop-companion на commit 3e7fb07 цільові TUI integration tests до змін: 22 passed (uv run --locked --extra dev --extra tui pytest tests/integration/test_tui.py -q).

Підсумок реалізації та обмежень наведено у [тематичній сторінці](../topics/desktop-companion.md); хронологію перевірок — у [журналі](../log.md).
