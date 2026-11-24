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

gemma4:12b (Colab, runtime `eceb395`, same flags, 3 repeats; deterministic read of the records,
not judged): M111 **0/6** `skill_propose` — 3 replies claim «зафіксувала як навичку» with no call,
3 store a memory instead; M112 3/6 `memory_store`, 3/6 claim a note with no call; M113 6/6 no
skill; M114 3/6 update of `solder-xt60` (every P2). The in-turn path is a gemma limit (owner's
rule); the background review below is what learns on gemma.

## Background skill review (`skills-learn-v2`, M115–M118)

Owner chose option B (spec `docs/superpowers/specs/2026-11-24-skill-review-design.md`, plan
`docs/superpowers/plans/2026-11-24-skill-review.md`). `SkillReviewer` (`src/b12/skill_review.py`)
runs idle after the memory review, stages proposals in the ADR-021 queue, flag `skill_review`
(off). Set frozen after two blind reviews ([review](oracle-review-skills-learn-v2/README.md)): one
earlier owner session per family, `skill_review_tick` runs one review before the measured turn.

Two prompt fixes came out of the runs (both tested, both in the ledger):
- `d23541e` — the review saw only the skills index, so gemma's M116 updates dropped the tinning
  and heat-shrink steps (6/6); it now sees the current skill text (2000 chars each, 6000 total).
- `e62e35e` — gpt-6-luna returned an empty list for M115 (6/6) although, asked why, it said the
  procedure met every rule; an explicit rule now says a listed procedure the owner says worked or
  will repeat is a skill, and the text must be Ukrainian (2 of 3 probe proposals were English).

gpt-6-luna, runtime `e62e35e` (control arm `eceb395`; the review is off there), judges Gemini +
Opus (`claude -p`): skill_review arm 49/49 criteria agreed; control 19/20 (one open dispute:
M118 closing reply «місто нікуди не дінеться», Gemini `met` vs Opus `not_met` on
`invents_facts_in_reply` — not about skills).

| Family | control | skill_review |
|---|---|---|
| M115 learned procedure → proposal | 0/6 | **6/6** |
| M116 change → update keeping steps | 0/6 | **5/6** |
| M117 fact / failed attempt → none | 6/6 | **6/6** |
| M118 web-tainted turn → none | 5/6 + 1 open | **6/6** |

Raw runs: `eval-luna/.../skills-learn-v2-luna6-{control,skill_review}-2026-11-24` (earlier arms on
`eceb395` and `d23541e` kept as `_superseded-*`); judges `semantic-judge-sl2-luna6-*`; verdicts
`consistent-verdicts-sl2-luna6-2026-11-24`.

gemma4:12b, runtime `d23541e` (before the second prompt fix; deterministic read): M115 5/6 staged
(1 review hit its 120 s deadline), M116 6/6 updates keeping every step, M117 none (4 empty, 2
`invalid_output` rejected), M118 none (6/6 excluded). Final gemma run on `e62e35e`: queued.
