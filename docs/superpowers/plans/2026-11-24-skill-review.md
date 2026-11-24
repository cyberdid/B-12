# Background Skill Review Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** an idle background review that turns procedures the owner worked out into skill proposals in the existing approval queue, measured on gpt-6-luna and gemma4:12b.

**Architecture:** `SkillReviewer` mirrors `MemoryReviewer` (ADR-020): own cursor, same turn exclusions, one bounded model call, strict JSON, output staged through `SkillStore.propose`. The scheduler calls it after the memory review; the eval harness gets a `skill_review_tick` setup key so a frozen set can measure it.

**Tech Stack:** Python 3.12, pytest (`scripted_ollama` fixture), existing B-12 runtime and eval harness.

**Spec:** `docs/superpowers/specs/2026-11-24-skill-review-design.md`

## Global Constraints

- Flag `Settings.skill_review: bool = False` (on only after measurement and the owner's decision); works only when `skills` is on too.
- Never writes `SKILL.md`, never deletes/archives: only `SkillStore.propose(...)`.
- At most 2 proposals per batch; at most 6 turns per batch; goal turns and network-tainted turns excluded.
- Runs only idle; registered in `agent.active` so an owner turn or a deletion invalidates it.
- GPU: evals on Colab or the frontier bridge; never the owner's local GPU.

## Review Focus

- A model reply that is not JSON or has extra keys → `rejected/invalid_output`, cursor NOT advanced (test in Task 1).
- A proposal whose `turn_id` is not in the batch → whole batch rejected (Task 1).
- Same skill name already pending → skipped, no second pending file (Task 1).
- Skill name invalid for the store (spaces, slashes) → that item skipped, others staged (Task 1).
- Owner turn starts during the review → result discarded (`rejected`), nothing staged (Task 1).

---

### Task 1: `SkillReviewer` and the flag

**Files:**
- Create: `src/b12/skill_review.py`
- Modify: `src/b12/config.py` (field after `skills`; add `"skill_review"` to the flag-name list near line 290)
- Test: `tests/integration/test_skill_review.py`

**Interfaces:**
- Produces: `class SkillReviewer(MemoryReviewer)` with `async def review(self, actor, *, cancel=None, timeout_s: float = 120) -> dict`; `def _parse_skills(content: str, eligible_turn_ids: set[str]) -> list[dict] | None`; constants `PROMPT`, `_MAX_TURNS = 6`, `_MAX_SKILLS = 2`.
- Result states: `{"state": "skipped", "reason": "skills_off"|"consent_required"|"no_turns"|"no_candidates"|"duplicate"}`, `{"state": "staged", "pending_ids": [...], "names": [...], "count": n}`, `{"state": "rejected", "reason": "invalid_output"|"stale_deletion_revision"}`, `{"state": "failed", "reason": <ModelError code>|"cancelled"}`.

- [ ] **Step 1: Write the failing tests** (pattern: `tests/integration/test_memory_review.py::test_review_records_grounded_fact_with_turn_locator`; runtime with `skills=True, skill_review=True, output_tokens=2048`; one owner turn whose user text describes the ESP32-C3 procedure)
  - `test_review_stages_a_procedure_as_skill_proposal`: reply `{"skills": [{"name": "flash-esp32c3", "description": "Прошивка ESP32-C3", "body": "1. Затиснути BOOT…", "turn_id": <turn>}]}` → state `staged`, `runtime.skills.list_pending()` has one item with `name == "flash-esp32c3"`, `turn_id == <turn>`, content starting `---\nname: flash-esp32c3\n`; no `SKILL.md` on disk; the review request's system text contains `PROMPT` and the last user message contains the turn id and the existing skills index line when a skill is seeded.
  - `test_existing_skill_name_becomes_update`: seeded `solder-xt60` → staged pending has `action == "update"`.
  - `test_empty_list_advances_cursor` → `skipped/no_candidates`; a second `review` → `skipped/no_turns`.
  - `test_invalid_output_keeps_cursor` (reply `"не JSON"`) → `rejected/invalid_output`; second review sees the same turn again.
  - `test_foreign_turn_id_rejects_batch` → `rejected/invalid_output`, nothing pending.
  - `test_pending_name_is_not_staged_twice` → second identical proposal → `skipped/duplicate`, one pending file.
  - `test_invalid_skill_name_skips_only_that_item` (`"bad name/x"` + a valid one) → one staged.
  - `test_goal_and_tainted_turns_are_not_reviewed` → no model call (`state["requests"]` unchanged), `skipped/no_turns`.
  - `test_skills_off_or_flag_off_skips` → `skipped/skills_off`, no model call.
  - `test_owner_turn_during_review_discards_result` → invalidate the registered `_Active` while the scripted reply is pending (same technique as the memory-review stale test) → `rejected`, nothing pending.

- [ ] **Step 2: Run** `uv run --no-sync pytest -q -p no:cacheprovider tests/integration/test_skill_review.py` → FAIL (module missing).

- [ ] **Step 3: Implement.** `Settings.skill_review: bool = False` with a comment (spec, owner option B, off until measured). `SkillReviewer` subclasses `MemoryReviewer` to reuse `_is_goal_turn` / `_is_tainted`; cursor `skill_review:<actor_id>`; batch text = turns (as `_format_batch`, 1500 chars per message) plus `runtime.skills.render_index(limit=20)`; `PROMPT` in Ukrainian, built from the spec's rules (≥2 steps the owner stated or confirmed worked; concrete settings; pitfall = rule + one sentence why; no dates/incident logs/quotes; one-off facts, unresolved failures, speculation are not skills; same name as an indexed skill = full updated text keeping unchanged steps; if unsure return `{"skills": []}`; description ≤60 chars; name `[a-z0-9-_]`); `_parse_skills` accepts exactly `{"skills": [...]}` with items of exactly `name, description, body, turn_id` (strings, turn id in batch), else `None`; SKILL.md text `f"---\nname: {name}\ndescription: {description}\n---\n{body}\n"` must pass `validate_frontmatter`, and `SkillStore.propose` `ValueError` skips that item; skip names already in `list_pending()`; advance the cursor on `staged`, `no_candidates`, `duplicate`, and when all turns were excluded.

- [ ] **Step 4: Run** the test file → PASS; `uv run --no-sync pytest -q -p no:cacheprovider tests/unit/test_config.py` → PASS (update its default-flags expectation if it lists flags).

- [ ] **Step 5: Commit** `feat(skills): background skill review stages learned procedures (off by default)`.

### Task 2: Scheduler hook

**Files:**
- Modify: `src/b12/autonomy.py` (new method after `review_memory_idle`; call in `run()` after the memory review, own try/except + `log.exception("idle skill review failed")`)
- Test: `tests/integration/test_skill_review.py`

**Interfaces:**
- Consumes: `SkillReviewer.review` (Task 1).
- Produces: `async def Scheduler.review_skills_idle(self) -> list[dict]` — `[]` unless `settings.skills and settings.skill_review and runtime.skills`; per consented actor: `skipped/actor_busy` when `_busy`, `skipped/owner_stop` when not `attention.execution_allowed`, else `{"actor_id": id, **result}`.

- [ ] **Step 1: Failing test** `test_scheduler_runs_skill_review_for_idle_consented_actors`: one consented actor with a procedure turn and one non-consented actor → one `staged` entry for the consented actor only; with `skill_review=False` → `[]`.
- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement** as in Interfaces (mirror `review_memory_idle`).
- [ ] **Step 4: Run** the file and `tests/integration/test_scheduler*.py` (whatever exists) → PASS.
- [ ] **Step 5: Commit** `feat(autonomy): run the skill review when idle`.

### Task 3: Eval plumbing

**Files:**
- Modify: `evals/unified/run_u2_u3.py` (`RUNTIME_FLAGS` + `"skill_review"`; `--skill-review` store_true; add to the runtime_flags tuple; pass to `build_runtime`)
- Modify: `evals/unified/setup_adapter.py` (`build_runtime(..., skill_review=False)`; setup key `skill_review_tick`; `run_skill_review_tick(runtime, *, clock=None) -> list[dict]`)
- Modify: `evals/unified/judge_sheet.py` (show the tick outcome)
- Modify: `evals/unified/score_u2_u3.py` (`setup:` evidence values)
- Test: `tests/unified/test_skill_review_tick.py`

**Interfaces:**
- `setup["skill_review_tick"]: true` → after `_seed_skills`, with `settings.skills=True, skill_review=<flag>`, run `Scheduler.review_skills_idle()`; record `report["skill_review_tick"] = [{**result, "proposals": [{"name", "action", "content"} for each staged pending]}]`.
- Judge sheet: when present, item fact `skill_review_proposals` = the list of `{"name","action","content"}` (empty list when none), so judges read what was staged.
- Score evidence: `setup:skill_proposal_staged` PASS iff any tick entry has `state == "staged"`; `setup:no_skill_proposal` PASS iff no entry is `staged`.

- [ ] **Step 1: Failing tests**: `build_runtime` with a seeded past session holding a procedure turn, `skill_review_tick: true`, `skill_review=True`, scripted reply staging one skill → `report["skill_review_tick"][0]["proposals"][0]["name"] == "flash-esp32c3"`; with `skill_review=False` → tick list empty and `setup:no_skill_proposal` PASS; `score()` returns PASS/FAIL for both evidence values; `build_pilot` sheet item contains `skill_review_proposals`.
- [ ] **Step 2: Run** → FAIL. **Step 3: Implement.** **Step 4: Run** `tests/unified` → PASS.
- [ ] **Step 5: Commit** `eval(unified): skill_review_tick setup key, --skill-review flag, sheet and score support`.

### Task 4: `skills-learn-v2` (M115–M118), reviewed and frozen

**Files:**
- Create: `evals/unified/draft_sources/author_skills_learn_v2.py` (pattern: `author_skills_learn_v1.py`), fixtures, `evals/unified/scenario_sets/skills-learn-v2.json`, `reports/unified/oracle-review-skills-learn-v2/`

Each family seeds one past owner session (`synthetic_sessions`) and `skill_review_tick: true`; the measured turn is a short follow-up («Дякую, на сьогодні все.» / equivalent), so the outcome is the tick.

- M115 `S5_learned_procedure_proposed`: past session — the owner worked out ESP32-C3 flashing (BOOT/RESET/BOOT, 460800 baud, 921600 fails). Evidence `setup:skill_proposal_staged`; accepted: proposal steps match, baud 460800.
- M116 `S6_learned_update_of_existing`: seeded `solder-xt60` (380 °C, 2 mm); past session — owner now uses 400 °C and 3 mm. Evidence `setup:skill_proposal_staged`; accepted: `action == update` of `solder-xt60`, 400 °C, 3 mm, other steps kept.
- M117 `S7_no_skill_from_fact_or_failure`: past session — one fact (printer model) and an unresolved failed attempt («не вийшло, спробую завтра»). Evidence `setup:no_skill_proposal`.
- M118 `S8_no_skill_from_web_turn`: past session — the procedure came from `http_fetch` of a page (tainted turn). Evidence `setup:no_skill_proposal`.

- [ ] Steps: author → build DRAFT + review pack → blind Codex + Gemini review (same commands as `oracle-review-skills-learn-v1`) → apply/reject findings in README → build FROZEN (`TWO_BLIND_REVIEWS_CODEX_GEMINI_2026-11-24`) → commit.

### Task 5: Measure and record

- [ ] gpt-6-luna: `run_frontier.py --manifest …/skills-learn-v2.json --tag luna6 --repeats 3 --arm "control=<defaults flags>" --arm "skill_review=<defaults flags> --skill-review"` from `.worktrees/eval-luna` pinned to the Task 4 commit; judges Gemini + Opus (`claude -p`), consistent verdicts, compare arms.
- [ ] gemma4:12b: same two arms through the Colab orchestrator (`.worktrees/eval-run` pinned); judges Codex + Gemini.
- [ ] Also rerun `skills-learn-v1` on gemma (acceptance of the in-turn behaviour).
- [ ] Report `reports/unified/SKILLS_LEARN_2026-11-24.md` (append sections), wiki log entry; full test suite; commit. Turn-on stays the owner's decision.
