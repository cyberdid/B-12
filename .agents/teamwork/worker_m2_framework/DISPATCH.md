## 2026-11-10T08:49:52Z
You are Worker: Evaluation Framework & Engine Architect (Milestone M2).
Working directory: /home/cyberdid/Projects/B-12
State folder: /home/cyberdid/Projects/B-12/.agents/teamwork/worker_m2_framework

MANDATORY FIRST STEP: Read the original request file at:
/home/cyberdid/Projects/B-12/.agents/teamwork/ORIGINAL_REQUEST.md

Also read the Project plan and Explorer handoffs:
/home/cyberdid/Projects/B-12/.agents/teamwork/orchestrator/PROJECT.md
/home/cyberdid/Projects/B-12/.agents/teamwork/spec_miner_survey_eval/handoff.md
/home/cyberdid/Projects/B-12/.agents/teamwork/spec_miner_survey_eval/analysis.md
/home/cyberdid/Projects/B-12/.agents/teamwork/explorer_survey_arch/handoff.md
/home/cyberdid/Projects/B-12/.agents/teamwork/explorer_survey_env/handoff.md

Domain skills to apply:
/home/cyberdid/.gemini/config/skills/statistical-analysis/SKILL.md
/home/cyberdid/.gemini/config/skills/scientific-method/SKILL.md

MANDATORY INTEGRITY WARNING:
DO NOT CHEAT. All implementations must be genuine. DO NOT hardcode test results, create dummy/facade implementations, or circumvent the intended task. A teamwork_auditor will independently verify your work. Integrity violations WILL be detected and your work WILL be rejected.

File Write Ownership:
You have exclusive write ownership of files under:
`/home/cyberdid/Projects/B-12/evals/capri_comprehensive/`
Do NOT modify core production code in `src/b12/` or existing files outside your ownership.

Your Mission:
Implement the foundational framework and execution engine for `evals/capri_comprehensive/`:
1. Documentation & Scientific Foundation:
   - `evals/capri_comprehensive/README.md`: Framework architecture, directory layout, usage guide, CLI invocation examples.
   - `evals/capri_comprehensive/methodology.md`: Complete scientific methodology: 4-tier taxonomy (Deterministic Software, Real-Model Behavioral, Controlled Experimental, Physical Acceptance), zero-fabrication invariant (strict rules for BLOCKED_HARDWARE and BLOCKED_DELAY / PENDING), Wilson score confidence intervals, bootstrap latency estimation, 5 ablation designs (Memory, Context, Tools, Gating, Model Swap), and RQ1–RQ10 evaluation criteria.
2. Directory Structure:
   - Create directories: `scenarios/` (with subdirectories for `group_a_memory`, `group_b_continuity`, `group_c_cross_model`, `group_d_reasoning`, `group_e_security`, `group_f_autonomy`, `group_g_interaction`, `group_h_voice`, `group_i_reliability`, `group_j_robotics`, `group_k_journeys`), `fixtures/`, `evaluators/`, `runners/`, `statistical_analysis/`, `reports/`, `artifacts/`.
3. Evaluators & Schema (`evals/capri_comprehensive/evaluators/`):
   - `schema.py`: Pydantic V2 models for Scenario YAML definitions (`ScenarioDefinition`, `PreConditions`, `InteractionTurn`, `EvaluationRule`, `AssertionOutcome`, `ExecutionReport`).
   - `deterministic.py`: Evaluator executing multi-rule assertions (exact string, substring, regex, tool_called, tool_forbidden, memory_state, file_state, exit_code, max_latency_ms).
   - `sandboxed_env.py`: Isolated disposable working directory manager creating temporary isolated root for each run, copying synthetic fixtures, preventing access to host `~/.ssh` or `~/.local/state/b12/secrets`.
   - `judge.py`: Independent LLM judge harness (never evaluates a model against itself).
4. Runners (`evals/capri_comprehensive/runners/`):
   - `runner.py`: Single scenario runner: loads scenario YAML, sets up sandbox, executes interaction turns against B-12 runtime or mocks, evaluates rules, captures latencies and tokens, returns `ExecutionReport`.
   - `suite_runner.py`: Batch runner executing multiple scenario files across groups with parallel or sequential options, progress output, JSON and JUnit test report output.
   - `ablation_runner.py`: Specialized runner to execute scenarios under the 5 ablation conditions (Memory: OFF/RAW/FULL; Context: 2K/4K/8K; Tools: MINIMAL/STRICT/FULL; Gating: PROMPT_ONLY/DETERMINISTIC; Model: bolt-e4b / gemma4:12b / qwen).
5. Statistical Analysis (`evals/capri_comprehensive/statistical_analysis/`):
   - `metrics.py`: Wilson score 95% confidence intervals for binomial success rates; non-parametric bootstrap (1000 resamples) for P50, P90, P95 latency percentiles.
   - `aggregator.py`: Aggregates batch execution JSON reports into the mandatory 15-column `CAPRI_SCENARIO_MATRIX.csv` format and statistical markdown summaries.
6. Verification & Self-Testing:
   - Create an automated verification script or pytest test in `evals/capri_comprehensive/tests/` (or run via runner) that executes sample scenarios verifying:
     - YAML schema parsing and validation.
     - Deterministic evaluator assertions.
     - Sandboxing isolation (attempting to access protected paths fails safely).
     - Wilson score CI and bootstrap latency calculation.
   - Run the tests with `python3` or `uv run pytest` and verify passing results.

Output Requirements:
Write your full technical progress and implementation report to:
`/home/cyberdid/Projects/B-12/.agents/teamwork/worker_m2_framework/handoff.md`
When complete, send a message to parent summarizing files created, verification test commands and outputs.
