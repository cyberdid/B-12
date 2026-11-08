# B-12 Desktop Capri Skin Implementation Plan

> **For agentic workers:** Execute inline in this session. Steps use checkbox syntax for tracking.

**Goal:** Make the native desktop companion use the original Capri visual when a local asset pack is present, while preserving the cybercat as a persistent selectable option.

**Architecture:** Merge the current project `main` into the existing desktop feature branch to reuse the validated external skin manifest. Add a Qt adapter that renders the shared atlas, persist the selected appearance, and add a small local asset importer that copies only image frames into user data. The original companion code will not run and its artwork will not enter the B-12 repository.

**Tech Stack:** Python 3.12–3.13, PySide6-Essentials, Pillow-backed B-12 skin manifest, Qt `QImage`, `QSettings`.

**Spec:** `docs/superpowers/specs/2026-11-08-b12-desktop-capri-skin-design.md`

## Global Constraints

- Desktop stays an optional client of the authenticated loopback API.
- The B-12 cybercat remains available; Capri is the default only when a valid external pack is present and no saved preference exists.
- Capri art stays in `~/.local/share/b12/skins/capri`, outside Git and release artifacts.
- The importer reads only image files from the pinned source revision; never execute its setup, voice, model, or PC-control code.
- Skin loading is local-only, data-only, bounded, and cannot alter permissions or agent behavior.
- Do not start a model, microphone, speaker, provider hook, or host-control process while implementing or viewing the overlay.
- Automated tests are not run in this session; perform static checks and inspect the user-visible launch.

---

### Task 1: Bring the desktop branch up to current main

**Files:** Git merge in the existing `feat/b12-desktop-companion` worktree; resolve any wiki/CLI conflicts while preserving both histories.

**Interfaces:** Import the current main branch's `SkinManifest`, `PackAtlas`, and `available_skins` as the shared source of truth.

- [ ] Merge local `main` into `feat/b12-desktop-companion` without pushing.
- [ ] Resolve conflicts without dropping current main TUI work, desktop work, or wiki chronology.
- [ ] Run `git diff --check` and verify the worktree contains no conflict markers.

### Task 2: Build a local Capri image pack

**Files:** Create `scripts/import-capri-skin.py`; write generated `manifest.json` and `atlas.png` only under `~/.local/share/b12/skins/capri`.

**Interfaces:** `python scripts/import-capri-skin.py --source PATH [--dest PATH]` reads `assets/anim/capri/*.png`, `assets/anim/eyes/*.png`, and selected transparent pose PNGs; writes a bounded v1 RGBA atlas and its phases/provenance. It rejects a source tree whose Git HEAD is not the pinned `7752959e7a708bac5b540d5380321c33694f6fb6`.

- [ ] Validate image dimensions, alpha channel, frame counts, and total atlas limits before copying.
- [ ] Create the generated pack outside the repository; record the code MIT / character-art exclusion in its manifest and local README.
- [ ] Confirm no images or generated atlas are staged in Git.

### Task 3: Render and switch desktop skins

**Files:** Modify `src/b12/desktop/cat.py`, `src/b12/desktop/app.py`, and `docs/desktop-companion.md`.

**Interfaces:** `CyberCatOverlay.set_skin(skin_id)` accepts only a validated built-in `cybercat` or manifest-discovered pack ID. `skin_changed(str)` notifies the shell. A context/tray submenu lists available skins, persists the selected ID in `QSettings`, defaults to Capri when present, and safely falls back to cybercat when it is absent or invalid.

- [ ] Add a Qt atlas adapter that reads the shared validated manifest and returns transparent QImage frames by phase.
- [ ] Add the persistent appearance menu to the pet context menu and system tray.
- [ ] Report unavailable Capri in the menu and leave the cybercat/chat usable.
- [ ] Document the pack location, switching behavior, and license boundary.

### Task 4: Update project evidence and launch

**Files:** Update `raw/source-manifest.json`, `wiki/sources/capri-desktop-companions-2026-11-07.md`, `wiki/topics/desktop-companion.md`, `wiki/project/status.md`, `wiki/index.md`, and `wiki/log.md`.

- [ ] Pin the additional Linux Capri source, image-only inspection scope, revision, and rights boundary.
- [ ] Record that artwork remains external and the original assistant code was not executed.
- [ ] Run static Ruff, Python syntax, JSON, wiki-link/index, and diff checks; do not run automated tests in this session.
- [ ] Launch the native desktop overlay using the external Capri pack, inspect its window and verify the menu can select the cybercat; leave model/audio disabled.
