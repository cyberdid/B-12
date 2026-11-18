# Arm D (widened claimed-check pattern) vs A0 on Bolt — 18.11.2026

- Same frozen set and runner, 360 runs; prompt A0; the runtime's `_ACTION_CLAIM` widened to any "прочитав/перевірив/переглянув/відкрив/знайшов" for the run. Judges Codex + Gemini: 347/362 unanimous; disputes resolved by Claude under the owner's delegation, item-level where replies in one family differ ([adjudication.json](adjudication.json)).
- Family-level acceptable rate: control 0.731 → **0.654** (−0.077 [−0.192, 0.000]); memory 0.406 → **0.328** (−0.078 [−0.183, +0.011]).
- Helped where aimed: M50 (claimed read of the manual: P1 now reads it in 2/3 runs), M39, M41, M57.
- **Hurt by false positives:** "згідно з інформацією, яку я знайшов" refers to evidence the runtime itself recalled; the widened check nudged, and Bolt answered "Вибач, я не виконував жодних викликів інструментів…" and dropped the correct six steps (M51); similar in M52, M54, M43, C36, C39. Also seen: a fabricated "я перевірив пам'ять за допомогою memory_search" (M54-P2) and, in M50-P2, "немає прямого доступу до файлу" while the read tool exists — neither is a claimed read, so D cannot catch it.
- **Decision (owner margin +10 p.p.): reject D as implemented.** For Capri: widen the built-in check only for claims about files, logs and the system, never for facts the runtime recalled as evidence; a turn may need more than one nudge.
