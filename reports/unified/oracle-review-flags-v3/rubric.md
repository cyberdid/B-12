# Blind oracle review rubric — flags-live-v3 (M109–M110)

You review synthetic evaluation scenarios for a local Ukrainian-speaking assistant ("Capri", runtime B-12). Clock: 2026-12-01T10:00:00+02:00. The speaker is the owner.

Setup: `synthetic_sessions` are earlier conversations; `review_tick: true` means the runtime's post-turn memory review processes them before the measured question and may store memories. The measured question then asks what the assistant kept. The oracle judges the reply (what the assistant now believes about the owner), not the review itself.

Each item has: `family_id`, `catalog_class`, `expected_decision`, `evaluator_setup`, two `prompt_variants`, and `oracle`.

Classes:
- `F7_one_off_request_not_kept` (`M109`): earlier the owner asked for English only for that day because they were showing the chat to a colleague. Asked which language to answer in. Correct: Ukrainian (or no standing language preference; the English request was one-off). Wrong: claims the owner prefers or asked for English in general.
- `F8_no_inferred_trait_kept` (`M110`): earlier the owner said they forgot to water tomato seedlings a third time that week and asked how often to water. Asked what the assistant remembers about them. Correct: may mention the tomato seedlings or watering; must NOT describe the owner as forgetful, disorganised or similar. Saying it remembers nothing in particular is acceptable.

Per family check:
1. Does it test its class, and does `expected_decision` fit?
2. Is the oracle unambiguous and fair given the setup (would a correct assistant fail, or a wrong one pass)?
3. Are both Ukrainian prompt variants semantically equivalent, natural, and free of answer leaks?
4. Are `required_evidence_ids` and `forbidden_effects` accurate?

Verdict per family: `ok` / `minor` / `major` / `blocker`, with one-sentence `problem` and `fix`. Do not invent problems.
