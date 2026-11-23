# Oracle review — convrecall-live-v1 (M100–M102), 23.11.2026

Two blind reviews of the draft (`sheet.json`, `rubric.md`, `schema.json`):

| Reviewer | M100 | M101 | M102 |
|---|---|---|---|
| Codex (`codex-review-1.json`) | ok | ok | ok |
| Gemini via agy (`gemini-review-1.json`) | ok | minor | ok |

Gemini M101 (minor, accepted): «в минулій розмові» / «минулого разу» could be read as "the most
recent conversation", while the bathroom session (20.11) precedes the kitchen distractor (22.11).
Fix before freezing: «в одній із минулих розмов» / «ми обговорювали раніше». Both rewordings
still trigger `refers_to_past_conversation`.

Frozen as `evals/unified/scenario_sets/convrecall-live-v1.json` with review status
`TWO_BLIND_REVIEWS_CODEX_GEMINI_2026-11-23`.
