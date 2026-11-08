---
type: topic
updated: 2026-11-08
status: compiled
sources: [wiki/sources/capri-desktop-companions-2026-11-07.md, docs/desktop-companion.md, docs/superpowers/specs/2026-11-07-b12-desktop-companion-design.md, docs/superpowers/specs/2026-11-08-b12-desktop-capri-skin-design.md, src/b12/skins.py, src/b12/desktop/client.py, src/b12/desktop/app.py, src/b12/desktop/chat.py, src/b12/desktop/cat.py, src/b12/api.py]
tags: [desktop, companion, Qt, Capri, cybercat]
---
# Desktop-компаньйон B-12

## Висновок

**Вимога власника:** у графічному desktop-компаньйоні основним виглядом має бути оригінальна Capri, а Кіберкіт — доступною опцією. **Перевірений факт у коді:** Qt shell тепер підтримує обидва варіанти, перемикач у tray/context menu та збереження вибору; за наявності валідного локального pack новий профіль починає з Capri. Це окрема графічна програма, не TUI. Порівняння референсів і межі прав наведені у [source review](../sources/capri-desktop-companions-2026-11-07.md); спосіб встановлення — у [desktop guide](../../docs/desktop-companion.md).

## Межі архітектури

- **Перевірений факт:** B-12 API надає owner-authenticated loopback endpoints для сесій, history, streaming chat, cancel/resume, exact approvals, memory, consent, service status та voice mute/status. Desktop клієнт також читає owner-scoped boolean стан конкретного turn через `GET /api/turns/{id}/status`, щоб після втрати потоку не розблокувати новий prompt раніше, ніж завершився попередній. HTTPX клієнт не відкриває БД/store напряму.
- **Вимога:** модель, grants, consent, пам’ять і tool execution залишаються в runtime B-12; модельний текст не надає дозволів. UI кнопки передають точний operation ID до наявного approval API.
- **Перевірений факт:** адресу клієнта обмежено loopback; owner token читається із наявного `api/owner.token`, не записується у UI settings чи логи. HTTP proxy із середовища вимкнений.
- **Вимога:** desktop успадковує лише можливості поточного owner API та конфігурацію B-12; він не створює grants і не розширює host access.
- **Вимога:** pointer реакції та анімації лишаються презентаційними. Desktop не має окремих host tools, global hooks, screenshot/window tracking, автозапуску чи власного server/model процесу.
- **Вимога:** microphone/audio capture та playback не стартують. Голосовий UI лише читає status і змінює існуючий mute flag через API.

## UX

Capri відображається з локального manifest atlas із прозорими RGBA кадрами; арт-пак зберігається поза Git у `~/.local/share/b12/skins/capri`. Вбудований Кіберкіт лишається в меню вибору. Для Capri додано вузьку неоново-рожеву/зелену плашку візуального статусу, а кадри малюються зі збереженням пропорцій. Прозорий topmost overlay підтримує кліки, перетягування й обмежений погляд за поточною позицією pointer; координату він опитує через Qt кожні 120 мс, без глобального input hook. Чат має вкладки розмови, пам’яті та стану системи. Всі API I/O та streaming винесені у worker pool.

Імпортер створює приватний локальний pack лише з pinned `nic0dvornikov/capricorn-linux` revision `7752959e7a708bac5b540d5380321c33694f6fb6`; він не запускає upstream-програму. Її LICENSE явно виключає Capri character/Cyberpunk IP, тому цей локальний preview не означає наявності прав на поширення. Арт не входить до репозиторію, wheel або release; питання подальшого розповсюдження лишається відкритим у [Q20](../project/open-questions.md).

Черга approvals навмисно не отримує аргументи через `/api/approvals`. Якщо tool args були отримані в поточному стрімі, transcript їх показує. Для черги, відновленої після перезапуску, UI явно попереджає про недоступність параметрів, не вигадуючи їх і не змінюючи API контракт.

## Докази й невідоме

**Перевірений факт у коді:** optional `desktop` extra; окремий `b12 desktop` CLI subcommand; owner-authenticated HTTPX loopback client; worker-thread API calls; Qt overlay/tray fallback; sessions/chat/approvals/memory/consent/status. Цільові offscreen tests покривають ці UI paths.

**Перевірений факт:** якщо NDJSON-потік обривається після `turn_started`, клієнт зберігає lock і показує recovery cancel. Лише після успішного cancel acknowledgement він перевіряє стан саме цього turn через authenticated API; тільки актуальна відповідь `active=false` знімає блокування та ініціює повторне завантаження історії. Кожне завантаження очищує маркер свіжої історії; помилка лишає надсилання заблокованим і дозволяє bootstrap retry. Старі stream, cancel, history та status callbacks ігноруються за поколінням і turn ID.

**Перевірений факт:** якщо API зникає під час очікування owner approval, overlay зберігає approval pose. Після reconnect із тим самим operation ID він лишається visible, доки approval не зникне із server queue.

**Перевірений факт:** X11 smoke на X.Org 21.1.11 створив видиме вікно 244×272 з 32-bit TrueColor visual; `QSystemTrayIcon.isSystemTrayAvailable()` повернув `true`. Запуск був із тимчасовим state/config, фіктивним токеном і порожнім локальним API endpoint; B-12 service/model/audio/GPU не запускався. Offscreen pixel regression виявив білий approval viewport системної палітри `#efefef`; після fix він має колір панелі `#0a1020`.

**Перевірений факт (2026-11-08):** Capri pack зібрано поза Git. На X11 `DISPLAY=:1` зафіксовано viewable Qt-вікно `B-12 · CAPRI` 300×410 на 2560×1600; збережено тимчасовий crop вікна, не повний desktop screenshot. Контекстне меню показало Capri і Кіберкіт; обидві зміни вигляду перевірено вручну, а після перезапуску persisted appearance лишився Capri. Клієнт був зібраний з `--extra desktop`, без імпорту TUI modules; API health повернув HTTP 200.

**Потребує перевірки:** tray icon/menu interaction, Wayland behavior, topmost/drag acceptance на різних X11 window managers, чистий системний package install і довготривалий streaming із живим API. Qt зазначає ARGB visual/compositing вимоги для translucent X11 top-level widgets; topmost — hint, залежний від window manager. Див. [Qt QWidget](https://doc.qt.io/qtforpython-6/PySide6/QtWidgets/QWidget.html), [Qt flags](https://doc.qt.io/qtforpython-6/PySide6/QtCore/Qt.html), [QSystemTrayIcon](https://doc.qt.io/qtforpython-6/PySide6/QtWidgets/QSystemTrayIcon.html).

**Межа прав:** upstream LICENSE виключає персонажа Capri й Cyberpunk IP. Користувач попросив локальний приватний preview, але це не є правом на розповсюдження; pack не комітиться і не включається до release. Деталі походження — у [source card](../sources/capri-desktop-companions-2026-11-07.md), відкрите питання — [Q20](../project/open-questions.md).

Детальний status і implementation checklist — у [project plan](../project/desktop-companion-plan.md); встановлення — у [guide](../../docs/desktop-companion.md).
