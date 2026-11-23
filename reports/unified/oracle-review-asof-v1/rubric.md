# Blind oracle review rubric — asof-live-v1 (M97–M99)

You review synthetic evaluation scenarios for a local Ukrainian-speaking assistant ("Capri", runtime B-12). Clock: 2026-12-01T10:00:00+02:00. Memory records carry validity windows (`valid_from`, `valid_to`).

The set measures whether the assistant answers a question about a PAST period with the record that was valid then, not with today's records. A tool call (`memory_search`, optionally with `as_of`) is allowed but NOT required: the runtime may already offer the right records. Judge the answer.

Each item has: `family_id`, `catalog_class`, `expected_decision`, `evaluator_setup` (evaluator-only memory), two `prompt_variants` shown to the assistant, and `oracle` (`accepted_outcomes`, `required_evidence_ids`, `forbidden_effects`, `tool_policy`).

Classes:
- `A1_period_recall_m96` (`M97`): the ports-live-v1 M96 setup (October main address, a temporary November address, the current address, ten numbered workshops valid from 5 November). Asked for October; correct: вул. Вишнева, 14.
- `A2_period_recall_supplier` (`M98`): plywood supplier in September; later suppliers of other materials and the October plywood supplier crowd it out. Correct: ТОВ «Ліс-Пром».
- `A3_day_precision` (`M99`): the address on 10 November, between the end of the October address and the start of the current one. Correct: вул. Тополина, 8 (mentioning that the move was temporary is optional). Warehouse addresses valid from 5 November are other entities.

Per family check:
1. Does it test its class, and does `expected_decision` fit?
2. Is the oracle unambiguous and fair given the setup (would a correct assistant fail, or a wrong one pass)?
3. Are both Ukrainian prompt variants semantically equivalent, natural, and free of answer leaks?
4. Are `required_evidence_ids` and `forbidden_effects` accurate?

Verdict per family: `ok` / `minor` / `major` / `blocker`, with one-sentence `problem` and `fix`. Do not invent problems.
