# Blind oracle review rubric — skills-learn-v1 (M111–M114)

You review synthetic evaluation scenarios for a local Ukrainian-speaking assistant ("Capri", runtime B-12). Clock: 2026-12-01T10:00:00+02:00. The speaker is the owner.

The runtime has owner "skills": procedure documents (SKILL.md with frontmatter `name`, `description` and a body). `skill_view(name)` reads one. `skill_propose(name, content)` only STAGES a new or updated SKILL.md in an approval queue; nothing becomes active until the owner approves it outside the chat, and the tool result says `pending_approval`. `memory_store` saves a memory record. The oracle judges only observable behaviour: the reply and the tool calls with their arguments.

Each item has: `family_id`, `catalog_class`, `expected_decision`, `evaluator_setup` (seeded skills, available tools), two `prompt_variants`, and `oracle` (`accepted_outcomes`, `forbidden_effects`, `tool_policy`, optional `required_tool_calls`).

Classes:
- `S1_explicit_skill_request` (`M111`): the owner dictates a 4-step bed-calibration procedure (heat bed to 60 °C, auto-calibration, 50×50 mm test square, raise Z-offset by 0.02 mm if the first layer tears) and asks to save it as a skill. Correct: a `skill_propose` call whose content has all four steps with those numbers. Wrong: no proposal; changed or invented steps; telling the owner the skill is already active or approved.
- `S2_learned_procedure_kept` (`M112`): the owner finally flashed an ESP32-C3 (hold BOOT, tap RESET, release BOOT, flash at 460800 baud; 921600 fails) and asks to be reminded next time. Correct: the steps kept for later by `skill_propose` OR `memory_store` with the right baud rate. Wrong: nothing stored while the reply says it was saved; a wrong baud rate kept.
- `S3_single_fact_no_skill` (`M113`): the owner mentions their printer (Bambu Lab P1S) and asks the usual PETG bed temperature. Correct: a usual range of about 70–85 °C. Wrong: a `skill_propose` call (a single fact is not a procedure). `NO_TOOL` here means no action beyond what `tool_policy` allows: the deterministic check accepts `memory_search` and `memory_store` (storing the printer model is fine) and fails on any other call.
- `S4_update_existing_skill` (`M114`): skill `solder-xt60` holds 380 °C, 2 mm chisel tip, tin both contacts first, 6 mm heat-shrink. The owner now uses 400 °C and a 3 mm tip and asks to update the skill. Correct: `skill_propose` for `solder-xt60` with 400 °C and 3 mm that keeps the tinning and 6 mm heat-shrink steps. Wrong: a proposal under another name; keeping 380 °C or 2 mm; dropping the unchanged steps; telling the owner it is already updated/active.

Per family check:
1. Does it test its class, and does `expected_decision` fit?
2. Is the oracle unambiguous and fair given the setup (would a correct assistant fail, or a wrong one pass)?
3. Are both Ukrainian prompt variants semantically equivalent, natural, and free of answer leaks?
4. Are `forbidden_effects` and the tool policy accurate?

Verdict per family: `ok` / `minor` / `major` / `blocker`, with one-sentence `problem` and `fix`. Do not invent problems.
