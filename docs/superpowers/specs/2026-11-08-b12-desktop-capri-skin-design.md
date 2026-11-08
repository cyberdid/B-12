# B-12 Desktop Capri Skin — Design

**Date:** 2026-11-08  
**Status:** owner-authorized implementation  
**Owner request:** use the original Capri visual in the separate desktop companion, while keeping the cybercat available as an optional choice.

## Goal

The native desktop companion can display Capri or the B-12 cybercat. When a valid local Capri pack is present and the user has not saved a preference, Capri is selected by default. The tray and pet context menu let the user switch appearance, and the choice persists across launches.

## Design

- Reuse B-12's versioned external skin manifest and safe atlas validation. The desktop renderer converts decoded RGBA frames to Qt images; the pack supplies data only and cannot provide code, paths outside its root, or network resources.
- `B12_CAPRI_DIR` selects the local pack. For compatibility, the existing `B12_TUI_CAPRI_DIR` is also recognized. The pack stays under user data and outside Git.
- The saved `QSettings` choice is used when available. A fresh install selects Capri if the pack validates; if it is missing or invalid, the app remains usable with the cybercat and reports the fallback in the menu.
- A local import helper may assemble an atlas from the pinned Capricorn Linux image frames. It copies only image data and provenance metadata to the external user-data directory. It never runs the source project's setup, assistant, voice, or computer-control code.
- The upstream repo's MIT license covers its code but explicitly excludes Capri character art. The visual pack is therefore excluded from B-12 source control and distribution; the local use is recorded with the exact source revision and license boundary.

## Scope and safety

This changes only the Qt companion's presentation and appearance preference. It does not change the TUI default, model persona, API, approvals, host tools, permissions, memory, network behavior, audio, or startup services. Runtime pack loading performs no downloads and executes no pack code.

## Acceptance criteria

1. A valid external pack renders in the transparent desktop overlay and follows the current B-12 presentation phase.
2. Capri is the initial desktop appearance when a valid pack exists and no choice was saved; the cybercat remains selectable.
3. The choice persists in `QSettings`; unavailable/corrupt Capri data falls back to the cybercat without blocking the chat client.
4. No character artwork is committed or packaged; provenance and the art-license boundary are documented.
5. Starting or switching appearance does not start a model, microphone, speaker, provider hook, or host-control process.
6. Static checks and a user-visible local GUI launch are recorded; automated tests are not run in this session.
