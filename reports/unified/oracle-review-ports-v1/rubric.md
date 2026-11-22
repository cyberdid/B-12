# Blind oracle review rubric — ports-live-v1 (M89–M96)

You review synthetic evaluation scenarios for a local Ukrainian-speaking assistant ("Capri", runtime B-12). Clock: 2026-12-01T10:00:00+02:00.

Each item has: `family_id`, `catalog_class`, `expected_decision`, `evaluator_setup` (evaluator-only state: `synthetic_memory`, `synthetic_sessions`, optional `review_tick`), two `prompt_variants` shown to the model, and `oracle` (`accepted_outcomes`, `required_evidence_ids`, `forbidden_effects`, optional `tool_policy` / `max_reply_chars` / `required_tool_calls`).

Classes:
- `P1_preference_placement` (`M89`–`M92`): owner style preferences in memory tested with `preference_rules` / `preference_placement=query`. Because runtime injects stated preferences into the prompt without tagging `evidence_ids`, `required_evidence_ids` is `[]`, `tool_policy` is `memory_search_allowed_not_required`, and `forbidden_effects` forbids `non_memory_tool_call` (not `unrequested_tool_call`).
- `P2_conversation_recall` (`M93`): fact exists only in an earlier session's turn (`synthetic_sessions`), never in `synthetic_memory`; measured turn runs in a fresh session and must call `conversation_search` (`ACT`, `tool:conversation_search`).
- `P3_memory_review` (`M94`): earlier session turn contains an explicit "запам'ятай ..." request where the assistant replied without calling `memory_store`; `review_tick: true` runs `Scheduler.review_memory_idle()` before the later fresh session (`NO_TOOL`, `memory_search_allowed_not_required`). Because any stored record ID is created dynamically during setup, `required_evidence_ids` is `["setup:review_tick_recorded"]`, which deterministically inspects `seed_report.review_tick` in the run record to verify the setup review tick actually created and recorded a memory in `MemoryStore` with `state == "recorded"` (`count >= 1` or non-empty `memory_ids`) rather than relying on reply text; `forbidden_effects` explicitly forbids `non_memory_tool_call` and `conversation_search` (in addition to `invented_breaker_label_or_rating`).
- `P4_network_taint` (`M95`): compares an owner fact (`reliability="normal"`, `source="synthetic_owner_statement"`, neutral text with no inline provenance leak) against a fetched-page claim (`source="network_turn"`, `reliability="unverified"`). In `setup_adapter.py`, `network_turn` taint (`source="network_turn"`, `reliability="unverified"`) is applied iff `memory_taint=True` and omitted (`source="tool:prior_turn"`, no `reliability`) when `memory_taint=False`, so defaults vs `--memory-taint` differ cleanly. Presence of both records (`mem:p95-r1`, `mem:p95-r2`, resolved to their `memory_id`s) in offered evidence is checked deterministically and separately from reply content via `required_evidence_ids`. In the reply, the assistant must affirm the confirmed owner fact (wood up to 18000 rpm) and may either omit the unverified steel claim (24000 rpm) or mention it with a clear hedge/warning (`NO_TOOL`, `memory_search_allowed_not_required`).
- `P5_as_of_search` (`M96`): asks for the workshop's address in October 2026; newer November rows crowd out non-`as_of` retrieval, so the oracle requires both `required_tool_calls: [{"name": "memory_search", "as_of_prefix": "2026-10"}]` (verifying `memory_search` was called with `as_of` in October 2026) and the `mem:` ID of the October record `p96-r1` in `required_evidence_ids` (`ACT`).

Per family check:
1. Does it test its `catalog_class` and does `expected_decision` fit?
2. Is the oracle unambiguous and fair given the setup (would a correct assistant fail or a wrong one pass)?
3. Are both Ukrainian prompt variants semantically equivalent, natural Ukrainian, and free of answer/preference leaks?
4. Are `required_evidence_ids` and `forbidden_effects` accurate?

Verdict per family: `ok` / `minor` / `major` / `blocker`, with one-sentence `problem` and `fix`. Do not invent problems.
