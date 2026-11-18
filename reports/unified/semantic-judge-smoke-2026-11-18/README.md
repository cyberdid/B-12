# Blind semantic judging — U2/U3 smoke run (18.11.2026)

- Sheet: [sheet.json](sheet.json) — 14 executed records, 39 prose criteria left by `score_u2_u3.py`; no model name or verdicts. Rubric: [rubric.md](rubric.md); schema: [schema.json](schema.json).
- Judges, each in an empty directory and blind to the other and to the author: Codex `gpt-6-luna` xhigh ([labels_codex.json](labels_codex.json)); agy **Gemini 4 Hydrogen (XHigh)** ([labels_agy.json](labels_agy.json)). The evaluation article used Gemini 4 Argon, so agreement figures are not directly comparable; the owner chose to keep Hydrogen.
- Combined ([combined.json](combined.json)): 35/39 criteria unanimous, 4 disputed.
  - SEMANTIC_PASS: C01, C06, C07, C10, C15, C19, M26.
  - SEMANTIC_FAIL: C22 (no read-back), M01 (record date as calibration date), M04 (record date as event date), M08 (ignores present evidence), M18 (claims a read without a tool call).
  - NEEDS_OWNER: C02 (is "спостерігаю за потоком даних у Нічному Місті" a fabricated status claim or persona flavour?), M12 (is naming the refuted hypothesis without who/when enough?).
- The M01 dispute (`invented_value`) does not change its verdict: the date criteria already fail unanimously.

## Owner adjudication (18.11.2026)

- **C02 → PASS** (`yes`): «це від самого персонажа — від його персони. треба подумати як це потім врегулювати. взагалі непогано. це ніяк не заважає». Open question: how to regulate persona-flavoured state remarks later.
- **M12 → PARTIAL** (`+-`): the refuted hypothesis is named, without who/when.
- Final smoke result (with the deterministic scorer and C20/C21): 8 PASS, 1 PARTIAL, 6 FAIL, 1 invalid fixture — see `../baseline/u2u3-smoke-2026-11-18.json`.
