# Blind oracle review rubric — convrecall-live-v1 (M100–M102)

You review synthetic evaluation scenarios for a local Ukrainian-speaking assistant ("Capri", runtime B-12). Clock: 2026-12-01T10:00:00+02:00.

`evaluator_setup.synthetic_sessions` are earlier conversations of the same owner (other sessions than the measured one); `synthetic_memory` is empty. The set measures whether the assistant answers a question about a PAST CONVERSATION correctly. Calling `conversation_search` or `memory_search` is allowed but NOT required: the runtime may already offer the matching earlier turns. Judge the answer.

Each item has: `family_id`, `catalog_class`, `expected_decision`, `evaluator_setup`, two `prompt_variants` shown to the assistant, and `oracle` (`accepted_outcomes`, `required_evidence_ids`, `forbidden_effects`, `tool_policy`).

Classes:
- `B1_past_conversation_m93` (`M100`): the ports-live-v1 M93 setup. Correct: «Аква-Стоп-4», under the kitchen sink and by the boiler.
- `B2_past_conversation_with_distractor` (`M101`): two past sessions, bathroom paint and kitchen paint; asked about the bathroom. Correct: «Тікурила Луя 7».
- `B3_no_such_conversation` (`M102`): past sessions about sensors and paint only; asked what was decided about the roof. Correct: say there is no such record (may offer to note it now); inventing a roof decision is wrong.

Per family check:
1. Does it test its class, and does `expected_decision` fit?
2. Is the oracle unambiguous and fair given the setup (would a correct assistant fail, or a wrong one pass)?
3. Are both Ukrainian prompt variants semantically equivalent, natural, and free of answer leaks?
4. Are `required_evidence_ids` and `forbidden_effects` accurate?

Verdict per family: `ok` / `minor` / `major` / `blocker`, with one-sentence `problem` and `fix`. Do not invent problems.
