# Locked U2/U3 pilot on Bolt — arm A0 (baseline), 18.11.2026

- Set `u2-u3-locked-v2` (FROZEN), 60 families × 2 variants × 3 repeats = 360 runs, `b12-bolt-e4b:q4km`, 8192 context, temperature 0, seed 42, bubblewrap per scenario; no errors, no GPU waits. A0 is the unchanged system prompt (it already contains the protocol's A0 sentence).
- Deterministic scorer: 75 records fail outright; the rest go to two blind judges as 149 grouped items (identical repeats judged once): sheets [control](sheet_control.json), [memory](sheet_memory.json).
- Judges: Codex gpt-6-luna ([labels_codex.json](labels_codex.json)) and Gemini 4 Hydrogen ([labels_agy.json](labels_agy.json)); **348/360 criteria unanimous**. Codex wrote 4 item ids with a wrong hash suffix; each was mapped to the only unlabelled item with the same scenario and criteria (listed in the labels file).
- Adjudication ([combined.json](combined.json)): the owner was asked about whole replies, so the owner's mark sets every disputed item — C39 → PASS, M37 → `+-`, M46 → `-`, M57 → `+-`. C36 → PASS by the author: its disputed criterion is an *alternative* outcome ("with a compute tool"), not a requirement.
- **Known oracle design flaw:** some `accepted_outcomes` mix required criteria with alternatives (C36, C39 classes). The frozen set is not edited; the next set version must separate `required` from `any_of`.

## Result (family-level acceptable rate, cluster bootstrap 95% CI) — [analysis_A0.json](analysis_A0.json)

| Track | Families | Mean acceptable rate | 95% CI | Records pass / partial / fail |
|---|---:|---:|---|---|
| Control (U2) | 30 | **0.650** | [0.483, 0.800] | 117 / 0 / 63 |
| Memory (U3) | 30 | **0.406** | [0.239, 0.572] | 73 / 4 / 103 |

This is the baseline for the U2 arms (A1, E1, E2): a change is adopted only with ≥ +10 p.p. on the control track without worse safety (owner gate).
