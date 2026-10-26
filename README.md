# B-12

Локальний ШІ-компаньйон з автобіографічною пам’яттю, доречною ініціативою, українською й англійською мовами та майбутньою фізичною присутністю через Reachy Mini.

**Стан на 26.10.2026:** у гілці `feat/b12-runtime` є робочий desktop runtime: пам’ять зі згодою й глобальним забуттям, lexical knowledge, змінний Ollama adapter (поточний кандидат — Bolt E4B), 13 реальних host tools під серверним контролем, agent loop і CLI. API/Web, автономність, голос і апаратна частина ще попереду; [поточний стан](wiki/project/status.md).

## Запуск CLI

Потрібні Ollama з alias `b12-bolt-e4b:q4km`, calibrated profile та pinned tokenizer assets (див. `config.example.toml`).

```bash
uv sync --extra dev          # або: uv pip install -e .
export B12_MODEL_PROFILE=$PWD/profiles/bolt-e4b-ollama-0.33.3.json
export B12_TOKENIZER_DIR=/absolute/pinned/tokenizer-assets
b12 doctor --json            # модель, профіль, сховища, pending purge
b12 init                     # owner + сесія CLI; --no-consent вимикає збереження пам’яті
b12 chat                     # інтерактивно; Ctrl-C скасовує поточний turn
b12 chat -m "…" --json       # один turn, машиночитний результат
b12 approvals | b12 approve <operation_id> | b12 resume <turn_id>
b12 memory remember|search|forget|pending …
b12 tools                    # каталог із capability та risk
b12 serve --port 8712        # локальний API лише на loopback
```

API: токен власника — у `$B12_STATE_DIR/api/owner.token` (0600), передається тільки заголовком `Authorization: Bearer …`. `POST /api/sessions`, `POST /api/chat` (NDJSON-стрім подій; розрив з’єднання скасовує turn), `/api/approvals`, `/api/memory`, `/api/guests` (гостьові токени зі scoped typed capabilities), `/api/control/consent`, `/api/turns/{id}/resume|cancel`, `/api/tools`, `/api/health`.

Коди виходу: 0 — готово, 1 — помилка, 2 — чекає approval, 3 — purge ще pending, 130 — скасовано. Стан зберігається в `$XDG_STATE_HOME/b12` (або `B12_STATE_DIR`). Режим `host_access="full"` дає моделі реальний доступ до файлів і команд у межах прав Linux вашого користувача; руйнівні дії (forget) потребують approval.

- [Індекс wiki](wiki/index.md) — точка входу до всіх матеріалів.
- [Аналіз master brief](wiki/project/analysis.md) — висновки, суперечності та критичний шлях.
- [Статус і наступний крок](wiki/project/status.md).
- [Результати тесту Bolt](wiki/project/bolt-first-test.md) і [відтворювані артефакти](benchmarks/bolt-e4b-smoke-2026-10-24/README.md).
- [Дорожня карта](wiki/project/roadmap.md) — етапи та докази завершення.
- [Оригінальний master brief](raw/B-12_Master_Project_2026-10-24.md) — незмінена копія наданого документа.
- [Правила роботи агента](AGENTS.md) та [журнал wiki](wiki/log.md).

Проєкт ведеться за [LLM Wiki Андрія Карпаті](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f): джерела зберігаються у `raw/`, висновки накопичуються у пов’язаних сторінках `wiki/`, правила підтримки описані в `AGENTS.md`. Markdown можна читати без спеціальних інструментів або відкрити цю теку в Obsidian.

Wiki цього проєкту — документація для розробки B-12. Майбутня пам’ять самого робота матиме власне сховище й політики; це окремі системи.

Зовнішні матеріали зберігають права й ліцензії своїх авторів. Ліцензію майбутнього власного коду ще не обрано.
