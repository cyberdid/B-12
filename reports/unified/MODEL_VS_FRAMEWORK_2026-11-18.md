---
type: report
updated: 2026-11-18
status: compiled
sources: [reports/unified/attribution_three_models.json, reports/unified/semantic-judge-locked-pilot-2026-11-18/README.md, reports/unified/semantic-judge-haiku-2026-11-18/README.md, reports/unified/semantic-judge-luna-2026-11-18/combined.json]
tags: [U2, U3, attribution, model-vs-framework]
---

# Model or framework? Bolt vs Claude Haiku vs gpt-6-luna on one frozen set

**Question (owner, 18.11.2026):** «може причина помилок не в нашому фреймворку — а в самій моделі». Same frozen locked set (`u2-u3-locked-v2`), same B-12 runtime, sandbox, scorer and blind judges; only the model differs. Bolt 3 repeats (A0), Haiku and gpt-6-luna 1 repeat each through the subscription bridge (no local context/reply limits). Judges never from the judged model's family (Bolt/Haiku: Codex + Gemini; luna: Gemini + Claude Opus); disputes adjudicated by the owner (Bolt) or by Claude under the owner's delegation with the owner's precedents. Families with an unstubbed synthetic environment (C11, C12, C51–C54) excluded.

| Track | Bolt | Haiku | gpt-6-luna |
|---|---|---|---|
| Control (26 families) | 0.731 [0.558, 0.885] | 0.731 [0.577, 0.865] | 0.750 [0.577, 0.904] |
| Memory (30 families) | 0.406 [0.239, 0.572] | 0.500 [0.317, 0.667] | 0.417 [0.250, 0.567] |

Stronger cloud models barely move the totals: **the runtime, not the model, limits Capri most.**

## Families every model fails (16) — where to fix

| Cause | Families | Fix |
|---|---|---|
| Memory metadata never reaches the model (event date, validity, reliability, superseded history) | M34, M35, M36, M38, M44, M45, M46, M47, M49, M59 | ADR-015 / U4 (implemented behind `memory_temporal`; measurement running) |
| Goal state not visible in chat (active list, partial progress) | M53, M55 | U5: goal-state projection into context or a read-only goal tool |
| Written files never verified | C58, C59 | Runtime read-back / hash check after `file_write` (deterministic completion verifier) |
| Oracle too strict (alternatives required together) | C35, C40 | Next set version separates `required` from `any_of` |

## Bolt-only (model) failures (7)

C57 (no `sudo_exec` call), M50 (claims a read without a tool call), and memory families where models disagree (M33, M37, M39, M41, M42). For M50 the widened claim check (arm D) helps partly; C57 needs a stronger model or a runtime rule. Bolt passes C39 where both cloud models fail.

## Caveats

One repeat for cloud models; cloud CLIs give the model the real date (18 Nov) while records are dated 30 Nov; gpt-6-luna M35-P2 exceeded a 400 s round and C38-P2 the turn deadline (counted as failures).
