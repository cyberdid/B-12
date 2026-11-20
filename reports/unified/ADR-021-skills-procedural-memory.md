---
type: decision
updated: 2026-11-20
status: proposed_draft
sources: [wiki/sources/hermes-agent-2026-11-20.md, research/hermes-agent-2026-11-20/notes-D-skills-curator.md, wiki/project/open-questions.md]
tags: [adr, skills, procedural-memory, Q10, hermes-derived]
---

# ADR-021 — Skills as procedural memory

**Status: proposed draft; answers open question Q10 in part (skill acquisition).** Needs the owner's decision; the implementation would be behind the flag `skills`, default off.

## Problem

B-12 remembers facts but not *how* the owner wants a recurring task done. Each time, the model rediscovers the procedure and its pitfalls.

## Decision (proposed)

1. **Format.**
   - A skill is `state_dir/skills/<name>/SKILL.md` in the agentskills.io format Hermes uses: frontmatter `name`, a description of at most 60 characters, then the sections when to use / procedure / pitfalls / verification.
   - Optional `references/` files.
   - The format is compatible with Hermes skills, so the owner can import vetted ones.
2. **Progressive disclosure.**
   - Only an index (name and description) goes into the system prompt, after the stable part.
   - The read-only tool `skill_view(name[, path])` loads the full text.
3. **Writes only through the owner.**
   - The model's `skill_propose` stages a create or patch with a diff. Hermes recommends this for small models.
   - The owner approves through the control path (web UI, CLI). Nothing is written without approval.
4. **Provenance.**
   - Each change records the session and turn it came from.
   - Forgetting that session marks the skill `source_forgotten` and shows it to the owner. It does not silently delete the skill.
5. **Curator** (deterministic, no LLM):
   - unused for 14 days → `stale`; for 30 days → archived (restorable);
   - pinned skills are never touched;
   - a JSONL ledger of every change with digests.
6. **What a good skill is.** The lint rules taken from Hermes:
   - no incident logs (dates, ticket numbers);
   - one rule per lesson;
   - no restating of the tool schemas.

## Measurement before turning it on

- A "repeated task" set: the same task class twice, with a recorded skill in between.
- Metrics:
  - tool calls, failures and turns on the second pass, from `efficiency_report`;
  - quality of the result, by the oracle.
- Exit: fewer wasted calls without a quality loss on gemma4:12b.

## Rollback

`skills` off hides the index and the tools; files stay on disk.
