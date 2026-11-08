---
type: project-plan
updated: 2026-11-08
status: implemented-with-capri-preview; platform-validation-open
sources: [docs/superpowers/specs/2026-11-07-b12-desktop-companion-design.md, docs/superpowers/plans/2026-11-07-b12-desktop-companion.md, docs/superpowers/specs/2026-11-08-b12-desktop-capri-skin-design.md, docs/superpowers/plans/2026-11-08-b12-desktop-capri-skin.md, docs/desktop-companion.md, wiki/topics/desktop-companion.md, wiki/sources/capri-desktop-companions-2026-11-07.md, src/b12/api.py, src/b12/skins.py, src/b12/desktop/client.py, src/b12/desktop/chat.py, src/b12/desktop/app.py, src/b12/desktop/cat.py, tests/desktop/, tests/integration/test_api.py]
tags: [desktop, companion, Capri, cybercat, plan]
---
# Desktop-компаньйон B-12 — план

**Вимога власника (07.11.2026):** уважно вивчити чотири Capricorn-репозиторії, спланувати й реалізувати найбільш корисний desktop-компаньйон B-12; надано широку згоду на роботу.

**Актуальна вимога власника (08.11.2026):** окреме графічне Qt-вікно показує Capri як початковий вигляд, а Кіберкіт лишається опційним вибором. Це не TUI scope. Native shell використовує тільки існуючий owner-authenticated API. Деталі: [Capri skin design](../../docs/superpowers/specs/2026-11-08-b12-desktop-capri-skin-design.md), [implementation plan](../../docs/superpowers/plans/2026-11-08-b12-desktop-capri-skin.md), [research](../sources/capri-desktop-companions-2026-11-07.md).

## Межі

- Capri artwork залишається тільки у приватному user-data pack поза Git/release; права на повторне поширення не підтверджені. B-12 не запускає upstream code.
- API/runtime лишається єдиним власником стану, моделі, tools, grants і approval.
- Нових host actions чи прихованих browser/window/screen listeners не додавати.
- Не запускати сервер, модель, мікрофон чи audio playback при старті desktop UI.
- PySide6 додається як окремий optional dependency; CLI/TUI без нього працездатні.
- Перший target — поточний Linux/X11 desktop; Wayland та інші ОС окремо не підтверджені.

## Етапи

1. **Дослідження й дизайн — зроблено.** Pinned 4 джерела, порівняно функції/права, визначено B-12 reuse межі.
2. **API client і CLI command — реалізовано.** Loopback-only bearer client, NDJSON-стрім, сталі коди помилок, кодування ID у URL-шляху й optional `b12 desktop`. Команда не бере runtime lock; Qt імпортується лише для desktop.
3. **Companion і tray — реалізовано.** Вбудований Кіберкіт лишився доступним; Qt overlay підтримує validated Capri atlas, pointer reaction і persistent appearance menu. Свіжий X11 acceptance підтвердив видиме вікно Capri 300×410 та ручне перемикання Capri ↔ Кіберкіт. Взаємодію із tray icon, drag/topmost на різних WM і Wayland ще не підтверджено.
4. **UI контур — реалізовано.** Sessions/history, streaming, cancel/resume, exact-operation approval/deny, memory CRUD, consent/persist, connectivity та лише voice mute/status. API не передає аргументи approvals; UI це показує. Markdown images і memory labels рендеряться як безпечний текст.
5. **Документація та локальна перевірка — виконано.** Після recovery та UI regression fixes locked full suite: 742 passed / 4 skipped за 151,69 с; фінальні Ruff `src tests`, lock check, `git diff --check`, wheel/sdist build і вміст wheel перевірені. Tests відтворюють approval-state reconnect і білий viewport та перевіряють темний піксель `#0a1020`. Wiki audit: 44 сторінки, 358 локальних links, 0 broken anchors, 0 неіндексованих сторінок; залишилися 11 історичних missing artifact links та одна відсутня snapshot source reference. Незалежний rereview підтвердив approval reconnect fix і не знайшов Critical/Important issues. Гілку опубліковано в [PR #2](https://github.com/cyberdid/B-12/pull/2), stacked на runtime PR #1 із base `feat/b12-runtime`; `main` є спільним предком через `5f6ba90`. Після злиття PR #1 треба retarget PR #2 на `main`. X11 smoke підтвердив mapped ARGB overlay/tray API availability; screenshot, реальна взаємодія з window manager/tray, Wayland, системний package install і live model stream ще відкриті. B-12 server/model/microphone/audio/GPU не запускали.

**Перевірений baseline:** у новій гілці feat/b12-desktop-companion на commit 3e7fb07 цільові TUI integration tests до змін: 22 passed (uv run --locked --extra dev --extra tui pytest tests/integration/test_tui.py -q).

Підсумок реалізації та обмежень наведено у [тематичній сторінці](../topics/desktop-companion.md); хронологію перевірок — у [журналі](../log.md).

## Capri appearance — виконано локально (2026-11-08)

- `src/b12/skins.py` — data-only v1 manifest validation, незалежний від Textual. Qt desktop встановлюється лише з `--extra desktop` (PySide6 + Pillow).
- `scripts/import-capri-skin.py` вимагає pinned `7752959e7a708bac5b540d5380321c33694f6fb6`, перевіряє розмір/режим/число кадрів і створює pack у `~/.local/share/b12/skins/capri`. Створено 60 кадрів 249×380 і три статичні пози; окремий eye sequence не композититься без перевіреної registration map.
- X11 user-visible launch підтвердив Capri за замовчуванням, перемикання на Кіберкіт і назад, а також збереження Capri після перезапуску. Модель і аудіо не запускались; автоматизовані тести цієї зміни не запускались.
- Підставу, provenance та обмеження арт-ліцензії описано у [source card](../sources/capri-desktop-companions-2026-11-07.md) та [Q20](open-questions.md). Поширювати арт разом із B-12 не можна без окремого права.
