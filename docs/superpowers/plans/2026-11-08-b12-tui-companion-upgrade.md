# B-12 TUI Companion Upgrade Implementation Plan

> **For agentic workers:** Execute with independent module owners and controller integration. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add activity integrations, task reports, explicit voice controls, and optional external skins to B-12's existing TUI.

**Architecture:** A versioned local event store accepts privacy-filtered hook events from provider-specific adapters. The Textual TUI renders those events alongside actual B-12 turn data. Voice remains behind explicit UI controls and existing authenticated API endpoints; a manifest loader handles optional external skins.

**Tech Stack:** Python 3.12, Textual, textual-image, Pillow, HTTPX, SQLite, local PipeWire/ALSA command-line tools, existing B-12 voice API.

**Spec:** docs/superpowers/specs/2026-11-08-b12-tui-companion-upgrade-design.md

## Global Constraints

- Textual TUI is the only UI being extended; the cybercat stays the default.
- Store only allowlisted activity metadata locally; never store prompts, tool arguments, command output, transcript content, or absolute paths.
- Hook adapters are telemetry-only and never alter provider decisions or call B-12 tools.
- The owner-authenticated B-12 API remains the only route for ASR/TTS and existing permissions.
- Audio capture starts only after direct PTT action; response speech is opt-in and stoppable.
- Capri artwork is loaded only from an external pack with provenance/license metadata; no reference-repository assets are copied.
- The owner authorized package installation/downloads when necessary. `uv`, `pw-record`, `pw-play`, `arecord`, and `aplay` are already available, so this work installed nothing; never persist credentials.
- Keep this work inside the existing Textual TUI. Do not add a second desktop UI or agent runtime.

---

### Task 1: Versioned activity store and hook normalizer

**Files:**
- Create `src/b12/tui/activity.py`
- Create `src/b12/tui/hook.py`
- Modify `src/b12/cli.py`

**Interfaces:**
- `ActivityStore(state_dir).append(source, payload) -> int` normalizes and persists one bounded event.
- `ActivityStore.after(cursor, limit=100) -> list[dict]` returns new local events in sequence order.
- `ActivityStore.recent(limit=100) -> list[dict]` returns the newest retained events in sequence order for initial UI history.
- `ActivityStore.clear() -> None` removes activity metadata only.
- `normalize_hook(source, payload, now) -> dict | None` emits a known event or ignores an unsupported hook name.
- CLI `b12 tui-hook --source ...` reads one JSON object from stdin, appends only normalized metadata, and never takes the runtime lock or imports Textual. Claude Code/Codex use payload `hook_event_name`; Antigravity uses `--event` because its schema carries no event name. For Antigravity, support only `SessionStart`, `PostToolUse`, and `PostInvocation` with documented no-op output shapes; do not configure required-decision events `PreToolUse` or `Stop`. Treat `PostInvocation` as model-call completion, never as turn/session completion.
- CLI `b12 tui` passes `settings.state_dir` into `B12App(state_dir=...)`.

- [x] Implement SQLite schema with WAL, private directory/database modes, input-size limits, 14-day and 10,000-event retention.
- [x] Map only provider lifecycle names, opaque session IDs, tool names, status, event time, and project basename; discard all prompt/argument/output/path fields. Normalize Antigravity camelCase fields and explicit `--event` separately from Claude/Codex snake_case payloads.
- [x] Add top-level `tui-hook` parser/handler and mark it lock-free/server-owned so provider hooks can append metadata while the B-12 server holds the runtime lock.
- [x] Keep malformed input and SQLite contention bounded; hook adapter exits 0 after dropping invalid telemetry. For recognized Antigravity events emit only the documented fixed no-op JSON response, never a permission/stop decision.

### Task 2: Optional skin manifest and selector

**Files:**
- Modify `src/b12/tui/sprites.py`
- Modify `src/b12/tui/pet.py`
- Create `src/b12/tui/assets/skins/README.md`

**Interfaces:**
- `SkinManifest.load(path)` validates a versioned external manifest, contained asset path, dimensions, frame grid, and phase mappings.
- `PortraitRenderer.set_skin(id)` releases owned terminal images before switching and falls back to built-in cybercat if a pack fails.
- `available_skins(capri_dir)` returns the built-in cybercat and any valid external packs.
- `CyberCat.set_skin(id)` changes rendering and exposes the active display name to the TUI.

- [x] Preserve the cybercat-specific tail and purr rendering path unchanged as the default.
- [x] Add generic atlas rendering for external packs with no network fetch or asset writes.
- [x] Validate manifest paths, dimensions, phase maps, and provenance fields; invalid packs must not terminate the TUI.
- [x] Document manifest fields, source/license provenance, and local installation path.

### Task 3: Opt-in PTT and speech playback

**Files:**
- Modify `src/b12/tui/client.py`
- Create `src/b12/tui/voice.py`

**Interfaces:**
- `ApiClient.voice_status()`, `voice_asr(pcm, sample_rate=16000)`, and `voice_tts(text, lang="auto")` use existing API routes.
- `PttRecorder.start()` and `PttRecorder.stop()` are async, manage an in-memory, 16 kHz mono recording via `pw-record` or `arecord`, and return bounded raw PCM bytes.
- `VoicePlayer.play(wav_bytes)` and `VoicePlayer.stop()` are async; playback pipes bytes to `pw-play` or `aplay` and stop interrupts only its own process.

- [x] Keep recording bounded to 12 seconds, volatile, and cancelable; do not write audio files.
- [x] Surface missing device/player errors with stable display-safe codes.

### Task 4: TUI integration for activity, voice, and skin selection

**Files:**
- Modify `src/b12/tui/app.py`
- Modify `src/b12/tui/theme.py`
- Modify `src/b12/tui/preview.py`

**Interfaces:**
- `B12App(..., state_dir=...)` polls the activity store without blocking chat/API calls.
- Activity events update the existing pet phases and a bounded timeline.
- `Turn` records actual start time and stream event counts; result rendering displays elapsed time, tool calls, approval waits, and failures.
- PTT button and binding call `PttRecorder`, then `ApiClient.voice_asr`; transcript fills the composer but does not submit it.
- Spoken reply is default-off, calls `ApiClient.voice_tts` only for completed responses, and uses an interruptible `VoicePlayer`.
- F9 cycles valid skin IDs; unavailable Capri pack leaves the built-in cybercat selected.

- [x] Add activity polling, a scrollable timeline, and a clear-history action that affects only the local activity store.
- [x] Map external lifecycle events to pet phases and show elapsed long-wait time without model/tool calls.
- [x] Build truthful B-12 and external task summaries from observed events only.
- [x] Add explicit PTT start/stop, visible recording state, mute check, and transcript review before Send.
- [x] Add a default-off spoken-reply control and stop playback action.
- [x] Add F9 skin cycling and update companion label/status without changing the default; recover to cybercat if an external pack disappears.
- [x] Keep preview mode self-contained and label sample activity/voice controls as demo-only; never launch mic/player/API operations.
- [x] Let external activity influence the pet only while B-12 has no active turn; label partial provider activity truthfully rather than inferring completion.

### Task 5: Provider hook examples and project wiki

**Files:**
- Create `integrations/claude-code/README.md` and hook example
- Create `integrations/codex/README.md` and plugin/hook example
- Create `integrations/antigravity/README.md` and hook example
- Create `integrations/b12-tui-hook` (offline, no-sync wrapper with fixed Antigravity no-op fallback)
- Create `wiki/sources/agent-hooks-2026-11-08.md`
- Modify `wiki/topics/cyberpunk-tui.md`, `wiki/index.md`, `wiki/project/status.md`, `wiki/log.md`

- [x] Provide project-local, telemetry-only examples that call the B-12 wrapper; do not modify global settings.
- [x] Record official provider docs, access date, what was read, and the lack of archived page snapshots.
- [x] Update source boundaries, setup steps, current status, unresolved asset-pack dependency, and wiki index.
- [x] Record checks not run under the current instruction rather than claiming they passed.

## Verification boundary

The current session instruction prohibits adding or running tests unless the owner asks to test or verify the implementation. Therefore automated tests and the test suite are not part of this execution; the final report must say so. A later owner-requested verification should run focused TUI/audio/store tests first, then the full locked suite and Ruff.
