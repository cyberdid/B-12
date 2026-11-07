# B-12 Desktop Companion — Design

**Date:** 2026-11-07

**Status:** owner-authorized implementation
**Owner request:** study four Capricorn repositories, plan, and implement useful desktop companion behavior for B-12.

## Goal

Add an optional Linux desktop companion: a polished, transparent, always-on-top animated cybercat plus a compact native chat and tray controls, connected to the existing authenticated B-12 API.

## Evidence and source boundaries

The comparison and pinned revisions are in [the source review](../../../wiki/sources/capri-desktop-companions-2026-11-07.md). The UX references are not code dependencies. B-12 will use its own approved cybercat asset. No Capri character art, source code, or model weights are copied.

Verified B-12 facts: it already has an owner-authenticated loopback API, sessions/history, streamed chat, turn cancellation/resume, exact-operation approvals, memory endpoints, consent control, voice mute/status, and a TUI cybercat atlas. See [TUI](../../../wiki/topics/cyberpunk-tui.md), [voice](../../../wiki/topics/voice.md), [CLI/API ownership](../../../wiki/topics/cli-server-mode.md), and [tool control](../../../wiki/topics/tool-control.md).

## Chosen approach

**Selected:** a separate optional PySide6-Essentials desktop client. Qt Widgets provides a native frameless pet, chat window, and system tray. A synchronous HTTPX client runs only from worker threads. The existing server remains the single runtime owner.

Alternatives considered:

1. **Extend the Textual TUI:** lowest dependency cost, but it cannot provide a native transparent always-on-top overlay outside a terminal.
2. **Electron desktop shell:** strong web styling and cross-platform packaging, but duplicates the runtime/client shell and has a larger bundled footprint.
3. **Qt optional desktop extra — selected:** native overlay and tray with a small Python integration layer, while keeping normal CLI/TUI installs unchanged.

## User-visible behavior

- The cat starts near the lower-right of the active display, can be dragged, remembers its position, blinks/breathes, follows the pointer with its gaze, and changes pose for typing, thinking, speaking, tool work, pending approval, success, failure, and cancellation.
- Clicking the cat opens the companion chat; right-click opens a small cyberpunk menu. The system tray offers pet sleep/wake, chat/new session, microphone mute/unmute controls, open B-12 web UI, and quit. If the desktop has no tray, the visible sleeping pet can be clicked to wake it.
- Chat displays B-12 session history, streams assistant text and tool events, creates sessions, cancels an active turn, resumes an exact pending approval, and exposes existing memory/consent/persist controls. Approval buttons call the existing owner-protected endpoint for the exact operation ID.
- The companion reports API connectivity and pending approvals. It never starts the server or model automatically. It can start while the authenticated API is offline and reconnect in the background.
- Voice capture remains off at application startup. The desktop reads voice status and can set the existing mute control; it does not open a microphone or play generated audio in this release.

## Data flow and security

1. CLI loads normal B-12 settings and reads the existing owner token from the existing state directory. It does not copy or persist the token elsewhere.
2. Desktop requests go to the configured B-12 loopback API URL, defaulting to the existing URL. HTTP client environment proxies are disabled for this local control connection.
3. B-12 keeps sole ownership of runtime state, model calls, tools, memory, grants, consent, and approvals. Desktop actions call the same authenticated API routes as the TUI.
4. The pet reads pointer coordinates only to animate its gaze. It does not inspect other window titles, capture screen pixels, hook global keystrokes, read arbitrary files, or initiate desktop automation.
5. The UI persists only presentation preferences such as overlay position. Conversation persistence remains controlled by B-12 request controls.
6. The desktop shell does not auto-start services or microphone capture and does not add new host capabilities.

## Error handling

- Missing owner token: exit with a clear server/initialization hint; never create or print a token.
- API offline: keep the pet available, show offline state, retry on a timer, and show request errors in chat.
- Stream interrupted: preserve rendered text and show a connection error. If the turn ID is known, keep the chat locked and allow cancellation. Query the owner-scoped turn-status endpoint only after the cancel request is acknowledged; unlock after the server confirms the turn ended, then reload history. If history reload fails, keep sending disabled until a fresh load succeeds. If no turn started, allow another prompt.
- Approval gone/stale: refresh pending approvals and explain that the operation is no longer pending; do not retry automatically.
- Missing Qt extra: print the install command without affecting other commands.
- Missing tray support: use the overlay menu.

## Scope and platform

Target is Linux, initially X11 with a compositing window manager. Qt documents alpha overlays on X11 as requiring an ARGB visual and compositor; topmost behavior depends on the window manager. The Qt widget paths are covered offscreen; actual display behavior and Wayland remain unverified. Core CLI/TUI/API installs must remain usable without the desktop extra.

This release does not port Windows-only window tracking, screen capture, OS settings/power actions, global keyboard hooks, auto-start installation, or the other projects' autonomous PC actions. New host actions require separate B-12 tool contracts and server-side policy review.

## Acceptance criteria

1. The desktop extra resolves, and remains optional.
2. The CLI command is available; running it does not start the API, Ollama, microphone, or any child process.
3. The overlay loads the B-12 atlas, renders alpha, tracks the pointer, moves by drag, and maps B-12 events to visual states.
4. Companion uses authenticated API for sessions, history, chat streaming, cancel, owner-scoped turn status, exact approval/deny and resume, consent/persist controls, memory CRUD, status, and microphone mute/status.
5. All network calls run off the GUI thread; widget changes occur on the Qt GUI thread.
6. Tests cover client auth/streams/errors, event-to-pet mapping, overlay interactions, and CLI behavior without live model/microphone.
7. Full tests, lint, and wheel build pass; wiki records sources, implementation status, checks, and platform limits.
