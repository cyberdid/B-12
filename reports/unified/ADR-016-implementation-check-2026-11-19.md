---
type: verification_report
updated: 2026-11-19
status: implementation_verified_tests_only
sources:
  - reports/unified/ADR-016-scoped-memory-to-action.md
  - docs/superpowers/plans/2026-11-18-dr2-dr3-execution-roadmap.md
  - src/b12/memory_packet.py
  - evals/unified/setup_adapter.py
  - evals/unified/run_u2_u3.py
  - evals/unified/judge_sheet.py
  - evals/unified/combine_judges.py
  - evals/unified/analyze_u5_metrics.py
  - tests/integration/test_memory_scoped.py
  - tests/unified/test_setup_adapter.py
  - tests/unified/test_run_u2_u3.py
  - tests/unified/test_judge_sheet.py
  - tests/unified/test_combine_judges.py
  - tests/unified/test_analyze_u5_metrics.py
tags: [U5, ADR-016, memory, verification]
---

# ADR-016 implementation check

## Scope and source state

- Worktree: `.worktrees/unified-dr2-dr3`.
- Branch: `feat/unified-dr2-dr3`.
- Base commit when this work resumed: `891f564`.
- All changes remain uncommitted; existing uncommitted Claude work and generated U5 drafts were preserved.
- No live model, GPU benchmark, desktop client, or service was started by this implementation check.

## Implemented

- SQLite schema v4 adds nullable `applies_when` and constrained nullable `origin`; v1–v3 upgrade paths remain additive.
- `memory_scoped` is an opt-in setting, default `false`, parsed from `B12_MEMORY_SCOPED` and threaded into tool registration and the agent.
- `memory_store` accepts scope/origin annotations only when scoped memory is enabled; temporal and scope fields coexist in the tool schema.
- Revoking with no replacement stores `status_reason='revoked'`; scoped automatic recall and `memory_search` omit revoked records. Superseded records are supplied as history with state metadata.
- Shared evidence packet code emits `{id, text, meta}` with event/recorded/valid times, current validity state, scope, origin label, reliability and source references. Lexical same-subject links are explicitly only candidates, not semantic conflict judgments.
- `ContextBuilder` validates the packet metadata shape. The agent supplies fixed application rules and an explicit no-evidence note when scoped recall is empty.
- With scoped memory enabled, goal context separates open and closed commitments, warns against restoring closed goals without owner instruction, and marks achieved goals when retained evidence becomes stale.
- Closed-goal status transitions require a trusted `reopen=True`; CLI and owner API paths pass it. Guest API requests receive 403 on reopening. Autonomy cannot complete an abandoned goal.
- The synthetic setup adapter now seeds temporal and scoped fields when their arms are enabled, applies superseded and revoked states through the memory lifecycle API, and reports fixture fields that were not applied. It creates goals before retirement transitions so a historically completed goal can retain evidence that later becomes stale.
- The U2/U3 runner exposes `--memory-scoped`, passes the same scoped flag to seeding and the agent runtime, and records revoked fixture memories. A scripted-model integration test confirms scope metadata reaches the prompt.

## Verification

The focused compatibility and regression command covered configuration, context admission, goal evidence, memory migration/temporal/scope, agent loop, autonomy, API, recovery and CLI tests:

```text
297 passed in 53.54s
```

The exact command was:

```bash
./.venv/bin/pytest -q \
  tests/unit/test_config.py tests/unit/test_context.py \
  tests/unit/test_goal_checkpoint_evidence.py tests/unit/test_memory.py \
  tests/unit/test_memory_migration.py tests/unit/test_memory_temporal.py \
  tests/unit/test_memory_temporal_render.py tests/unit/test_memory_scope_schema.py \
  tests/integration/test_memory_scoped.py tests/integration/test_memory_temporal_recall.py \
  tests/integration/test_memory_restart.py tests/integration/test_goals_in_context.py \
  tests/integration/test_agent_loop.py tests/integration/test_autonomy.py \
  tests/integration/test_api.py tests/e2e/test_recovery.py tests/e2e/test_cli.py
```

Ruff passed on all touched Python files; `git diff --check` passed. A repository-wide `ruff check src tests --statistics` still reports 32 findings (29 `E501`, 3 `F401`) outside the touched Python files.

## U5 harness verification (no live model)

The selected U5 evaluator suite passed **49 tests in 11.50 s** across `test_setup_adapter.py`, `test_run_u2_u3.py`, `test_judge_sheet.py`, `test_combine_judges.py`, and `test_analyze_u5_metrics.py`. The adapter/scripted-runner subset accounts for 35 of these. They cover seeding every one of the 24 U5 v3 P1 fixtures with no nonempty memory fields dropped; explicit scope/origin and document provenance; revocation; a completed goal whose evidence later becomes superseded; and a scripted turn confirming scope reaches context.

The judge pipeline now preserves per-criterion labels and votes in `combined.json`; optional criterion-level owner adjudication can resolve tagged disputes without replacing the whole-response verdict. Judge-sheet construction retains metric-tagged semantic criteria even when an unrelated deterministic check fails. `analyze_u5_metrics.py` treats `met` on a tagged forbidden effect as adverse, leaves disputed/unclear/missing results unknown, reports pooled and complete-family rates, and computes paired family-cluster bootstrap intervals. v1, v2, and v3 scenario manifests pass structural/hash validation. The five-module selected suite, changed-file Ruff, and `git diff --check` pass. These changes verify the evaluator bridge only; they are not an oracle review or model-quality result.

## Not established

- The active U5 corpus `u5-application-v3` remains `DRAFT`; two independent blind oracle reviews have not been completed. v1 and v2 are preserved as `RETIRED`. No model was run against these sets.
- No result demonstrates better decision quality, less stale-memory use, or fewer goal resurrections. The flag therefore remains off by default.
- The `origin` value supplied through model tool arguments is a model annotation, not runtime-verified provenance.
- `conflicts_with` links are lexical candidates and may include related facts; they do not prove contradiction.
- Explicit forgetting deletes dependent goal content under the existing purge contract, so no stale-goal marker remains after forget.
- Cross-model behavior, natural-language preference-scope interpretation, and long-term use have not been evaluated.
