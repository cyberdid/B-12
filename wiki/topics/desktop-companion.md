---
type: topic
updated: 2026-11-07
status: compiled
sources: [wiki/sources/capri-desktop-companions-2026-11-07.md, docs/desktop-companion.md, docs/superpowers/specs/2026-11-07-b12-desktop-companion-design.md, src/b12/desktop/client.py, src/b12/desktop/app.py, src/b12/desktop/chat.py, src/b12/desktop/cat.py, src/b12/api.py]
tags: [desktop, companion, Qt, cybercat]
---
# Desktop-компаньйон B-12

## Висновок

**Пропозиція, реалізована у feature worktree:** нативна Qt оболонка поверх чинного B-12 API дає плаваючого кіберкота, чат, tray і owner control без другого agent/runtime. Порівняння чотирьох референсів і ліцензійні межі наведені у [source review](../sources/capri-desktop-companions-2026-11-07.md); налаштування описані у [desktop guide](../../docs/desktop-companion.md).

## Межі архітектури

- **Перевірений факт:** B-12 API надає owner-authenticated loopback endpoints для сесій, history, streaming chat, cancel/resume, approvals, consent, memory, status та voice mute/status. Desktop клієнт викликає ці endpoints через окремий HTTPX клієнт і не відкриває БД/store напряму.
- **Вимога:** модель, grants, consent, пам’ять і tool execution залишаються в runtime B-12; модельний текст не надає дозволів. UI кнопки передають точний operation ID до наявного approval API.
- **Перевірений факт:** адресу клієнта обмежено loopback; owner token читається із наявного `api/owner.token`, не записується у UI settings чи логи. HTTP proxy із середовища вимкнений.
- **Вимога:** desktop успадковує лише можливості поточного owner API та конфігурацію B-12; він не створює grants і не розширює host access.
- **Вимога:** pointer реакції та анімації лишаються презентаційними. Desktop не має окремих host tools, global hooks, screenshot/window tracking, автозапуску чи власного server/model процесу.
- **Вимога:** microphone/audio capture та playback не стартують. Голосовий UI лише читає status і змінює існуючий mute flag через API.

## UX

Cybercat використовує власний B-12 atlas із TUI. Прозорий topmost overlay підтримує кліки, перетягування й обмежений погляд за поточною позицією pointer; він опитує координату через Qt кожні 120 мс, без глобального input hook. Чат має вкладки розмови, пам’яті та стану системи. Всі API I/O та streaming винесені у worker pool.

Черга approvals навмисно не отримує аргументи через `/api/approvals`. Якщо tool args були отримані в поточному стрімі, transcript їх показує. Для черги, відновленої після перезапуску, UI явно попереджає про недоступність параметрів, не вигадуючи їх і не змінюючи API контракт.

## Докази й невідоме

**Перевірений факт у коді:** optional `desktop` extra; окремий `b12 desktop` CLI subcommand; owner-authenticated HTTPX loopback client; worker-thread API calls; Qt overlay/tray fallback; sessions/chat/approvals/memory/consent/status. Цільові offscreen tests покривають ці UI paths.

**Потребує перевірки:** візуальна якість на реальному X11 compositor/window manager, Qt tray на фактичному desktop session, Wayland behavior, package artifacts і реальний довготривалий streaming із B-12 API. Qt офіційно зазначає ARGB visual/compositing вимоги для translucent X11 top-level widgets; topmost — hint, залежний від window manager. Див. [Qt QWidget](https://doc.qt.io/qtforpython-6/PySide6/QtWidgets/QWidget.html), [Qt flags](https://doc.qt.io/qtforpython-6/PySide6/QtCore/Qt.html), [QSystemTrayIcon](https://doc.qt.io/qtforpython-6/PySide6/QtWidgets/QSystemTrayIcon.html).

Детальний status і implementation checklist — у [project plan](../project/desktop-companion-plan.md); встановлення — у [guide](../../docs/desktop-companion.md).
