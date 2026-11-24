# TUI: model switching, Capri, compact tool calls, failure log — design, 24.11.2026

## Why

Owner, 24.11.2026: «в TUI треба додати перше те, щоб була змога на ходу перемикати моделі… також
вибирати frontier моделі через codex, claude, agy… щоб я бачив прогрес завантаження… на
альтернативу кота я б ще хотів бачити вигляд Capri… системні виклики… як в opencode… через ctrl+o».
The frontier model is the full Capri — same session, memory and tools (owner: «А звичайно»;
ADR-023). TUI tests run on the laptop GPU, never Colab. Owner left the rest to Claude («роби
якнайкраще»; «дороби все до кінця»), so the calls below marked *Claude's call* are delegated.
Agreed direction adds a log of real failures that become scenarios.

## Goals

1. Switch the model between turns from the TUI: local Ollama models with a profile, and frontier
   models through the owner's subscription CLIs (Codex, Claude, agy/Gemini).
2. See which model thinks, where (laptop / cloud) and its state, including load progress.
3. Capri as the companion figure; the cat stays one key away.
4. Tool calls as one compact line each; Ctrl+O shows every detail.
5. Mark a bad turn with a note; the log feeds new scenarios.

Non-goals: new agent behaviour; mid-turn model changes; API keys (subscriptions only); remote
access. Anti-goals: the model text never switches models (control path only); a cloud model must
never be shown as local.

## Approaches (model switching)

- **A. In-process switch (chosen, Claude's call).** The server keeps a model catalog and swaps
  `agent.model` / `agent.settings` / `agent.builder` between turns under `model_lock`; cloud models
  are a `CliModel` that calls the CLI per model round (the eval bridge's method, moved into
  `src/b12`). One process, no fake Ollama.
- B. Restart `b12 serve` on every switch — loses the "on the fly" goal and in-flight state.
- C. Point the runtime at the eval bridge (a fake Ollama) — works in evals, but fakes provider
  metadata and lives in `evals/`.

## Design

**Cloud model** — `src/b12/cloud_model.py`: `CliModel(backend, model)` with the `OllamaModel.chat`
signature, returning `ModelReply`. Prompt building, the JSON answer schema, Codex event checks and
the Codex/Claude/agy command lines move here from `evals/subscription_bridge.py`, which imports
them (one implementation). The reply text is emitted once through `on_delta`. Tools still run
locally under the same grants. Context for cloud models: `num_ctx` 200000, `output_tokens` 16384
(owner decision 18.11.2026); token counting keeps the local profile (approximate; the CLI does not
report it).

**Catalog and switch** — `src/b12/model_switch.py`:
- Local choices: Ollama `/api/tags` models that have a profile in `~/.local/share/b12/profiles`
  (matched by `model`) and its tokenizer dir; a model over the GPU memory is still listed with a
  warning (*Claude's call*: 26b/31b do not fit 8 GB).
- Cloud choices: `codex` → gpt-6-luna, `claude` → Opus and Sonnet, `agy` → Gemini (default model),
  listed when the CLI is on PATH (*Claude's call*).
- `switch(id)`: waits for `model_lock`, swaps the three agent fields, records the choice in control
  meta `active_model` so it survives restarts; a local switch starts a warm-up task.
- Status: `ready` / `loading` (elapsed, VRAM from `/api/ps`) / `pulling` (percent from `/api/pull`
  when the model is not downloaded) / `error` / `unavailable`; cloud is `ready` when its CLI exists.

**API** (owner only): `GET /api/models`, `POST /api/models/active {"id"}`,
`GET /api/models/status`, `POST /api/feedback {"turn_id", "session_id", "note"}` →
`state_dir/feedback.jsonl` with the active model id and time; `b12 feedback` lists it.

**TUI**:
- Header second line: `◆ gemma4:12b · ноутбук · готова` or `☁ gpt-6-luna · Codex · хмара`; while
  loading a bar `▓▓▓░░ 43% · 12 с · 6.1 ГБ`.
- `F3` or `/model` opens the picker (grouped Локальні / Хмарні, cloud marked ☁); `/model <id>`
  switches directly; `F4` returns to the previous model.
- Tool calls: one collapsed line `● name  summary  ✓/✗/…`; `Ctrl+O` toggles details for every call
  (arguments and results expanded); new calls follow the current mode.
- Companion: Capri by default when its local pack exists; the choice (`F9`) is remembered in
  `state_dir/tui.json` (*Claude's call*).
- `F10` marks the last turn: a note field, sent to `/api/feedback`.

## Left to the builder

Widget layout details, polling interval (1 s while loading, 10 s otherwise), exact wording.
