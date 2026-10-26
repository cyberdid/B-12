# Task 9 — local API, auth, control channel

Coordinator/implementer: Claude Code (Claude Opus 5.5), 26.10.2026. BASE `4d7b7c0`, commit `9632cdc`.

Routes: `/api/health` (public, `{"ok":true}` only), `/api/tools`, `/api/sessions`, `/api/sessions/{id}/history`, `/api/chat` (NDJSON stream), `/api/turns/{id}/resume|cancel`, `/api/memory` (GET q / POST / DELETE id → purge receipt 200/202), `/api/approvals` (+ `/{op}` decide), `/api/guests` (+ DELETE revoke), `/api/control/consent`. `/api/goals` → Task 11 (не імітується). Plan `/api/tasks/{id}/cancel` замінено на turn-level `/api/turns/{id}/cancel` (cancellation одиниця — turn).

Rulings:
- Токени лише в `Authorization: Bearer`; у ControlStore тільки HMAC digest. Owner token bootstrap у `state_dir/api/owner.token` (0600, dir 0700), перевипуск якщо файл зник/невалідний.
- Guest capabilities ⊆ {time.read, memory.read, memory.write, knowledge.read, system.read}; без full execution, filesystem/process/network/forget. Гість може видаляти свої memory без capability (право на видалення), revoke лише власного consent; надати consent — тільки owner.
- Guard: Host allowlist (127.0.0.1:port, localhost:port) проти DNS rebinding; Origin обов’язково з allowlist для не-GET, якщо заголовок є; тіла >64 KiB → 413; pydantic `extra=forbid` → 422 для actor/consent/grant/owner у тілі.
- Усі routes async (same-thread SQLite). Disconnect: finally стріму ставить cancel; turn task завершується сам (без await у скасованому anyio scope).
- `b12 serve` відмовляє не-loopback host.

Evidence: 11 security + 5 ASGI integration + 1 live uvicorn process test (disconnect → turn cancelled, нічого не збережено, наступний turn працює). 8 мутацій (disconnect cancel, host, origin, body limit, guest consent, session ownership, guest caps, owner-only approvals) — усі спіймані. Full 382 passed / 2 skipped, Ruff clean.
Live real Bolt (`.venv/bin/b12 serve`, temp state): stream tool_started/result current_time → completed, відповідь `2026-10-26T05:18:26Z` збіглася з `date -u`; без токена 401; чужий Origin 403.
Limits: немає TLS (лише loopback); rate limiting відсутній; owner token ротація — видаленням файлу + restart; Web UI (Task 10) ще не існує.
