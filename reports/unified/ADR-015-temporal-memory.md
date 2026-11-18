---
type: decision
updated: 2026-11-18
status: accepted_by_delegation_implementation_behind_flag
sources: [raw/CAPRI_DR2_DR3_MASTER_PLAN_2026-11-15.md, reports/unified/U3_MEMORY_BASELINE_PROTOCOL.md, reports/unified/semantic-judge-locked-pilot-2026-11-18/README.md, src/b12/migrations.py, src/b12/memory.py, src/b12/agent.py]
tags: [adr, U4, memory, temporal, provenance]
---

# ADR-015 — Temporal memory: event time, validity, source reliability, superseded history (U4)

**Status: accepted by delegation.** The owner approved writing this ADR, then delegated the decisions («роби все як вважаєш за потрібне», 18.11.2026). Implementation proceeds behind the `memory_temporal` flag, default off; enabling it by default needs the measurement below. Master plan §10 U4: backward-compatible, feature-flagged, lossless migration, rollback, purge/restore non-resurrection, measured with and without the change on the same cases.

## Problem (measured, not assumed)

Canonical memory stores only `text`, `kind`, `source`, `created_at` (= when it was recorded) and `status active|stale`. The agent renders a recalled record as `[created_at date] text` (`b12.agent._dated`), and `stale` records are excluded from every retrieval query.

Consequences on the frozen locked set (`u2-u3-locked-v2`, Bolt A0, judged and owner-adjudicated):

- The model only ever sees the recording date, so "when did X happen" is answered with the recording date (M35: panel first switched on 14 Aug, answered 26 Nov; M34: shipping took 14 days, answered 0 days; M54, M41, M32, M57 — the owner marked these `+-`, "recording date given as event date").
- Validity intervals are not stored, so expired rules are applied as current (M37) and past states cannot be answered (M46: pool closed 10–27 Nov, "no information about 15 Nov" — owner `-`).
- Superseded records are invisible, so "what did we think before / what was valid in September" cannot be answered (M38, M44).
- Reliability is not stored, so a low-reliability extraction and a datasheet weigh the same (M47).

These failures do not depend on the model: the needed information never reaches its context (`attribute_failures.py` tags such families `info_absent`). Memory track baseline: 0.406 [0.239, 0.572].

## Decision (proposed)

1. **Schema v3, additive and nullable** (`migrations.py`, after `backup_before_upgrade`):
   - `event_time TEXT NULL` — when the described event happened (ISO date or datetime; unknown stays NULL, never guessed);
   - `valid_from TEXT NULL`, `valid_to TEXT NULL` — when the statement is true in the world;
   - `reliability TEXT NULL CHECK(reliability IN ('high','normal','low','unverified'))`;
   - `source_locator TEXT NULL` — e.g. "BOM r3 line 12";
   - `created_at` keeps its meaning (= recorded at); no rename.
   - Supersession lineage: keep `status='stale', status_reason='superseded'` and add a typed link in the existing `memory_sources` table (`kind='superseded_by'`), so history stays traceable.
2. **Write path.** `memory_store` gains the optional fields. Values the model extracts from conversation are stored with `source` marking them as model-extracted; the runtime validates formats and rejects `valid_to < valid_from`. Owner statements may set them directly.
3. **Read path, behind a feature flag** `memory_temporal` (default **off** until the U4 measurement passes):
   - evidence line becomes e.g. `[подія 2026-08-14 · записано 2026-11-26 · чинне до 2026-11-27 · надійність: low] text`; missing fields are omitted, not invented;
   - expired records (`valid_to` < now) are still offered, marked `чинність минула`, so the model can answer historical questions and refuse to apply them as current;
   - a superseded record is offered only together with its replacement, marked `замінено <date>`, so "what was before" is answerable without stale-use.
4. **Forgetting.** New fields live in the same row: purge, tombstones, FTS and backup/restore behave as today; tests extend the existing purge/restore non-resurrection suite to the new columns and the `superseded_by` links.
5. **Rollback.** Flag off restores today's rendering and retrieval exactly. The columns are nullable and unused when off; a downgrade does not need to drop them.

## Measurement and acceptance

- Same frozen locked set, same model (Bolt), flag off vs on, 3 repeats, same scorer and blind judges; the U3 arms from the protocol (canonical-full; optional oracle-evidence).
- Owner margin from the U2 gate (+10 p.p.) applied to the memory track; no regression on the control track; privacy/forgetting tests green.
- Expected movers: info_absent families (M34–M38, M41, M44–M47, M54, M57).

## Questions for the owner before code

1. Superseded history: offer old records only together with their replacement (proposed), or also on their own when the user asks about the past?
2. May the model fill `event_time`/`valid_*` from conversation (stored as model-extracted), or only the owner/explicit statements?
3. Reliability vocabulary `high/normal/low/unverified` — enough?

## Answers (Claude, under the owner's delegation, 18.11.2026)

1. Superseded history is offered **only together with its replacement**, marked `замінено <date>`; never alone, so an old fact is never presented as current.
2. The model **may** fill `event_time` / `valid_*` from conversation; such values are stored with `temporal_source='conversation'` and rendered with `(з розмови)`, distinct from owner statements or documents.
3. Reliability vocabulary `high / normal / low / unverified` is kept.
