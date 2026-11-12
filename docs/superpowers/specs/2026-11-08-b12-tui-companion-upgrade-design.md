# B-12 TUI Companion Upgrade — Design

**Date:** 2026-11-08
**Status:** owner-authorized implementation
**Owner request:** implement useful nonvisual ideas from the reviewed companion repositories in B-12's existing TUI and make Capri an optional companion skin. The owner clarified that the existing TUI is the only interface in scope and authorized installs/downloads if needed. Required local audio/uv tools were already present, so none were installed.

## Goal

Extend the existing Textual TUI with local activity from coding agents, concise task reports, explicit voice interaction, and a switchable companion skin. Keep the cybercat as the default; Capri is available only from an externally supplied asset pack with its provenance and usage rights recorded.

## Chosen approach

Keep the current Textual TUI and authenticated B-12 API. Add a small local activity spool under the existing B-12 state directory. Provider hook commands normalize lifecycle notifications into that spool; the TUI reads them and renders a timeline and task summary. Voice uses existing B-12 ASR/TTS endpoints and local `pw-record`/`arecord` and `pw-play`/`aplay` tools. The renderer gains a manifest-driven external skin loader while preserving the built-in cybercat renderer and its generated assets.

This avoids a second app/runtime and does not add model or host-tool capabilities. Reference repositories provide interaction patterns only; their code and character artwork are not copied.

## Components

### 1. Agent activity and reports

- `b12 tui-hook --source {claude-code,codex,antigravity}` reads one provider JSON payload from stdin and maps known lifecycle events into a versioned B-12 activity event. Claude Code and Codex supply `hook_event_name`; Antigravity requires an explicit `--event` because its payload has no common event-name field. For Antigravity, wire only `SessionStart`, `PostToolUse`, and `PostInvocation`; return the documented no-op JSON shapes (`{}` or empty injection/default termination) where required. Never wire `PreToolUse` or `Stop`, whose required outputs can control execution. `PostInvocation` marks only model-invocation completion and must not be represented as a completed conversation turn.
- Activity records are local metadata in `$B12_STATE_DIR/ui/activity.sqlite3`. Store only provider, opaque session ID, event kind, time, project basename, tool name, and bounded status text. Do not retain prompts, tool arguments, command output, transcript text, or absolute paths.
- The TUI polls activity without blocking the chat/API stream. It shows current state, a bounded timeline, and reports with elapsed time, tool-event count, approval-event count, and failures. B-12's own live turn report is derived from its actual stream events.
- Hook examples are provided for each supported agent. They are opt-in and project-local; installation does not edit global agent settings. Hooks only report state. They cannot approve/deny actions, modify prompts, run B-12 tools, or control the computer. Antigravity events and no-op outputs follow the source card's provider-specific boundaries.
- Long quiet intervals update the companion's waiting state and elapsed time. Notifications are visual and never invoke the model.

### 2. Explicit voice controls

- Push-to-talk begins only after a direct TUI action and stops on a second action or the bounded recording limit. Capture uses mono 16 kHz PCM and retains audio only in memory until the existing authenticated ASR endpoint returns.
- A successful transcript is inserted into the composer for review; it is not submitted automatically.
- Spoken assistant replies are off by default. When explicitly enabled, completed reply text is synthesized by the existing local TTS endpoint and played through an available local player. A stop control interrupts playback. No audio is captured or played during application startup.
- The offline preview is strictly visual: its sample voice controls are labeled as demo/inactive and never launch a microphone, playback process, or API request.
- A muted state blocks capture; the TUI never unmutes by itself. It does not write recordings, transcripts, or generated WAV files to disk.

### 3. Optional skins

- The built-in cybercat remains selected by default and keeps the current registered-tail animation path.
- A versioned `manifest.json` describes an external RGBA atlas, grid, animation duration, and phase-to-frame mapping. The pack must include source and license/provenance fields and remain outside the repository.
- `B12_TUI_CAPRI_DIR` points to an optional Capri pack. F9 cycles available skins. If the pack is absent or invalid, the TUI retains the cybercat and explains the issue in its status line.
- No Capri code or art is bundled. The reviewed Capri repositories either have no explicit art license or expressly exclude the character/artwork from the code license.

## Boundaries

- B-12's runtime remains the sole owner of models, tools, approvals, consent, memory, and host access.
- External hook events are telemetry, not instructions. Payloads are reduced to an allowlisted schema before persistence or rendering.
- External activity may update the companion only while B-12 has no active turn; it never overrides a live B-12 speaking, working, or approval state. Incomplete provider lifecycle signals are labeled as observed activity, not as a completed task.
- Event persistence is local, bounded, clearable from the TUI, and separate from B-12 memory. It is not used for model context.
- Microphone and speaker operations require direct user action or an explicit opt-in setting. No automatic capture, unmute, or playback.
- Do not edit Claude Code, Codex, or Antigravity configuration automatically. Package installation/downloads are authorized when required, but this implementation needed none. Do not store credentials.
- Only the Textual TUI is in scope; do not extend the optional Qt desktop client.

## External interface evidence

Provider hook details and date/access limits are recorded in [the hook source card](../../../wiki/sources/agent-hooks-2026-11-08.md). The user-provided repository review and art-license boundaries remain in [the Capricorn source review](../../../wiki/sources/capri-desktop-companions-2026-11-07.md).

## Acceptance criteria

1. Existing TUI remains the only UI entry point and cybercat remains the default.
2. A valid provider hook payload creates a bounded local event; unknown or malformed payloads do not affect the agent or crash the TUI.
3. The TUI shows event phases and truthful reports without storing prompts, arguments, output, or absolute paths.
4. Activity can be cleared, expires by retention policy, and is not searchable through B-12 memory.
5. Push-to-talk is explicit, capped, volatile, respects mute, and leaves the transcript in the composer for review.
6. Optional TTS is disabled by default, uses the existing local endpoint, and can be stopped.
7. F9 changes between cybercat and a valid external skin pack; missing/invalid Capri assets leave the cybercat usable.
8. No global hook configuration, model, server, microphone, playback, GPU job, or host tool is started or modified by implementing these changes.
9. Documentation records source boundaries, setup, behavior, and any verification not performed.
