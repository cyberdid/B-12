# TUI Models Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** switch Capri's model between turns from the TUI (local Ollama or a subscription CLI), see its state and load progress, Capri companion, compact tool calls with Ctrl+O, and a failure log.

**Architecture:** in-process switch (spec approach A): a model catalog and `ModelSwitch` on the server swap the agent's model, settings and context builder under `model_lock`; cloud models are `CliModel`; the TUI calls new owner-only API routes.

**Tech Stack:** Python 3.12, FastAPI, Textual 8, httpx, pytest (`scripted_ollama`, headless `App.run_test`).

**Spec:** `docs/superpowers/specs/2026-11-24-tui-models-design.md`

## Global Constraints

- Owner only for every new route; the model text never switches models.
- Cloud: `num_ctx` 200000, `output_tokens` 16384; subscriptions through CLIs only, no API keys.
- Tools always run locally under existing grants.
- No GPU use in tests; TUI tests are headless with a fake client.

## Review Focus

- Switching while a turn runs → waits for `model_lock`, the running turn finishes on the old model.
- Unknown model id → 404, nothing changes.
- CLI missing or failing (quota, exit 1) → `ModelError`, the turn fails cleanly with a readable code.
- A local model not downloaded → status `pulling` with percent, then `ready`.
- A Codex round that runs its own command → rejected (`invalid_round`), never executed.

---

### Task 1: `CliModel` and shared bridge helpers

**Files:** Create `src/b12/cloud_model.py`; Modify `evals/subscription_bridge.py` (import the moved
helpers, keep their names); Test `tests/unit/test_cloud_model.py`.

**Interfaces — Produces:** `class CliModel: __init__(self, backend: str, model: str, *, timeout_s: float = 230, runner=None)`; `async chat(self, request, *, on_delta=None, cancel=None, deadline=None) -> ModelReply`; `async unload(self, **_) -> bool` (returns True); constants `SCHEMA`, `PREAMBLE`; `split_messages(body: dict) -> tuple[str, str]`; `codex_events_ok(text: str)`; `codex_overrides(config_path)`; `ask_backend(backend, model, body, *, timeout=200, codex_config=None) -> tuple[dict, tuple[int, int]]`. `runner` (async `(argv, stdin_text, cwd, timeout) -> str`) is injectable for tests.

- [ ] Tests: claude JSON → `ModelReply(content, tool_calls=[ToolCall])`; tool `arguments_json` not an object → `ModelError("invalid_tool_call")`; codex stream with a `command_execution` item → `ModelError("invalid_round")`; runner raising (exit 1 / quota text) → `ModelError("transport_error")`; `on_delta` gets the content once; cancel set → `ModelError("cancelled")`; agy `response` JSON parsed. Bridge tests (`tests/unified/test_subscription_bridge.py`) still pass.
- [ ] Implement; run; commit `feat(model): CliModel runs a subscription CLI as Capri's model`.

### Task 2: catalog, switch and status

**Files:** Create `src/b12/model_switch.py`; Modify `src/b12/runtime.py` (attach `runtime.models = ModelSwitch(runtime)`, restore `active_model` from meta); Test `tests/integration/test_model_switch.py`.

**Interfaces — Produces:** `@dataclass(frozen=True) class ModelChoice: id, label, kind ("local"|"cloud"), backend ("ollama"|"codex"|"claude"|"agy"), model, location ("ноутбук"|"хмара"), warning: str = ""`; `ModelSwitch.catalog() -> list[ModelChoice]` (async), `ModelSwitch.active_id: str`, `async switch(choice_id: str) -> ModelChoice` (KeyError unknown), `async status() -> dict` (`{"id","state","progress","elapsed_s","vram_mb","detail"}`).

- [ ] Tests (fake Ollama answering `/api/tags`, `/api/ps`, `/api/pull` stream, `/api/generate`): catalog lists local models with profiles and cloud CLIs found on a patched PATH; switch to cloud swaps `agent.model` to `CliModel` and `settings.num_ctx == 200000`; switch waits for `model_lock`; switch back restores `OllamaModel` and the profile's model; unknown id → KeyError; status `pulling` with progress then `ready`; `active_model` persists across `open_runtime`.
- [ ] Implement; run; commit `feat(model): model catalog and between-turn switching`.

### Task 3: API and client

**Files:** Modify `src/b12/api.py`, `src/b12/tui/client.py`, `src/b12/cli.py` (`b12 feedback`); Test `tests/integration/test_api_models.py`.

**Interfaces — Produces:** routes in the spec; `ApiClient.models() -> dict`, `ApiClient.switch_model(id) -> dict`, `ApiClient.model_status() -> dict`, `ApiClient.feedback(turn_id, session_id, note) -> dict`.

- [ ] Tests: guest token → 403 on all four; switch to unknown → 404; feedback appends a JSONL line with `model_id`; client methods hit the right routes (httpx `MockTransport`).
- [ ] Implement; run; commit `feat(api): model switching and feedback routes`.

### Task 4: TUI

**Files:** Modify `src/b12/tui/app.py`, `src/b12/tui/chrome.py`, `src/b12/tui/pet.py` (remembered skin), `src/b12/tui/theme.py`; Create `src/b12/tui/models.py` (picker screen, status line formatting); Test `tests/integration/test_tui.py`.

- [ ] Tests (FakeClient gains `models`, `switch_model`, `model_status`, `feedback`): header shows `◆ gemma4:12b · ноутбук · готова`; cloud shows `☁`; loading shows a bar with percent; F3 opens the picker and Enter switches; `/model <id>` switches without sending a chat; F4 returns to the previous model; Ctrl+O expands all tool collapsibles and collapses them again; a new tool call during detail mode is expanded; F10 + note calls `feedback` with the last turn id; skin choice remembered across app instances (tmp state dir).
- [ ] Implement; run all TUI tests; commit `feat(tui): model switcher, compact tool calls, Capri, failure log`.

### Task 5: Record

- [ ] Wiki status / log; full test suite; ruff; final whole-branch review; fix Critical/Important.
