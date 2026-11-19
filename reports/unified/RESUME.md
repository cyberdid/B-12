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
