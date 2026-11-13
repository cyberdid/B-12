---
type: topic
updated: 2026-11-08
status: compiled
sources:
  - src/b12/cli.py
  - src/b12/cli_remote.py
  - src/b12/api.py
  - src/b12/service.py
  - tests/e2e/test_cli_server.py
tags: [cli, server, runtime-lock, api, architecture]
---

# CLI і запущений `b12 serve` (A-02)

**Правило.** Запущений `b12 serve` — єдиний власник активного runtime. Коли він працює, CLI
звертається лише до його API. Коли він не працює, CLI відкриває локальний runtime, але тільки
після того, як отримав exclusive lock на `state_dir/runtime.lock`. Два незалежні runtime, що
змінюють один стан, не можуть існувати одночасно.

**Визначення режиму.** `cli.py:main` намагається взяти `RuntimeLock` без очікування:

- лок вільний → локальний режим; лок тримається до завершення команди;
- лок зайнятий (сервер або відновлення) → `run_remote`:
  - API недоступний → `{"error": "server_unavailable"}`, код виходу 4; прямого доступу до баз немає;
  - команди без API → `{"error": "requires_stopped_server"}`, код виходу 5.

`serve` і `tui` не беруть лок CLI: `serve` бере `RuntimeLock` сам у lifespan, `tui` говорить з API.

## Зіставлення команд з API

| Команда CLI | Режим через сервер | Ендпоінт |
|---|---|---|
| `status`, `tools`, `approvals` | так | `GET /api/status`, `/api/tools`, `/api/approvals` |
| `approve`, `deny` | так | `POST /api/approvals/{op}` |
| `memory remember`, `search`, `forget` | так | `POST /api/memory`, `GET /api/memory`, `DELETE /api/memory/{id}` |
| `memory pending` | **ні** | немає ендпоінта |
| `goals list`, `pause`, `resume`, `abandon` | так | `GET /api/goals`, `POST /api/goals/{id}/status` |
| `goals add` | **ні** | `GoalBody` вимагає явного списку інструментів; локальна типова (можливості власника без `process.sudo`) ще не перенесена |
| `quiet`, `stop` | так | `POST /api/attention` |
| `backup create`, `list` | так | `POST /api/backups`, `GET /api/backups` |
| `backup verify`, `restore`, `delete` | **ні** | немає ендпоінтів |
| `voice status`, `mute`, `unmute` | так | `GET /api/voice/status`, `POST /api/voice/mute` |
| `voice say`, `listen`, `--chat`, `--file` | **ні** | `/api/voice/tts` і `/api/voice/asr` є, але мікрофон і динамік належать процесу |
| `chat -m` | так | `POST /api/chat` (сесія `GET /api/cli-session`) |
| `chat` без `-m` (інтерактивно) | **ні** | потрібен потік вводу з сервером |
| `resume` | так | `POST /api/turns/{id}/resume` |
| `init`, `session clear`, `autonomy`, `mcp …`, `doctor` | **ні** | немає ендпоінтів; `doctor` має частину в `/api/status` |

Додано в цьому кроці: `GET /api/cli-session` (сесія CLI власника, щоб `chat` продовжував ту саму історію).

Desktop-клієнт додатково використовує owner-scoped `GET /api/turns/{id}/status`: endpoint повертає лише ID ходу та факт, чи він зараз активний. Це дає змогу безпечно розблокувати чат після втрати NDJSON-потоку; статус не розкриває текст, інструменти чи дані іншого актора.

## Перевірено

- `tests/e2e/test_cli_server.py`:
  1. `memory forget` через CLI під час активного ходу, який сервер тримає відкритим (`hang`), повертає `complete`, хід завершується, у stderr немає помилок бази.
  2. Лок зайнятий, API недоступний → код 4 і `server_unavailable`, без доступу до баз.
  3. Команда без API при запущеному сервері → код 5 і `requires_stopped_server`.
- Мутація: примусовий локальний режим при запущеному сервері ламає тест 1 (локальний `memory remember` падає на зайнятому стані).
- Повний набір: 564 пройшли, 3 пропущено.

## Не зроблено

Команди з таблиці «ні» поки працюють тільки без запущеного сервера. Для повного паритету потрібні
ендпоінти для `memory pending`, `goals add`, `backup verify/restore/delete`, `session clear`, `autonomy`, `mcp`,
інтерактивного `chat` і голосових команд з мікрофоном.
