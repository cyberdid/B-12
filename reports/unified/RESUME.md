# How to stop and resume the U2/U3 work (branch feat/unified-dr2-dr3)

**Stopping** is always safe: kill the drivers/bridges or reboot. Every scenario writes one
JSON record atomically; on resume a missing or cut record is re-run, complete ones are kept.

**Resume everything** (idempotent; also restarts the subscription bridges if needed):

    evals/unified/resume_runs.sh            # start what is not running
    evals/unified/resume_runs.sh --status   # progress only

Runs (frozen set `u2-u3-locked-v2`, raw records under `evals/capri_comprehensive/artifacts/`,
git-ignored): A0 (Bolt baseline, 3 repeats), A1 and E1 (Bolt style arms, 3 repeats), haiku
(Claude Haiku via Claude Code), luna (gpt-6-luna via Codex) — cloud runs 1 repeat, no local
context/reply limits. Cloud runs need the owner's subscriptions logged in (`claude`, `codex`);
Codex may pause on its 5-hour limit — just resume later.

**After runs finish** (in this order; plan: `docs/superpowers/plans/2026-11-18-dr2-dr3-execution-roadmap.md`, section F):

1. Judge sheets: `evals/unified/judge_sheet.py` `build_pilot()` per run; judges must not share a
   family with the judged model (luna → Gemini Hydrogen + Claude Opus via agy; haiku → Codex +
   Gemini; Bolt arms → Codex + Gemini). Owner adjudicates disputes (marks yes/+, +-, -).
2. `python -m evals.unified.analyze_pilot <set> <run dir> --semantic <semantic.json>`.
3. `python -m evals.unified.attribute_failures <set> --reference bolt --model bolt=… --model haiku=… --model luna=…`
   → model vs framework table.
4. Owner-approved next work: U4 ADR (memory clocks/validity), U2 arm D (completion verifier).

Done so far: A0 judged and adjudicated — control 0.650 [0.483, 0.800], memory 0.406
[0.239, 0.572] (`reports/unified/semantic-judge-locked-pilot-2026-11-18/`).

## Pause checkpoint — 2026-11-18

The U2/U3 benchmark drivers, pending D launcher, polling shells, and task-specific subscription bridges were stopped. Completed scenario records remain under the ignored `evals/capri_comprehensive/artifacts/` tree; interrupted scenarios will be safely retried by the resume script. Last status snapshot from `evals/unified/resume_runs.sh --status`:

- A0 (Bolt baseline): 360/360 complete
- A1 (brevity arm): 360/360 complete
- E1: 47/360 complete; stopped
- D: 0/360; stopped before launch
- Haiku: 120/120 complete
- Luna: 43/120 complete

To continue later, first review this checkpoint, then run `evals/unified/resume_runs.sh --status`; when ready, `evals/unified/resume_runs.sh` resumes missing work. Worktree `feat/unified-dr2-dr3` and its uncommitted files were preserved; no commit was made during shutdown.

## Checkpoint — 18.11.2026, 22:30 (stopped on the owner's request)

All drivers, queued launchers, judges and subscription bridges were stopped; Ollama only.
Status (`evals/unified/resume_runs.sh --status`): A0, A1, E1, D, U4, D2, F 360/360; Haiku and
gpt-6-luna 120/120; **A0b 51/360 (stopped)**; **D3 0/360**.

Judged and decided (reports under `reports/unified/semantic-judge-*`, aligned comparison in
`consistent-verdicts-2026-11-18/`): A1, E1, D rejected; D2 neutral; **U4 memory +20.6 p.p.
[+8.9, +33.9]**; three-model attribution in `MODEL_VS_FRAMEWORK_2026-11-18.md`.

To continue, in this order:
1. **F judges** (were running, stopped): `evals/unified/launch_judges.sh F evals/capri_comprehensive/artifacts/unified-locked-framework-F-2026-11-18 codex gemini`,
   then `python -m evals.unified.combine_judges reports/unified/semantic-judge-F/sheet.json reports/unified/semantic-judge-F --labels codex=…/codex-0/out.json,… --labels gemini=…` → write `adjudication.json` with the owner's precedents → rerun with `--adjudication`.
2. **A0b and D3 runs**: `evals/unified/resume_runs.sh` (resumes A0b; D3 is listed too — run it after A0b to keep the GPU single-tenant).
3. Re-run `consistent_verdicts.py` over all arms and compare with A0 and A0b.
4. Decide defaults: candidates `memory_temporal` (measured +20.6 p.p.), `goals_in_context` (F: M53/M55 now correct), `verify_writes`, `annotate_unverified_claims` — after A0b settles the control-track drift.

## Update — 19.11.2026, morning (resumed after a reboot)

- **Sandbox leak found and fixed** (commit c17b0aa): the unified worker bound the whole repository,
  so a model searching the home directory reached judge sheets and the oracle review (Haiku
  M42-P1 read a sheet with `sed`; Bolt U4 C39-P1 opened `oracle-review-locked-v1/sheet.json`).
  The worker now sees only its scenario's input/setup fixtures; reports, paper, raw, wiki,
  research, docs, tests, draft sources, other records and `/var/log` are empty tmpfs.
  `B12_EVAL_ENTRY=unified-probe` checks this from inside. Audit and the 13 set-aside records:
  `sandbox-leak-audit-2026-11-19.json`; re-run, judged with `launch_delta_judges.sh` and
  combined with `combine_judges --stale-sheet`. Residual: the runtime source and README stay
  readable (needed to run); they hold no answers.
- **F judged** (adjudication by delegation, owner precedents) and all arms re-aligned:
  `consistent-verdicts-2026-11-19/` (`compare_arms.py`). Vs A0: **F memory +0.267
  [+0.150, +0.394]**, control −0.038 [−0.115, +0.038]; U4 memory +0.211 [+0.083, +0.344];
  D2 neutral; A1/E1/D unchanged (rejected). Haiku memory 0.483, gpt-6-luna control 0.769.
- Next: A0b finishes → judge (`launch_judges.sh A0b … codex gemini`) → compare A0b with A0
  (drift) → D3 → defaults decision.

## Checkpoint — 19.11.2026, ~11:30: U2–U4 closed

Nothing is running except Ollama. Everything is committed on `feat/unified-dr2-dr3` (not pushed).
Read `CAPRI_COGNITIVE_CONTROL_AB.md`, `CAPRI_MEMORY_BASELINE.md`, `CAPRI_U4_TEMPORAL_ABLATION.md`
and roadmap section H. Defaults changed: `memory_temporal` and `goals_in_context` are on.
Open: per-actor file scope (security, postponed), U5 next per the master plan.

## Checkpoint — 19.11.2026, U5 implementation in progress

- Worktree: `.worktrees/unified-dr2-dr3`, branch `feat/unified-dr2-dr3`, base `891f564`.
- ADR-016 implementation is present but uncommitted. Read `reports/unified/ADR-016-scoped-memory-to-action.md`, `reports/unified/ADR-016-implementation-check-2026-11-19.md`, and roadmap section I before continuing.
- Current changes include schema v4; opt-in `memory_scoped` (default off); scope/origin tool fields; shared structured evidence packets; no-evidence instruction; revoked-record filtering; split open/closed goal context; stale retained-evidence label; and closed-goal reopen protection in GoalStore/CLI/API.
- Targeted relevant suite: **296 passed**; Ruff and `git diff --check` passed. No live model, GPU benchmark, client, or service was started in this checkpoint.
- U5 set `u5-application-v1` is still `DRAFT`. `reports/unified/oracle-review-u5-v1/` currently contains only the review prompt, rubric, schema and blank sheet; no completed independent Codex/Gemini reviews were found. **Do not run this draft.** First complete two independent blind reviews, revise to a new version, validate fixture hashes, and freeze; only then follow ADR-016's B0/U5 benchmark protocol.
- Preserve other existing uncommitted files (SIM/CRSI ingest, F judgement files, and U5 draft fixtures). Do not stage or commit the whole worktree.

## Checkpoint — 19.11.2026, U5 author preflight

- Added the explicit-vs-inferred application rule to the scoped-memory system prompt. `origin` is still explicitly described as a model annotation, not independently verified provenance. A regression test checks that rule and that other unresolved current conflicts still request clarification.
- Internal corpus preflight found inconsistencies in M68 (unresolved reliability conflict), M83 (overlapping default and trip-specific scope), and M75 (imperative wording with an ask-before-resume oracle). Corrected M68/M83 and made M75 a genuine advice/ambiguity request; details in `reports/unified/U5-author-preflight-2026-11-19.md`.
- v1 fixtures and review pack are preserved; manifest status is `RETIRED` because it was superseded before independent review. Active candidate `u5-application-v2` has 24 families / 48 variants, status `DRAFT`, and passes `evals.unified.validate_scenarios`. Review pack: `reports/unified/oracle-review-u5-v2/`; it contains no model outputs.
- No model, benchmark, GPU process, client, or service was started. Do not run the draft. Two independent blind reviews remain necessary before any frozen set or model arm.
- The exact focused regression suite has since been rerun: **297 passed**. U5 evaluator setup and scripted-runner tests: **35 passed**; both U5 manifests validate structurally and by fixture hashes. See the latest checkpoint below.

## Checkpoint — 19.11.2026, U5 evaluator bridge verified

- Updated `setup_adapter.py` to seed temporal metadata, scoped fields (`applies_when`, `origin`), superseded history and revocations; unhandled nonempty fixture fields remain visible in `dropped_fields`. Updated `run_u2_u3.py` to pass scoped mode consistently during seed and runtime, expose `--memory-scoped`, and include revocations in the seed report.
- Seed order preserves history: goals are created/completed while their evidence is live, then later supersession/revocation transitions are applied. A no-model test verifies the U5 M76 case where a completed goal retains evidence that later becomes stale.
- Verification: 35 adapter/scripted-runner tests passed; all 24 U5 v2 P1 setups seed without dropping nonempty memory fields; v1/v2 structural/hash validation, targeted Ruff, and `git diff --check` pass. The focused ADR-016 regression suite is 297 passed.
- No live model, GPU benchmark, desktop client, or service was started. U5 v2 remains DRAFT. Two independent blind oracle reviews, scorer semantics review, version freeze, and only then any model experiment remain outstanding.
- Preserve the existing uncommitted worktree and do not stage or commit unrelated files.

## Checkpoint — 19.11.2026, U5 criterion-level evaluator verified

- `judge_sheet.combine` now preserves per-criterion labels and votes in `combined.json`; optional criterion-level owner adjudication is supported without changing the overall response verdict. Tagged adverse criteria remain in blind sheets even if a different deterministic check already failed.
- Added `evals/unified/analyze_u5_metrics.py` for tagged adverse outcomes, unknown handling, pooled and complete-family rates, and paired family-cluster bootstrap intervals. Expected missing repeats count as unknown; unexpected repeat directories are rejected.
- Verification: selected suite across five modules **49 passed in 11.50 s**; changed-file Ruff passed; `git diff --check` passed; v1/v2 scenario manifests validated and v2 review-pack checksums passed. The 49 are evaluator/tooling tests, not model results.
- No model, GPU, client, or service was started. U5 v2 remains `DRAFT`; two independent blind oracle reviews, scorer-semantics confirmation, and a new frozen set remain prerequisites. No commit was made.

## Checkpoint — 19.11.2026, GPU/run status reconciliation

- Read-only `evals/unified/resume_runs.sh --status` reports all scheduled local arms complete: A0, A1, E1, D, U4, D2, F, A0b, and D3 at 360/360 each; Haiku and Luna at 120/120 each. No pending frozen run remains to resume.
- Snapshot from `nvidia-smi`: RTX 4060 Laptop at 6% utilization and 15 MiB / 8188 MiB; the owner confirmed the GPU is free. This is a transient status check, not a benchmark.
- No evaluation was launched. The next planned experiment is the U5 B0/U5 comparison, still gated on two independent blind reviews of the active v3 set, scorer-semantics confirmation, and a new frozen corpus. Do not run DRAFT fixtures.

## Checkpoint — 19.11.2026, U5 v3 author preflight

- A static pass found that M61/M62 reminder prompts and M83 wake-up wording could be read as action requests, although the oracle expected `NO_TOOL`. Rephrased them as questions about which time applies; this preserves the scope/validity task while removing the scheduling/alarm interpretation.
- Preserved v2 and its review pack, marked its 48 scenarios `RETIRED`, and generated v3 from `author_u5_application_v3.py`: 24 families / 48 variants, all `DRAFT`. Prepared a new pack at `reports/unified/oracle-review-u5-v3/`, including the exact manifest SHA-256. v2 pack is marked superseded and its checksums refreshed.
- v1/v2/v3 scenario validators pass. Both v2 and v3 review-pack SHA-256 checks pass. The active v3 pack contains no model outputs or arm labels.
- This is author preflight, not independent review. No GPU/model run was started; two independent blind oracle reviews of v3 remain required before freezing or running it.

## Checkpoint — 19.11.2026, ~15:30 (Claude): U5 measured, regression run going

Codex stopped on its usage limit while combining judges. Committed: ADR-016 implementation (80527e1), U5 eval tooling and sets (5a589bf), U5 results (29acf9b). Running on the GPU: `memory_scoped` on `u2-u3-locked-v2` (`evals/capri_comprehensive/artifacts/unified-locked-U5scoped-2026-11-19`, flags temporal + goals + scoped). Next: `launch_judges.sh U5scoped <run> codex gemini` → combine/adjudicate → `consistent_verdicts` with F/U4/A0 → decide the `memory_scoped` default (roadmap section J).

## Checkpoint — 19.11.2026, ~16:50 (Claude; owner is gaming, GPU left free)

- U5: `memory_scoped` failed the non-regression gate (control −7.1 p.p. vs F on `u2-u3-locked-v2`), stays off (86e47a7). U5.1 (600a292) adds the rules only to turns with memory evidence.
- U6: ADR-017 goal step ledger implemented behind `task_ledger` (off), crash-injection suite 7/7, runbook `CAPRI_WORKFLOW_RECOVERY.md` (4d6155a). Needs owner review of ADR-017 before turning it on.
- **Waiting for a free GPU** (ask the owner first), U5.1 re-measurement, ~45 min:
  ```
  A=evals/capri_comprehensive/artifacts
  EXTRA_RUNNER_ARGS='--memory-temporal --goals-in-context --memory-scoped' evals/unified/run_locked_pilot.sh evals/unified/scenario_sets/u5-application-locked-v1.json $A/unified-u5-application-locked-v1-U51-2026-11-19 3 A0
  EXTRA_RUNNER_ARGS='--memory-temporal --goals-in-context --memory-scoped' evals/unified/run_locked_pilot.sh evals/unified/scenario_sets/u2-u3-locked-v2.json $A/unified-locked-U51scoped-2026-11-19 3 A0
  ```
  Then judges as for U5/U5scoped, adjudicate by oracle text, compare with B0 and F.

## Checkpoint — 19.11.2026, ~18:00 (owner left; everything stopped)

- Nothing runs: gemma driver stopped, SSH tunnel closed, **Colab session stopped** (`colab sessions`: none). e2-micro idle.
- gemma4:12b on Colab (revision `6114515d`, profile `gemma4-12b-colab-6114515d-ollama-0.33.3.json`; the owner's deployment is `4eb23ef1` — owner said to ignore the difference): `unified-locked-gemma-colab-A0-2026-11-19` 123/360, `…-defaults-…` 0/360. Resume: `colab new -s b12eval --gpu L4`, install zstd + Ollama 0.33.3 + `ollama pull gemma4:12b` (check the digest is still 6114515d), tunnel `ssh -fN -L 11435:127.0.0.1:11434 b12eval`, then the same `run_locked_pilot.sh` commands with `B12_EVAL_PROFILE_FILE=… B12_EVAL_OLLAMA_URL=http://127.0.0.1:11435 B12_EVAL_VARIANT=deployed NO_GPU_WAIT=1 EXTRA_RUNNER_ARGS='--variant deployed --model-timeout 300 [--memory-temporal --goals-in-context]'` (resumable).
- **e2-micro orchestrator (owner: runs must survive the laptop being off)** — `paper2-colab-watchdog`, project `gen-lang-client-0903767759`, us-west4-a, user `cyberdid`. Done: git, rsync, bubblewrap (works, incl. `--unshare-net`), tmux, socat; repo at `~/Projects/B-12` (bundle of 95ebc9d), Python 3.12 venv via uv; B-12 profiles/tokenizers + Bolt tokenizer; Colab CLI 0.7.5 with the owner's Colab auth (`~/.config/colab-cli`, mode 600). Codex/Gemini judge credentials NOT copied (needs the owner's yes).
- Colab cannot host the runtime: bubblewrap fails there (no /proc mount, no netns). Design: Colab = Ollama + embeddings only; e2-micro = sandbox runner, queue, storage.
- Remote embeddings: `scripts/st_embedder.py` (B-12's own backend from the model card) gives vectors matching the owner's local install (cos 1.000/0.997) when loaded from a dereferenced snapshot copy (`/root/emb/embeddinggemma-2`; the HF cache uses symlinks into `~/.cache/huggingface/hub/blobs`, copy with `tar -h`). Libraries on Colab: sentence-transformers 6.1.0, transformers 5.19.0.
- **Left to build:** (1) embed relay — on e2-micro `socat UNIX-LISTEN:<sock>,fork EXEC:"ssh b12eval … embed_bridge.py --backend st_embedder:Embedder"`, a stdlib shim inside the sandbox as `embedding_python` (env `B12_EVAL_SEMANTIC_PYTHON`, socket bind in `sandboxed_suite.sh` instead of the local EmbeddingGemma binds); (2) systemd service on e2-micro: ensure Colab session + bootstrap + tunnel, run a job queue with `run_locked_pilot.sh`, `colab stop` when the queue is empty; (3) migrate the gemma arms (rsync records to e2-micro first). Only one SSH connection to a Colab session at a time (close the laptop's master before e2-micro connects).

## Checkpoint — 20.11.2026, ~17:00

Everything committed; Colab stopped by the orchestrator (queue empty); the laptop orchestrator idles (`~/b12-queue-local`, restart with `B12_REPO=<worktree> B12_QUEUE=~/b12-queue-local B12_ASSETS=~/b12-assets-local setsid nohup ops/remote/orchestrator.sh &`; add jobs to `jobs.tsv`). Results: `CAPRI_INTEGRATED_ACCEPTANCE.md` (U9/U8 on gemma). Waiting for the owner: ADR-017 (`task_ledger`) and ADR-018 (`initiative_gate`).

## Handoff — 20.11.2026 ~20:45: plan `2026-11-20-hermes-market-ports.md` (for agy or any agent)

**State:** branch `feat/unified-dr2-dr3`, worktree `.worktrees/unified-dr2-dr3`. Last commit is the plan (`63f24a2`). All work is committed. Uncommitted edits in `wiki/index.md`, `wiki/project/{open-questions,status}.md`, `wiki/topics/{evals,memory,operations}.md` belong to Codex (19.11): never stage, revert or rewrite them. Colab is stopped.

**Read first:** `AGENTS.md`, `wiki/index.md`, `wiki/project/status.md`, the last entries of `wiki/log.md`, then the plan and its spec (`wiki/sources/hermes-agent-2026-11-20.md`, `wiki/sources/market-landscape-2026-11-20.md`).

**Do:** the plan's tasks in order A1 → A2 → A3 → A4 → B1 → D1 → E1 → H3 → H1 → H2 → H5. Each task follows the same loop:
1. Write the failing test and see it fail.
2. Implement.
3. Run the task's tests plus `.venv/bin/python -m pytest -q tests/unit tests/integration tests/unified -p no:cacheprovider` (849 passed, 1 skipped at handoff) and `.venv/bin/ruff check` + `ruff format --check` on the changed files.
4. Commit with explicit paths.

Every new behaviour is a `Settings` flag, default False (see Global Constraints in the plan).

**Do not:**
- push;
- force-push;
- run a bare `git stash`;
- stage whole wiki files carrying others' edits;
- run model evaluations or touch `ops/remote/*` / Colab (phase G is for the owner + Claude);
- load the owner's local GPU;
- open a file for writing in the same expression that reads it (this emptied `wiki/index.md` once — read into a variable first);
- write secrets into docs.

**Stop and ask the owner** before:
- any schema migration beyond the plan;
- any new dependency or download (wake-word model H6);
- turning any flag on by default.

**Prompt surface:** a task that changes what the model sees with flags off must regenerate `tests/fixtures/prompt_surface/owner_default.json` (`B12_UPDATE_PROMPT_SURFACE=1`) and say so in the commit. With flags off it should not change.

**Log:** append one `## [YYYY-MM-DD] lint | …` entry to `wiki/log.md` per finished phase (append only).

## Decision — 22.11.2026: wake word deferred entirely (owner)

Owner: «давай поки без цього взагалі». H6 step 2 is cancelled for now: no openWakeWord model downloads, no hey_jarvis classifier, no custom «Капрі» training. The code from H6 step 1 (`src/b12/audio/wake.py`, `wake_word` flag, off) stays in place and is not extended. Do not start any wake-word work until the owner reopens it.
