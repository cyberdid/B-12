---
type: decision
updated: 2026-11-20
status: proposed_draft
sources: [wiki/sources/hermes-agent-2026-11-20.md, research/hermes-agent-2026-11-20/notes-C-memory.md, src/b12/enrichment.py, src/b12/reflection.py, src/b12/tools/memory.py]
tags: [adr, memory, self-improvement, hermes-derived]
---

# ADR-020 — Post-turn memory review

**Status: proposed draft.** Needs the owner's decision; the implementation would be behind the flag `memory_review`, default off.

## Problem

- Memory is written only when the model calls `memory_store` during the turn.
- Small models often say "I will remember" without calling it. We measured this on Bolt (M50); Hermes' documentation reports the same for models under about 30B.
- A write during the turn also costs the user latency.

## Decision (proposed)

1. **When the review runs.**
   - After a completed owner turn with consent, a background review runs. It reuses the scheduler's idle slot and never runs during a user's turn.
   - A new turn cancels the review, as in Hermes ("self-improvement must never block a user").
2. **What the review sees.**
   - Input: the turn's user message and final reply, plus the facts already stored that the retrieval offered.
   - Prompt: the grounding rule (`memory_grounding`), with one output per candidate: `{text, kind, origin=explicit, evidence: turn id}`.
3. **How candidates are written.**
   - Each candidate is written through the same `MemoryStore.remember` with the turn as evidence. Forgetting the turn's session therefore removes it.
   - No `forget` or `supersede` from the review: such changes go to the owner's pending list (Hermes stages these even with its gate off).
   - Duplicates are skipped, matched as exact text of a live record of the same actor.
4. **Owner gate (optional).** `memory_review_approval` stages candidates instead of writing them; the owner approves in the web UI or CLI.

## Measurement

- Scenarios: M50-like "remember X" turns where the model does not call the tool, plus turns with no memorable fact.
- Metrics:
  - **recall:** the fact stored and later retrieved;
  - **precision:** no invented or inferred records;
  - duplicates;
  - added background tokens.
- Exit: recall up, precision not down, measured on gemma4:12b with clustered intervals.

## Rollback

`memory_review` off; records already written stay ordinary, traceable memory.
