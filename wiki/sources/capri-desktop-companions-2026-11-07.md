---
type: source-review
updated: 2026-11-07
status: reviewed
sources: [raw/source-manifest.json]
tags: [desktop, companion, cybercat, github, licensing]
---
# Capri / Capricorn desktop-компаньйони — огляд 07.11.2026

**Обсяг перевірки:** чотири надані GitHub-репозиторії та вибрані офіційні Qt for Python сторінки про прозорі вікна й системний трей. Для кожного репозиторію зафіксовано pinned HEAD на дату огляду. Повні історії та всі runtime-поведінки не перевірялися; код сторонніх проєктів не запускався. Оригінальні архіви до raw/ не додавалися. URL pinned commits, дату перевірки й межі прочитаного внесено у supplemental_checks [маніфесту](../../raw/source-manifest.json); file-level findings і посилання на переглянуті файли зібрані в цій картці.

## Порівняння джерел

| Джерело та перевірений зріз | Що перевірено | Висновок для B-12 |
|---|---|---|
| [Capri-Capricorn-The-Desktop-Construct, a807efd](https://github.com/Juliowiwiwiwi/Capri-Capricorn-The-Desktop-Construct/commit/a807efd4490da64d843917fad66a6195fb817c82) | Python/PySide6 desktop pet, topmost прозорий avatar, клік/перетягування, idle, локальний Ollama streaming-чат, прототип Whisper/Piper PTT/TTS. README відстає від наявного voice-коду. Явного LICENSE у перевіреному зрізі не знайдено; README каже Windows 11, voice English-only та ручне встановлення. [README](https://github.com/Juliowiwiwiwi/Capri-Capricorn-The-Desktop-Construct/blob/a807efd4490da64d843917fad66a6195fb817c82/README.md), [window.py](https://github.com/Juliowiwiwiwi/Capri-Capricorn-The-Desktop-Construct/blob/a807efd4490da64d843917fad66a6195fb817c82/capri/desktop/window.py), [voice initialization](https://github.com/Juliowiwiwiwi/Capri-Capricorn-The-Desktop-Construct/blob/a807efd4490da64d843917fad66a6195fb817c82/capri/main.py) | **Пропозиція:** topmost pet, gaze, простий чат і tray/menu — корисні UX-ідеї. Код/арт не копіювати: явну ліцензію не знайдено, voice налаштування відрізняються. |
| [CHNFTQ/Capricorn, d934e88](https://github.com/CHNFTQ/Capricorn/commit/d934e88af8b46b886852a75ac04154917e7f4763) | Академічний Python/PyTorch diffusion код для Hi-C contact matrices; README, train/infer структура, MIT code license. [README](https://github.com/CHNFTQ/Capricorn/blob/d934e88af8b46b886852a75ac04154917e7f4763/README.md), [LICENSE](https://github.com/CHNFTQ/Capricorn/blob/d934e88af8b46b886852a75ac04154917e7f4763/LICENSE) | **Перевірений факт:** назва збігається, тематика desktop-companion — ні. У B-12 не інтегрувати; ліцензія зовнішніх pretrained weights окремо не підтверджена. |
| [kystt29/capricorn, 27e724d](https://github.com/kystt29/capricorn/commit/27e724d9eb155e70c85cc2d1889217ca6f1e4bc2) | Windows-only Russian assistant із прозорим avatar, tray, Ollama chat і системними командами. README називає чат локальним, але default config використовує Google STT і Edge TTS; є optional Anthropic path. Команди керують застосунками/вікнами/вводом і пишуть логи. Код MIT, Capri/IP та деякі ресурси виключені. [README](https://github.com/kystt29/capricorn/blob/27e724d9eb155e70c85cc2d1889217ca6f1e4bc2/README.md), [voice defaults](https://github.com/kystt29/capricorn/blob/27e724d9eb155e70c85cc2d1889217ca6f1e4bc2/main.py), [LICENSE](https://github.com/kystt29/capricorn/blob/27e724d9eb155e70c85cc2d1889217ca6f1e4bc2/LICENSE) | **Пропозиція:** лише приклади для tray, тихого режиму й реакцій на стан ПК. Не копіювати desktop automation, cloud voice defaults або моделі безпеки: вони не відповідають B-12 consent/grants/approval межам. |
| [mochiiwuff/capri-desktop, cb33e87](https://github.com/mochiiwuff/capri-desktop/commit/cb33e87dfaee79cec8b4b0f737ca89e07b87ba4b) | Electron app для Claude Code/Codex/Antigravity hooks, work events, thinking/approval/error/success анімацій, permission notifications, mission report і PC/chat control. Linux пет плаває, window tracking зазначений Windows-only. Version 0.5.1 має PolyForm Noncommercial 1.0.0; README виключає character/art IP власників. [README](https://github.com/mochiiwuff/capri-desktop/blob/cb33e87dfaee79cec8b4b0f737ca89e07b87ba4b/README.md), [package](https://github.com/mochiiwuff/capri-desktop/blob/cb33e87dfaee79cec8b4b0f737ca89e07b87ba4b/package.json), [LICENSE](https://github.com/mochiiwuff/capri-desktop/blob/cb33e87dfaee79cec8b4b0f737ca89e07b87ba4b/LICENSE) | **Пропозиція:** корисні UX-ідеї — approval attention, task event phases, long-think reassurance, success/error reactions, tray, timeline/report. Не використовувати код/Capri assets. Hook та PC-control integration відкласти до окремих B-12 contracts/policies. |

## Першоджерело для Qt

Офіційний Qt for Python описує прозорість top-level widget через WA_TranslucentBackground; для X11 потрібні ARGB visual та compositing window manager. WindowStaysOnTopHint є запитом до віконного менеджера, не гарантією кожного WM. QSystemTrayIcon працює в Linux середовищах зі StatusNotifierItem або XEmbed і має isSystemTrayAvailable() для fallback. [Qt QWidget](https://doc.qt.io/qtforpython-6/PySide6/QtWidgets/QWidget.html), [Qt window flags](https://doc.qt.io/qtforpython-6/PySide6/QtCore/Qt.html), [Qt system tray](https://doc.qt.io/qtforpython-6/PySide6/QtWidgets/QSystemTrayIcon.html), [PySide6-Essentials](https://pypi.org/project/PySide6-Essentials/).

## Синтез і межі

- **Перевірений факт:** B-12 уже має stream chat, session/history, memory, consent, exact approval, cancellation/resume, voice status/mute, локальний owner-authenticated API та власний cybercat atlas.
- **Пропозиція:** desktop shell огортає ці API можливості, не створює другий agent. Анімація інформує користувача, не створює model/tool calls.
- **Вимога з brief/AGENTS:** local-first; permission/consent на контрольному шляху; один runtime-owner; mic/audio не запускається без явної дії; art має provenance.
- **Потребує перевірки:** X11 compositing/topmost/tray на цільовому хості; Wayland; desktop packaging; довгі streaming/error cycles. Огляд не підтверджує Windows/macOS сумісність.
