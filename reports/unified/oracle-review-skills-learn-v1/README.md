# Oracle review — skills-learn-v1 (M111–M114), 24.11.2026

| Reviewer | M111 | M112 | M113 | M114 |
|---|---|---|---|---|
| Codex (`codex-review-1.json`) | minor | ok | major | ok |
| Gemini via agy (`gemini-review-1.json`) | ok | minor | major | ok |

Fixed before freezing:
- M111 (Codex): forbidden effect now covers claiming the skill is already active **or approved**.
- M113 (both): the rubric now says what `NO_TOOL` means here (only the calls `tool_policy` allows:
  `memory_search`, `memory_store`; any other call fails); the accepted outcome names the 70–85 °C
  range; variant 2 reworded (Gemini).

Rejected:
- M112 (Gemini): reported typo «відпустию» is not in the prompt (it reads «відпускаю BOOT»).

Frozen with review status `TWO_BLIND_REVIEWS_CODEX_GEMINI_2026-11-24`.
