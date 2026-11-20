# Hermes / market ports Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement every improvement selected from the Hermes Agent study and the market deep dive in B-12. Each one lands behind an off-by-default flag and is enabled only after a measured A/B on gemma4:12b.

**Architecture:** Each feature is a small, separately flagged change to an existing owner module:
- memory: `memory.py`, `tools/memory.py`;
- sessions: `sessions.py`;
- goals and autonomy: `goals.py`, `autonomy.py`;
- the agent prompt path: `agent.py`.

New subsystems (post-turn memory review, schedules, skills) get their own module and are driven by the existing single scheduler (`autonomy.Scheduler`). Nothing lets model text grant permissions, change consent or bypass the ControlPlane.

**Tech Stack:** Python 3.12, asyncio, SQLite (FTS5), pydantic, pytest with the `scripted_ollama` fixture. Evaluations use `evals/unified/*` runners and the laptop orchestrator `ops/remote/orchestrator.sh` with a Colab GPU.

**Spec:**
- `wiki/sources/hermes-agent-2026-11-20.md`
- `wiki/sources/market-landscape-2026-11-20.md`
- `research/market-landscape-2026-11-20/deep-*.md`
- `reports/unified/ADR-019-goal-completion-contract.md`
- `reports/unified/ADR-020-post-turn-memory-review.md`
- `reports/unified/ADR-021-skills-procedural-memory.md`
- `reports/unified/ADR-022-owner-schedules.md`

**Owner decision (20.11.2026):** "нам треба розробити план і все це впровадити". ADR-019…022 are accepted for implementation behind flags, off by default. Turning any of them on needs the measurement in Phase G and an owner yes.

## Global Constraints

- Every new behaviour has a `Settings` flag in `src/b12/config.py`, default `False`, listed in the env bool tuple there and in `tests/unit/test_config.py` defaults.
- Model-facing flags are also added to `RUNTIME_FLAGS` and to an argparse option in `evals/unified/run_u2_u3.py`.
- Architecture invariants from `AGENTS.md`:
  - local-first;
  - the model is replaceable;
  - motion and audio are never blocked by the LLM;
  - one actuator writer;
  - permissions and consent come from the control path, never from model text;
  - memory sources are traceable.
- Memory writes require actor consent (`MemoryStore._consent`). Anything derived from a turn must be removable when that turn's session is cleared or its evidence is purged.
- Background work never runs during the actor's active turn (`Scheduler._busy`). A user turn preempts it.
- No schema change to `memories.origin` (CHECK `explicit|inferred`). The untrusted provenance is expressed with `reliability='unverified'` plus `source`, both existing columns.
- Ukrainian-first text: normalisation for duplicate and trigger matching uses `b12.audio.voice_guards.normalize` (apostrophes `’ ʼ \`` → `'`).
- Model evaluations:
  - gemma4:12b on Colab only; never load the owner's local GPU;
  - 3 repeats;
  - judges Codex + Gemini (agy), disputes decided by owner precedents;
  - verdicts aligned with `consistent_verdicts`.
- **Evaluation runs execute from a dedicated worktree `.worktrees/eval-run` checked out at a fixed commit**, never from the development worktree. Incident 20.11.2026: an edit during a run broke 8 records.
- Commits: explicit paths only; never stage another agent's uncommitted wiki edits (blob staging, see memory `b12-shared-wiki-edit-safety`); commit trailer lines as in this repository.

## Review Focus

1. **Undeclared network content.** A file fetched by `http_fetch`, then read with `file_read` in the same turn, must still taint later memory writes. Taint is per turn once any network tool ran, not per tool result. Task A2 tests it.
2. **Forgotten or foreign turns in search.** Session search must never return a turn from another actor, a cleared session or a turn whose evidence was purged. Task B1 tests all three.
3. **Memory review racing a purge or an owner turn.** A review that started before a purge must not write; a review must not start while the actor is busy. Task C1 tests the deletion-revision check and `_busy`.
4. **Schedules after restart and in quiet hours.** A schedule must not fire twice for one occurrence after a crash, and during quiet hours or owner stop it must go through the initiative gate (defer/inbox), not speak. Task E1 tests both.
5. **Ukrainian duplicates.** `Власник п’є каву` and `Власник п'є каву.` are one fact for the recall-loop guard. Task A1 tests the apostrophe and punctuation variants.

---

## Phase A — memory hygiene and preference placement (no new subsystem)

### Task A1: Recall-loop / duplicate guard in `memory_store`

Restating a fact the model just read from evidence must not create a second record (OpenClaw: "a fact recalled one hundred times stays one fact").

**Files:**
- Modify: `src/b12/memory.py` — add `find_duplicate`.
- Modify: `src/b12/tools/memory.py` — `memory_store` handler.
- Test: `tests/integration/test_memory_duplicate_guard.py`.

**Interfaces:**
- Produces: `MemoryStore.find_duplicate(text: str, actor: Actor) -> MemoryRecord | None`. It returns a live, non-superseded record of the actor whose `normalize(text)` equals `normalize(record.text)`, trailing punctuation ignored.
- Produces: on a duplicate, `memory_store` returns `HandlerOutcome(content={"duplicate_of": <id>, "stored": False})` and writes nothing. This is not behind a flag: a no-op write never changes the model input.

- [ ] **Step 1: Write the failing test**

```python
async def test_restating_a_stored_fact_writes_nothing(scripted_ollama, tmp_path):
    # seed "Власник п’є каву з однією ложкою цукру." ; scripted model calls
    # memory_store(text="Власник п'є каву з однією ложкою цукру") ;
    # assert len(runtime.memory.recent(actor, limit=10)) == 1
    # assert tool result content == {"duplicate_of": seeded.id, "stored": False}
```

- [ ] **Step 2:** run `.venv/bin/python -m pytest tests/integration/test_memory_duplicate_guard.py -v`. Expected: FAIL (2 records).
- [ ] **Step 3:** implement `find_duplicate`, checking only the actor's live records (use the FTS search on the first 3 normalised words, then compare normalised full text). Call it in the handler before `memory.remember`.
- [ ] **Step 4:** run the test plus `tests/unit/test_memory.py`. Expected: PASS.
- [ ] **Step 5:** commit `feat(memory): duplicate guard in memory_store (recall loop)`.

### Task A2: Network taint for memory writes in the same turn

**Files:**
- Modify: `src/b12/agent.py` — mark the turn after a completed `network.http` call.
- Modify: `src/b12/tools/memory.py` — `register(..., turn_tainted=None)`.
- Modify: `src/b12/tools/__init__.py`, `src/b12/runtime.py` — pass the callable.
- Modify: `src/b12/config.py` — flag `memory_taint`.
- Test: `tests/integration/test_memory_taint.py`.

**Interfaces:**
- Produces: `Agent.turn_tainted(context: ExecutionContext) -> bool` — True once any tool with capability `network.http` completed in `context.turn_id`. The state lives in `Agent._tainted: set[str]`, cleared in `_commit` and on cancel.
- Produces: with `settings.memory_taint`, a `memory_store` in a tainted turn writes `reliability="unverified"` and `source="network_turn"`, whatever the model passed.

- [ ] **Step 1: Write the failing tests**

```python
async def test_store_after_http_fetch_is_unverified(...):
    # script: http_fetch (stubbed ok) -> file_read -> memory_store("Сервер у Франкфурті")
    # flag on: record.reliability == "unverified" and record.source == "network_turn"
    # flag off: record.reliability is None and record.source != "network_turn"

async def test_taint_does_not_leak_into_the_next_turn(...):
    # turn 1 fetches; turn 2 only memory_store -> reliability is None
```

- [ ] **Step 2:** run them. Expected: FAIL.
- [ ] **Step 3:** implement. Record the taint in `Agent._run_calls` after a result with `status == "completed"` and `capability == "network.http"`.
- [ ] **Step 4:** run the new tests, `tests/integration/test_preference_rules.py` and `test_prompt_surface.py`. Expected: PASS, snapshot unchanged.
- [ ] **Step 5:** commit `feat(memory): network taint for same-turn memory writes (memory_taint, off)`.

### Task A3: Preference directive next to the query (PrefEval placement)

**Files:**
- Modify: `src/b12/config.py` — `preference_placement: Literal["system", "query"] = "system"`. Add it to the env mapping as a string field.
- Modify: `src/b12/agent.py` — `_admit`: when `preference_rules` is on and placement is `query`, prepend the rules line to the **request copy** of the last user message, never to `state["turn_messages"]`.
- Modify: `evals/unified/run_u2_u3.py` — `--preference-placement {system,query}`, recorded in `runtime_flags` as `preference_placement=query`.
- Test: extend `tests/integration/test_preference_rules.py`.

**Interfaces:**
- Consumes: `_preference_rules(memory, actor, now, limit=8) -> str` (`agent.py`).
- Produces: in the request, the last `user` message content is `f"{rules}\n\n{original}"`. The system prompt then carries no rules line. Persisted history keeps `original`.

- [ ] **Step 1: Write the failing test**

```python
async def test_query_placement_puts_rules_beside_the_question_and_never_persists_them(...):
    # flag preference_rules=True, preference_placement="query"
    # request = state["requests"][-1]["messages"]
    # assert "Вподобання співрозмовника" not in request[0]["content"]
    # assert request[-1]["content"].endswith("Що таке ШІМ?") and "Пояснюй технічне коротко" in request[-1]["content"]
    # assert runtime.sessions.history(session, actor.id)[0]["content"] == "Що таке ШІМ?"
```

- [ ] **Steps 2–5:** fail → implement → pass (plus `test_prompt_surface.py` unchanged) → commit `feat(agent): preference directive placement beside the query (off)`.

### Task A4: `memory_search` as of a date

**Files:**
- Modify: `src/b12/memory.py` — `search(..., as_of: str | None = None)`.
- Modify: `src/b12/tools/memory.py` — `TemporalSearchArgs(SearchArgs)` with `as_of: str = ""` (ISO date). It is offered only when `memory_temporal` and the new flag `memory_as_of` are on.
- Test: `tests/unit/test_memory_temporal.py` (extend).

**Interfaces:**
- Produces: `MemoryStore.search(query, actor, *, limit=8, as_of=None) -> list[MemoryRecord]`. With `as_of`:
  - include records whose validity window contains `as_of` (`valid_from` ≤ `as_of` ≤ `valid_to`, missing bounds open), **superseded ones included**;
  - exclude records whose `event_time` is after `as_of`.

- [ ] **Step 1: Write the failing test**

```python
def test_as_of_returns_the_value_that_held_then(tmp_path):
    # "Адреса: Шевченка 5" valid_to=2026-10-31 ; "Адреса: Лесі 3" valid_from=2026-11-01 supersedes it
    # search("Адреса", actor, as_of="2026-10-15") -> ids == [old.id]
    # search("Адреса", actor, as_of="2026-11-15") -> ids == [new.id]
    # search("Адреса", actor) -> ids == [new.id]   # unchanged default
```

- [ ] **Steps 2–5:** fail → implement → pass → commit `feat(memory): as_of search for past validity (memory_as_of, off)`.

---

## Phase B — conversation recall

### Task B1: Session search store and `conversation_search` tool

**Files:**
- Modify: `src/b12/sessions.py`:
  - FTS5 table `messages_fts(content, message_id UNINDEXED, turn_id UNINDEXED, actor_id UNINDEXED)`, filled in `commit_turn` for `user` and `assistant` rows;
  - rows deleted in `_delete_turns`, `clear_session` and `purge_evidence`;
  - backfill on open when the FTS table is new.
- Create: `src/b12/tools/conversation.py` — tool `conversation_search`, capability `memory.read`.
- Modify: `src/b12/tools/__init__.py`, `src/b12/runtime.py`, `src/b12/config.py` (flag `session_search`).
- Test: `tests/integration/test_session_search.py`.

**Interfaces:**
- Produces: `SessionStore.search(actor_id: str, query: str, *, limit: int = 5, live: Callable[[str, str], bool] | None = None) -> list[dict]`. Each dict has `{turn_id, session_id, created_at, role, snippet}`.
  - The snippet comes from FTS5 `snippet()`, at most 240 characters.
  - Only rows of `actor_id`.
  - Turns with dead evidence are hidden through `live`, as `history_with_tags` does.
- Produces: tool `conversation_search(query: str, limit: int = 5)`. It returns `{"matches": [...]}` with the date and the snippet. Results are wrapped as data, like memory evidence; there is no scroll mode in v1.

- [ ] **Step 1: Write the failing tests**

```python
def test_search_finds_own_past_turns_only(tmp_path):
    # actor A turn "Ми обрали Neovim" ; actor B turn "Neovim" ; search(A, "Neovim") -> 1 match, A's turn

def test_cleared_session_and_purged_turns_are_not_found(tmp_path):
    # commit turn ; clear_session -> search == [] ; commit tagged turn ; purge_evidence -> search == []

def test_ukrainian_prefix_matching(tmp_path):
    # turn "редактором" ; search("редактор") finds it   # use the same _forms() as MemoryStore.search
```

- [ ] **Steps 2–5:** fail → implement. Reuse `memory._forms` for query terms and quote every term (no FTS syntax from the model). Run the tests and `tests/unit/test_sessions.py`, then commit `feat(sessions): conversation_search over past turns (session_search, off)`.

---

## Phase C — ADR-020 post-turn memory review

### Task C1: `MemoryReviewer` in the scheduler

**Files:**
- Create: `src/b12/memory_review.py`.
- Modify: `src/b12/autonomy.py` — `Scheduler.review_memory_idle()`, called from `run()` after `reflect_idle`.
- Modify: `src/b12/sessions.py` — `turns_since(actor_id, after_sequence, limit) -> list[dict]` (turn_id, sequence, session_id, messages).
- Modify: `src/b12/memory.py` — `forget_by_locator(actor, prefix) -> int`, called from `SessionStore.clear_session` callers (`api.py`, `cli.py` session clear).
- Modify: `src/b12/config.py` — flags `memory_review`, `memory_review_approval`.
- Test: `tests/integration/test_memory_review.py`.

**Interfaces:**
- Produces: `MemoryReviewer(runtime).review(actor, *, cancel=None, timeout_s=120) -> dict`, with state `skipped | recorded | staged | rejected | failed`.
- One model call per batch of at most 6 unreviewed **interactive** turns. Turns of goal tasks (present in `task_goals`) and turns marked by A2's taint are excluded from candidates. Tainted turns may still be read, but their candidates get `reliability="unverified"`.
- Prompt: `reflection.GROUNDING` plus the output contract `{"candidates": [{"text": str, "kind": "fact"|"preference"|"decision", "turn_id": str}]}`. At most 5 candidates per batch.
- Each candidate is:
  - checked with `find_duplicate` (A1);
  - written with `remember(..., source="post_turn_review", origin="explicit", source_locator=f"turn:{turn_id}", expected_deletion_revision=<captured before the call>)`.
- With `memory_review_approval`, candidates go to a new table `review_pending(id, actor_id, text, kind, turn_id, created_at)` in `memory.sqlite3` instead. Approve and reject are CLI commands: `b12 memory pending|approve|reject`.
- Progress cursor: `control.set_meta(f"memory_review:{actor_id}", <last sequence>)`.
- Never forget or supersede from the review.

- [ ] **Step 1: Write the failing tests**

```python
async def test_review_records_a_grounded_fact_with_a_turn_locator(...)
    # committed owner turn "запам'ятай: у мене алергія на горіхи" with a reply that did NOT call memory_store
    # scripted review reply -> candidates=[{"text": "У власника алергія на горіхи", "kind": "fact", "turn_id": t}]
    # after review: one record, source_locator == f"turn:{t}", origin == "explicit"

async def test_review_skips_goal_turns_and_duplicates(...)
async def test_purge_during_review_rejects_the_write(...)      # deletion revision changes mid-call -> state "rejected"
async def test_clearing_the_session_forgets_reviewed_records(...)  # forget_by_locator removes it
async def test_approval_mode_stages_instead_of_writing(...)
async def test_review_does_not_run_while_the_actor_is_busy(...)
```

- [ ] **Steps 2–5:** fail → implement → pass (with `tests/integration/test_autonomy.py`) → commit `feat(memory): ADR-020 post-turn memory review (memory_review, off)`.

---

## Phase D — ADR-019 goal completion contract

### Task D1: Contract fields, trusted checks, boundaries, failure streak

**Files:**
- Modify: `src/b12/goals.py`:
  - additive nullable columns `contract TEXT` (JSON) and `failure_streak INTEGER NOT NULL DEFAULT 0`;
  - `create(..., contract=None)`; the contract is immutable like the intent (extend the trigger to `contract`);
  - `record_check(goal_id, passed: bool) -> int` (streak).
- Modify: `src/b12/autonomy.py`:
  - `check_passes` gains `file_sha256` (`{"kind","path","sha256"}`), `command_exit_zero` (`{"kind","argv"}`) and `http_status` (`{"kind","url","status"}`);
  - `command_exit_zero` runs only when `argv` is in `settings.goal_check_commands` (tuple of argv tuples, owner config), with `subprocess.run(argv, timeout=60, shell=False)` and no network;
  - `http_status` runs only for hosts in `network_allow`.
- Modify: `src/b12/tools/registry.py` — in a goal turn, refuse calls outside `contract["boundaries"]` (tools list, path prefixes) with error `outside_goal_boundaries` before control prepare.
- Modify: `src/b12/agent.py` `_goals_context` — show `verification`, `constraints`, `boundaries` and `stop_when` to the goal turn. A reply starting with `[GOAL_BLOCKED]` pauses the goal with `needs_owner` and the reason.
- Modify: `src/b12/config.py` — flag `goal_contract`, `goal_check_commands: tuple = ()`.
- Modify: `src/b12/cli.py` — `goals add --verify-kind/--verify-arg/--constraints/--boundary-tool/--boundary-path/--stop-when`.
- Test: `tests/integration/test_goal_contract.py`.

**Interfaces:**
- Produces: `GoalStore.create(..., contract: dict | None = None)`. The contract keys are `verification`, `constraints`, `boundaries` (`{"tools": [...], "paths": [...]}`) and `stop_when`.
- Produces: three failed checks in a row → `set_status(goal, "paused", "check_failed_3x")` and a `needs_owner` InitiativeCandidate.

- [ ] **Step 1: Write the failing tests**

```python
def test_command_exit_zero_runs_only_allowlisted_argv(...)   # not in allowlist -> False, never executed
def test_file_sha256_check(...)
async def test_call_outside_boundaries_is_refused_before_prepare(...)  # policy decision outside_goal_boundaries
async def test_goal_blocked_marker_pauses_with_needs_owner(...)
async def test_three_failed_checks_pause_the_goal(...)
def test_contract_is_immutable(...)                          # UPDATE contract -> IntegrityError
```

- [ ] **Steps 2–5:** fail → implement → pass (with `tests/integration/test_autonomy.py`, `test_intg_journeys.py`) → commit `feat(goals): ADR-019 completion contract, trusted checks, boundaries (goal_contract, off)`.

---

## Phase E — ADR-022 owner schedules

### Task E1: Schedules through the initiative gate

**Files:**
- Create: `src/b12/schedules.py` — `ScheduleStore` (table `schedules` in `goals.sqlite3`) and `next_occurrence`.
- Modify: `src/b12/autonomy.py` — `Scheduler.run_schedules()` in `tick()`.
- Modify: `src/b12/cli.py` — `schedule add|list|pause|resume|remove`.
- Modify: `src/b12/config.py` — flag `schedules`.
- Test: `tests/integration/test_schedules.py`, `tests/unit/test_schedule_times.py`.

**Interfaces:**
- Produces: `next_occurrence(spec: dict, after: datetime, tz: str) -> datetime | None`. Specs:
  - `{"kind": "daily", "time": "HH:MM", "weekdays": [0-6]}`;
  - `{"kind": "once", "at": ISO}`;
  - `{"kind": "interval", "minutes": int}`.
  - No cron dependency.
- Produces: `ScheduleStore.add(actor_id, session_id, spec, prompt, *, tz, allowed_tools=(), budget_turns=1) -> dict`, `due(now) -> list[dict]`, `claim(schedule_id, occurrence: str) -> bool`, `finish(schedule_id, occurrence, outcome)`.
- `claim` inserts `(schedule_id, occurrence)` into `schedule_runs` with a PRIMARY KEY, so a restart never runs one occurrence twice. An `unknown` run is not retried.
- Catch-up: an occurrence older than `clamp(period/2, 2 min, 2 h)` is skipped and recorded `missed`.
- Run:
  - one background turn as `run_goal` does, through the ADR-017 step ledger;
  - the reply becomes `InitiativeCandidate(trigger="goal_review", goal_id=f"schedule:{id}")` and passes through `initiative.decide`;
  - a reply equal to `[SILENT]` → `drop`;
  - a run that failed before any model call (`ModelError` transport codes) is re-run after 5/15/30 min;
  - `failure_streak` ≥ 3 → paused;
  - a schedule turn has no access to schedule management.

- [ ] **Step 1: Write the failing tests** (unit tests on `next_occurrence` around DST and weekdays; integration with a fake clock)

```python
def test_daily_weekdays_skip_weekend(): ...
def test_kyiv_dst_change_keeps_wall_clock(): ...          # 2026-10-25 change, Europe/Kyiv
async def test_occurrence_runs_once_across_restart(...)   # claim twice -> second False
async def test_quiet_hours_defer_not_speak(...)
async def test_silent_reply_is_dropped(...)
async def test_transport_failure_reruns_after_5_minutes(...)
```

- [ ] **Steps 2–5:** fail → implement → pass (with `tests/integration/test_autonomy.py`, initiative tests) → commit `feat(autonomy): ADR-022 owner schedules (schedules, off)`.

---

## Phase F — ADR-021 skills (procedural memory)

### Task F1: Skill store, index and `skill_view`

**Files:**
- Create: `src/b12/skills.py` — `SkillStore(state_dir / "skills")`.
- Create: `src/b12/tools/skills.py` — `skill_view(name, path="")`, capability `memory.read`.
- Modify: `src/b12/agent.py` — the skills index line after the stable system prompt part, at most 20 skills and 60 characters per description.
- Modify: `src/b12/config.py` — flag `skills`.
- Test: `tests/integration/test_skills.py`.

**Interfaces:**
- Produces: `SkillStore.list() -> list[dict(name, description, status)]` (`active` only in the index), `SkillStore.view(name, path="") -> str`. The path is confined to the skill directory, with no `..` and no symlinks.
- `SKILL.md` frontmatter needs `name` and `description` (≤60 characters). Anything else is ignored.

### Task F2: Proposals, owner approval, ledger, curator

**Files:**
- Modify: `src/b12/skills.py`:
  - `propose(name, content, *, turn_id) -> str` (pending id, stored with a unified diff);
  - `approve(pending_id) -> None`, `reject(pending_id)`;
  - JSONL ledger `skills/.ledger.jsonl` with `{actor, action, name, sha256_before, sha256_after, turn_id, at}`;
  - `curate(now)`: unused 14 days → `stale`, 30 days → moved to `.archive/`; `pinned` is never touched.
- Create: tool `skill_propose(name, content)`, capability `memory.write`. It only stages and never writes `SKILL.md`.
- Modify: `src/b12/cli.py` — `skills list|show|pending|diff|approve|reject|pin|unpin`.
- Modify: `src/b12/autonomy.py` — `curate` weekly when idle.
- Test: `tests/integration/test_skills.py` (extend).

- [ ] **Steps (F1 and F2):** failing tests first, as follows.

```python
def test_view_refuses_paths_outside_the_skill(...)
async def test_index_lists_active_skills_only_with_the_flag(...)
async def test_skill_propose_stages_and_never_writes(...)
def test_approve_writes_and_ledgers_hashes(...)
def test_curator_marks_stale_then_archives_and_spares_pinned(...)
def test_forgetting_the_source_session_marks_source_forgotten(...)
```

  Implement, pass, commit `feat(skills): ADR-021 skills store, view, proposals, curator (skills, off)`.

---

## Phase G — measurement and decisions (owner-visible)

### Task G1: Evaluation worktree and new frozen scenario sets

**Files:**
- Create: `evals/unified/draft_sources/author_ports_v1.py` → `evals/unified/scenario_sets/ports-live-v1.json` (FROZEN after two blind reviews), with these families:
  - **P1 preference placement:** M88-like and three new style preferences;
  - **P2 conversation recall:** a fact stated only in an earlier session's turn, never stored as memory;
  - **P3 memory review:** "запам'ятай …" where the model tends not to call the tool; asked in a later session after a scheduler review tick;
  - **P4 taint:** a fact from a fetched page vs from the owner — the later answer must hedge the fetched one;
  - **P5 as-of:** "яка була адреса в жовтні?".
- Modify: `evals/unified/setup_adapter.py` to seed prior sessions (P2) and run a review tick (P3) before the measured turn.
- Reviews:
  - `reports/unified/oracle-review-ports-v1/` — blind Gemini (agy default model) and Codex, findings fixed before any run;
  - the builder refuses to overwrite: remove draft outputs first.

- [ ] Steps:
  1. Create `.worktrees/eval-run` at the plan's final commit: `git worktree add .worktrees/eval-run <sha>`, `uv sync`.
  2. Author the set.
  3. Run both blind reviews and fix the findings.
  4. Freeze the set.
  5. Commit `eval: ports-live-v1 frozen`.

### Task G2: Runs, judging, decisions

Queue on `~/b12-queue-local/jobs.tsv` (orchestrator, Colab, gemma4:12b, 3 repeats), all with `B12_REPO=<.worktrees/eval-run>`:
- `u2-u3-locked-v2` with each model-facing flag alone: `memory_grounding`, `preference_placement=query`, `memory_taint`, `session_search`, `memory_as_of`;
- `ports-live-v1` with defaults vs each flag;
- the INTG set with `preference_placement=query`.

- [ ] Steps:
  1. Run.
  2. Judges: `launch_judges.sh` with `MANIFEST` per set.
  3. Adjudicate by precedent.
  4. `consistent_verdicts` with `compare_arms` vs `GDEF`.
  5. Efficiency report for each run.
  6. Report `reports/unified/CAPRI_PORTS_DECISION_REPORT.md`: one row per flag with control and memory deltas, CI, efficiency and a recommendation. A flag is recommended **on** only if memory or the targeted family improves, the control CI lower bound is ≥ −5 p.p., and the efficiency report shows no more failed or repeated calls.
  7. Owner decides.
  8. Turn the chosen defaults on in `config.py`, update the prompt surface snapshot, wiki (`status`, `log`, `index`) and the ADR statuses.
  9. Commit.

---

## Phase H — remaining ports from the study (each flagged, each measured in G2)

### Task H1: `clarify` with choices

**Files:**
- Create: `src/b12/tools/clarify.py` — tool `clarify(question: str, choices: list[str] (2–4), allow_other: bool = True)`, capability `time.read`, so it is always grantable.
- Modify: `src/b12/agent.py` — treat a `clarify` call like `approval_pending`. The turn waits, keeps the same turn id, and resumes with `{"answer": str, "status": "answered|skipped|timed_out"}`.
- Modify: `src/b12/api.py` (`POST /api/clarify/{operation_id}`), `cli.py` (`b12 answer <id> <text>`), voice: the next utterance answers.
- Flag: `clarify_tool`.

**Tests** (`tests/integration/test_clarify.py`):
- `test_turn_waits_and_resumes_with_the_answer`;
- `test_voice_reply_answers_pending_clarify`;
- `test_timeout_returns_timed_out_and_the_turn_finishes`.

### Task H2: Importance at write, recency in ranking

**Files:**
- Modify: `src/b12/migrations.py` — schema v5 with nullable `importance INTEGER CHECK(importance BETWEEN 1 AND 10)`; backup before upgrade as for v4.
- Modify: `memory.remember(..., importance=None)`; `TemporalStoreArgs.importance: int = 0` (0 = unknown).
- Modify: `src/b12/retrieval.py` — score = relevance × `0.5 ** (age_days / 30)` × `(0.5 + importance / 10)`; unknown importance scores 1.0. Applied only with flag `memory_ranking`.

**Tests:** `test_recent_important_outranks_old_trivial` and `test_unknown_importance_is_neutral` (unit, `tests/unit/test_memory_temporal.py`); migration test in `tests/unit/test_memory_migration.py`.

### Task H3: Event-based standing intents

**Files:**
- Modify: `src/b12/schedules.py` — table `intents(id, actor_id, keywords JSON, text, expires_at, fires_left INTEGER DEFAULT 3, cooldown_s INTEGER DEFAULT 86400, last_fired_at, status)`.
- Modify: `src/b12/agent.py` — before recall, a rule-based keyword match on the normalised user text (`voice_guards.normalize`, whole words) injects at most 3 matching intents as a data block. No model call.
- Modify: `cli.py` — `intent add --keyword ... --text ... --days 90`.
- Flag: `standing_intents`.

**Tests:**
- `test_matching_keyword_injects_once_then_cools_down`;
- `test_budget_and_expiry_stop_firing`;
- `test_no_match_no_block`.

### Task H4: Compaction recall harness, then summary compaction

**Files:**
- Create: `evals/unified/compaction_recall.py` (Hermes `evals/compaction` design):
  - a synthetic long owner conversation with planted facts in the middle;
  - questions answered by the model from the post-admission context only;
  - an exact-match scorer;
  - output: recall vs prompt tokens per policy.
- Policies:
  - `trim` — current `_fit_history`;
  - `trim+memory` — current plus memory evidence;
  - `summary` — new.
- Modify: `src/b12/agent.py` — policy `summary` behind flag `history_summary`: when `_fit_history` drops turns, a structured summary of the dropped part replaces them. Template: Мета / Обмеження й вподобання / Зроблено / В процесі / Рішення / Наступні кроки. The summary updates the previous one instead of rewriting it, and is stored as a derived session row tagged with the dropped turn ids, so purge removes it.

**Order:**
1. Build the harness and run it on Colab for `trim` and `trim+memory`.
2. Implement `summary` only if `trim+memory` recall is below 0.8.
3. Re-run.

**Tests:** `test_summary_replaces_dropped_turns_and_is_purged_with_them`.

### Task H5: Stable prefix and parallel read-only calls

**Files:**
- Modify: `src/b12/agent.py` — flag `stable_prefix`. Volatile system parts (date line, goals, preferences, companion profile) move after the fixed persona/policy text.
- Create: `evals/unified/ttft_prefix.py` — 20 turns warm and cold on Ollama; records TTFT P50/P95, host, model digest, `num_ctx`.
- Flag `parallel_reads`: queued calls whose capability is `*.read` run with `asyncio.gather`, results in call order; effectful calls stay sequential.

**Tests:**
- `test_stable_prefix_keeps_persona_bytes_first`;
- `test_parallel_reads_keep_order_and_effects_stay_sequential`.

**Measurement:** TTFT on the owner's deployed stack is **not** run on the local GPU. Run it on Colab and label it Colab-only.

### Task H6: Wake word (local)

- Create: `src/b12/audio/wake.py` — openWakeWord ONNX model, frame-level detector, threshold, refractory 2 s. Before activation nothing is buffered beyond the 1.5 s ring buffer, and nothing is written to disk.
- Modify: `live.py` — mode `wake` where utterances are accepted only within 8 s after a detection.
- Flag: `wake_word`.

**Model download:** needs owner approval (file name, source, size) before fetching.

**Tests:**
- `test_utterances_before_wake_are_ignored`;
- `test_window_closes_after_8_seconds`;
- `test_ring_buffer_never_persists`.

### Task H7: Eywa and external memory benchmarks (research, no code)

- Read arXiv:2605.30771 and the published artifacts.
- Write `wiki/sources/eywa-2026-11-20.md`.
- Decide whether to run B-12 memory on LongMemEval-S / BEAM: feasibility, licence, local runtime cost, what our runtime would need (bulk ingestion without a model turn).
- Record it as an open question with a recommendation.

## Order and dependencies

- A1 → A2 → C1: the review uses the duplicate guard and the taint.
- B1 is independent. A3, A4, D1 and E1 are independent of each other.
- F1 → F2.
- E1 → H3: intents live in `schedules.py`.
- H4 harness before the H4 feature.
- G1 needs A–F and H1–H3, H5 merged. H4 and H6 are measured separately. G2 needs G1.
- Suggested sequence: A1, A2, A3, A4, B1, C1, D1, E1, H3, H1, H2, H5, F1, F2, H4 (harness), H7, H6, G1, G2.

**Already done before this plan (20.11.2026):** interruption note, stop phrase, phantom filter, `memory_grounding` (off), prompt surface snapshot, efficiency report, saved companion profile — commits `593e991`, `8bd65f3`, `f9772ac`.

**Decided not to port:**
- Keeping the heard part of a cancelled answer in history: covered by the interruption note. Cancelled turns stay unpersisted (agent invariant).
- LLM judge as the completion criterion.
- `smart` approvals.
- Flat memory files.
- Cloud GPT-Live and Honcho.
