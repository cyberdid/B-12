# B-12 Capri Feature Parity Implementation Plan

> **For agentic workers:** Execute the approved feature scope in `/home/cyberdid/.codex/worktrees/cb2c/B-12`; do not modify the main checkout. No one is working alone in this codebase: preserve prior compact-chat/action changes and coordinate file ownership before edits.

**Goal:** Implement the transferable Capri Desktop user-facing capabilities in B-12's native Qt companion on Linux/X11.

**Architecture:** Reimplement behavior in B-12 modules. Keep the existing owner-authenticated API and runtime as the only model/tool/grant authority; collect external coding-agent events through opt-in, local-only hooks and persist only bounded, non-content metadata.

**Tech Stack:** Python 3.12+, PySide6, existing B-12 API/client, QSettings, standard-library Linux interfaces, JSON/TOML configuration.

**Spec:** `docs/superpowers/specs/2026-11-08-b12-capri-feature-parity-design.md`

## Global Constraints

- Never copy source code or character artwork from `mochiiwuff/capri-desktop`.
- Never change TUI behavior or create a second model/runtime authority.
- Hook installation is explicit, preserves unrelated settings, backs up before writes, and supports uninstall.
- Activity logs exclude prompts, raw arguments, output, file contents, secrets, and audio.
- Screen capture/window awareness is off by default; captures are transient and never saved.
- Destructive host actions need a direct, exact-target owner confirmation; shell commands retain B-12 grants and approval.
- Automated tests are outside this plan's requested verification; use static checks and narrowly scoped local UI construction only.

---

## Task 1 — Complete the source-to-B-12 capability matrix

**Files:**
- Modify: `wiki/sources/capri-desktop-companions-2026-11-07.md`
- Modify: `raw/source-manifest.json`
- Modify: `wiki/topics/desktop-companion.md`
- Modify: `wiki/project/status.md`

- [x] **Step 1:** Pin the current source head, inspect README, LICENSE, feature modules and adapters, and record each advertised capability family with direct file links and platform/consent limits.
- [x] **Step 2:** Map every family to existing B-12 code, a planned implementation, or a documented platform/model limitation in the source card and topic page.
- [x] **Step 3:** Record the clean-room/license boundary and explicit privacy/action gates in ADR-012.

## Task 2 — External-agent integrations and activity reports

**Files:**
- Create: `src/b12/desktop/integrations.py`
- Create: `src/b12/desktop/activity.py`
- Create: `src/b12/desktop/hooks.py`
- Modify: `src/b12/desktop/app.py`
- Modify: `src/b12/desktop/chat.py`

- [x] Add opt-in install/status/uninstall adapters for Claude Code, Codex and Antigravity, with per-file validation, backup, atomic write, and marker-only removal.
- [x] Add a bounded local event journal and hook entrypoint that accepts only supported event names and persists no prompt, path, command argument, result or secret content.
- [x] Add an assistant selector, current-activity indicator, permission/wait/error/completion feedback, an owner-readable daily mission report, and local clipboard image export.
- [x] Keep external-provider approvals in their own application; never present them as B-12 approvals.

## Task 3 — Personalization, natural-language reminders, and local memory

**Files:**
- Modify: `src/b12/desktop/actions.py`
- Create: `src/b12/desktop/profile.py`
- Modify: `src/b12/desktop/app.py`
- Modify: `src/b12/desktop/chat.py`

- [x] Add editable user name, conversation-style note, user-authored catchphrases, and transparent interaction history.
- [x] Route durable B-12 facts through the existing memory API; the local profile does not mirror model memory in QSettings.
- [x] Parse common Ukrainian/English relative and clock-time reminder phrases deterministically; ask when timing or reminder text is ambiguous; retain snooze/dismiss.

## Task 4 — File, system, and media action center

**Files:**
- Create: `src/b12/desktop/local_features.py`
- Modify: `src/b12/desktop/actions.py`
- Modify: `src/b12/desktop/app.py`
- Modify: `src/b12/desktop/client.py` only if an existing owner endpoint is needed

- [x] Add bounded name search and opt-in UTF-8 content search (400 files/16 MiB caps) for one user-selected folder, safe open/reveal buttons, and a recent-results list.
- [x] Add local read-only system snapshot for CPU/RAM/disk/battery/network with no telemetry upload.
- [x] Add supported Linux controls for volume/media/settings and XRandR display modes; actions show their exact target and require owner confirmation.
- [x] Keep arbitrary shell execution in the existing chat/tool/grant/approval path; no UI free-text is passed to a shell.
- [x] Mark unavailable Windows-only functionality and missing optional host tools clearly.

## Task 5 — Pet interaction, accessibility, guide, and startup

**Files:**
- Modify: `src/b12/desktop/cat.py`
- Modify: `src/b12/desktop/app.py`
- Create: `src/b12/desktop/presentation.py`
- Modify: `docs/desktop-companion.md`

- [x] Add owner-controlled wander/peek/demo, 10-minute idle sleep, optional cursor-follow across displays, manual pointer-display relocation, reduced-motion and optional OS beep controls, and hide-to-tray when tray is available.
- [x] Add a concise in-app guide for pairing hooks, talking to B-12, permissions, and privacy options.
- [x] Add a user-level autostart manager with an explicit off/on state and exact file preview; never enable startup by default.
- [x] Use only existing B-12 atlas frames and user-provided appearance packs; no upstream art assets.
- [x] Add a timer-driven Capri gesture/effect controller independent of model streaming, chat-phase reactions, manual preview menu, pointer/drag reactions, and reduced-motion stop behavior. FX are drawn procedurally in Qt over the local pack.
- [x] Confirm the nested animation menus construct in `DesktopShell`, render representative action frames with the local pack in Qt, and restart the live X11 overlay at 300×410. Manual owner selection of each menu item remains optional acceptance.

## Task 6 — Reconcile every upstream feature and verify locally

**Files:**
- Modify: `wiki/topics/desktop-companion.md`
- Modify: `wiki/project/desktop-companion-plan.md`
- Modify: `wiki/project/status.md`
- Modify: `wiki/index.md`
- Modify: `wiki/log.md`

- [x] Revisit every upstream README feature and set its evidence status; this remains feature-parity-in-progress because vision/model or platform limitations remain.
- [x] Run static Ruff, syntax, format, whitespace, and local-link/source-index checks; render representative Qt action frames and restart only the native companion client. No automated test suite, model inference, voice, GPU work, system action, real hook install, or server restart was performed for this verification.
- [x] Record static-check results and remaining X11/Wayland, model-vision, permissions, and external-config acceptance gaps. Runtime/host acceptance remains open.
