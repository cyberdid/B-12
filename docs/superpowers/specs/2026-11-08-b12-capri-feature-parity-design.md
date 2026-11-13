# B-12 Capri Feature Parity — Design

**Date:** 2026-11-08
**Status:** owner-authorized; implementation in progress
**Owner request:** implement all useful functions of `mochiiwuff/capri-desktop` in the B-12 native Qt companion, not only its compact chat and reminders.
**Reviewed source:** `mochiiwuff/capri-desktop` main HEAD `cb33e87dfaee79cec8b4b0f737ca89e07b87ba4b` (2026-11-08).

## Goal

Bring the user-facing companion feature families from Capri Desktop into B-12 where they fit B-12's local-first runtime and the current Linux/X11 host. The prior compact chat, reminders, sites, prompt shortcuts, launchers, and command handoff are the starting point, not the completion criterion.

## Feature families to cover

1. **Coding-agent activity:** user-managed observe/unobserve hooks for Claude Code, Codex, and Antigravity; non-blocking local event intake; activity ticker, permission/wait/error/completion reactions, and a daily mission report.
2. **B-12 chat and setup:** keep the configured B-12 runtime as the single assistant/model authority; surface model/runtime state and existing memory/voice controls in the companion. Do not create a parallel provider/key store or silently change the runtime model.
3. **Local actions:** owner-created app/site launchers, file search/open/reveal, system information, media/audio and desktop actions where the host supports them. Destructive actions require a clearly named owner click and show exact targets. Arbitrary shell continues through B-12 tools/grants/approval.
4. **Reminders:** manual date/time creation plus a small deterministic Ukrainian/English parser for common relative and clock-time phrases; uncertain times must ask the user instead of guessing.
5. **Screen/PC awareness:** explicit, user-visible, local-first opt-ins for resource/device status. Screen capture occurs only on an explicit request and only when the configured B-12 runtime can consume images; never persist a capture. Periodic screen observation remains off by default and must show a clear active indicator.
6. **Personalization:** local editable name, conversation style, and catchphrases; use B-12's traceable memory API for facts. A transparent companionship-history display may count days and interactions; it must not claim sentience or punish absence.
7. **Character interaction and presentation:** optional wander/peek/teleport/demo gestures, multi-display follow, reduced-motion, local sound cues, locale and startup settings, and an in-app guide. Use only B-12's built-in art or a separately supplied local skin pack.

## Architecture and control boundaries

- B-12 API/runtime remains the only model, memory, tool, grant, and approval authority. Keep the compact/full Qt chat on the same session controller.
- Hooks are opt-in and owner-installed from a Qt manager. Installer must preserve unrelated config, create a timestamped backup, support exact uninstall, and refuse malformed files. Hook delivery must never block an external assistant.
- Store only bounded activity metadata needed for the ticker/report: provider, event category, tool name/category, success/error/approval state, and timestamps. Do not persist prompts, command arguments, source text, tool output, secrets, or raw audio.
- Local file search is explicit, bounded to selected/user folders, skips hidden/cache/dependency directories by default, and returns results to a click-controlled UI.
- Resource monitoring is local-only, read-only, and opt-in. Screen capture, active-window inspection, and any automatic periodic behavior are separate opt-ins with visible state; no auto-close of other AI tabs or application windows.
- Every app launch and destructive desktop action shows the exact executable/target/action and asks for a click. Existing B-12 shell grants and exact approval remain required for arbitrary commands.
- Do not copy upstream code or Capri/Cyberpunk artwork. Upstream current code is PolyForm Noncommercial; artwork is excluded from its license. Reimplement behavior independently and preserve source provenance.
- Linux/X11 is the active target. Windows-only behavior is either implemented through an explicit Linux equivalent or documented unavailable; never label an unsupported platform function as complete. Wayland remains a separate acceptance target.
- The B-12 text-only model transport currently has no image input. Screen understanding is unavailable until a vision-capable model transport is explicitly configured and validated; do not pretend OCR or a screenshot path is equivalent to model vision.

## Completion evidence

- A repository-source matrix maps every README capability family to B-12 as implemented, equivalent, platform-limited, intentionally gated, or unavailable with a reason.
- The Qt UI exposes all implemented capabilities without changing TUI behavior.
- Static checks, documentation/link audit, and a local Qt construction smoke are recorded. Do not start the B-12 server/model/audio/GPU or execute real app/system actions as part of development verification.
- Live desktop, hook installation against real user configs, screen/window-manager behavior, media controls, and any real external-agent event remain unverified until separately observed on the host.
