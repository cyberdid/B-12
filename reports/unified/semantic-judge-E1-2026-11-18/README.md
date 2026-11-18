# Arm E1 (final-only brevity instruction) vs A0 on Bolt — 18.11.2026

- Same frozen set and runner, 360 runs; judges Codex gpt-6-luna + Gemini 4 Hydrogen: 329/347 criteria unanimous; 10 disputed families resolved by Claude under the owner's delegation with the owner's precedents ([adjudication.json](adjudication.json)). Harness-invalid families (C11, C12, C51–C54) excluded.
- Casual replies: median 106 (A0) → 58 (A1) → **75 (E1)** chars; agentic runs with a tool call 108 / 111 / **107** of 120.
- Family-level acceptable rate: control 0.731 (A0) → **0.635** (E1), paired diff −0.096 [−0.269, +0.077]; memory 0.406 → **0.383**, −0.022 [−0.106, +0.044].
- **Decision (owner margin +10 p.p.): reject E1.** Like A1 it shortens casual replies without improving verified completion; neither style arm is adopted. Style changes will be revisited only together with control arms (D) or the E2 renderer.
