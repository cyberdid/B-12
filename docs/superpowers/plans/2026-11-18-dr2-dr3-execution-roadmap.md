# DR2/DR3 Execution Roadmap (shared by Codex and Claude)

> **For agentic workers:** this is the single running plan for branch `feat/unified-dr2-dr3`. Codex started it; Claude continues it while Codex is rate-limited. Whoever works next reads this file, the last entries of `wiki/log.md`, and `reports/unified/MVP_ACCEPTANCE_LEDGER.md`, then picks the first unchecked item whose dependencies are met. Tick items only with an artifact and a recorded check.

**Source of truth:** `raw/CAPRI_DR2_DR3_MASTER_PLAN_2026-11-15.md` §10 (U0–U10, gates) and §13 (first package), in the main checkout. Owner goal 18.11.2026: an MVP that passes all tests and re-verifies the problems found in earlier versions and articles.

**Dependency graph (master plan §10.1):** `U0 → U1 → {U2, U3}`; `U3 → U4 → U5`; `U1 → U6` (after shared IDs/actor/evidence/purge contracts); `U5 → U7`; `U3+U5 → U8`; all → `U9 → U10`.

## Working rules

- Ask the owner before moving past a gate into production behaviour changes (U4+ schema, U6 ledger, U7 inbox). Each needs an ADR, tests and owner review.
- Model runs only through `evals/capri_comprehensive/runners/sandboxed_suite.sh` or the Docker networkless path; never on production memory. Check the GPU is free first (the owner plays games on it).
- Wiki log is append-only. Stage explicit paths only. No push or PR without the owner.
- A passing structural test is not acceptance. Keep FAIL/BLOCKED results as they are; do not edit an oracle after seeing model output without a new version.

## Stage status (18.11.2026, 15:30)

| Stage | State | Evidence | What closes it |
|---|---|---|---|
| U0 freeze/audit/contracts | partial | `reports/unified/U0_BASELINE_AUDIT.md`, `THREAT_MODEL.md`, schemas, environment manifest, historical repeats ledger | full store inventory, frozen scenario schema, locked splits |
| U1 telemetry | partial | `evals/unified/trace.py`, `tool_oracles.py`, `on_policy_decision` in `ToolRegistry`, runtime trace observer | classification proposal and typed retrieval evidence per step; trace correlation across approval resume |
| U2 control pilot | protocol + draft corpus v2 + setup adapter | `U2_BREVITY_REPRODUCTION.md`, `u2-u3-draft-v2` (C01–C30) | oracle review, setup runner adapter, frozen arms, runs, keep/rollback report |
| U3 memory baseline | protocol + draft corpus | `U3_MEMORY_BASELINE_PROTOCOL.md`, `u2-u3-draft-v2` (M01–M30), `runtime_snapshot.py` | store coverage audit, setup adapter seeding memory and goals, runs, report |
| U4–U10 | not started | — | per master plan §10 |

## Next items, in order

### A. Close the U2/U3 corpus gate
- [x] Draft corpus v1 (60 families × 2 variants, hashed).
- [x] Independent read-only review by Codex; v2 fixes: evaluator-only setup files, UUID ids, registered tool names, GoalStore goals, exact `ExecArgs`; 6 families BLOCKED.
- [x] Blind second review of v2 by agy/Gemini: 50 ok / 2 minor / 6 major / 2 blocker; 9 accepted → v3, 1 rejected (sheet artifact); no owner adjudication needed (`reports/unified/oracle-review-v2/`).
- [ ] Freeze: copy reviewed families to `status: FROZEN` in a new set version; never edit a frozen file.

### B. Setup runner adapter (needed before any U2/U3 run)
- [x] `evals/unified/setup_adapter.py`: files under a fresh private root, actors/sessions, memory via `MemoryStore` (`recorded_at` → `created_at`, `supersedes` → stale), goals via `GoalStore`; report maps declared → real ids and lists dropped clock/provenance fields. 13 tests; all 54 unblocked v2 setups seed.
- [x] Fresh tmpfs `/sandbox` and `/actors` in the bubblewrap worker (`B12_EVAL_ENTRY=unified-u2u3`).
- [ ] Apply `available_tools`, approval policy and the `sudo_exec` stub from the setup through the control path (now recorded as `tool_policy.applied: false`).
- [x] `evals/unified/run_u2_u3.py`: adapter seed → real agent turn → raw record (no oracle access); scripted-Ollama tests.
- [ ] Blind scorer: oracle + raw record → verdict per outcome; unsupported outcomes `NOT_SCORABLE`.
- [x] Real smoke run on Bolt, 14 scenarios × 1 (`reports/unified/baseline/u2u3-smoke-2026-11-18.json`): path works end to end; manual 9 PASS / 1 PARTIAL / 4 FAIL. Findings: M18 claims a file read with no tool call; M01/M04 report record dates as event dates (no `event_time` in memory); M08 ignores present evidence; C22 skips read-back.
- [ ] Map oracle checks onto existing verifiers: `file_verifier.py`, `tool_oracles.py`, trace classification; unsupported oracle outcomes stay `NOT_SCORABLE`, not PASS.
- [ ] Tests with scripted Ollama (no real model) for at least one family per class.

### C. U1 remaining items
- [ ] Typed retrieval evidence per step in the trace (which memory IDs were offered as evidence).
- [ ] Correlate collectors across approval resume.

### D. U2 and U3 pilot runs (GPU; owner-visible)
- [ ] Freeze arms A0/A1/E1/E2 per `U2_BREVITY_REPRODUCTION.md`; run frozen U2 families with repeats; analysis with confidence intervals.
- [ ] U3 arms per `U3_MEMORY_BASELINE_PROTOCOL.md`; retrieval vs application scored separately.
- [ ] Reports `CAPRI_COGNITIVE_CONTROL_AB.md`, `CAPRI_MEMORY_BASELINE.md`.

### E. Open problems already measured (track, do not hide)
- [ ] Latency gates: MEM-01 TTFT 1.74–1.78 s warm vs 1.5 s target; SEC-02/04/06 latency FAILs. Re-measure on an idle GPU with the same context size before changing anything.
- [ ] Bolt `ls` target directory: 2/3 correct with the natural prompt.

## Handoff log

- 18.11 Codex: U0/U1 artifacts, real Bolt smoke runs, plan `2026-11-18-u2-u3-draft-corpus.md` Task 1 (builder). Paused on the 5-hour limit.
- 18.11 Claude: Tasks 2–4 of that plan (v1), Codex review, v2 fixes, this roadmap (commit f41df73); setup adapter (B1); blind agy/Gemini review of v2 started (A3).
