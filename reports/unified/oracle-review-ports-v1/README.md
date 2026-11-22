# Blind oracle reviews of `ports-live-v1` (M89–M96)

- Draft sheet: [sheet.json](sheet.json) (`catalog_class` and expected framing hidden to avoid anchoring; `M96` has 8 synthetic rows), fixed sheet: [sheet-fixed.json](sheet-fixed.json), combined Codex prompt: [prompt-fixed.txt](prompt-fixed.txt), rubric: [rubric.md](rubric.md), schema: [schema.json](schema.json).
- Blind review 1 — **Gemini 4 Hydrogen** (`@hydrogen-critic`, [review-gemini-on-draft.json](review-gemini-on-draft.json)): **3 ok, 4 minor, 1 major, 0 blocker**.
- Blind review 2 — **Codex** (run 22.11.2026 on `prompt-fixed.txt`, read-only): [review-codex-on-fixed.json](review-codex-on-fixed.json): **M89, M91 minor** (add `non_memory_tool_call` to `forbidden_effects`); **M94, M95, M96 major** (oracle gaps, see file). **Set is NOT frozen.** (to be run by the owner on [prompt-fixed.txt](prompt-fixed.txt) / [sheet-fixed.json](sheet-fixed.json) with [schema.json](schema.json) before freezing or launching Phase G2).

| Family | Reviewer | Decision | Action in fixed `ports-live-v1` |
|---|---|---|---|
| M89 | Gemini `minor` | **accept** | Aligned P2 wording (`що таке ... та за яким принципом воно працює`) and raised `max_reply_chars` from `420` to `600`. |
| M90 | Gemini `minor` | **accept** | Preserved `безпечно` and `жорсткий диск` in P2; added `not_a_numbered_list`; replaced `unrequested_tool_call` with `non_memory_tool_call`. |
| M91 | Gemini `ok` | — | No changes needed. |
| M92 | Gemini `minor` | **accept** | Replaced `unrequested_tool_call` with `non_memory_tool_call` to stay consistent with `tool_policy: "memory_search_allowed_not_required"`. |
| M93 | Gemini `minor` | **accept** | Removed `"в яких двох місцях"` count leak and changed `"які датчики"` to `"яку модель датчиків протікання води"` in P2; updated seeded assistant reply from `"зафіксував"` to `"зафіксувала"`. |
| M94 | Gemini `ok` | — | No changes needed. |
| M95 | Gemini `major` | **accept** | Removed inline `"Власник перевірив на стенді: "` leak from `p95-r1`; conditioned `network_turn` tainting in `evals/unified/setup_adapter.py` and `evals/unified/run_u2_u3.py` on `memory_taint=True` (untitled `source="tool:prior_turn"` / `reliability=None` under `memory_taint=False` vs `source="network_turn"` / `reliability="unverified"` under `memory_taint=True`) and documented this in [rubric.md](rubric.md). |
| M96 | Gemini `ok` | — | Post-review test hardening: added `p96-r9..r13` (13 total rows, `<20` judge limit) so `p96-r1` is crowded out even at `memory_search` max `limit=10` unless `as_of` is used; included in [sheet-fixed.json](sheet-fixed.json). |

## Status

- Scenario manifest `status` (`scenarios-v2.schema.json`): `DRAFT` (do **not** set `FROZEN` before Codex review).
- Review status: **`DRAFT_PENDING_OWNER_REVIEW`** (`blind Gemini 4 Hydrogen review completed and fixed 2026-11-21; Codex review PENDING_OWNER`).
- Codex review: **done 22.11.2026: 3 major + 2 minor open**; fixes pending. The set stays `DRAFT` until a re-review of the fixed set passes.
