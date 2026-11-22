# Remaining work for agy (B-12, 22.11.2026)

> **For agentic workers (agy):** read this file completely, then `AGENTS.md`, then `reports/unified/RESUME.md` (sections «Handoff» and the latest one). Work track by track in the order given. Use checkbox steps. Every task is TDD: write the failing test first, see it fail, implement, run, commit.

**Goal:** finish everything left for the Hermes/market ports and the measurement, except the owner's decisions.

**Owner of decisions:** the owner (Vladyslav). You never enable a flag by default, never freeze a scenario set without the owner's review, never push, never merge into `main`.

**Spec and context:**
- plan of ports: `docs/superpowers/plans/2026-11-20-hermes-market-ports.md` (phases F, H4, H6, H7, G1–G2)
- ADR-020 `reports/unified/ADR-020-post-turn-memory-review.md`, ADR-021 `reports/unified/ADR-021-skills-procedural-memory.md`
- market card `wiki/sources/market-landscape-2026-11-20.md`

---

## Global rules (violations stop the track and go into your report)

1. Work only in `~/Projects/B-12/.worktrees/unified-dr2-dr3` (branch `feat/unified-dr2-dr3`), except model runs, which go to `~/Projects/B-12/.worktrees/eval-run` on a pinned commit (track G).
2. Do not touch the uncommitted Codex files: `wiki/index.md`, `wiki/project/open-questions.md`, `wiki/project/status.md`, `wiki/topics/evals.md`, `wiki/topics/memory.md`, `wiki/topics/operations.md`, and the untracked `raw/arxiv-2611.18856v1.pdf`, `reports/unified/semantic-judge-F/*`, `wiki/sources/self-improvement-memory-2026-11-18.md`, `wiki/topics/engineering-improvement-memory.md`. Before reading-and-writing any file that has someone else's changes, copy it to your scratchpad first, and never open a file for writing in the same expression that reads it (this emptied `wiki/index.md` once).
3. Commit with explicit paths only (`git add <file>`), never `git add -A` or `git add .`. Copy the commit trailers from the previous commit (`git log -1 --format=%B`).
4. No `git push`, no `--force`, no `reset --hard`, no bare `git stash`, no `git worktree remove` of anything you did not create.
5. Every new behaviour sits behind a `Settings` flag in `src/b12/config.py`, default `False`, and every flag is listed in the env bool tuple there and in `tests/unit/test_config.py`.
6. The prompt-surface snapshot (`tests/fixtures/prompt_surface/owner_default.json`) must not change unless a task says so. Check it with `tests/integration/test_prompt_surface.py` after each task.
7. Full check after each track: `.venv/bin/python -m pytest -q tests/unit tests/integration tests/unified -p no:cacheprovider` (currently 954 passed, 1 skipped) and `.venv/bin/ruff check` / `ruff format --check` on the changed files. Two ruff findings in `evals/unified/audit/reproduce.py` and `evals/unified/draft_sources/freeze_u5_application_locked_v1.py` predate this work: leave them.
8. After each track append one entry to `wiki/log.md` (append only, format `## [2026-11-22] lint | <track>`).
9. No new dependencies, no downloads without an explicit owner yes (see track H6).
10. Never print secrets. Judge credentials are read from `~/.config`, not copied anywhere.

## Stop-and-ask list (write it in your report and wait)

- any database schema change beyond the ones named in a task;
- any model download or new package;
- any change to `ops/remote/*` beyond task R4, or any restart of the running orchestrator;
- any step that spends Colab time beyond the budget in track G (the budget is set by the owner; until it is set, do not queue model runs);
- a judge verdict that contradicts an owner precedent (adjudication is a draft for the owner in that case);
- an invariant doubt: consent, permissions, one writer for actions, memory deletion revision.

---

## Track R — hygiene (no model, no Colab)

### R1: bound the taint history in `Agent`
- Files: `src/b12/agent.py` (`_tainted_history`), test `tests/integration/test_memory_taint.py`.
- The set grows without limit in a long-running process. Keep the recent taint marks in a `collections.deque(maxlen=1024)` and a set mirror for membership; the durable mark stays `control.set_meta(f"tainted_turn:{turn_id}", "1")`, which the reviewer already reads.
- Test `test_tainted_history_is_bounded`: after 1100 network turns, `len(agent._tainted_history) <= 1024`, and the oldest turn's durable meta is still `"1"`.

### R2: scoring rule for tool names in `score_u2_u3.py`
- Files: `evals/unified/score_u2_u3.py` (constant `TOOLS`, function `_claimed_tools`), test `tests/unified/test_score_u2_u3.py`.
- Problem: `clarify` has no underscore, so the regex in `_claimed_tools` can never match it, and `conversation_search` matches as a claim whenever the reply writes the literal name without a call. Decide: keep the name list, document the rule in the module docstring, and add tests: a literal `conversation_search` in the reply without a call is an unexecuted claim; a call to it is not.
- Add a note in `evals/unified/README.md` (create it if absent): any change of this rule requires re-scoring every arm (track G does that).

### R3: review of the extra runtime changes (done by you, reported to the owner)
- Read the diff `0c6643f..HEAD` for `src/b12/agent.py`, `src/b12/control.py`, `src/b12/runtime.py`, `evals/unified/judge_sheet.py`, `evals/unified/build_scenario_drafts.py`, `evals/unified/score_u2_u3.py`.
- Write `reports/unified/REVIEW_extra_changes_2026-11-22.md`: per file, what changed, why, whether it changes behaviour with flags off (it must not, except where a task says so), and a verdict. Do not change code in R3; put findings into R1/R2 or a new task in the report.

### R4: orchestrator TERM handling
- Files: `ops/remote/orchestrator.sh`, test `tests/ops/test_orchestrator_term.sh`.
- Problem: when the orchestrator is stopped, the driver it started keeps running. Add a `trap` on TERM and INT that kills the driver's process group (`kill -TERM -- -$driver`) before exit, using the existing `setsid` driver.
- Test without Colab: a stub driver script that sleeps; start the orchestrator in a dry mode (add `B12_ORCH_DRYRUN=1` that skips Colab calls), send TERM, assert the stub is gone within 5 s.
- Do not restart the running orchestrator. The owner restarts it.

---

## Track F — skills (ADR-021, flag `skills`)

### F1: store, index and `skill_view`
- Create `src/b12/skills.py` (`SkillStore(state_dir / "skills")`), `src/b12/tools/skills.py` (tool `skill_view(name: str, path: str = "")`, capability `memory.read`), flag `skills` in `config.py`, registration in `tools/__init__.py` and `runtime.py`.
- Interfaces:
  - `SkillStore.list() -> list[dict]` with keys `name`, `description`, `status` (`active|stale|archived`); the index shows only `active`, at most 20 entries, descriptions cut to 60 characters.
  - `SkillStore.view(name: str, path: str = "") -> str`; `path` must resolve inside the skill directory, no `..`, no symlinks, no absolute paths; otherwise raise `ValueError("path outside skill")`.
- `SKILL.md` needs frontmatter `name` and `description`; a missing or over-long description makes the skill `invalid` (not listed).
- Agent: with `skills` on, append the index block after the stable system prompt part (never inside the cached prefix bytes that the prompt surface snapshot covers; with the flag off nothing changes).
- Tests (names are fixed): `test_view_refuses_paths_outside_the_skill`, `test_index_lists_active_skills_only_with_the_flag`, `test_invalid_frontmatter_is_not_indexed`.

### F2: proposals, approval, ledger, curator
- In `src/b12/skills.py`: `propose(name, content, *, turn_id) -> str` (stores pending diff under `skills/.pending/`), `approve(pending_id)`, `reject(pending_id)`, JSONL ledger `skills/.ledger.jsonl` with `{actor, action, name, sha256_before, sha256_after, turn_id, at}`, `curate(now)`.
- Curator rules: unused 14 days → `stale`; 30 days → moved to `skills/.archive/`; pinned skills are never touched; a skill whose source session was cleared gets status `source_forgotten` and is reported, not deleted.
- Tool `skill_propose(name, content)`, capability `memory.write`: it only stages. It never writes `SKILL.md`.
- CLI: `b12 skills list|show|pending|diff|approve|reject|pin|unpin`.
- `Scheduler`: call `curate` once a week when idle, same guard as `review_memory_idle` (`_busy`, owner stop).
- Tests: `test_skill_propose_stages_and_never_writes`, `test_approve_writes_and_ledgers_hashes`, `test_curator_marks_stale_then_archives_and_spares_pinned`, `test_forgetting_the_source_session_marks_source_forgotten`.
- Stop-and-ask if the ledger needs a SQLite table (the plan says JSONL on purpose).

---

## Track H — remaining ports

### H4: compaction-recall harness (measure first)
- Create `evals/unified/compaction_recall.py` and `tests/unified/test_compaction_recall.py`.
- Input: a synthetic long owner conversation (generated in the file, no real data) with 12 planted facts in the middle.
- Policies: `trim` (current `_fit_history`), `trim+memory` (current plus memory evidence). The `summary` policy is NOT implemented in this track.
- Questions answered from the post-admission context only; exact-match scorer on the planted values; output JSON with recall and prompt tokens per policy.
- Test with the scripted model: the harness runs end to end and the scorer gives 1.0 when the answer is in context and 0.0 when it is not.
- Real measurement is a G-track job (see G2.2 job 9). Do not run it here.
- Implement the `summary` policy (flag `history_summary`) only if the owner says so after the measurement.

### H6: wake word (local) — STOP before the download
- Step 1 (allowed): write `src/b12/audio/wake.py` with a detector interface `WakeDetector.feed(frame) -> bool` and a refractory period of 2 s; the window logic in `live.py` (`wake` mode: accept utterances only within 8 s after a detection); flag `wake_word`. Tests with a fake detector: `test_utterances_before_wake_are_ignored`, `test_window_closes_after_8_seconds`, `test_ring_buffer_never_persists` (no file is written; the buffer is memory only).
- Step 2 (STOP): the real model (openWakeWord ONNX). Report the file name, source URL, licence and size, and wait for the owner's yes. Do not download it.

### H7: Eywa reading (no code)
- Read arXiv:2605.30771 and its artifacts at `eywa.to/research` (use your web tools). Write `wiki/sources/eywa-2026-11-22.md` in the same format as `wiki/sources/hermes-agent-2026-11-20.md`: source, access date, what was read, claims marked as author claims, comparison with B-12, feasibility of running LongMemEval-S or BEAM on B-12 (bulk ingestion without a model turn, licence, local cost).
- End with one open question for the owner, with a recommendation.

---

## Track R5 — prerequisites for G (owner's actions; you prepare, the owner confirms)

These steps block track G. Do the preparation, then stop and report.

1. **Owner's Codex review of `ports-live-v1`.** Prepare only: `reports/unified/oracle-review-ports-v1/prompt-fixed.txt` and `sheet-fixed.json` already exist. Do not run Codex yourself.
2. **Freeze.** After the owner's review result is in the report folder, update the set status to `FROZEN` and record the SHA-256 of `ports-live-v1.json` in `reports/unified/oracle-review-ports-v1/README.md`. Only then.
3. **Pin the run commit.** Once R1–R4 and F1–F2 are committed, record the final commit hash `<PIN>` in `reports/unified/RUN_PIN_ports-live-v1.md`. Move `.worktrees/eval-run` to it (`git -C .worktrees/eval-run checkout --detach <PIN>`). Never run model jobs from `unified-dr2-dr3`.
4. **Budget.** The owner sets the Colab budget in hours. Write it in the same pin file. Until a number is written there, do not queue jobs.

---

## Track G — measurement (model runs on Colab; decisions stay with the owner)

### G2.0: what the orchestrator needs
- The orchestrator is `ops/remote/orchestrator.sh`. It reads `~/b12-queue-local/jobs.tsv` (columns: name, manifest, out_dir, repeats, arm, model, extra args). It runs from `REPO`, which must be `B12_REPO=<eval-run path>`.
- Start it only from the owner's terminal or with the owner's yes. Check `~/b12-queue-local/orchestrator.log` after every change.
- The GPU rule: the owner's local GPU is never loaded. Check `nvidia-smi` before any local step; all model calls go to Colab through the orchestrator.

### G2.1: screen (1 repeat per flag)
Queue these jobs, one at a time, all with manifest `ports-live-v1.json` (frozen), `repeats=1`, arm `A0`, model `gemma4:12b`:
1. `ports-baseline` — all new flags off (control).
2. `ports-memory_grounding` — `--memory-grounding`
3. `ports-preference_placement` — `--preference-rules --preference-placement query`
4. `ports-memory_taint` — `--memory-taint`
5. `ports-memory_review` — `--memory-review`
6. `ports-memory_review_approval` — `--memory-review --memory-review-approval`
7. `ports-memory_as_of` — `--memory-as-of`
8. `ports-session_search` — `--session-search`
9. `ports-memory_ranking` — `--memory-ranking`
10. `ports-standing_intents` — `--standing-intents`
11. `ports-clarify_tool` — `--clarify-tool`
12. `ports-stable_prefix` — `--stable-prefix`
13. `ports-parallel_reads` — `--parallel-reads`
14. `ports-skills` — only after F2 exists and the runner has `--skills`; add the option in the runner if needed (tested).
Each job also gets the base options from the existing jobs (`--model-timeout 300 --memory-temporal --goals-in-context`).

Screen result rule: a flag goes to confirmation only if its screen result is not worse than baseline on the targeted family by more than one item out of the family's cases. This is a screen, not a decision.

### G2.2: confirm (3 repeats), only for flags that pass the screen
- Same jobs with `repeats=3`, plus one job per flag on `intg-live-v1.json` for the INTG families.
- Plus job `h4-compaction` (track H4) on the planted-fact set, `trim` and `trim+memory`.

### G2.3: judging
- For each run: `MANIFEST=<set> RUBRIC_DIR=<dir> evals/unified/launch_judges.sh <name> <run_dir> codex gemini`. If Codex is rate-limited, run `gemini` twice and say so in the report (do not invent a Codex verdict).
- Wait for `out.json` files (the judge work dir `reports/unified/.judge-work-<name>/`). Do not pipe `launch_judges.sh` into `tail` (it hangs on inherited pipes).

### G2.4: combine and adjudicate by precedent
- `python -m evals.unified.combine_judges <sheet.json> <out_dir> --labels codex=... --labels agy=... --adjudication <adj.json>`.
- Write `adjudication.json` only for disputes that match an existing owner precedent. Cite the precedent in the reason (look at `reports/unified/semantic-judge-*/adjudication.json`, e.g. C02, M57, M37).
- Any dispute without a precedent goes into `reports/unified/CAPRI_PORTS_OWNER_DISPUTES.md` for the owner. Do not decide it.

### G2.5: aligned verdicts and comparison
- `python -m evals.unified.consistent_verdicts reports/unified/consistent-verdicts-ports-2026-11-22 <name>=<judge_dir> ...`
- `python -m evals.unified.compare_arms <dir> <manifest> <baseline> <name>=<run_dir> ...`
- `python -m evals.unified.efficiency_report <run_dirs...> --json ...`
- Because R2 may change the scoring rule, re-score every arm you compare under the same rule first (`score_u2_u3`), and say so in the report.

### G2.6: decision report (recommendation only)
- Write `reports/unified/CAPRI_PORTS_DECISION_REPORT.md`: one row per flag with control and memory deltas, confidence intervals, efficiency columns (failed calls, repeated calls, policy denials, unfinished turns, TTFT P50/P95), the screen and confirm results, and a recommendation.
- Recommendation rule: a flag is recommended ON only if the targeted family improves, the control interval lower bound is no worse than −5 percentage points, and efficiency shows no more failed or repeated calls. Otherwise recommend OFF.
- The report never turns a flag on. The owner decides.

---

## Order and exit criteria

| Order | Track | Exit criterion | Who waits for whom |
|---|---|---|---|
| 1 | R1, R2 | tests green, committed | — |
| 2 | R4 | stub test green, orchestrator untouched | — |
| 3 | R3 | `REVIEW_extra_changes_2026-11-22.md` written | after R1, R2 |
| 4 | F1 | 3 tests green | — |
| 5 | F2 | 4 tests green, CLI works | after F1 |
| 6 | H4 | harness test green | — |
| 7 | H6 step 1 | 3 tests green, step 2 reported | — |
| 8 | H7 | wiki source written | — |
| 9 | R5 | pin file, budget written, owner's review done | after R1–F2 committed; owner's Codex review |
| 10 | G2.1 | 14 screen results, adjudicated | after R5 |
| 11 | G2.2–G2.5 | confirm results, verdicts, comparison | after G2.1 and owner's budget |
| 12 | G2.6 | decision report written, owner informed | after G2.5 |

**Done means:** every track above has committed tests, a wiki log entry, and a report in `reports/unified/`. Every stop-and-ask item is listed in your final report with the question for the owner. Nothing is pushed.
