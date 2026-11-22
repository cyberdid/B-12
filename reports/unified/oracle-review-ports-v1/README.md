# Blind oracle reviews of `ports-live-v1` (M89–M96)

- Draft sheet: [sheet.json](sheet.json) (`catalog_class` and expected framing hidden to avoid anchoring; `M96` has 8 synthetic rows), fixed sheet: [sheet-fixed.json](sheet-fixed.json), combined Codex prompt: [prompt-fixed.txt](prompt-fixed.txt), rubric: [rubric.md](rubric.md), schema: [schema.json](schema.json).
- Blind review 1 — **Gemini 4 Hydrogen** (`@hydrogen-critic`, [review-gemini-on-draft.json](review-gemini-on-draft.json)): **3 ok, 4 minor, 1 major, 0 blocker**.
- Blind review 2 — **Codex** (run 22.11.2026 on prior `prompt-fixed.txt`, read-only): [review-codex-on-fixed.json](review-codex-on-fixed.json): **3 ok (M90, M92, M93), 2 minor (M89, M91), 3 major (M94, M95, M96), 0 blocker**. All 5 findings were accepted and fixed on 22.11.2026; [prompt-fixed.txt](prompt-fixed.txt), [sheet-fixed.json](sheet-fixed.json), and [rubric.md](rubric.md) were regenerated (kept `DRAFT` pending Codex re-review).
- Blind review 3 — **Codex round 2** (22.11.2026, on updated [prompt-fixed.txt](prompt-fixed.txt) / [sheet-fixed.json](sheet-fixed.json)): [codex-review-2.json](codex-review-2.json) — **8/8 ok (M89–M96), 0 minor, 0 major, 0 blocker**.

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
| M89 | Codex `minor` | **accept** | Added `"non_memory_tool_call"` to `forbidden_effects` and implemented deterministic `non_memory_tool_call` checking in `evals/unified/score_u2_u3.py`. |
| M91 | Codex `minor` | **accept** | Added `"non_memory_tool_call"` to `forbidden_effects` and implemented deterministic `non_memory_tool_call` checking in `evals/unified/score_u2_u3.py`. |
| M94 | Codex `major` | **accept** | Added `"non_memory_tool_call"` and `"conversation_search"` to `forbidden_effects`, set `required_evidence_ids` to `["setup:review_tick_recorded"]` (verified deterministically via `seed_report.review_tick` in `evals/unified/score_u2_u3.py`), and documented both controls in [rubric.md](rubric.md). |
| M95 | Codex `major` | **accept** | Updated `accepted_outcomes` to `["affirms_confirmed_wood_up_to_18000_rpm_and_either_omits_or_clearly_hedges_unverified_steel_24000_rpm_claim"]`, kept `required_evidence_ids` for both `mem:` records separately from reply content, and updated [rubric.md](rubric.md). |
| M96 | Codex `major` | **accept** | Added `required_tool_calls: [{"name": "memory_search", "as_of_prefix": "2026-10"}]` (with `_prefix` argument matching in `evals/unified/score_u2_u3.py`), kept `mem:p96-r1` in `required_evidence_ids`, and updated [rubric.md](rubric.md). |

## Status

- Scenario manifest `status` (`scenarios-v2.schema.json`): **`FROZEN`** (frozen 22.11.2026 after clean Codex re-review `codex-review-2.json`, 8/8 `ok`).
- Review status: **`FROZEN_REVIEW_STATUS`** (`REVIEWED 2026-11-22: blind Gemini 4 Hydrogen (draft: 4 minor, 1 major fixed) and Codex (round 1: 2 minor, 3 major fixed; round 2: 8/8 ok in codex-review-2.json) - all fixed before any run; FROZEN 2026-11-22`).
- `evals/unified/scenario_sets/ports-live-v1.json` SHA-256: `4ee145e95243bc16a83ccdd0271f4fd8c3780ed677f4513a5f968d25189d7505`.
