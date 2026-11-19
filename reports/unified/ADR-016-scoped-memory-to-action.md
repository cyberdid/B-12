---
type: decision
updated: 2026-11-19
status: accepted_by_delegation_implementation_behind_flag
sources: [raw/CAPRI_DR2_DR3_MASTER_PLAN_2026-11-15.md, reports/unified/ADR-015-temporal-memory.md, reports/unified/CAPRI_MEMORY_BASELINE.md, reports/unified/CAPRI_U4_TEMPORAL_ABLATION.md, reports/unified/ADR-016-implementation-check-2026-11-19.md, reports/unified/U5-author-preflight-2026-11-19.md, evals/unified/scenario_sets/u5-application-v2.json, src/b12/agent.py, src/b12/api.py, src/b12/cli.py, src/b12/config.py, src/b12/context.py, src/b12/contracts.py, src/b12/goals.py, src/b12/memory.py, src/b12/memory_packet.py, src/b12/migrations.py, src/b12/runtime.py, src/b12/tools/memory.py]
tags: [adr, U5, memory, preferences, goals, decision]
---

# ADR-016 — Scoped memory-to-action: preference scope, protected commitments, decision packet (U5)

**Status: accepted by delegation; implementation present behind an opt-in flag** (owner: «давай U5», 19.11.2026; decisions delegated since 18.11). `memory_scoped` defaults off. The U5 benchmark has not run, and the scenario set remains DRAFT pending independent oracle review.

## Problem (measured)

After U4 the model sees when a fact happened and whether it is still valid, but the evidence is still a list of strings with a prefix. On the locked set (`CAPRI_U4_TEMPORAL_ABLATION.md`) what still fails is **applying** memory to a decision:

- **Preference scope:** a preference stated for a situation is applied outside it, or an expired one is applied as current (M37: 0.33 in U4). No field says *when* a preference applies or whether the owner said it or the model inferred it. Revocation has no own meaning: it is the same "superseded" status as a replaced fact.
- **Conflicts:** two current records that disagree are reported inconsistently (M41, M42: datasheet vs recollection answered both ways).
- **Commitments:** `goals_in_context` lists cancelled goals next to open ones; the model put a cancelled task under "open tasks" (M53, F). Nothing in the runtime stops a cancelled goal from becoming active again through a status change.
- **No evidence:** an empty recall is invisible to the model, which then sometimes answers from general knowledge (M56, M57 classes).

## Decision

1. **Schema v4, additive and nullable** (same pattern as ADR-015; old rows keep NULL = unknown):
   - `applies_when TEXT NULL`: the condition in words under which a preference or rule applies ("під час ремонту кухні"); NULL = always within its validity.
   - `origin TEXT NULL` ∈ {`explicit`, `inferred`}: the memory writer's source classification; NULL = unknown. For `memory_store`, this is a model-supplied annotation and is not independently verified by the runtime.
   - Revocation: `supersede` without a replacement records `status_reason='revoked'` (was `superseded`); a revoked record is never offered as evidence, even as history.
   - `memory_store` (with `memory_scoped`) accepts `applies_when` and `origin`.
2. **Decision packet** (`memory_scoped`): automatic recall and `memory_search` return `{id, text, meta}` objects rather than prefixed text. `meta` carries `kind`, `event`, `recorded`, `valid`, `state` (`чинне`, `минуло`, `ще не чинне`, `замінено`), `applies_when`, `origin`, `reliability`, `source`, source references, and optional `conflicts_with`. That field is only a lexical same-subject candidate link (≥2 shared content stems among currently valid records), not a semantic contradiction judgment. Application guidance uses only current evidence under its scope; treats a current explicit-owner record as stronger than a conflicting inference, while disclosing that `origin` is a model annotation rather than verified provenance; uses expired/replaced records only for historical questions; surfaces other unresolved conflicts and asks; and says when no memory evidence was found. Revoked and source-invalid records are omitted. The runtime does not enforce whether the model actually applies the packet correctly.
3. **Protected commitments** (`memory_scoped`): the goal context separates open tasks from closed ones, and closed ones are labelled «не відновлювати без прямої вказівки власника». An achieved goal whose stored evidence later becomes stale is marked «доказ виконання вже не чинний». Correction: if that evidence is explicitly forgotten, the existing transitive-purge invariant deletes dependent goal content; B-12 does not retain a stale-goal marker after forgetting. In the runtime, `GoalStore.set_status` refuses to move a goal from `abandoned` or `achieved` to another status unless a trusted caller passes `reopen=True`; only owner control paths (CLI, API) do so. `GoalStore.complete` cannot mark an abandoned goal achieved. Protection applies regardless of the flag.
4. **Out of scope:** the key/value preferences in `GoalStore` (no scope field; shown as before); automatic preference inference. A model may label a write as `inferred`, but that label is not proof of the inference's correctness.

## Implementation checkpoint — 19.11.2026

The opt-in path is implemented through configuration, tool schemas, memory retrieval, context admission, and goal rendering. The prompt explicitly distinguishes a current explicit-owner record from a conflicting assistant inference; `origin` remains an unverified annotation. A prompt regression verifies this instruction and preserves the ask-on-other-conflicts rule. Tests and scripted models do not establish model-level decision quality. See the [implementation check](ADR-016-implementation-check-2026-11-19.md).

## Measurement (U5 exit)

- Current review target **`u5-application-v2`** (M61–M84, 24 families × 2 variants, synthetic) is DRAFT. It corrects two policy/corpus inconsistencies found in the author pre-review: M68 now discloses both conflicting records and asks; M83 makes the general wake-time preference apply at home, so it does not conflict with the trip-only preference. The prompt policy for explicit-vs-inferred memory is now explicit and tested. `u5-application-v1` is preserved as RETIRED; no blind review or model run was made against it. Two independent blind oracle reviews are still required before freezing v2; do not run the DRAFT.
- Arms on Bolt, 3 repeats: **B0** = current defaults (`memory_temporal`, `goals_in_context`), **U5** = B0 + `memory_scoped`. Also U5 on `u2-u3-locked-v2` to check that nothing regresses there.
- **Decision quality**: family acceptable rate (same pipeline: deterministic scorer, two blind judges, adjudication by owner precedents, aligned verdicts, cluster bootstrap). Owner margin +10 p.p.
- **Stale-use** and **resurrection** rates: oracles tag their forbidden effects (`stale_use`, `resurrection`); the rate of records where judges mark such an effect must not rise in U5.

## Rollback

`memory_scoped` off restores the U4 behaviour exactly; schema v4 columns are nullable and ignored when the flag is off. `reopen=True` protection stays (owner paths are unchanged in effect).

## Status update — 19.11.2026 (measured)

Measured on the frozen `u5-application-locked-v1` ([CAPRI_U5_DECISION_REPORT.md](CAPRI_U5_DECISION_REPORT.md)): decision quality 0.618 → 0.743, +12.5 p.p. [+1.4, +26.4]; stale-use 0/30 and resurrection 0/24 in both arms; over-application 4/36 → 0/36. The freeze relied on Gemma 4 12B and Bolt oracle reviews; the stronger blind Codex/Gemini reviews of v1 found issues that partly remain, and a sensitivity split shows the same +12.5 p.p. on the uncontested half. `memory_scoped` stays off until the non-regression run on `u2-u3-locked-v2` is judged.
