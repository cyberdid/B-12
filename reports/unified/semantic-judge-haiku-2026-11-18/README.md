# Claude Haiku (subscription bridge) on the locked set — 18.11.2026

- Same frozen set and runtime as Bolt A0; 1 repeat; no local context/reply limits (owner decision). 45 memory runs hit the shared Claude subscription limit at 17:45–17:50 (bridge `http_error`); they were set aside in `infra-failed-subscription-limit-1745/` and re-run.
- Judges Codex gpt-6-luna + Gemini 4 Hydrogen (never a Claude judge for a Claude model): 237/248 criteria unanimous; 11 disputes resolved by Claude under the owner's delegation using the owner's precedents ([combined.json](combined.json)).
- **Harness finding:** families whose setup describes a synthetic environment (C11, C12, C51–C54: disk, uptime, local services) are not stubbed — tools return the real sandbox values, so the oracle is unreachable for every model. They are excluded from all rates (`analyze_pilot.HARNESS_INVALID`) until an environment stub exists.
- **Confound:** a cloud model is given the real date by its CLI (Haiku: "сьогодні 18 листопада") while synthetic records are dated 30 Nov; hedging in M39/M42 comes from this.

| Track | Bolt A0 | Haiku | 
|---|---|---|
| Control (26 families) | 0.731 [0.558, 0.885] | 0.731 [0.577, 0.865] |
| Memory (30 families) | 0.406 [0.239, 0.572] | 0.500 [0.317, 0.667] |

Attribution ([../attribution_bolt_vs_haiku.json](../attribution_bolt_vs_haiku.json)): control — 20 all-pass, 4 both fail, model-only C57 (+ M50 in memory), Bolt-only pass C39; memory — 12 all-pass, **13 both fail (10 with required metadata never reaching the model)**, 5 model-only (M33, M39, M41, M42, M50). Memory failures are mostly framework; ADR-015/U4 targets them.
