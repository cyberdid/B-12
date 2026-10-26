# Task 8 — owner CLI

Coordinator/implementer: Claude Code (Claude Opus 5.5), 26.10.2026. BASE `bddd571`, commit `964709b`.

Commands: `b12 init [--no-consent]`, `doctor [--json]`, `chat [-m TEXT] [--json] [--timeout]`, `resume TURN`, `approve/deny OP`, `approvals`, `memory remember|search|forget|pending`, `session clear`, `tools`. Entry point `b12 = b12.cli:main`; settings — TOML (`--config` або `$XDG_CONFIG_HOME/b12/config.toml`) + B12_* env override.

Rulings:
- Локальний CLI = owner control channel. Owner і default session зберігаються в ControlStore `meta`; `init` за замовчуванням consent=True (явний `--no-consent`). Cost if wrong: owner мусить запустити `init --no-consent` повторно на новому state.
- Кожен виклик chat створює task і grant (ttl timeout+1h) за `host_access`: full → усі capabilities + full_execution; read_only; none.
- `chat` виконує `purge.resume()` до першого turn (startup recovery).
- `serve`/`eval` не зареєстровано як фейкові команди: вони належать Task 9/14.
- Approval queue (`ControlStore.pending_approvals`) повертає лише generated IDs і trusted tool names, без аргументів.

Evidence: 11 subprocess e2e tests (`python -m b12.cli`, реальний loopback HTTP Ollama stand-in, temp state): doctor uninit→ok; JSON turn із реальним файлом; memory між окремими процесами + forget; approval між процесами (exit 2 → approve → resume); інтерактивна розмова з історією; SIGINT → exit 130, стан цілий, наступний turn працює; недоступна модель → `transport_error`; відсутній profile → `profile_invalid`; каталог 13 tools; startup завершує pending purge; entry point declared. Мутації: no SIGINT handler, no purge resume (спершу НЕ ловилась → додано тест → ловиться), init not idempotent, approve-as-deny — усі спіймані. Full suite 361 passed / 2 skipped; Ruff clean.
Live (real Bolt, installed `.venv/bin/b12`, temp state): doctor before init ok=false/model reachable digest match; init; doctor ok, 13 tools; `chat -m` file_write+file_read completed, файл на диску «Привіт від B-12», 8.8 s wall включно із запуском процесу; interactive turn чесно відповів, що імені не знає.
Not covered: `uv sync` у повністю чистому середовищі (перевірено editable install у наявному venv), людська оцінка UX.
