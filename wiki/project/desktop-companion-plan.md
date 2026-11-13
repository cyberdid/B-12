---
type: project-plan
updated: 2026-11-08
status: capri-feature-parity-in-progress; host-acceptance-open
sources: [docs/superpowers/specs/2026-11-07-b12-desktop-companion-design.md, docs/superpowers/plans/2026-11-07-b12-desktop-companion.md, docs/superpowers/specs/2026-11-08-b12-desktop-capri-skin-design.md, docs/superpowers/plans/2026-11-08-b12-desktop-capri-skin.md, docs/superpowers/specs/2026-11-08-b12-capri-compact-actions-design.md, docs/superpowers/plans/2026-11-08-b12-capri-compact-actions.md, docs/superpowers/specs/2026-11-08-capri-persona-brand-design.md, docs/superpowers/plans/2026-11-08-capri-persona-brand.md, docs/desktop-companion.md, wiki/topics/desktop-companion.md, wiki/sources/capri-desktop-companions-2026-11-07.md, wiki/project/decisions.md, src/b12/api.py, src/b12/persona.py, src/b12/agent.py, src/b12/skins.py, src/b12/desktop/actions.py, src/b12/desktop/activity.py, src/b12/desktop/hooks.py, src/b12/desktop/integrations.py, src/b12/desktop/local_features.py, src/b12/desktop/profile.py, src/b12/desktop/presentation.py, src/b12/desktop/client.py, src/b12/desktop/chat.py, src/b12/desktop/app.py, src/b12/desktop/cat.py, tests/desktop/, tests/integration/test_api.py]
tags: [desktop, companion, Capri, cybercat, plan]
---
# Desktop-компаньйон Capri — план

Повний gap audit і нове доручення власника від 08.11 описані в [Capri feature parity plan](../../docs/superpowers/plans/2026-11-08-b12-capri-feature-parity.md) та [ADR-012](decisions.md#adr-012--функціональна-сумісність-capri-desktop). Ця сторінка зберігає окремо вже зроблений компактний-chat етап; він не означає, що всі функції Capri Desktop уже реалізовані.

**Вимога власника (07.11.2026):** уважно вивчити чотири Capricorn-репозиторії, спланувати й реалізувати найбільш корисний desktop-компаньйон B-12; надано широку згоду на роботу.

**Актуальна вимога власника (08.11.2026):** окреме графічне Qt-вікно показує Capri як початковий вигляд, а Кіберкіт лишається опційним вибором. Це не TUI scope. Native shell використовує тільки існуючий owner-authenticated API. Деталі: [Capri skin design](../../docs/superpowers/specs/2026-11-08-b12-desktop-capri-skin-design.md), [implementation plan](../../docs/superpowers/plans/2026-11-08-b12-desktop-capri-skin.md), [research](../sources/capri-desktop-companions-2026-11-07.md).

## Межі

- Capri artwork залишається тільки у приватному user-data pack поза Git/release; права на повторне поширення не підтверджені. B-12 не запускає upstream code.
- API/runtime лишається єдиним власником стану, моделі, tools, grants і approval.
- Початкова межа 07.11 забороняла нові host actions. Її вузько переглянуто прямою вимогою власника 08.11: owner-click launchers із підтвердженням; довільний shell лишається в існуючих B-12 grants/approval (див. [ADR-011](decisions.md#adr-011--desktop-launchers--system-commands)). Hidden browser/window/screen listeners заборонені.
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

## Capri feature parity extension — код додано локально (2026-11-08)

- `integrations.py`, `hooks.py`, `activity.py`: явне підключення Claude Code/Codex/Antigravity, backup і marker-only uninstall, bounded metadata journal та денний звіт із clipboard image export. Antigravity hook дотримується актуального `PreToolUse`/`Stop` output contract; конфіги власника не змінювалися.
- `profile.py`: локальний профіль, owner-authored фрази, opt-in історія лише типу/часу, детермінований UA/EN reminder parser з ручним підтвердженням.
- `local_features.py`: пошук назв і opt-in UTF-8 content search у вибраній теці з лімітами 400 файлів/16 MiB, read-only host snapshot і Linux/X11 фіксовані media/volume/power/theme/display дії з точним підтвердженням.
- `presentation.py`, `cat.py` та `app.py`: guide/autostart, auto-sleep, optional multi-display follow і Qt animation controller; реакції на chat phases, pointer/drag і owner menu; процедурні motion/effects поверх приватного local art. `reduced motion` вимикає цей controller.
- **Перевірено:** Ruff/format усіх desktop modules, `compileall`, `git diff --check`, локальні Markdown/source links; representative effect frames відрендерено у Qt; live X11 overlay із feature worktree відкрито (300×410), loopback API health — `true`. Automated test suite не запускали; live chat inference, hooks, host actions і owner click-through меню ще не приймали.
- **Не реалізовано з upstream:** image understanding/periodic capture, window possession/close/layout, USB/game/active-window sensing, повне provider/model setup, locales та custom sounds. Fall/throw/tumble, satellite/beam і cut-in мають власні Qt-аналогії, без upstream art. X11/Wayland і реальні конфіги потребують окремого host acceptance.
- **Виправлення зі скриншота:** compact-chat 422 спричиняв зайвий локальний `history_opt_in` у strict `companion_profile`; клієнт фільтрує його і відправляє тільки дозволені style fields. Після фіксу live model turn не запускався, щоб не займати GPU.

## Compact chat та додаткові функції — реалізовано локально (2026-11-08)

- Повторно перевірено pinned code paths наданих репозиторіїв. Прямі посилання та межі ліцензій записано у [джерельній картці](../sources/capri-desktop-companions-2026-11-07.md); зовнішні snapshots до `raw/` не збережені.
- `ChatWindow` перемикається між повною вкладковою формою й малим frameless bubble, який кліком відкривається біля Capri, переїжджає разом із нею, ховається через ×/Escape і розгортається до повного чату. Сесія, історія, stream, cancel, approval і recovery залишаються у тому самому контролері.
- Додано local reminder manager із date/time, overdue notifications, snooze/dismiss; owner-managed prompt shortcuts заповнюють composer без автозапуску; HTTP(S) site shortcuts і абсолютні app launchers доступні після user click; запуск програми має confirmation; shell command editor створює prompt для звичайного B-12 tool flow.
- Власник 08.11 прямо попросив запуск програм і системні команди. ADR-011 дозволяє лише підтверджені локальні launcher entries та лишає shell/control permissions у runtime. TUI, API та voice не змінювалися.
- Перевірено Ruff і `py_compile`; offscreen Qt smoke перемкнув compact/full і створив усі action dialogs. Не запускали B-12 server/model, audio, GPU, реальні програми або автоматизований suite. Реальна compositor/layout, live session/approval, persistence across restart, desktop notification backend і Wayland acceptance ще відкриті.

## Persona та видиме ім’я Capri — код додано локально (2026-11-08)

- `src/b12/persona.py` задає самостійно написану базову манеру й нормалізує desktop profile як bounded style-only JSON context.
- Desktop profile автоматично передає ім’я користувача, власну style note та фрази у `/api/chat`; API schema обмежує поля й довжини, а `Agent.turn` тримає контекст тільки у поточному in-memory turn state та додає його до system prompt на reasoning rounds.
- Видимі assistant/product labels у desktop, TUI, Web, CLI та API title оновлені на Capri; налаштування читаються зі старого `QSettings("B-12", "NeonCompanion")`.
- **Межа приватності:** з локальним model provider профіль лишається на цьому комп’ютері; з cloud provider поля йдуть йому у складі prompt. Вони не записуються до чату, довгої пам’яті чи activity journal; interaction history окрема й opt-in.
- **Не перейменовано:** Python package/CLI command/API routes/environment keys/state paths/hook markers, щоб не зламати встановлення та інтеграції. Це ADR-013, а не твердження, що історичні B-12 записи були переписані.
- **Потребує перевірки:** runtime/Qt запуск і людська оцінка стилю моделі не виконувались у цій зміні; profile flow із конкретним локальним або cloud provider не приймався.
