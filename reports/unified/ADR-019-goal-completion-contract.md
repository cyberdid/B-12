---
type: decision
updated: 2026-11-20
status: proposed_draft
sources: [wiki/sources/hermes-agent-2026-11-20.md, research/hermes-agent-2026-11-20/notes-E-autonomy.md, src/b12/goals.py, src/b12/autonomy.py]
tags: [adr, goals, autonomy, hermes-derived]
---

# ADR-019 — Goal completion contract and more trusted checks

**Status: proposed draft.** It changes goal behaviour, so it needs the owner's decision. The implementation would sit behind the flag `goal_contract`, default off.

## What exists (verified in code)

- A goal has an immutable `intent` and `criteria` (SQLite trigger), a turn budget and a review interval.
- `achieved` requires live evidence IDs; `check_spec` supports only `file_contains` (`autonomy.check_passes`).
- The model cannot define new check kinds. "Done" never comes from a model claim.

## Problem

- `criteria` is free text, so nothing structured says what must not regress, which files and tools are in scope, or when to stop and ask.
- `file_contains` covers few real goals ("tests pass", "service answers", "file has exactly this content").

Hermes `/goal` has an optional contract (`outcome`, `verification`, `constraints`, `boundaries`, `stop_when`) and shell quality gates. Its final verdict, however, is an LLM judge reading the agent's last reply, and it fails open. We keep our rule, "done needs trusted evidence", and take only the structure.

## Decision (proposed)

1. **Contract fields**, all optional and immutable with the intent:
   - `verification`: which trusted check proves the outcome;
   - `constraints`: what must not change;
   - `boundaries`: allowed paths and tools, intersected with the grant and never widening it;
   - `stop_when`: a condition that pauses the goal with `needs_owner`.
2. **Who sets the contract.** The model may *propose* a contract; only the owner's control path accepts it. Until accepted, the goal runs on `criteria` as now.
3. **New trusted check kinds** (runtime code, not model text):
   - `file_sha256`: the exact digest;
   - `command_exit_zero`: an allowlisted command run in the evaluation sandbox, without network, with a timeout;
   - `http_status`: only for hosts in `network_allow`.
   - Each check records its output tail as evidence.
4. **Gate order per review.** Trusted checks run first. A failing check feeds its output tail into the next goal turn (as Hermes does) and counts toward `failure_streak`. Three failures in a row pause the goal with the reason shown to the owner.
5. **`boundaries` enforcement.** Calls outside the boundaries are refused by the registry with `outside_goal_boundaries` before control prepare.

## Measurement

A synthetic goal set:
- goals reachable only by fixing a failing command;
- goals that would be "claimed done" without a check;
- goals that hit `stop_when`.

Metrics:
- false completions: must stay 0;
- turns to completion;
- wrongly continued goals after `stop_when`;
- out-of-boundary calls.

Scripted model first, then gemma4:12b on Colab.

## Rollback

`goal_contract` off ignores the new nullable columns.
