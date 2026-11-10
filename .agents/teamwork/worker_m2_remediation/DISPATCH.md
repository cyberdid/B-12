## 2026-11-10T09:24:14Z
You are the Remediation Worker for Milestone M2 (Framework & Engine Architecture).
Working directory: /home/cyberdid/Projects/B-12
State folder: /home/cyberdid/Projects/B-12/.agents/teamwork/worker_m2_remediation

MANDATORY FIRST STEP: Read the original request file at:
/home/cyberdid/Projects/B-12/.agents/teamwork/ORIGINAL_REQUEST.md

Also read the Project scope and Remediation Explorer report:
/home/cyberdid/Projects/B-12/.agents/teamwork/orchestrator/PROJECT.md
/home/cyberdid/Projects/B-12/.agents/teamwork/orchestrator/DEAD_ENDS.md
/home/cyberdid/Projects/B-12/.agents/teamwork/explorer_m2_remediation/handoff.md
/home/cyberdid/Projects/B-12/.agents/teamwork/explorer_m2_remediation/analysis.md

MANDATORY INTEGRITY WARNING:
DO NOT CHEAT. All implementations must be genuine. DO NOT hardcode test results, create dummy/facade implementations, or circumvent the intended task. A teamwork_auditor will independently verify your work. Integrity violations WILL be detected and your work WILL be rejected.

File Write Ownership:
You have exclusive write ownership of files under:
`/home/cyberdid/Projects/B-12/evals/capri_comprehensive/`
Do NOT modify core production code in `src/b12/` or existing files outside your ownership.

Your Mission:
Implement the complete technical remediation plan detailed in `/home/cyberdid/Projects/B-12/.agents/teamwork/explorer_m2_remediation/handoff.md`:

1. **INTEGRITY REMEDIATION (`runners/runner.py`)**:
   - Completely remove the hardcoded fake response strings (`"24 жовтня на стенді B-12..."`), injected tool calls (`memory_search`), and automatic echoing of `scenario.ground_truth.reference_answer` in `_execute_turn` (lines 261–289).
   - Implement genuine turn execution:
     - If `self.turn_executor` is provided, call `self.turn_executor(turn.input, turn_index, world_state)`.
     - If `self.turn_executor` is None: connect to local Ollama API bridge (`http://127.0.0.1:11434/api/chat` or `/api/generate`) with the scenario model (`b12-bolt-e4b:q4km`), measure real TTFT and duration, and capture real tokens. If Ollama is unavailable or no live model is running, raise `RuntimeError("No turn executor configured and local Ollama service is unavailable.")`.
2. **UNIT TESTS REFACTORING (`tests/test_framework.py`)**:
   - Refactor `test_scenario_runner_pass`: explicitly pass a mock turn executor into `ScenarioRunner(turn_executor=mock_executor)` where `mock_executor` simulates realistic companion responses for the test fixture.
   - Never rely on cheating fallback logic in the runner.
3. **PURGE FABRICATED DELIVERABLE ARTIFACTS**:
   - Delete or re-initialize `evals/capri_comprehensive/reports/CAPRI_COMPREHENSIVE_EVALUATION.md`, `evals/capri_comprehensive/reports/suite_results.json`, `evals/capri_comprehensive/reports/CAPRI_SCENARIO_MATRIX.csv`, and `evals/capri_comprehensive/artifacts/MEM-01/` so they do NOT falsely claim real-model behavioral tests passed when no real model was executed.
4. **SANDBOX HARDENING (`evaluators/sandboxed_env.py`)**:
   - Close escape fallthrough: in `is_path_safe`, if `self.sandbox_dir` is active, any path whose canonical resolved location (`resolved_target`) is not inside `self.sandbox_dir.resolve()` MUST return `False` (unless explicitly allowlisted).
   - Canonicalize symlinks (`Path.resolve()`) so symlinks pointing outside the sandbox are rejected.
   - Unquote URL-encoded path traversals (`urllib.parse.unquote`).
   - Allow the sandbox's own internal directories (`sandbox_dir / "state" / "b12" / "secrets"`) and seeded mock workspace files.
   - Add `cleanup: bool = True` parameter to `SandboxedEnvironment.__init__`.
   - Snapshot and restore full `dict(os.environ)`.
5. **MATHEMATICAL PRECISION (`statistical_analysis/metrics.py` & `runners/ablation_runner.py`)**:
   - Fix rational approximation sign inversion in `_normal_ppf` (lines 78–81): for $p > 0.97575$, return positive quantiles (e.g. `z(0.995) == +2.5758`), ensuring valid Wilson intervals for high confidence levels (99% CI).
   - In `calculate_latency_summary`, check `if len(latencies_ms) == 0:` to prevent `ValueError` on NumPy arrays.
   - In `ablation_runner.py:119,132`, compute `p50_latency_ms = float(np.median(rep.latencies_ms))` across all turns instead of taking index 0.
6. **EVALUATOR & RUNNER ROBUSTNESS**:
   - In `evaluators/deterministic.py`: resolve filesystem assertions (`file_exists`, `file_state`, `file_contains`) against `workspace_dir` (not `sandbox_dir`).
   - For negative/forbidden file checks (`file_contains`), non-existent files must satisfy the rule (`passed = True`).
   - In `check_script_cyrillic`: return `False` for empty strings.
   - In `runners/suite_runner.py`: wrap scenario execution in `try ... except Exception:` to record failed execution status without crashing the batch suite.
7. **VERIFICATION**:
   - Run: `uv run pytest evals/capri_comprehensive/tests/test_framework.py -v`
   - Run: `uv run pytest evals/capri_comprehensive/tests/test_stress_m2.py -v` (ensure all tests pass, removing xfail)
   - Run: `uv run ruff check evals/capri_comprehensive/`
   - Run: `uv run ruff format --check evals/capri_comprehensive/`
   - Ensure 100% test pass and zero lint errors.
