# Background skill review (Hermes-style) — design, 24.11.2026

## Why

Owner, 24.11.2026, chose option **B** after `skills-learn-v1` on gpt-6-luna: Capri proposes a
skill when asked (M111 5/6) and updates one (M114 5/6), but never on its own — a procedure the
owner has just worked out goes to plain memory (M112 0/6 via `skill_propose`). In Hermes the
learning step is a background review after the turn. Our port (ADR-021) has the approval queue,
the ledger and the curator, but no such trigger, so the procedural self-improvement loop is open.

## Goals

- After interactive turns, a background review finds **reusable procedures the owner stated or
  confirmed as working** and stages them as skill proposals (create, or update of an existing
  skill) in the existing approval queue.
- Nothing becomes active without the owner (ADR-021 point 3 unchanged).
- Measured on gpt-6-luna first, then gemma4:12b, before it is turned on by default.

## Non-goals and anti-goals

- Not a memory review: facts, preferences and decisions stay with ADR-020.
- Never writes `SKILL.md`, never deletes or archives (the curator does that).
- Must not turn one-off facts, failed attempts or guesses into skills; must not learn from web
  content (tainted turns) or goal turns — the same exclusions as the memory review.
- Must never delay the owner: it runs only when idle and yields to a new turn.

## Approaches

- **A. Prompt hint for `skill_propose` in the turn** — cheap, but the model is busy answering and
  in M112 always chose `memory_store`; owner rejected it in favour of B.
- **B. Background skill review (chosen).** A separate idle pass over finished turns, like
  `MemoryReviewer`; one bounded model call per batch; proposals go to the queue.
- **C. Extend `MemoryReviewer` to also emit skills** — one call instead of two, but mixes two
  output contracts and two approval paths in one prompt; harder to measure separately. Rejected.

## Design

- **Module** `src/b12/skill_review.py`, class `SkillReviewer(runtime)`, mirroring
  `MemoryReviewer`:
  - own cursor `skill_review:<actor_id>` in control meta; up to 6 unreviewed turns per batch;
    consent required; goal and network-tainted turns excluded (reuse the same checks);
  - context: the turns (user/assistant text, bounded), plus the current skills index (name and
    description) so an existing skill is updated instead of duplicated;
  - prompt (Ukrainian), from Hermes' "what a good skill is": only procedures with ≥2 steps that
    the owner stated or confirmed worked; steps with concrete settings; pitfalls as a rule plus one
    sentence why; no dates, incident logs or quotes; one-off facts, unresolved failures and
    speculation are not skills; if unsure, return nothing;
  - output JSON `{"skills": [{"name", "description", "body", "turn_id"}]}`, at most 2 per batch;
    `turn_id` must be one of the batch; strict parsing like `_parse_candidates`;
  - each item becomes `SkillStore.propose(name, SKILL.md text, turn_id, session_id, actor_id)`
    (frontmatter validated by `validate_frontmatter`); a name with a pending proposal already is
    skipped; an existing skill name produces an update diff (ADR-021 provenance applies);
  - one model call under `agent.model_lock`, registered in `agent.active` so an owner turn or a
    deletion invalidates it (same pattern and outcome states: `staged` / `skipped` / `rejected` /
    `failed`).
- **Scheduler**: `Scheduler.review_skills_idle()` after `review_memory_idle()` in `run()`, same
  busy / owner-stop / consent checks; only when `skills` and the new flag are on.
- **Flag** `Settings.skill_review: bool = False` until measured (project rule); CLI/eval flag
  `--skill-review`.
- **Owner side**: proposals appear in the existing `b12 skills` pending list; the TUI work will
  show them (separate spec).

## Measurement

New frozen set `skills-learn-v2` (blind Codex + Gemini oracle review first), with a setup key
`skill_review_tick` that runs one review before the measured turn (like `review_tick`) and records
its outcome and the staged proposal in `seed_report`:

- procedure worked out in a past session → one proposal with the right steps;
- the same, but for an existing skill → an update of that skill;
- a one-off fact / an unresolved failed attempt → no proposal;
- the procedure came from a web page (tainted turn) → no proposal.

gpt-6-luna first (judges Gemini + Opus via `claude -p`), then gemma4:12b on Colab (Codex +
Gemini). Turn-on decision is the owner's.

## Left to the builder

Exact prompt wording, the bounded text sizes, test layout, and how the judge sheet shows the
staged proposal.
