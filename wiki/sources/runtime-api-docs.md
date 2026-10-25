---
type: source
updated: 2026-10-25
status: selected_sections_read
sources: [raw/runtime-api-docs-2026-10-25/SOURCE.json]
tags: [ollama, transport, streaming]
---
# Native Ollama API: контракт transport

Прочитано вибрані розділи офіційної документації 25.10.2026. [Облік URL та меж](../../raw/runtime-api-docs-2026-10-25/SOURCE.json). HTML snapshot не збережено; точну попередню редакцію сторінок відтворити з цього обліку неможливо.

**Зовнішній факт:** REST stream передає partial content, окреме поле thinking та tool calls; потрібне накопичення частин повідомлення. B-12 за власною вимогою відкидає reasoning перед callbacks і durable logs. [Streaming](https://docs.ollama.com/capabilities/streaming).

**Зовнішній факт:** native tool-call example має `function.index`, `name`, object `arguments`; результат передається повідомленням role `tool` з `tool_name`. Це wire format, а не дозвіл на виконання. [Tool calling](https://docs.ollama.com/capabilities/tool-calling).

**Зовнішній факт:** `/api/chat` приймає messages, tools, options, stream і think; відповідь має terminal `done`/`done_reason` та token/duration metrics. [API](https://docs.ollama.com/api/chat).

**Межа:** документація не доводить поведінку локального Ollama 0.33.3 або точність admission. Task 4 потребує власних NDJSON/fault/cancel tests і real-model profile checks. [План реалізації](../project/implementation.md).
