# Blind oracle review rubric — flags-live-v2 (M107–M108)

You review synthetic evaluation scenarios for a local Ukrainian-speaking assistant ("Capri", runtime B-12). Clock: 2026-12-01T10:00:00+02:00. The speaker is the owner.

Each family targets one runtime feature; the oracle judges only observable behaviour (reply and tool calls). The runtime may inject owner state as data beside the question: standing intents (keyword-triggered owner notes) and a skills index (names and descriptions; the body is read with `skill_view`).

Each item has: `family_id`, `catalog_class`, `expected_decision`, `evaluator_setup` (`synthetic_intents` with keywords and text, `synthetic_skills` with name, description, body), two `prompt_variants`, and `oracle`.

Classes:
- `F5_standing_intent_fires` (`M107`): the owner's intent says that before buying paint the bathroom needs primer «Церезит CT 17». The owner says they are going to buy paint for the bathroom and asks what not to forget. Correct: mentions the primer Ceresit CT 17. Generic advice without the primer is not enough.
- `F6_owner_skill_used` (`M108`): the owner skill `solder-xt60` says: 380 °C, 2 mm chisel tip, tin both contacts first, 6 mm heat-shrink. Asked how to solder XT60 and at what temperature. Correct: 380 °C as the owner's setting (other details welcome). A different temperature presented as the owner's setting is wrong.

Per family check:
1. Does it test its class, and does `expected_decision` fit?
2. Is the oracle unambiguous and fair given the setup (would a correct assistant fail, or a wrong one pass)?
3. Are both Ukrainian prompt variants semantically equivalent, natural, and free of answer leaks?
4. Are `required_evidence_ids` and `forbidden_effects` accurate?

Verdict per family: `ok` / `minor` / `major` / `blocker`, with one-sentence `problem` and `fix`. Do not invent problems.
