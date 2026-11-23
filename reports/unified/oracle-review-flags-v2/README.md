# Oracle review — flags-live-v2 (M107–M108), 23.11.2026

| Reviewer | M107 | M108 |
|---|---|---|
| Codex (`codex-review-1.json`) | ok | major |
| Gemini via agy (`gemini-review-1.json`) | ok | major |

Both reviewers, independently, on M108: 380 °C sits only in the skill body, which the index does
not show, so `NO_TOOL` with an optional `skill_view` let a lucky guess pass; and variant 1 asked
for advice while variant 2 asked to recall the owner's procedure. Fixed before freezing:
`expected_decision` `ACT`, `required_tool_calls: [skill_view]`, both variants ask to recall the
owner's own procedure.

Frozen with review status `TWO_BLIND_REVIEWS_CODEX_GEMINI_2026-11-23`.
