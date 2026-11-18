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
