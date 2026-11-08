# Antigravity → B-12 TUI

Це необов'язковий workspace-level telemetry hook для B-12 Activity у наявному
Textual TUI. Він не є permission policy і не підключає desktop automation.

## Підключення вручну

1. Переконайся, що B-12 Python environment уже готовий і `uv` доступний. Wrapper
   запускає `uv run --offline --no-python-downloads --no-sync`: без інсталяції залежностей,
   завантаження Python або доступу до мережі. Якщо environment не підготовлений, hook
   поверне no-op response, але не запише Activity.
2. У `hooks.example.json` заміни `/absolute/path/to/B-12` на абсолютний шлях до цього
   checkout B-12. Скопіюй або вручну об'єднай його з `.agents/hooks.json` потрібного
   workspace; не перезаписуй існуючі hook definitions.
3. Переглянь конфіг у меню Hooks Antigravity і вмикай тільки якщо погоджуєшся з його
   локальною telemetry поведінкою.
4. Запусти B-12 server і TUI; відстеження з'явиться в Activity.

Приклад підключає лише `SessionStart`, `PostToolUse` і `PostInvocation`. B-12 повертає
документовані no-op envelopes для кожної події: `{}` для перших двох і порожні
`injectSteps`/`terminationBehavior` для `PostInvocation`. `PreToolUse` та `Stop` не
підключаються, бо їхній output керує дозволом або завершенням циклу.

`PostInvocation` — це завершення одного виклику моделі, не розмови. У TUI воно лишається
проміжною подією. Із payload зберігаються лише allowlisted metadata; prompt, `toolCall.args`,
transcript та абсолютні шляхи відкидаються. Для вимкнення прибери hook із workspace
`.agents/hooks.json`; глобальні налаштування не змінюються.
