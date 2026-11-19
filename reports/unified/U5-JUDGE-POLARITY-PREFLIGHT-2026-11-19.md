---
type: evaluation-methodology
updated: 2026-11-19
status: corrected_before_final_scoring
sources:
  - evals/unified/score_u2_u3.py
  - evals/unified/judge_sheet.py
  - evals/unified/scenario_sets/u5-application-locked-v1.json
  - evals/unified/draft_fixtures/u5-application-locked-v1/m65/m65-p1.oracle.json
  - tests/unified/test_judge_sheet.py
  - reports/unified/semantic-judge-u5-template/rubric.md
tags: [U5, judging, scorer, polarity, reproducibility]
---

# U5 judge polarity preflight

## Finding

The deterministic scorer places both `accepted_outcomes` and semantic `forbidden_effects`
in one `semantic_pending` array. The original judge-sheet builder exposed only that array
as criterion names. Its rubric described some negative-name conventions (`claims_*`,
`invented_*`, and similar), but not every forbidden effect follows those conventions.

For example, M65-P1 has `uses_inferred_no_sugar` in `forbidden_effects`. Without polarity,
that name can be read as either a required behavior or a prohibited effect. The first
blind B0 judge run showed disagreement on this criterion. The corresponding labels are
not used for U5 results. The first U5 judge run was stopped and likewise excluded.

## Correction

`judge_sheet.py` now adds a `criterion_polarity` map: `required` for accepted outcomes and
`prohibited` for semantic forbidden effects. It fails closed if a criterion appears in
both groups or neither. The U5-specific judge rubric defines how each polarity maps to
`met`/`not_met` and prohibits inference from name prefixes alone.

The regression test first failed because `criterion_polarity` was absent, then passed after
the change. The corrected judge sheets and prompts are regenerated from the frozen raw
records; the frozen scenario manifest and its fixtures are unchanged. No model response
run is repeated for this scorer-only correction.

Archived, invalid first-pass judge material is under:

- `reports/unified/semantic-judge-u5-b0-invalid-polarity-2026-11-19/`
- `reports/unified/semantic-judge-u5-treatment-invalid-polarity-2026-11-19/`

These folders are provenance only and must not be included in scoring or publication.

## Verification

- Reproduced the issue on `u5-application-locked-v1` M65-P1: oracle source class was
  `forbidden_effects`, while the judge item displayed only `uses_inferred_no_sugar`.
- Before implementation, the new regression failed with `KeyError: criterion_polarity`.
- After implementation, `tests/unified/test_judge_sheet.py`: 5 passed.
