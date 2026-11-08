# B-12 Capri Compact Conversation and Actions — Design

**Date:** 2026-11-08
**Status:** approved by owner; implemented locally; host acceptance open
**Owner request:** chat with Capri from a small panel attached to her, and add useful missing behavior found in the supplied Capricorn repositories, including launching applications and system commands.

## Goal

Make the Qt companion useful without opening the large multi-tab window. Keep the existing full chat available for history, approvals, memory, and status. Add compatible companion features from the repository review without copying their code, artwork, or unsafe host-control model.

## Included

1. **Compact chat attached to the pet.** The existing `ChatWindow` remains the sole chat/session/stream controller. A compact presentation hides the memory/status tabs and keeps the current session, transcript, composer, cancel, approval cards, and an explicit expand-to-full-chat action. The panel follows the draggable pet and stays inside the available screen; it chooses a side when it cannot fit below. Closing the compact panel hides it without stopping API polling or an active stream.
2. **Activity and notification handling.** Show the current B-12 phase and tool detail in the compact panel/pet status. Keep approval attention visible. Defer non-urgent completion notices while the user is reading or typing and show a small missed-activity indicator after focus returns.
3. **Local reminders.** Provide a date/time picker and a persistent list in the Qt companion. Due reminders are surfaced while the client runs; overdue reminders remain visible after restart. The owner can snooze or dismiss. Do not infer times from model text or send reminders to B-12 memory.
4. **Saved prompt shortcuts.** Let the owner manage named prompt templates in local settings. Selecting one prefills the composer; it never sends automatically.
5. **Site shortcuts.** Let the owner manage named `http`/`https` links without embedded credentials. Open a selected link in the external browser only after an explicit click; do not accept model-originated URLs for automatic opening.
6. **Application launchers.** Let the owner manage named application entries as absolute executable paths plus argument lists. Launch only after a deliberate click in the companion. Never interpret entries through a shell and never accept model-originated launcher definitions.
7. **System command entry.** A command composer sends the owner's exact command and working directory as a normal B-12 chat request. Execution remains in the runtime's existing `shell_exec`/approval/grant path; the desktop does not create grants, execute shell text itself, or suppress B-12 approval UI.

## Controls and boundaries

- Runtime B-12 remains the sole owner of model turns, process tools, grants, consent, and approval decisions.
- User-created application launchers are a local Qt UI feature. Each entry is displayed as an absolute executable and argument list, and clicking its named button is the explicit action. No shell parsing or arbitrary PATH lookup.
- Arbitrary shell text is submitted to the existing chat tool flow; exact approval/grant requirements are unchanged.
- Reminders and prompt shortcuts are local user data, not model memory. Do not persist secrets or transcripts in `QSettings`.
- No global hotkeys, window/screen capture, auto-start, unsolicited chatter, microphone, speaker, or background server/model launch.
- Capri artwork remains in the private external pack; the supplied projects are behavior references only.
- Leave TUI files and behavior unchanged.

## Acceptance criteria

1. Clicking Capri opens a compact anchored panel; dragging Capri repositions the panel; screen edges are clamped; close hides the panel; expand opens the existing full multi-tab chat.
2. Compact chat uses the existing B-12 session, transcript, stream, cancel, approval, and reconnect state. Sending or canceling in the compact presentation has the same lifecycle as the full chat.
3. Current activity is visible. Approval state is never deferred; ordinary success/cancel notices do not cover active typing/reading.
4. Reminders survive Qt client restart, surface when due, and can be snoozed/dismissed. Invalid settings entries are ignored safely.
5. Prompt shortcuts only prefill the composer.
6. A user-added site opens only after a click and passes `http`/`https`, host, and no-credentials validation.
7. A user-added launcher starts the configured executable/argv only after a click and confirmation; malformed entries are rejected.
8. System command text is submitted through the existing B-12 chat/runtime control path, and the UI does not directly spawn a shell.
9. No new model-callable host-control behavior is exposed; no API, TUI, voice, or artwork changes.
10. Run static checks and a local UI smoke without starting B-12 server/model/audio or running automated tests.
