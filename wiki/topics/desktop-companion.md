---
type: topic
updated: 2026-11-08
status: compiled
sources: [wiki/sources/capri-desktop-companions-2026-11-07.md, docs/desktop-companion.md, docs/superpowers/specs/2026-11-07-b12-desktop-companion-design.md, docs/superpowers/specs/2026-11-08-b12-desktop-capri-skin-design.md, docs/superpowers/specs/2026-11-08-b12-capri-compact-actions-design.md, docs/superpowers/specs/2026-11-08-b12-capri-feature-parity-design.md, docs/superpowers/plans/2026-11-08-b12-capri-feature-parity.md, docs/superpowers/specs/2026-11-08-capri-persona-brand-design.md, docs/superpowers/plans/2026-11-08-capri-persona-brand.md, wiki/project/decisions.md, src/b12/persona.py, src/b12/agent.py, src/b12/skins.py, src/b12/desktop/client.py, src/b12/desktop/actions.py, src/b12/desktop/activity.py, src/b12/desktop/hooks.py, src/b12/desktop/integrations.py, src/b12/desktop/profile.py, src/b12/desktop/local_features.py, src/b12/desktop/presentation.py, src/b12/desktop/app.py, src/b12/desktop/chat.py, src/b12/desktop/cat.py, src/b12/api.py]
tags: [desktop, companion, Qt, Capri, cybercat]
---
# Desktop-компаньйон Capri

## Висновок

**Вимога власника:** у графічному desktop-компаньйоні основним виглядом має бути оригінальна Capri, а Кіберкіт — доступною опцією. **Перевірений факт у коді:** Qt shell тепер підтримує обидва варіанти, перемикач у tray/context menu та збереження вибору; за наявності валідного локального pack новий профіль починає з Capri. Це окрема графічна програма, не TUI. Порівняння референсів і межі прав наведені у [source review](../sources/capri-desktop-companions-2026-11-07.md); спосіб встановлення — у [desktop guide](../../docs/desktop-companion.md).

**Вимога власника (08.11.2026):** Capri є видимим ім’ям самого компаньйона незалежно від вибраної графіки; Кіберкіт — лише альтернативний вигляд. **Перевірений факт у коді:** спільний `Agent` prompt і написи desktop/TUI/Web/CLI називають компаньйона Capri. `b12` лишається внутрішнім runtime/API/package namespace для сумісності; див. [ADR-013](../project/decisions.md#adr-013--ідентичність-capri-та-сумісність-runtime).

## Межі архітектури

- **Перевірений факт:** B-12 API надає owner-authenticated loopback endpoints для сесій, history, streaming chat, cancel/resume, exact approvals, memory, consent, service status та voice mute/status. Desktop клієнт також читає owner-scoped boolean стан конкретного turn через `GET /api/turns/{id}/status`, щоб після втрати потоку не розблокувати новий prompt раніше, ніж завершився попередній. HTTPX клієнт не відкриває БД/store напряму.
- **Вимога:** модель, grants, consent, пам’ять і tool execution залишаються в runtime B-12; модельний текст не надає дозволів. UI кнопки передають точний operation ID до наявного approval API.
- **Перевірений факт:** адресу клієнта обмежено loopback; owner token читається із наявного `api/owner.token`, не записується у UI settings чи логи. HTTP proxy із середовища вимкнений.
- **Вимога:** desktop не створює grants або model-callable host tools. Shell-команди залишаються в runtime B-12; додані application launchers можуть викликатися тільки owner-кліком із локального Qt UI та явним підтвердженням точних executable/argv, див. [ADR-011](../project/decisions.md#adr-011--desktop-launchers--system-commands).
- **Вимога:** pointer реакції й анімації лишаються презентаційними. Coding-agent hooks є окремими opt-in integration з явним підключенням; глобальні keyboard hooks і приховані listeners не додаються. XDG autostart opt-in та вимкнений за замовчуванням.
- **Вимога:** microphone/audio capture та playback не стартують. Голосовий UI лише читає status і змінює існуючий mute flag через API.

## UX

Capri відображається з локального manifest atlas із прозорими RGBA кадрами; арт-пак зберігається поза Git у `~/.local/share/b12/skins/capri`. Вбудований Кіберкіт лишається в меню вибору. Для Capri додано вузьку неоново-рожеву/зелену плашку візуального статусу, а кадри малюються зі збереженням пропорцій. Прозорий topmost overlay підтримує кліки, перетягування й обмежений погляд за поточною позицією pointer; координату він опитує через Qt кожні 120 мс. Додані дії власника: wander, peek, demo, reduced motion, optional system beep, ручне перенесення на дисплей під pointer та необов’язкове слідування за курсором між дисплеями після 3 секунд. За замовчуванням слідування вимкнене; reduced motion вимикає його. Після 10 хвилин без взаємодії саме з companion він засинає; таймер можна вимкнути. Глобальні клавіатурні чи віконні події не відстежуються.

Capri animation controller відтворює незалежні від моделі жести та графічні ефекти. Натискання/перетягування запускають curious/held/throw; chat phases — curious, повторювану satellite-анімацію під час thinking, talk, speed, approval hold, celebration, reconnect glitch, cancel shockwave і sleep. Меню `АНІМАЦІЇ CAPRI` запускає intro, sit/lounge, peek, leap/fall/throw, held, tumble/KO, teleport, satellite/beam, lightning, shards, shockwave, speed, celebration, glitch, cut-in і sleep. Трансформації, лінії, частинки, кільця та промені малюються процедурно поверх приватного локального sprite pack; timer не залежить від LLM. Reduced motion зупиняє жести й ефекти. Це незалежна реалізація поведінкових типів, а не upstream код, арт чи звук; керування сторонніми вікнами сюди не входить.

Компактний frameless chat bubble біля персонажа повторно використовує той самий `ChatWindow`: session/history/stream/cancel/recovery/exact approval state не дублюється. Enter надсилає, Escape/× ховає, ⤢ повертає багатовкладкове вікно. Bubble переміщується за pet і перевіряє геометрію доступного екрана, віддаючи перевагу розташуванню під персонажем; за браком місця обирає інший бік і затискає себе в межах дисплея. Загальний activity status лишається тихим індикатором; approval notifications не відкладаються.

У legacy `QSettings` локально зберігаються reminders, prompt/site/app launchers, profile і presentation preferences. Reminder parser приймає лише явні українські/англійські фрази, перед записом показує exact title/time, а нечітку дату спрямовує у форму уточнення. Профіль передає ім’я користувача, стиль і фрази до кожного desktop-запиту як bounded style-only context; він не потрапляє в transcript, довгу пам’ять чи interaction history. При локальному model provider контекст лишається на цьому комп’ютері; при хмарному — надсилається тому provider у складі prompt. Ці дані не змінюють конфігурацію tools чи дозволів. Interaction history вимкнена за замовчуванням; після згоди зберігає максимум 100 пар kind/time без transcript.

**Виправлення за скриншотом власника (2026-11-08):** запит compact chat відхилявся з `HTTP 422`, бо локальний `history_opt_in` ішов усередині `companion_profile`, а API schema використовує strict `extra="forbid"`. `DesktopApiClient` тепер відправляє лише `name`, `style_note`, `catchphrases`; прапорець згоди залишається локально. Для виправлення не потрібна зміна API чи дозволів.

`LocalFeaturesDialog` шукає назви у теці, яку обрав власник, а за окремою галочкою — вміст UTF-8 текстових файлів (до 400 файлів, 256 KiB на файл і 16 MiB загалом). Приховані теки та symlink-и пропускаються; результати показують шляхи, вміст не зберігається й не надсилається. Open/reveal потребують exact-path confirmation. Панель також показує локальні read-only CPU/RAM/disk/battery/network metrics. Linux/X11 fixed-argv controls пропонують доступні media, volume, lock/suspend/reboot/poweroff/cancel, GNOME theme і XRandR display mode APIs. Точний target/action показано до кліку; power actions вимагають ввести точну назву. Shell text не виконується із цього меню.

`IntegrationManager` має opt-in hook management для Claude Code, Codex і Antigravity з backup, atomic config write і видаленням лише entries з точним B-12 marker. Hook subprocess відкидає payload і персистує лише allowlisted provider/event/time/HMAC session pseudonym/count у bounded JSONL. `IntegrationDialog` фільтрує provider, показує activity ticker і денний mission report; картку звіту можна відрендерити у пам’яті й скопіювати в clipboard без запису файла. Зовнішні approvals завжди вирішуються в зовнішньому агенті; інсталяція конфігів і реальні events ще не перевірялися на host. Локальна реалізація та межі наведені у [gap review](../sources/capri-desktop-companions-2026-11-07.md), [feature parity plan](../../docs/superpowers/plans/2026-11-08-b12-capri-feature-parity.md) та [ADR-012](../project/decisions.md#adr-012--функціональна-сумісність-capri-desktop).

**Непокриті upstream можливості:** B-12 text chat не має image input, тому screen view/capture і periodic watching відсутні. Немає active-window/USB/game sensing, авто-закриття чужих вкладок/програм, app close/arrangement, screen/window possession, upstream art/sound cut-ins, синтезованих/custom sound bank або повного перемикача UI мов. Власні Qt-аналогії fall/tumble/satellite/beam та ефектів описані вище. XRandR змінює тільки режим дисплея, не його геометрію чи rotation. Windows-specific UI та Wayland ще не підтримані.

Чат має вкладки розмови, пам’яті та стану системи. Всі API I/O та streaming винесені у worker pool.

Імпортер створює приватний локальний pack лише з pinned `nic0dvornikov/capricorn-linux` revision `7752959e7a708bac5b540d5380321c33694f6fb6`; він не запускає upstream-програму. Її LICENSE явно виключає Capri character/Cyberpunk IP, тому цей локальний preview не означає наявності прав на поширення. Арт не входить до репозиторію, wheel або release; питання подальшого розповсюдження лишається відкритим у [Q20](../project/open-questions.md).

Черга approvals навмисно не отримує аргументи через `/api/approvals`. Якщо tool args були отримані в поточному стрімі, transcript їх показує. Для черги, відновленої після перезапуску, UI явно попереджає про недоступність параметрів, не вигадуючи їх і не змінюючи API контракт.

## Докази й невідоме

### Ідентичність і манера відповідей

**Перевірений факт у коді:** [`src/b12/persona.py`](../../src/b12/persona.py) містить самостійно написаний базовий prompt Capri та обмежувач desktop-профілю. Базова манера тепла, уважна, розмовна й дотепна; легка іронія та Night City slang з’являються зрідка. Інженерні відповіді лишаються точними й повними, нерозбірливий уривок викликає уточнення, а не вигадане тлумачення. Модель не повинна вигадувати вчинки чи людські почуття, тиснути на власника або перетворювати кожну відповідь на рольову сцену.

**Перевірений факт у коді:** локальний desktop profile provider додає поля `name`, `style_note`, `catchphrases` тільки до нового desktop-запиту. API schema й formatter обмежують їх довжину та трактують як дані, не control instructions. Після очікування approval контекст лишається в межах in-memory turn state; transcript і persistent memory не змінюються цим механізмом.

**Потребує перевірки:** ця persona ще не проходила blind human preference review, model repeat/consistency eval або перевірку конкретного cloud provider. Prompt є інструкцією, а не гарантією точного голосу; поведінку треба оцінити на вибраній моделі.

**Перевірений факт у коді:** optional `desktop` extra; окремий `b12 desktop` CLI subcommand; owner-authenticated HTTPX loopback client; worker-thread API calls; Qt overlay/tray fallback; sessions/chat/approvals/memory/consent/status. Новий Capri parity code додає opt-in hooks/activity journal, reminder parser, local profile/history, local file/system/media/action center, guide і autostart manager.

**Перевірений факт (2026-11-08):** native Qt client із feature worktree запущений на X11, overlay видимий 300×410; representative animation actions відрендерено з локальним pack у Qt і переглянуто. Static Ruff, format, compileall, local Markdown/source links і whitespace checks пройшли. **Потребує перевірки:** успішний живий chat turn після HTTP 422 fix, automated test suite, owner click-through action menu, реальні hooks/system actions/app launch та інші WM/Wayland acceptance. Модель inference, audio/GPU і server restart не запускалися.

**Перевірений факт:** якщо NDJSON-потік обривається після `turn_started`, клієнт зберігає lock і показує recovery cancel. Лише після успішного cancel acknowledgement він перевіряє стан саме цього turn через authenticated API; тільки актуальна відповідь `active=false` знімає блокування та ініціює повторне завантаження історії. Кожне завантаження очищує маркер свіжої історії; помилка лишає надсилання заблокованим і дозволяє bootstrap retry. Старі stream, cancel, history та status callbacks ігноруються за поколінням і turn ID.

**Перевірений факт:** якщо API зникає під час очікування owner approval, overlay зберігає approval pose. Після reconnect із тим самим operation ID він лишається visible, доки approval не зникне із server queue.

**Перевірений факт:** X11 smoke на X.Org 21.1.11 створив видиме вікно 244×272 з 32-bit TrueColor visual; `QSystemTrayIcon.isSystemTrayAvailable()` повернув `true`. Запуск був із тимчасовим state/config, фіктивним токеном і порожнім локальним API endpoint; B-12 service/model/audio/GPU не запускався. Offscreen pixel regression виявив білий approval viewport системної палітри `#efefef`; після fix він має колір панелі `#0a1020`.

**Перевірений факт (2026-11-08):** Capri pack зібрано поза Git. На X11 `DISPLAY=:1` зафіксовано viewable Qt-вікно `B-12 · CAPRI` 300×410 на 2560×1600; збережено тимчасовий crop вікна, не повний desktop screenshot. Контекстне меню показало Capri і Кіберкіт; обидві зміни вигляду перевірено вручну, а після перезапуску persisted appearance лишився Capri. Клієнт був зібраний з `--extra desktop`, без імпорту TUI modules; API health повернув HTTP 200.

**Потребує перевірки:** tray icon/menu interaction, Wayland behavior, topmost/drag acceptance на різних X11 window managers, чистий системний package install і довготривалий streaming із живим API. Qt зазначає ARGB visual/compositing вимоги для translucent X11 top-level widgets; topmost — hint, залежний від window manager. Див. [Qt QWidget](https://doc.qt.io/qtforpython-6/PySide6/QtWidgets/QWidget.html), [Qt flags](https://doc.qt.io/qtforpython-6/PySide6/QtCore/Qt.html), [QSystemTrayIcon](https://doc.qt.io/qtforpython-6/PySide6/QtWidgets/QSystemTrayIcon.html).

**Перевірений факт (2026-11-08):** offscreen Qt smoke створив `DesktopShell`, перемкнув chat bubble → full chat і створив reminders/launchers/prompts/command dialogs із тестовим `QSettings`. Зв’язок із тестовим loopback API був недоступний; server/model/microphone/speaker/GPU не стартували. Smoke підтверджує лише побудову widgets і перемикання режимів, не compositor layout, live streaming, запуск реальних програм чи події нагадувань.

**Межа прав:** upstream LICENSE виключає персонажа Capri й Cyberpunk IP. Користувач попросив локальний приватний preview, але це не є правом на розповсюдження; pack не комітиться і не включається до release. Деталі походження — у [source card](../sources/capri-desktop-companions-2026-11-07.md), відкрите питання — [Q20](../project/open-questions.md).

Детальний status і implementation checklist — у [project plan](../project/desktop-companion-plan.md); встановлення — у [guide](../../docs/desktop-companion.md).
