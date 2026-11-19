---
type: decision
updated: 2026-11-19
status: proposed_draft
sources: [raw/CAPRI_DR2_DR3_MASTER_PLAN_2026-11-15.md, src/b12/control.py, src/b12/tools/registry.py, src/b12/autonomy.py, src/b12/goals.py, src/b12/sessions.py]
tags: [adr, U6, workflow, recovery, idempotency]
---

# ADR-017 — Goal step ledger and crash-safe reconciliation (U6)

**Status: proposed draft.** Master plan U6 requires owner review before production behaviour changes. Written 19.11.2026 while the owner delegated decisions; implementation goes behind the flag `task_ledger`, default off, until the crash-injection suite passes.

## What exists (verified in code)

- `ControlPlane.operations`: every tool call is `proposed → (approved) → started → completed|failed|unknown`, keyed by an HMAC of `(actor, session, turn, call id)`. A replayed call in the **same turn** is blocked (`replay_blocked`); on restart every `started` operation becomes `unknown/interrupted` and is never retried. Approvals are bound to the argument digest, capability and control revision, consumed once, and expire.
- `cancel_turn` marks running operations `unknown/cancelled` and erases pending approvals.
- Background goals (`autonomy.run_goal`) run one **new turn** per review, then write a goal checkpoint (`[state] reply`, budget, evidence).

## Problem

The idempotency key contains the turn id, so it does not survive across turns. If the process stops after a side effect but before the goal checkpoint, the next review starts a fresh turn, the model sees the old checkpoint and may repeat the same effect: an append, a note, a command, a network request. The earlier operation sits in the ledger as `unknown`, but nothing consults it. Nothing reconciles `unknown` against the real world either; it stays unknown for ever.

## Decision (proposed)

1. **Goal step ledger** (`control.sqlite3`, table `goal_steps`): one row per **effectful** tool call (capability not `*.read`) made inside a goal turn: `goal_id`, `plan_revision`, `effect_key`, `operation_id`, `state`, `turn_id`, `verified_by`, timestamps. `effect_key = HMAC(goal_id, plan_revision, tool, canonical argument digest)`, so the key is the same across turns for the same intended effect. Turns of a goal are linked through a `task_goals(task_id, goal_id, plan_revision)` row written by autonomy before the turn starts.
2. **Dedupe before execution** (registry, after `prepare` admits the call, before the handler runs; goal turns only):
   - a step with the same key already `completed` (or `reconciled_completed`) → the handler is not run; the model receives the recorded outcome marked «already done in an earlier run»;
   - a step `unknown` → run the tool's **trusted state verifier** if it has one: effect present → `reconciled_completed`, not repeated; effect absent → `reconciled_absent`, the call may run once; no verifier → `needs_owner`: the call is refused with `unknown_outcome_needs_owner`, the goal is paused with that reason, and the owner sees it in pending items. Unknown is never blind-retried.
3. **Verifiers** (runtime code, not model text): `file_write` — the target's SHA-256 equals the digest of the intended content; `memory_store` — a live record with the same actor and exact text exists; `note_add` — the note exists. `run_command`, `shell_exec`, `sudo_exec`, `http_fetch` with a body and MCP tools have no verifier and go to `needs_owner`.
4. **Plan revision**: `goals.plan_revision` starts at 1 and increases only through owner control (reopen, explicit replan). Steps of an older revision are not reused, so a deliberate repeat after a replan is allowed.
5. **Resume revalidation**: resuming an approval-waiting turn re-checks turn cancellation, grant validity and expiry, control revision and the exact approval digest (most exists; the suite pins it).
6. **Out of scope**: an explicit step DAG with dependencies (the model still plans inside each turn; the ledger records effects, not plans); distributed or multi-host execution.

## Measurement (U6 exit)

Crash-injection suite with a scripted model that repeats the same effect after a restart. Fault points: (a) after `started`, before the handler; (b) after the effect, before `finish`; (c) after `finish`, before the goal checkpoint; (d) during the checkpoint write; (e) after approval consumption, before `started`; (f) owner cancellation during the effect. For each tool class (verifiable, unverifiable): count effects in the synthetic world after recovery. **Exit:** zero duplicated side effects, zero false completions, zero blind retries of `unknown` across the suite; recovery runbook `CAPRI_WORKFLOW_RECOVERY.md`.

## Rollback

`task_ledger` off restores current behaviour. The new tables are additive in `control.sqlite3`; they are ignored when the flag is off.
