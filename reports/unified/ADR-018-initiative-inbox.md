---
type: decision
updated: 2026-11-19
status: accepted_by_owner_enabled_by_default
sources: [raw/CAPRI_DR2_DR3_MASTER_PLAN_2026-11-15.md, src/b12/attention.py, src/b12/autonomy.py, src/b12/goals.py, src/b12/api.py]
tags: [adr, U7, initiative, attention, inbox]
---

# ADR-018 — Initiative inbox with a deterministic five-way gate (U7)

**Status: proposed draft.** Master plan U7 requires owner review before production behaviour changes. Implementation goes behind the flag `initiative_gate`, default off.

## What exists (verified in code)

- `AttentionPolicy.decide`: owner stop, quiet mode, quiet hours, an hourly cap, cooldown with exponential backoff after ignored or dismissed proposals, and an urgent bypass. Feedback is `engaged | ignored | dismissed`. Quiet silences delivery only; stop also halts background execution.
- `autonomy.run_goal` turns **every** goal review into a proposal (`Ціль «…»: <reply>`), delivered when attention allows, otherwise stored as undelivered.

## Problem

- **Too much gets delivered.** Nothing checks whether a proposal is worth saying. A routine «nothing new» review is delivered like a finding; the same text is delivered again on the next review.
- **Stale or closed sources still produce proposals.** A proposal is made even if its goal was cancelled in the meantime or its evidence became stale. The only filter is the rate limit.
- **No inbox.** An undelivered proposal is stored but never resurfaces in a bounded way. «Quiet» therefore loses things instead of postponing them.
- **No high-risk path.** A proposal that suggests a destructive or external action is delivered like any other.

## Decision (proposed)

1. **`InitiativeCandidate`** (data, not model text): `actor_id`, `goal_id`, `trigger` ∈ {`goal_review`, `deadline`, `source_revision`, `dependency`}, `evidence_ids`, `text`, `risk` ∈ {`info`, `action`, `high`}, `due_at` (optional), `novel` (the runtime sets it false when the review reported no change, i.e. a completed turn with no effectful tool call and no new evidence).
2. **Five-way decision**, evaluated in this order; first match wins:
   - `drop`: goal not active (abandoned, achieved, failed); any cited evidence no longer live; same dedupe key (goal + normalized text digest) delivered or queued in the last 24 h; `novel` false and no deadline within 24 h.
   - `needs_owner`: `risk = high`. The proposal goes to the inbox flagged for approval and is never spoken unprompted.
   - `deliver`: attention allows it, or `deadline` with `due_at` within 2 h (urgent, so quiet mode is bypassed but owner stop is not).
   - `defer`: attention refuses because of quiet hours, cooldown or the cap. Kept with `not_before` = the end of the blocking window and re-decided then; it expires after 48 h.
   - `inbox`: quiet mode, or owner stop. Visible on request (`/api/proposals`, CLI), never spoken.
3. **Feedback**: `engaged`, `ignored`, `dismissed` (as now) plus `mute_goal`, which drops further non-urgent candidates of that goal until the owner unmutes it.
4. **Semantics**: quiet means nothing is spoken but work goes on and the inbox fills; stop means no background execution and no speech. Neither is a delete.

## Measurement (U7 exit)

An offline replay set of synthetic candidates with expected decisions, at least 5 per class: relevant, irrelevant (not novel), quiet, stale evidence, cancelled goal, high-risk, duplicate, urgent deadline under quiet. The gate is deterministic, so the replay runs without a model.

- **False-positive interventions**: delivered when the expected decision is not `deliver`.
- **Missed high-value**: expected `deliver` or `needs_owner` but the gate gave `drop` or `inbox`.

**Exit:** both rates are reported per class, and the quiet/stop semantics hold in tests. Any opt-in prospective study with the owner comes only after this.

## Rollback

`initiative_gate` off keeps the current behaviour: every review becomes a proposal, filtered only by attention. The new columns are additive.

## Owner decision — 20.11.2026

The owner approved the ADR; the flag is on by default.
