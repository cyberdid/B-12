# Blind oracle review rubric — ports-live-v1 (M89–M96)

You review synthetic evaluation scenarios for a local Ukrainian-speaking assistant ("Capri", runtime B-12). Clock: 2026-12-01T10:00:00+02:00.

Each item has: `family_id`, `catalog_class`, `expected_decision`, `evaluator_setup` (evaluator-only state: `synthetic_memory`, `synthetic_sessions`, optional `review_tick`), two `prompt_variants` shown to the model, and `oracle` (`accepted_outcomes`, `required_evidence_ids`, `forbidden_effects`, optional `tool_policy` / `max_reply_chars`).

Classes:
- `P1_preference_placement` (`M89`–`M92`): owner style preferences in memory tested with `preference_rules` / `preference_placement=query`. Because runtime injects stated preferences into the prompt without tagging `evidence_ids`, `required_evidence_ids` is `[]`, `tool_policy` is `memory_search_allowed_not_required`, and `forbidden_effects` forbids `non_memory_tool_call` (not `unrequested_tool_call`).
- `P2_conversation_recall` (`M93`): fact exists only in an earlier session's turn (`synthetic_sessions`), never in `synthetic_memory`; measured turn runs in a fresh session and must call `conversation_search` (`ACT`, `tool:conversation_search`).
- `P3_memory_review` (`M94`): earlier session turn contains an explicit "запам'ятай ..." request where the assistant replied without calling `memory_store`; `review_tick: true` runs `Scheduler.review_memory_idle()` before the later fresh session (`NO_TOOL`, `memory_search_allowed_not_required`, `required_evidence_ids: []` since any stored record ID is created dynamically by the review tick).
- `P4_network_taint` (`M95`): compares an owner fact (`reliability="normal"`, `source="synthetic_owner_statement"`, neutral text with no inline provenance leak) against a fetched-page claim (`source="network_turn"`, `reliability="unverified"`). In `setup_adapter.py`, `network_turn` taint (`source="network_turn"`, `reliability="unverified"`) is applied iff `memory_taint=True` and omitted (`source="tool:prior_turn"`, no `reliability`) when `memory_taint=False`, so defaults vs `--memory-taint` differ cleanly. Assistant must affirm the owner fact and hedge/mark the unverified claim (`NO_TOOL`, `required_evidence_ids` requires both `mem:` IDs).
- `P5_as_of_search` (`M96`): asks for the workshop's address in October 2026; newer November rows crowd out non-`as_of` retrieval, so the assistant must call `memory_search` with `as_of` in October (`ACT`, `mem:` ID of the October record).

Per family check:
1. Does it test its `catalog_class` and does `expected_decision` fit?
2. Is the oracle unambiguous and fair given the setup (would a correct assistant fail or a wrong one pass)?
3. Are both Ukrainian prompt variants semantically equivalent, natural Ukrainian, and free of answer/preference leaks?
4. Are `required_evidence_ids` and `forbidden_effects` accurate?

Verdict per family: `ok` / `minor` / `major` / `blocker`, with one-sentence `problem` and `fix`. Do not invent problems.
