---
type: decision
updated: 2026-11-20
status: proposed_draft
sources: [wiki/sources/hermes-agent-2026-11-20.md, research/hermes-agent-2026-11-20/notes-E-autonomy.md, src/b12/autonomy.py, reports/unified/ADR-018-initiative-inbox.md]
tags: [adr, autonomy, schedules, hermes-derived]
---

# ADR-022 — Owner schedules ("every morning at 8 — a summary")

**Status: proposed draft.** Needs the owner's decision; the implementation would be behind the flag `schedules`, default off.

## Problem

Goals have a review interval but no wall-clock schedule. The owner cannot ask for "every weekday at 8:00, a short summary of my notes and goals" or "remind me on Friday at 17:00".

## Decision (proposed)

1. **What a schedule is.**
   - Data: `cron` expression or one-shot time, timezone, prompt, allowed tools (no wider than the owner's grant) and a turn budget.
   - Created only through the owner's control path; the model may propose one.
2. **How a run executes.**
   - Each run is a fresh background turn, as a goal review is, through the scheduler's single lock.
   - The output becomes an `InitiativeCandidate`, so ADR-018 decides deliver, defer or inbox. Quiet hours and owner stop are respected.
3. **Taken from Hermes cron:**
   - a catch-up window: half the period, clamped to 2 minutes–2 hours; older misses are skipped;
   - a re-run only when no model call was made (network or Ollama down): 5/15/30 minutes;
   - `[SILENT]` in the reply → `drop`;
   - `failure_streak` ≥ 3 → pause with the reason shown to the owner;
   - a scheduled run cannot create schedules.
4. **Effects.** These go through the ADR-017 step ledger, so a restart never repeats one blindly.

## Measurement

- Deterministic replay with a fake clock:
  - missed and caught-up runs;
  - quiet hours;
  - stop;
  - Ollama down → re-run;
  - silent replies;
  - failure streaks.
- Then one live week with the owner, opt-in.

## Rollback

`schedules` off; the table is additive and ignored.
