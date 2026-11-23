# Blind oracle reviews of `asof-live-v1` (M97–M99)

Set: `evals/unified/scenario_sets/asof-live-v1.json` (6 scenarios), author `evals/unified/draft_sources/author_asof_v1.py`.
Purpose: measure `recall_as_of` (answer about a past period). M96 in `ports-live-v1` checks the `memory_search(as_of)` call and cannot measure a runtime fix; this set judges the answer.

| Family | Codex ([codex-review-1.json](codex-review-1.json)) | Gemini 4 Hydrogen ([gemini-review-1.json](gemini-review-1.json)) | Action |
|---|---|---|---|
| M97 | ok | ok | — |
| M98 | ok | ok | — |
| M99 | ok | minor: accepted outcome named the move "temporary" | renamed to `reports_topolyna_8_on_november_10`; temporary is optional |

Both reviews ran blind on [prompt.txt](prompt.txt) (rubric + sheet), read-only, 23.11.2026. The fix was made before any run.

**Status: FROZEN 2026-11-23**, manifest SHA-256 `880ff6a215f782a017cf597e7a766ea115b92d968456154de59376df963f44cd`.

The "current state" control is not a family here (only M97–M99 were free two-digit IDs): it is the `ports-live-v1` run with `--recall-as-of`, whose M89–M95 ask about the present.
