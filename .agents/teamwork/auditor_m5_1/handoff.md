# Forensic Audit Report: Milestone M5 Gate (Capri Comprehensive Evaluation Deliverables)

**Author**: Forensic Auditor (`auditor_m5_1`)  
**Target Milestone**: M5 Gate (Deliverable Reports & Evaluation Synthesis)  
**Date**: 2026-11-10T14:10:00Z  
**Recipient**: Orchestrator / Parent Agent (`9ecc6249-32cc-48fe-ada7-ff8ec7dc5a4f`)  
**Integrity Mode**: Development Mode (with strict Zero-Fabrication Invariant)  
**Verdict**: **CLEAN**

---

## 1. Observation

1. **Test Suite Execution**:
   - Command: `uv run pytest evals/capri_comprehensive/tests/ -v`
   - Result: 134 passed in 4.93s (`test_framework.py`: 15 passed, `test_stress_m2.py`: 21 passed, `test_stress_m3.py`: 79 passed, `test_stress_m4.py`: 19 passed). Zero test failures, zero warnings.

2. **Empirical Data Artifacts & Cross-Verification**:
   - `evals/capri_comprehensive/reports/batch_summary.json` (6839 lines, 364 KB, timestamp `2026-11-10T13:35:06.808889+00:00`):
     - Total scenarios: 92
     - Passed (`EXECUTED_PASS`): 29
     - Failed (`EXECUTED_FAIL`): 49
     - Blocked Hardware (`BLOCKED_HARDWARE`): 12 (VOI-04..08: 5, ROB-01..06: 6, JOURNEY-05: 1)
     - Blocked Delay (`BLOCKED_DELAY`): 2 (LT-02: 1, JOURNEY-04: 1)
     - Runnable total: 78 (29 pass, 49 fail). Runnable pass rate: 37.2% [27.3%, 48.3%].
   - `evals/capri_comprehensive/reports/CAPRI_SCENARIO_MATRIX.csv` (92 rows x 15 columns):
     - 1-to-1 match with `batch_summary.json` across all 92 scenario IDs, execution statuses, raw scores, Wilson confidence intervals, and bootstrap P50/P95 latencies.
   - Cross-check of all 65 scenario latency citations in `CAPRI_COMPREHENSIVE_EVALUATION.md`:
     - 100% of cited parenthetical latencies (e.g., `MEM-01 (6571.4 мс)`, `MEM-06 (5445.3 мс)`, `CM-01 (64078.5 мс)`, `SEC-01 (12295.0 мс)`) exactly match `CAPRI_SCENARIO_MATRIX.csv` P50 latency column to within rounding precision.

3. **Systematic Ablations Artifact Verification**:
   - `evals/capri_comprehensive/artifacts/ablations/MEM-01_A1_MEMORY.json`: FULL: Fail (6508.14 ms), RAW: Pass (3569.51 ms), OFF: Fail (8699.90 ms). Exactly cited in reports.
   - `evals/capri_comprehensive/artifacts/ablations/MEM-01_A2_CONTEXT.json`: 2048 (6435.63 ms), 4096 (6337.21 ms), 8192 (6365.90 ms). Exactly cited in reports.
   - `evals/capri_comprehensive/artifacts/ablations/SEC-01_A3_GATING.json`: DETERMINISTIC: Pass (11893.36 ms, 1111 prompt tokens), PROMPT_ONLY: Pass (7812.74 ms, 1011 prompt tokens). Verbatim JSON snippet and tokens cited in `CAPRI_SECURITY_EVALUATION.md`.
   - `evals/capri_comprehensive/artifacts/ablations/RE-01_A4_TOOLS.json`: FULL: Fail (10459.34 ms, 1131 tokens), STRICT: Fail (7155.32 ms, 633 tokens), MINIMAL: Fail (5168.02 ms, 423 tokens). Exactly cited in reports.
   - `evals/capri_comprehensive/artifacts/ablations/CM-01_A5_MODEL.json`: `b12-bolt-e4b:q4km`: Fail (8210.08 ms, 509 comp tokens), `gemma4:12b`: Fail (63943.60 ms, 841 comp tokens). Verbatim JSON snippet and tokens cited in `CAPRI_MODEL_CONTINUITY.md`.

4. **Zero-Fabrication on Blocked Protocols**:
   - Exactly 14 scenarios are designated as blocked (12 `BLOCKED_HARDWARE`, 2 `BLOCKED_DELAY`).
   - Zero simulated or fabricated passes exist for Reachy robotic bus (`reachy_actuator_bus`) or physical microphone fixture (`audio_mic_speaker_rig`).
   - Zero fabricated passes exist for 7-day (`LT-02`) or 30-day (`JOURNEY-04`) longitudinal soak tests.

5. **AGENTS.md & Repository Invariants**:
   - All 4 reports (`CAPRI_COMPREHENSIVE_EVALUATION.md`, `CAPRI_MODEL_CONTINUITY.md`, `CAPRI_SECURITY_EVALUATION.md`, `CAPRI_LONG_TERM_PROTOCOL.md`) are written in Ukrainian prose while strictly preserving technical identifiers (`b12-bolt-e4b:q4km`, `gemma4:12b`, `SandboxedEnvironment`, `ControlStore`, `MemoryStore`, `PathGuard`, etc.).
   - Frontmatter in all 4 reports is fully compliant with YAML schema (`type`, `updated`, `status`, `sources`, `tags`).
   - Epistemological tags (**вимога**, **перевірений факт**, **зі слів master brief**, **пропозиція**, **потребує перевірки**) are consistently used across all reports.
   - Security scanner (`check_secrets.py`) scanned 400 files in `evals/capri_comprehensive/reports/` and `artifacts/`: exactly 0 host secrets, private keys, or personal credentials leaked.
   - `git diff --stat` is completely empty; `git status --short` confirms 0 modified tracked files outside `evals/capri_comprehensive/`.

6. **Definitive Classification & Zero Concealment of Failures**:
   - The reports make zero attempt to gloss over failures or inflate scores.
   - 49 failure scenarios are explicitly analyzed with root causes (e.g., failure of `b12-bolt-e4b` to invoke `memory_search` in multi-turn dialogues, guest memory leak in MEM-05, context degradation in CM-07, lack of headless daemon IPC in Group I).
   - Definitive Technical Judgment: Formally rejects Tier-1 autonomous companion status (*"системі B-12 / Capri ВІДМОВЛЕНО у присвоєнні статусу повноцінного автономного компаньйона 1-го рівня"*) and classifies Capri as *"Hybrid Model-Centric Agent System with Emerging Memory and External Control Plane"*.

---

## 2. Logic Chain

1. **Traceability from Raw Artifacts to Final Reports**:
   - Raw scenario executions logged in `batch_summary.json` contain timestamped records and per-turn metrics.
   - `CAPRI_SCENARIO_MATRIX.csv` aggregates these into a 15-column matrix with Wilson 95% CIs and non-parametric bootstrap medians.
   - The 4 deliverable reports cite these values directly without discrepancies or alterations. Every cited number corresponds to genuine raw experimental data.

2. **Validation of Scientific Honesty**:
   - The framework encountered 49 failures across 92 scenarios. Rather than cherry-picking passing runs, the author documented every failure, evaluated hypotheses against pre-established thresholds, and rejected hypotheses where data did not support them (e.g., RQ1: "ГІПОТЕЗУ СПРОСТОВАНО", RQ8: "ГІПОТЕЗУ КАТЕГОРИЧНО СПРОСТОВАНО").
   - Missing hardware was neither simulated nor marked as passed; it was formally classified under `BLOCKED_HARDWARE` and `BLOCKED_DELAY`.

3. **Adherence to Core System Invariants**:
   - Local-first execution is verified: all tests were executed against local Ollama and local SQLite stores with zero external API calls.
   - Host isolation is verified: red-team tests ran in disposable synthetic directories under `/tmp/` without touching `~/.ssh` or host secrets.

---

## 3. Caveats

- **Headless Runner vs Live Daemon**: 15 deterministic software tests in Groups F and I failed due to running in standalone headless mode without an active `b12.service` daemon. This limitation is transparently documented in Section 3 and Section 4.9 of `CAPRI_COMPREHENSIVE_EVALUATION.md`.
- **Hardware Absence**: 12 scenarios remain blocked awaiting physical Reachy actuators and acoustic test fixtures.

---

## 4. Conclusion

**Verdict: CLEAN**

Milestone M5 deliverables fully satisfy all requirements of `ORIGINAL_REQUEST.md`, `PROJECT.md`, `methodology.md`, and `AGENTS.md`:
1. Zero fabricated passes, zero facade implementations, zero cherry-picked statistics.
2. 100% empirical grounding and exact mathematical consistency between raw data (`batch_summary.json`, `CAPRI_SCENARIO_MATRIX.csv`, ablation JSONs) and prose reports.
3. Strict adherence to repository language rules, epistemic tagging, and architectural invariants.
4. Clean git working tree and complete safety isolation with zero leaked credentials.
5. All 134 automated unit/stress/schema tests pass cleanly.

Milestone M5 Gate is approved without reservation.

---

## 5. Verification Method

To independently verify these conclusions:

1. **Run full pytest suite**:
   ```bash
   uv run pytest evals/capri_comprehensive/tests/ -v
   ```
2. **Verify 1-to-1 data alignment between batch_summary and CSV**:
   ```bash
   python3 -c "
   import json, csv
   with open('evals/capri_comprehensive/reports/batch_summary.json') as f:
       batch = json.load(f)
   with open('evals/capri_comprehensive/reports/CAPRI_SCENARIO_MATRIX.csv') as f:
       rows = list(csv.DictReader(f))
   assert len(batch['reports']) == len(rows) == 92
   csv_map = {r['Scenario_ID']: r for r in rows}
   for r in batch['reports']:
       crow = csv_map[r['scenario_id']]
       assert r['status'] == crow['Execution_Status']
   print('Verified: 92/92 scenarios match 1-to-1')
   "
   ```
3. **Verify Git clean status**:
   ```bash
   git diff --stat
   git status --short
   ```
4. **Verify secret hygiene**:
   ```bash
   python3 .agents/teamwork/auditor_m5_1/check_secrets.py
   ```
