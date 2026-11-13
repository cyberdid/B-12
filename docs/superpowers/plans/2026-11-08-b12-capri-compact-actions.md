# B-12 Capri Compact Conversation and Actions — Implementation Plan

> Execute inline in the active `feat/b12-desktop-companion` worktree. Owner has authorized the feature scope.

**Goal:** Add a compact character-anchored conversation surface and compatible missing companion functions found in the pinned Capri/Capricorn repositories.

**Architecture:** Reuse `ChatWindow` as the sole UI/controller for conversation state; persist only local reminders, saved prompts, and owner-authored application launchers in `QSettings`. Keep arbitrary command execution inside the existing B-12 API/chat/tool control plane. No upstream code or art is copied.

**Spec:** `docs/superpowers/specs/2026-11-08-b12-capri-compact-actions-design.md`

## Tasks

### 1. Complete pinned-source gap audit and record the decision

**Files:** `raw/source-manifest.json`, `wiki/sources/capri-desktop-companions-2026-11-07.md`, `docs/superpowers/specs/2026-11-08-b12-capri-compact-actions-design.md`, `wiki/project/decisions.md`.

- [x] Record pinned code paths and additional behavior: anchored chat, reminders, prompt/launcher management, and activity/notification handling.
- [x] Explicitly exclude unrelated genomics repo, broad model-triggered PC automation, cloud/experimental voice, and art/code copying.
- [x] Record owner authorization for the limited user-controlled launcher UI; retain B-12 grants/approval for shell execution.

### 2. Build the compact companion chat

**Files:** `src/b12/desktop/chat.py`, `src/b12/desktop/app.py`.

- [x] Add a compact presentation that hides advanced tabs but reuses session/history/stream/cancel/approval state.
- [x] Add expand, hide, and compact Return-to-send controls.
- [x] Anchor and clamp the panel relative to the pet across screens and while dragging.
- [x] Keep a visible activity indicator and defer non-urgent notices while the user is composing/reading.

### 3. Add compatible owner-facing actions

**Files:** new `src/b12/desktop/actions.py`, `src/b12/desktop/app.py`, `src/b12/desktop/chat.py`.

- [x] Add persistent local reminder create/list/snooze/dismiss controls using explicit date/time selection.
- [x] Add saved prompt templates that prefill but never submit the composer.
- [x] Add owner-managed HTTP(S) site shortcuts that open only on a user click.
- [x] Add user-managed launchers using absolute paths and argv, with no shell interpretation.
- [x] Add a command composer that submits owner-authored command text through the regular B-12 chat/tool path.

### 4. Document and verify

**Files:** `docs/desktop-companion.md`, `wiki/topics/desktop-companion.md`, `wiki/project/desktop-companion-plan.md`, `wiki/project/status.md`, `wiki/index.md`, `wiki/log.md`.

- [x] Document installed controls, persistence, screen placement, host-action boundaries, and limitations.
- [x] Update source provenance and describe reviewed versus not-reviewed scope.
- [x] Run Ruff/format/syntax/JSON/diff/wiki-link checks and a local Qt UI smoke only; do not run automated tests or start server/model/audio/GPU.
- [x] Record exact outcomes and unresolved host/Wayland acceptance in the project journal.
