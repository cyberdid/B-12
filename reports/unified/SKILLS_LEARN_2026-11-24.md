# skills-learn-v1 — does Capri learn procedures through `skill_propose`? (24.11.2026)

Owner, 24.11.2026: check the self-improvement parts ported from Hermes. `skill_view` was measured
(M108, 6/6 on gpt-6-luna and gemma4:12b); proposing a skill was not.

Set: `skills-learn-v1` (M111–M114), frozen after two blind oracle reviews
([review](oracle-review-skills-learn-v1/README.md)). Runtime `e96e488` (eval-luna), every new
default on (`--recall-as-of --recall-conversations --memory-ranking --standing-intents --skills`),
3 repeats × 2 variants.

## gpt-6-luna (subscription bridge)

Judges: Gemini (agy) + Opus 5.5 (`claude -p` on the owner's Claude subscription; agy's own Opus
quota was exhausted). 75/75 criteria agreed, 0 disputes; a second independent Gemini run agreed
with Opus on 75/75.

| Family | What | Result |
|---|---|---|
| M111 | owner asks to save a 4-step procedure as a skill | **5/6**; 1 reply says there is no tool for skills (wrong: `skill_propose` was offered) |
| M112 | owner tells how a recurring task finally worked, «нагадай наступного разу» | **6/6** kept, but **0/6 via `skill_propose`**: always `memory_store` |
| M113 | a single fact + a question | **6/6**, no skill proposed (70–80 °C) |
| M114 | owner changes two settings of an existing skill | **5/6** (update of `solder-xt60`, other steps kept); 1 reply refuses because the tool «only prepares a proposal» |

Reading: Capri proposes skills when asked to, and keeps updates on the same skill. It never
proposes a skill on its own: a procedure the owner has just worked out goes to plain memory. In
Hermes that step is done by a background review after the turn; our port has no such trigger, so
the procedural self-improvement loop is not closed. Raw run:
`eval-luna/.../skills-learn-v1-luna6-defaults-2026-11-24`; judges:
`semantic-judge-skills-luna6-defaults`; verdicts: `consistent-verdicts-skills-luna6-2026-11-24`.

gemma4:12b acceptance: queued after the loop and compaction checks.
