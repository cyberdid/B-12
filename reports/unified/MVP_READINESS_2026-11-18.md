# Capri MVP — поточна готовність

Зріз `36d557d83ce2f44f694cea5d19939031c630a471`; ціль — компактний desktop Capri, локальний runtime, чат, пам'ять за згодою і контрольоване використання tools. Це перевірка готовності, не приймання продукту.

## Встановлено

- Ollama слухає loopback `127.0.0.1:11434`; локальний перелік моделей включає `gemma4:12b` і `b12-bolt-e4b:q4km`. Перевірка переліку не завантажувала ваги і не доводить inference.
- Локальні profile та tokenizer directory для `gemma4:12b` присутні; їхня відповідність встановленій моделі не перевірена в цьому проході.
- На GPU RTX 4060 Laptop 8 GB під час огляду було використано 245 MiB із 8188 MiB. Це моментальний стан, не гарантія доступності VRAM при запуску.
- На `127.0.0.1:8712` у момент перевірки слухача не було; `b12.service` у user systemd — inactive. Не зроблено висновків про інші можливі порти чи процеси.
- У наявному B-12 venv немає PySide6; у загальному системному Python його також не знайдено. Графічний desktop-клієнт не готовий до запуску в цих середовищах.
- Спроба `uv sync --frozen --offline --extra desktop --extra dev --python /usr/bin/python3.12` у новому worktree не завершилася: необхідний locked `pydantic-core` відсутній у локальному cache. Це не доказ недоступності пакетів через мережу. Робоча інсталяція користувача не змінювалася.
- Для поточного baseline: 771 passed, 8 skipped, 1 failed у наявному venv без desktop extra; деталі в `baseline/pytest-2026-11-18.txt`. Desktop CLI закономірно повідомляє про відсутній extra раніше, ніж потрапляє до перевірки токена; тест очікує інший код. Це не доводить дефект пріоритету повідомлень для користувача.

## MVP acceptance, яку ще треба виконати

1. Підготувати ізольоване середовище з locked desktop dependencies і зафіксувати їх версії.
2. Перевірити відповідність configured model, tokenizer, profile і Ollama; не змінювати production memory для тесту.
3. Запустити реальний сервер і компактний Qt client у тестовому state; зробити видиму перевірку базового діалогу, збереження й recall синтетичної пам'яті, tool read/search, approval, cancellation і повернення після context overflow.
4. Перевірити internet search окремо, з посиланнями на джерела і повідомленням про недоступність мережі; live network actions тільки в належно ізольованому тесті.
5. Перевірити особисті дані й side effects через окремий synthetic actor/state; заміряти час і VRAM для обраної моделі. Після реального приймання описати запуск і відомі обмеження.
6. Узгодити інтеграцію робочої гілки з поточним checkout, зберігши незакомічені дослідження власника. До цього незавершені U0–U10 не називати готовим MVP.

Голос, hardware acceptance, автономна ініціатива і повна behavioral continuity потребують окремого scope/перевірок. Наявні документи U0/U1 і попередній trace не є готовою реалізацією всього плану.

## Продовження перевірки 18.11.2026

- Повний детерміністичний suite на фінальному evaluation diff: **879 passed, 4 skipped, 175.83s**; opt-in real-model/Docker checks лишаються окремими gates. Сирий лог і hash — у [acceptance ledger](MVP_ACCEPTANCE_LEDGER.md).
- Виправлено unsafe entry path у single-scenario runtime CLI: `--runtime-dir` без sandbox marker тепер зупиняється до завантаження сценарію. Додано regression test і README пояснення. Marker не є security boundary; використовується bubblewrap wrapper для OS ізоляції.
- Це не закриває готовність: реальний Bolt directory task лишається 2/3, 92 historical scenarios не пройдені повторно, чотири default-suite tests opt-in, а real desktop/UI, voice, hardware, longitudinal і model-swap gates мають окрему acceptance.
- Виняток до попереднього підрахунку: REL-08 тепер повторно перевірений без моделі на синтетичному state. Дві перевірки — snapshot restore і non-resurrection — пройшли; content-event-log критерій є відомим oracle mismatch. Стан записано в matrix як `ORACLE_MISMATCH`, а 91 сценарій лишився `NOT_RETESTED`; див. [route audit](SCENARIO_EXECUTION_PATH_AUDIT.md).

## Оновлення того ж дня

Ізольований `.venv` цієї гілки підготовлено через `uv sync --frozen --extra desktop --extra dev` із доступом до package registry; встановлено Qt 6.12.0. Попередній desktop CLI test пройшов; desktop/API/auth subset — 100 passed. Оригінальний venv користувача не змінено. В окремому тимчасовому state `doctor` перевірив локальний Ollama 0.33.3 і digest Gemma 12B (`ok=true`), один текстовий хід завершився успішно; GPU inference було запущено. Це не тест усіх MVP вимог. Пріоритет acceptance уточнено власником у [MVP_ACCEPTANCE_LEDGER.md](MVP_ACCEPTANCE_LEDGER.md).
