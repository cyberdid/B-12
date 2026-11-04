---
type: feature
updated: 2026-11-04
status: implemented
sources: [src/b12/tui/app.py, src/b12/tui/pet.py, src/b12/tui/sprites.py, src/b12/tui/chrome.py, src/b12/tui/theme.py, src/b12/tui/preview.py, src/b12/tui/assets/provenance.json, tests/integration/test_tui.py, tests/unit/test_cybercat_sprites.py]
tags: [tui, cyberpunk, companion, cybercat, interface]
---
# Кіберпанковий TUI та кіберкіт

**Вимога власника (розмова 04.11.2026):** виразний красивий cyberpunk TUI, бічний virtual pet із реакціями на мишку та спілкування з B-12. Власник обрав кіберкота. Це окреме UI-доручення після зупинки попередньої великої реалізації.

## Наявна поведінка

**Перевірений факт:** Textual layout містить ліву навігацію, центральний chat/composer та праву companion-панель. Палітра — темний індиго, cyan, magenta та violet.

**Вимога й погодження власника (продовження розмови 04.11.2026):** якість як у прикріпленого об’ємного синього pixel-art робота, але кіт. Власник схвалив згенерований concept («мені нрав») і авторизував анімації («давай»). [Concept](../../src/b12/tui/assets/cybercat-concept.png) і [atlas](../../src/b12/tui/assets/cybercat-atlas.png) скопійовані з built-in `image_gen` без змін; SHA-256, розміри, походження й [prompt atlas](../../src/b12/tui/assets/atlas-prompt.txt) — у [provenance](../../src/b12/tui/assets/provenance.json). Точна model revision генератора не була відкрита інструментом.

**Замінено:** первинний програмно намальований 32×34 half-block кіт. Новий renderer бере 12 кадрів з RGBA atlas 1448×1086, 4×3 клітинки по 362×362. `textual-image 0.14.2` у Kitty використовує TGP, а в терміналі без image protocol — ANSI half-cell fallback з того самого зображення. Пропорції враховують фізичний розмір terminal cell; у компактному режимі залишається весь кіт. [Таблиця підтримки upstream](https://github.com/lnqs/textual-image#supported-terminals) виключає TGP/Sixel у GNOME Terminal; локальна VTE 0.76 не заявляє SIXEL (`vte_get_features`: `+BIDI +GNUTLS +ICU +SYSTEMD`).

Кіт кліпає, дихає, рухає хвостом, стежить за положенням курсора; клік або Ctrl+K викликає локальну реакцію «мурр» із сердечком. Фази typing/thinking/speaking/working/approval/success/error/cancelled відповідають UI та API events. Tool name показується в working phase. Ці реакції не створюють окремих model/tool calls і не зберігають pet data.

**Растрова анімація:** дихання — зсув на 2 native pixels без деформації; моргання — напівзакритий/закритий кадри; хвіст компонується як окрема registered область atlas і рухається також під час стеження за мишкою. Частота UI timer — 0,12 с. F8 припиняє ambient motion, але дозволяє клік, gaze й зміну стану розмови. Кеші decoded frames і terminal renderables мають межу 48 кожен; terminal cache звільняється при зміні розміру й unmount. TGP cleanup адресує тільки власний image id (`a=d,d=I,i=…`), за [специфікацією Kitty](https://sw.kovidgoyal.net/kitty/graphics-protocol/#deleting-images), і звільняє його дані; широкий delete upstream не використовується.

| Дія | Клавіша |
|---|---|
| Нова розмова | Ctrl+N |
| Пам’ять та підтвердження | Ctrl+P |
| Погладити | клік по коту або Ctrl+K |
| Навігація | F2 |
| Пауза анімацій | F8 |
| Скасувати хід | Esc |
| Вийти | Ctrl+Q |

**Компонування:** від 110 колонок видно всі три колонки; нижче навігація відкривається через F2 і згортається після вибору розмови. Кіт залишається збоку. На короткому екрані portrait компактніший; панель пам’яті прокручується. Після вибору сесії фокус повертається в composer, історія відкривається на останніх повідомленнях. Найкращий вигляд — truecolor terminal 120×36 або більше; 80×24 також перевірено. NO_COLOR не перевизначається застосунком.

## Запуск та перевірка

Реальний клієнт: `uv run --no-sync b12 tui` за вже запущеного `b12 serve`. Офлайн-перегляд: `uv run --no-sync python -m b12.tui.preview`; header явно показує «ДЕМО / БЕЗ СЕРВЕРА». У preview лише ephemeral sample data й scripted replies; немає мережі, реальної моделі чи host tools.

Для повної якості: [launcher](../../scripts/tui-cybercat) `./scripts/tui-cybercat --demo` (перегляд) або `./scripts/tui-cybercat` (живий API client). Локально встановлено офіційний Kitty 0.50.0 в `~/.local/opt/b12-visual/kitty.app`; стандартний термінал, PATH і desktop associations не змінювалися. Launcher підтримує `B12_KITTY`, використовує окремий `--config NONE` і прибирає `NO_COLOR` лише з дочірнього вікна для кольорових graphics placeholders. Звичайний запуск з NO_COLOR переходить на fallback.

**Докази:** [TUI tests](../../tests/integration/test_tui.py) використовують Textual Pilot для mouse hover/click, keyboard bindings, streaming phases, responsive layouts, navigation/focus та history scrolling. Окремий сценарій працює через справжній API stack із synthetic model transport та реальною file_write дією в temp directory. PTY smoke перевіряє запуск preview, SGR mouse reporting і вихід Ctrl+Q. [Рендер](../../docs/images/tui-cybercat.png) — синтетична розмова, не знімок приватної сесії.

**Додаткові докази растрової версії:** [sprite tests](../../tests/unit/test_cybercat_sprites.py) порівнюють справжні pixels для gaze, purr, ambient motion, незалежного хвоста та паузи, перевіряють aspect fit, bounded cache/resize/close і точний owned-image cleanup. Новий Pilot test порівнює видимий рендер для двох положень мишки та перевіряє cleanup при виході. [Знімок Kitty 144×44](../../docs/images/tui-cybercat-raster.png) отримано з реального вікна офлайн-preview до останнього доопрацювання незалежного хвоста. [Повноколірний APNG](../../docs/images/cybercat-motion.png) експортований на CPU з фінального renderer; це демонстрація станів, не запис TUI або живої розмови.

**Межі перевірки:** після повідомлення власника, що GPU зайнята іншими процесами, тестове вікно закрито. Фінальне доопрацювання хвоста перевірене на CPU, повторний native graphics прогін і native resize залишені до вільної GPU. Локальні LLM/voice/robotics тести в межах цієї UI-задачі не запускалися. Один повторний review-launch спіткнувся об повторне використання тимчасового Unix socket; це виправлено новим socket у тимчасовому review-wrapper. Постійний launcher remote-control socket не використовує.
