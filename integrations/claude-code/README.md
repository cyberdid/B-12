# Claude Code → B-12 TUI

Це необов'язковий project-level telemetry hook. Він додає локальні події до панелі
Activity у вже наявному B-12 Textual TUI. Він не надсилає prompts до B-12, не
викликає tools і не видає permission decisions.

## Підключення вручну

1. Переконайся, що B-12 Python environment уже готовий і `uv` доступний. Wrapper
   використовує `uv run --offline --no-python-downloads --no-sync`; цей виклик не
   встановлює залежності, не завантажує Python і не звертається до мережі. Якщо environment
   не підготовлений, hook тихо пропустить telemetry.
2. У `hooks.example.json` заміни `/absolute/path/to/B-12` на абсолютний шлях до цього
   checkout B-12. Збережи придатний для твого проєкту фрагмент у `.claude/settings.json`.
   Якщо файл уже має `hooks`, об'єднай події вручну, не перезаписуй його.
3. Переглянь diff і довіряй project hooks лише в репозиторії, де погоджуєшся їх запускати.
4. Запусти B-12 server і TUI звичайним способом. Події з'являться в Activity; очистка
   Activity у TUI видаляє тільки локальні UI metadata.

Hook зчитує JSON зі stdin, але B-12 зберігає лише allowlisted lifecycle, hashed session
ID, project basename, tool name, короткий status і час отримання. Prompt, `tool_input`,
transcript та абсолютні шляхи відкидаються. Команда завершується з кодом 0 без output,
тому Claude зберігає звичайний permission flow.

Щоб вимкнути інтеграцію, прибери додані event entries з project `.claude/settings.json`.
Глобальні `~/.claude/settings.json` не змінюються.
