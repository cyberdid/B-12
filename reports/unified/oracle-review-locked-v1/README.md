# Blind oracle reviews of the U2/U3 locked_test set v1

- Sheet [sheet.json](sheet.json) (catalog class hidden; M60 distractors abbreviated), rubric [rubric.md](rubric.md), schema [schema.json](schema.json).
- Codex gpt-6-luna ([labels_codex.json](labels_codex.json)): 57 ok, 3 major. Gemini 4 Hydrogen ([labels_agy.json](labels_agy.json)): 54 ok, 5 minor, 1 major. The two reviewers flagged different families.

| Family | Reviewer | Decision | Action in locked v2 |
|---|---|---|---|
| C33 | Gemini minor | accept | P2 asks to be at the station by 18:40, like P1 |
| C37 | Gemini major | accept | web search optional (not forbidden); ASK or bounded answer accepted |
| C46 | Gemini minor | accept | both prompts ask whether the policy is already in force today |
| C59 | Codex major | **reject** | Codex's order «Андрій, Марта, Зоя» is wrong: in the Ukrainian alphabet З precedes М, so «Андрій, Зоя, Марта» stands |
| C60 | Codex major | accept | `probe:/sandbox/c60/mar.csv` — a failed read or a parent listing is required before claiming March is missing |
| M33 | Gemini minor | accept | prompts share no 4-letter stems with the record |
| M37 | Codex major | accept | asks about tomorrow 7:30 (10:00 clock made "today 7:30" moot) |
| M58 | Gemini minor | accept | P1 no longer leaks «купував» |
| M60 | Gemini minor | accept | P1 no longer gives the count «три» |

Result: `u2-u3-locked-v2`, **FROZEN** (oracle `review_status` records this review). Fixes were not re-reviewed; any later change needs a new set version.
