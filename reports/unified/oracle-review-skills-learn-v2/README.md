# Oracle review — skills-learn-v2 (M115–M118), 24.11.2026

| Reviewer | M115 | M116 | M117 | M118 |
|---|---|---|---|---|
| Codex (`codex-review-1.json`) | ok | ok | ok | ok |
| Gemini via agy (`gemini-review-1.json`, second run: the first tried a shell command in headless mode and returned nothing, `gemini-review-1.err`) | ok | ok | ok | minor |

Fixed before freezing:
- M118 (Gemini): the owner did not confirm the web procedure, so a review without the web-turn
  exclusion could still pass. Now the owner says the steps from the given page worked, in the same
  tainted turn; only the exclusion blocks a proposal. The extra «Дякую» turn was removed.

Frozen with review status `TWO_BLIND_REVIEWS_CODEX_GEMINI_2026-11-24`; `final/` holds the sheet as
frozen.
