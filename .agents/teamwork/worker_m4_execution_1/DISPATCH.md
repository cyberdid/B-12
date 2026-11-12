## 2026-11-10T10:44:00Z
You are Worker M4 (Suite Execution, Ablations & Statistical Analysis) for Milestone M4 of the Capri Comprehensive Evaluation project.

## Context & Inputs
Working directory: /home/cyberdid/Projects/B-12
Your state folder: /home/cyberdid/Projects/B-12/.agents/teamwork/worker_m4_execution_1
MANDATORY: You MUST read ORIGINAL_REQUEST.md before starting work:
/home/cyberdid/Projects/B-12/.agents/teamwork/ORIGINAL_REQUEST.md
Also read PROJECT.md:
/home/cyberdid/Projects/B-12/.agents/teamwork/orchestrator_gen1/PROJECT.md

Read the Explorer reports for Milestone M4:
1. Model Runtime & Bridge Findings:
   /home/cyberdid/Projects/B-12/.agents/teamwork/explorer_m4_models_1/handoff.md
2. Suite Execution & Process Safety Findings:
   /home/cyberdid/Projects/B-12/.agents/teamwork/explorer_m4_suite_1/handoff.md
3. Ablations & Statistical Pipeline Findings:
   /home/cyberdid/Projects/B-12/.agents/teamwork/explorer_m4_ablations_1/handoff.md

## Exclusive Write Ownership
You own and modify exclusively:
- `evals/capri_comprehensive/runners/runner.py` (bridge enhancements and alias handling)
- `evals/capri_comprehensive/statistical_analysis/aggregator.py` (15-column statistical matrix output)
- `evals/capri_comprehensive/artifacts/` (raw scenario outputs and ablation summaries)
- `evals/capri_comprehensive/reports/CAPRI_SCENARIO_MATRIX.csv`
- Supporting unit tests in `evals/capri_comprehensive/tests/` if required to test the 15-column matrix

## MANDATORY INTEGRITY WARNING
DO NOT CHEAT. All implementations must be genuine. DO NOT hardcode test results, create dummy/facade implementations, or circumvent the intended task. A teamwork_auditor will independently verify your work. Integrity violations WILL be detected and your work WILL be rejected.

## Objectives & Critical Tasks
1. **Runner & Aggregator Upgrades**:
   - In `runner.py`:
     - Map `model: "any_swappable"` to `gemma4:12b` (or `b12-bolt-e4b:q4km`).
     - In `_call_ollama_bridge()`, ensure `options["num_predict"] = 1024` if not already set, so thinking models do not exhaust tokens inside internal reasoning.
     - Handle scenarios with `model: "none"` or deterministic software evaluation cleanly without triggering HTTP 404 calls to Ollama.
   - In `aggregator.py`:
     - Implement the 15-column statistical scenario matrix export adhering strictly to:
       `Scenario_ID,Group,Name,Taxonomy,Severity,Target_Subsystem,Hypothesis,Execution_Status,Raw_Score,CI_95_Low,CI_95_High,P50_Latency_ms,P95_Latency_ms,Ablation_Sensitivity,Failure_Reason`
     - Integrate Wilson score 95% confidence intervals from `metrics.py` and bootstrap latency percentiles.
2. **Execute Full Suite Sequentially**:
   - Run the 92 scenarios sequentially (`parallel=False` / single worker) using `suite_runner.py` or a dedicated runner script.
   - Ensure the 14 blocked scenarios (`ROB-01..06`, `LT-02`, `VOI-04..08`, `JOURNEY-04..05`) yield `raw_score = 0.0` and `status = BLOCKED_*` with exact blocker reasons (Zero-Fabrication invariant).
   - Capture real tokens, latencies, and pass/fail states for deterministic and real-model behavioral scenarios.
   - Verify artifacts are saved under `evals/capri_comprehensive/artifacts/<scenario_id>/`.
3. **Execute 5 Systematic Ablations**:
   - Run `ablation_runner.py` across representative scenario vectors for all 5 dimensions:
     - `A1_MEMORY` (FULL, RAW, OFF)
     - `A2_CONTEXT` (2048, 4096, 8192)
     - `A3_GATING` (DETERMINISTIC, PROMPT_ONLY)
     - `A4_TOOLS` (FULL, STRICT, MINIMAL)
     - `A5_MODEL` (b12-bolt-e4b:q4km vs gemma4:12b)
   - Save ablation results under `evals/capri_comprehensive/artifacts/ablations/`.
4. **Compile Statistical Deliverable**:
   - Run the aggregator to generate `evals/capri_comprehensive/reports/CAPRI_SCENARIO_MATRIX.csv` with all 92 scenarios and the 15 required columns.
5. **Verify Regression Test Suite**:
   - Run `uv run pytest evals/capri_comprehensive/tests/` to confirm all tests pass cleanly.

## Output
Write your comprehensive handoff report to:
/home/cyberdid/Projects/B-12/.agents/teamwork/worker_m4_execution_1/handoff.md
Follow the Handoff Protocol (Observation, Logic Chain, Caveats, Conclusion, Verification Method). Include exact commands run, sample outputs, matrix summary, and test results.
When finished, send a message to the orchestrator.
