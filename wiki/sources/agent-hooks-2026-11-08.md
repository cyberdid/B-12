---
type: source
updated: 2026-11-08
status: checked-primary-docs-no-archived-snapshot
sources: [raw/source-manifest.json]
tags: [agent-hooks, claude-code, codex, antigravity, integration]
---
# Lifecycle hooks для coding agents

## Джерела і межі перевірки

Перевірено 08.11.2026 безпосередньо офіційні сторінки документації:

| Продукт | Першоджерело | Перевірені розділи |
|---|---|---|
| Claude Code | [Hooks reference](https://code.claude.com/docs/en/hooks) | події життєвого циклу, JSON input, команди hook, decision control і security |
| Codex | [Hooks](https://learn.chatgpt.com/docs/hooks) | конфігурація, lifecycle events, JSON з stdin, можливість впливу output/exit code на дозвіл |
| Antigravity | [Hooks](https://antigravity.google/docs/hooks) | App/CLI/IDE workspace configuration, supported events, camelCase input/output contract, event-specific decision behavior |

**Межа:** raw snapshot сторінок до `raw/` не збережено. Перевірено лише перелічені офіційні сторінки й наведені нижче частини; це не runtime acceptance конкретних установлених версій coding agents і не повний аудит усіх hook schemas.

## Підтверджені факти

- **Перевірений факт:** усі три системи надають lifecycle hooks або command hooks, які можна використати для сигналів про старт/завершення сесії та tool activity. Codex command hooks отримують один JSON object через stdin; у схемі є `session_id`, `cwd`, `hook_event_name` та, для подій tool use, `tool_name` і `tool_input`.
- **Перевірений факт:** hook output може змінювати перебіг виконання. Зокрема, Codex `PermissionRequest` підтримує allow/deny decisions; Claude `PreToolUse` має decision control; Antigravity hooks можуть виконувати команди в агентському циклі. Тому B-12 telemetry adapter має повертати успіх без decision JSON і без зміни input.
- **Перевірений факт:** Claude `UserPromptSubmit` payload містить текст prompt, а інші події можуть містити `tool_input`, transcript paths, assistant message або повідомлення. Інтеграційний адаптер має явно відкинути ці поля до запису.
- **Перевірений факт:** Claude Code підтримує project hooks у `.claude/settings.json`; Codex знаходить project hooks у `<repo>/.codex/hooks.json` або project `.codex/config.toml` лише коли цей config layer trusted; Antigravity workspace hooks лежать у `.agents/hooks.json`. Для Codex документація вимагає review/trust hook-джерела до запуску. B-12 надає лише opt-in project-local приклади та не створює/змінює ці config файли автоматично.
- **Перевірений факт (повторно звірено 08.11.2026):** приклад Codex підключає лише документовані `SessionStart`, `UserPromptSubmit`, `PreToolUse`, `PostToolUse`, `PermissionRequest`, `Stop` і `SessionEnd`. `Notification` не включено, бо його немає в перевіреному переліку Codex hook events. Це межа шаблону, не runtime-висновок про те, як конкретна встановлена версія обробляє невідому подію.
- **Перевірений факт (повторно звірено 08.11.2026):** Antigravity надсилає JSON через stdin із camelCase полями `conversationId`, `workspacePaths` (масив абсолютних шляхів), `transcriptPath`, `artifactDirectoryPath`, `modelName` і `lastUserInput`. У подіях інструментів ім'я лежить у `toolCall.name`, деталі в `toolCall.args`; `PostToolUse` має optional `error`. Payload не має спільного `hook_event_name`, тож hook-приклад має передати назву події окремим CLI-параметром. Зберігати можна лише хеш `conversationId`, basename першого workspace та allowlisted tool name; решту полів відкидати.
- **Перевірений факт:** Antigravity `PreToolUse` вимагає `decision` і може дозволити/заблокувати/запросити дію; `Stop` також вимагає decision і може продовжити цикл. Ці події не підключати до telemetry hook. Для безпечних telemetry прикладів використовувати тільки `SessionStart`, `PostToolUse` і `PostInvocation`; останні два мають визначений документацією no-op JSON output (`{}` та порожні `injectSteps`/`terminationBehavior`). Не підмінювати цей no-op рішенням про доступ.
- **Інженерна межа:** Antigravity `PostInvocation` означає завершення одного виклику моделі, а не всієї розмови/turn. Без `Stop` telemetry може показати останню модельну подію та тривалість спостереження, але не має позначати сесію завершеною.
- **Межа перевірки:** назви project config layers, payload fields і no-op outputs звірено з офіційною документацією, але не з фактичними встановленими Claude Code/Codex/Antigravity runtimes; delivery/exit semantics конкретних локальних версій ще потребують окремої інтеграційної перевірки.

## Інженерна пропозиція для B-12

**Пропозиція:** нормалізувати provider події до малого telemetry контракту: `source`, opaque session ID, подія, час, basename проєкту, tool name і короткий статус. Не зберігати prompts, tool arguments, console output, transcript content чи абсолютні шляхи. Зберігати їх локально окремо від пам’яті B-12; TUI показує timeline і агрегований звіт, але hook не може приймати дозволи або викликати інструменти.

Це є проектною межею B-12, а не властивістю зовнішніх продуктів. Зміни їхніх hook схем у майбутньому потребуватимуть повторної перевірки перед оновленням adapter.
