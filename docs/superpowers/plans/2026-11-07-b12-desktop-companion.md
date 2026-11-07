# B-12 Desktop Companion Implementation Plan

> **For agentic workers:** Execute inline in this session. Steps use checkbox syntax for tracking.

**Goal:** Add an optional native desktop cybercat and chat client for the authenticated B-12 runtime.

**Architecture:** A PySide6-Essentials Qt Widgets client connects to the existing owner-authenticated loopback API. API calls and streaming run in worker threads; B-12 remains the sole owner of models, tools, memory, permissions, and runtime state.

**Tech Stack:** Python 3.12–3.13, optional PySide6-Essentials, HTTPX, Qt Widgets, pytest, Ruff.

**Spec:** docs/superpowers/specs/2026-11-07-b12-desktop-companion-design.md

## Global Constraints

- Desktop is optional; standard CLI/TUI/API installs must not import Qt.
- Default API URL is the current B-12 loopback URL; desktop never starts the server/model.
- Reuse existing owner token; never print, copy, or persist it.
- Voice capture and playback remain disabled in this release.
- Add no host tool, permission grant, global hook, screenshot, window tracking, or OS automation.
- Use the B-12 cybercat asset; copy no Capri code/art.
- Remote I/O runs outside Qt GUI thread; Qt signals update widgets.
- UI works when the system tray is unavailable.

---

### Task 1: Optional dependency and authenticated API client

**Files:** Modify pyproject.toml and uv.lock. Create src/b12/desktop/__init__.py, src/b12/desktop/client.py, tests/desktop/test_client.py.

**Interfaces:**
- DesktopApiClient(base_url, token) owns a synchronous HTTPX client with trust_env=False.
- call(method, path, **kwargs) raises DesktopApiError with a stable code for HTTP/transport errors.
- stream_turn(session_id, text, persist, on_event) parses NDJSON, invokes on_event(event), and returns the final result.
- Methods cover health, owner identity, sessions/history, approvals/decisions, resume/cancel, exact turn status, consent, memory CRUD, service status, voice status/mute, and CLI session.

- [x] Write tests first for bearer auth, requested API URL, malformed NDJSON, final-result parsing, HTTP errors, and transport errors using httpx.MockTransport.
- [x] Run the tests and confirm expected failures because the client module is missing.
- [x] Add optional desktop extra PySide6-Essentials>=6.8,<7 and run uv lock.
- [x] Implement the client with no Qt import and no direct state/database access.
- [x] Run uv run --locked --extra dev --extra tui --extra desktop pytest tests/desktop/test_client.py -q.

### Task 2: Animated cybercat overlay and phase mapping

**Files:** Create src/b12/desktop/cat.py and tests/desktop/test_cat.py. Reuse src/b12/tui/assets/cybercat-atlas.png and its provenance.

**Interfaces:**
- pose_for(phase, frame, look_x, look_y) -> int maps presentation states to existing atlas cells.
- CyberCatOverlay(QWidget) emits open_chat and position_changed; menu callback is injected.
- set_phase(phase, detail=""), track_pointer(point), and toggle_motion() never call model/API.

- [x] Add failing tests for state-to-pose mapping, pointer dead-zone gaze, atlas dimensions/alpha, drag position signal, and menu/close behavior under QT_QPA_PLATFORM=offscreen.
- [x] Run the cat tests and confirm expected missing-module failures.
- [x] Implement a transparent topmost Qt widget with 120 ms animation, global pointer gaze sampling, click-to-open-chat, right-click menu, and drag.
- [x] Run cat tests and confirm package-relative asset loading.

### Task 3: Worker threads and companion chat

**Files:** Create src/b12/desktop/workers.py, src/b12/desktop/chat.py, tests/desktop/test_chat.py.

**Interfaces:**
- ApiSignals carries event(dict), result(object), and error(str) from workers.
- ApiJob(QRunnable) runs an injected synchronous operation and emits result/error.
- ChatWindow(QWidget) supports session select/new, history, stream chat, cancel, persistent-turn and consent toggles, approvals, and memory CRUD.
- handle_turn_event(event) updates chat and emits the cat phase without synchronous network I/O.

- [x] Write offscreen Qt tests for event rendering, escaped tool detail, pending approval controls, stale approval refresh, cancellation, consent/persist semantics, and no synchronous network call in GUI handlers.
- [x] Run the chat tests and confirm expected failures.
- [x] Implement a compact cyberpunk chat window with sessions, streamed markdown, tool details, exact approval/deny, memory panel, connection state, and retry messaging.
- [x] Run chat tests with a fake client that emits the API event contract.

### Task 4: Desktop shell, tray, and CLI

**Files:** Create src/b12/desktop/app.py. Modify src/b12/cli.py. Create tests/desktop/test_app.py; modify tests/e2e/test_cli.py.

**Interfaces:**
- run_desktop(settings, url, persist_default=False) creates QApplication, reads the existing owner token, builds client/pet/chat/tray/reconnect timer, and runs Qt's event loop.
- Add b12 desktop [--url URL] [--persist]; register it as server-owned so CLI never opens the runtime lock or DB.
- Missing Qt extra prints uv sync --extra desktop. Missing token prints the owner-token initialization hint.

- [x] Write failing CLI tests for parser/dispatch, token-missing diagnostics, and missing-Qt diagnostics.
- [x] Run those tests and confirm failures before implementation.
- [x] Implement tray and overlay menu actions: show/hide, open chat/new session, microphone mute/status, web UI, quit; create no autostart file or child process.
- [x] Run CLI/app tests with fake HTTP and offscreen Qt; confirm microphone is never started.

### Task 5: Docs, package, and complete verification

**Files:** Modify README.md and create docs/desktop-companion.md, wiki/topics/desktop-companion.md, wiki/sources/capri-desktop-companions-2026-11-07.md. Modify wiki/project/status.md, wiki/index.md, wiki/log.md, raw/source-manifest.json.

- [x] Document setup, API/token boundaries, X11 target, tray fallback, and voice-off startup.
- [x] Record all pinned GitHub reviews and Qt primary-source checks, explicitly noting no archived source snapshot in raw.
- [x] Update wiki with evidence, remaining Wayland/packaging questions, and a final lint record.
- [x] Run uv run --locked --extra dev --extra tui --extra desktop pytest -q; uv run --locked --extra dev --extra tui --extra desktop ruff check src tests; uv build; uv lock --check; git diff --check.
- [x] Inspect for tokens/audio artifacts, unrelated changes, uncited source claims, and optional Qt imports in standard CLI/TUI paths.
