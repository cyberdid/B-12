# Capri Persona and Brand Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Capri the user-facing assistant identity and connect bounded desktop profile preferences to model responses.

**Architecture:** Keep the B-12 runtime and control plane intact. Add a bounded profile field to the existing chat request, format it as non-operational style context inside the active agent turn, and source it from the existing local desktop profile. Change visible names while preserving package, API, state, hook, and QSettings identifiers.

**Tech Stack:** Python 3.12, FastAPI/Pydantic, Qt/PySide6, existing `Agent`/desktop API client.

**Spec:** `docs/superpowers/specs/2026-11-08-capri-persona-brand-design.md`

## Global Constraints

- Consent and permissions come only from the existing control plane.
- Owner profile text can influence wording only and is never stored as memory or transcript content.
- Keep API and internal `b12` identifiers stable.
- Do not copy upstream prompts, authored lines, source code, or artwork.
- Do not add unsolicited background speech, jealousy, or monitoring.

---

### Task 1: Capri persona context and request wiring

**Files:**
- Create: `src/b12/persona.py`
- Modify: `src/b12/agent.py`
- Modify: `src/b12/api.py`
- Modify: `src/b12/desktop/client.py`
- Modify: `src/b12/desktop/chat.py`
- Modify: `src/b12/desktop/app.py`
- Modify: `src/b12/desktop/profile.py`

**Interfaces:**
- `build_companion_profile_context(profile: Mapping[str, object] | None) -> str` returns an empty string or a bounded style-only instruction block.
- `/api/chat` optionally accepts a strict `companion_profile` object with `name`, `style_note`, and `catchphrases` only.
- `DesktopApiClient.stream_turn(..., companion_profile: dict | None = None)` sends that object only when supplied.

- [x] Update the main system identity to Capri while retaining every existing tool, memory, consent, and safety rule.
- [x] Add a pure formatter that bounds name/style/phrase lengths, serializes user values clearly as data, and explicitly limits them to wording preferences.
- [x] Validate the optional API profile with strict Pydantic fields and pass it to `Agent.turn`.
- [x] Store only the formatted context in in-memory turn state; append it to the model system prompt on each reasoning round, including resumed approval turns.
- [x] Add an optional desktop profile provider to `ChatWindow`; `DesktopShell` supplies the current local profile at send time.
- [x] Update the profile dialog copy to say the saved style and phrases now affect replies automatically.
- [x] Run syntax/format/whitespace checks; do not start the server, model, audio, or tools.

### Task 2: Visible Capri rename and project notes

**Files:**
- Modify: `src/b12/desktop/app.py`, `src/b12/desktop/chat.py`, `src/b12/desktop/cat.py`, `src/b12/desktop/actions.py`, `src/b12/desktop/local_features.py`, `src/b12/desktop/presentation.py`, `src/b12/desktop/integrations.py`
- Modify: `src/b12/tui/app.py`, `src/b12/tui/preview.py`, `src/b12/web/index.html`, `src/b12/web/style.css`, visible web labels as needed
- Modify: `README.md`, `docs/desktop-companion.md`, `wiki/project/status.md`, `wiki/topics/desktop-companion.md`, `wiki/project/desktop-companion-plan.md`, `wiki/index.md`, `wiki/log.md`
- Modify: `raw/source-manifest.json` only if the new source review changes its recorded scope

**Interfaces:**
- User-facing assistant name is Capri; visual appearance selection between Capri and Кіберкіт is independent of assistant identity.
- Existing install commands, Python import paths, API paths, QSettings namespace, state directory, and hook ownership markers remain backward-compatible.

- [x] Replace user-visible B-12 assistant/product labels with Capri; retain technical and historical identifiers.
- [x] Keep `QSettings("B-12", "NeonCompanion")` to preserve saved profile, skin, and desktop preferences.
- [x] Update current documentation to distinguish Capri the assistant from the existing B-12 runtime namespace.
- [x] Record the accepted scope, source references, limits, and static-check results in the wiki; leave historical source notes unchanged.
- [x] Run `python -m compileall -q src/b12`, JSON parsing for the source manifest, and `git diff --check`; do not add/run tests or launch user services.
