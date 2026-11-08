# B-12 Desktop Capri Skin Implementation Plan

> **For agentic workers:** Execute inline in this session. Steps use checkbox syntax for tracking.

**Goal:** Make the native desktop companion use the original Capri visual when a local asset pack is present, while preserving the cybercat as a persistent selectable option.

**Architecture:** Keep the native Qt work isolated from the Textual interface. Move the bounded data-only manifest reader into `b12.skins`, add a Qt adapter that renders its validated RGBA atlas, persist the selected appearance, and add a local asset importer that writes only to user data. The upstream companion code will not run and its artwork will not enter the B-12 repository.

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

### Task 1: Keep desktop independent from the TUI

**Files:** `src/b12/skins.py`, `src/b12/desktop/app.py`, `src/b12/desktop/cat.py`, and `pyproject.toml`.

**Interfaces:** The generic `SkinManifest`/`available_skins` module uses Pillow and has no Textual dependency. The desktop extra installs only Qt and Pillow; the TUI remains a separate entry point.

- [x] Extract the bounded manifest validation into a module shared by UIs.
- [x] Point the desktop imports to `b12.skins`; leave the TUI implementation outside this change.
- [x] Confirm desktop startup imports no TUI/Textual modules.

### Task 2: Build a local Capri image pack

**Files:** Create `scripts/import-capri-skin.py`; write generated `manifest.json` and `atlas.png` only under `~/.local/share/b12/skins/capri`.

**Interfaces:** `python scripts/import-capri-skin.py --source PATH [--dest PATH]` reads the 60 files in `assets/anim/capri/` and three selected pose PNGs; writes a bounded v1 RGBA atlas and its phases/provenance. The separate `assets/anim/eyes/` sequence is not composed because a body registration map was not verified. The importer rejects a source tree whose Git HEAD is not the pinned `7752959e7a708bac5b540d5380321c33694f6fb6`.

- [x] Validate image dimensions, alpha channel, frame counts, and total atlas limits before copying.
- [x] Create the generated pack outside the repository; record the code MIT / character-art exclusion in its manifest and local README.
- [x] Confirm no images or generated atlas are staged in Git.

### Task 3: Render and switch desktop skins

**Files:** Modify `src/b12/desktop/cat.py`, `src/b12/desktop/app.py`, and `docs/desktop-companion.md`.

**Interfaces:** `CompanionOverlay.set_appearance(id, name, atlas)` accepts the built-in `cybercat` or a manifest-discovered pack already validated by the shared loader. A context/tray submenu lists available skins, persists the selected ID in `QSettings`, defaults to Capri when present, and safely falls back to cybercat when it is absent or invalid.

- [x] Add a Qt atlas adapter that reads the shared validated manifest and returns transparent QImage frames by phase.
- [x] Add the persistent appearance menu to the pet context menu and system tray.
- [x] Report unavailable Capri in the menu and leave the cybercat/chat usable.
- [x] Document the pack location, switching behavior, and license boundary.

### Task 4: Update project evidence and launch

**Files:** Update `raw/source-manifest.json`, `wiki/sources/capri-desktop-companions-2026-11-07.md`, `wiki/topics/desktop-companion.md`, `wiki/project/status.md`, `wiki/index.md`, and `wiki/log.md`.

- [x] Pin the additional Linux Capri source, image-only inspection scope, revision, and rights boundary.
- [x] Record that artwork remains external and the original assistant code was not executed.
- [x] Run static Ruff, Python syntax, JSON, wiki-link/index, and diff checks; do not run automated tests in this session.
- [x] Launch the native desktop overlay using the external Capri pack, inspect its window and verify the menu can select the cybercat; leave model/audio disabled.
