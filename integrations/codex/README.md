# Codex → B-12 TUI

Це необов'язковий project-level telemetry hook. Він додає локальні lifecycle-події до
Activity у наявному B-12 Textual TUI й не змінює Codex allow/deny decisions.

## Підключення вручну

1. Переконайся, що B-12 Python environment уже готовий і `uv` доступний. Wrapper
   використовує `uv run --offline --no-python-downloads --no-sync`: залежності та Python
   не встановлюються, мережеві звернення не виконуються. Якщо environment не підготовлений,
   hook тихо пропустить telemetry.
2. У `hooks.example.json` заміни `/absolute/path/to/B-12` на абсолютний шлях до цього
   checkout B-12. Скопіюй конфіг до `.codex/hooks.json` у потрібному project repo.
   Якщо такий файл уже є, об'єднай поля вручну, не перезаписуй існуючі hooks.
3. Переглянь конфігурацію в Codex `/hooks`; окремо довіряй новий або змінений hook.
4. Запусти B-12 server і TUI. Activity надходить через локальний SQLite spool і
   очищається окремо від B-12 пам'яті.

Зі stdin приходить provider JSON, але зберігається тільки allowlisted metadata:
lifecycle, hashed session ID, project basename, tool name, короткий status і час
отримання. Prompt, arguments, transcript і абсолютні шляхи відкидаються. Команда
повертає успішний exit без decision JSON; штатна permission flow Codex лишається власною.

Щоб вимкнути інтеграцію, прибери додані entries з project `.codex/hooks.json`.
Глобальні `~/.codex/hooks.json` і `~/.codex/config.toml` не змінюються.
