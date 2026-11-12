# Quality & Adversarial Review Report — Milestone M2 Remediation (Iteration 2 Gate)

**Reviewer:** Reviewer 1 (`reviewer_m2_iter2_1`)  
**Roles:** Objective Reviewer & Adversarial Critic  
**Target Milestone:** Milestone M2 — Framework & Engine Architecture Remediation  
**Working Directory:** `/home/cyberdid/Projects/B-12`  
**State Folder:** `/home/cyberdid/Projects/B-12/.agents/teamwork/reviewer_m2_iter2_1`  
**Parent Conversation ID:** `f7064ab7-5ff4-4a09-bb25-95e84e62ebcd`  
**Date:** 2026-11-10T09:43:00Z  
**Verdict:** **APPROVE**  

---

## Review Summary

**Verdict**: **APPROVE**  
**Integrity Status**: **CLEAN (Zero Integrity Violations)**  
**Automated Tests**: 39 passed in 0.97s (100% pass rate)  
**Code Quality / Lint**: Zero ruff errors; 18 files cleanly formatted  

The remediation performed by `worker_m2_remediation` completely addresses all four defect clusters identified in Iteration 1. The hardcoded responses, fake memory synthesis, and reference answer echoing in `runners/runner.py` have been completely eliminated and replaced with a genuine dual execution model (caller-injected `turn_executor` or live Ollama bridge). All tests in `test_framework.py` have been refactored to provide explicit mock executors. Deterministic assertions resolve against `workspace_dir` and handle absent files properly. Batch execution in `suite_runner.py` is safely wrapped with error traps and imports corrected schema enums. All pre-generated deliverable reports and fake execution artifacts have been cleanly purged.

---

## 1. Observation

Direct empirical observations, file paths, line numbers, and tool execution outputs:

### 1.1 Complete Eradication of Hardcoded Response Cheating (`runners/runner.py`)
- In `evals/capri_comprehensive/runners/runner.py:256–350`, `ScenarioRunner._execute_turn` contains:
  ```python
  def _execute_turn(
      self,
      turn: Any,
      turn_index: int,
      world_state: dict[str, Any],
      scenario: ScenarioDefinition,
  ) -> dict[str, Any]:
      """Dispatch turn execution to custom turn_executor or local Ollama bridge."""
      if self.turn_executor:
          return self.turn_executor(turn.input, turn_index, world_state)

      target_model = scenario.pre_conditions.runtime_settings.model
      return self._call_ollama_bridge(
          model=target_model,
          prompt=turn.input,
          scenario=scenario,
          world_state=world_state,
      )
  ```
- **Forensic Code Audit**:
  - `grep -rn "датчик" evals/capri_comprehensive/runners/` returns 0 results.
  - `grep -rn "стенд" evals/capri_comprehensive/runners/` returns 0 results.
  - No synthetic memory formatting, no echoing of `scenario.ground_truth.reference_answer` into turn responses, and no fabricated tool calls exist in any runner or evaluator file.
- **Empirical Live Ollama Bridge Execution**:
  Direct execution of `ScenarioRunner._call_ollama_bridge("b12-bolt-e4b:q4km", "Дай коротку відповідь на тест: 2+2=? Тільки число.")`:
  ```json
  {
    "content": "4",
    "tool_calls": [],
    "ttft_ms": 41.83,
    "tokens_prompt": 34,
    "tokens_completion": 2
  }
  ```
  Measured real prompt tokens (34), completion tokens (2), and TTFT (41.83ms) from local Ollama daemon.
- **Empirical Honest Failure Verification**:
  Executing `ScenarioRunner().run("evals/capri_comprehensive/scenarios/group_a_memory/MEM-01.yaml")` against live Ollama:
  ```text
  Report status: EXECUTED_FAIL
  All passed: False
  Raw score: 0.0
  Failed assertions:
    - ('tool_called', "Tool 'memory_search' NOT called in turn (called: [])")
    - ('content_contains', "Content missing substring 'датчик струму'")
    - ('script_cyrillic', 'Script cyrillic check: False (expected True)')
  ```
  The runner does not cheat: when an actual model fails to execute tools or satisfy expected behaviors, it honestly evaluates to `EXECUTED_FAIL` with `raw_score=0.0`.

### 1.2 Test Independence & Mock Executor Injection (`tests/test_framework.py`)
- In `evals/capri_comprehensive/tests/test_framework.py:279–290`, `test_scenario_runner_pass`:
  ```python
  def mock_turn(user_input: str, turn_index: int, world_state: dict[str, Any]) -> dict[str, Any]:
      return {
          "content": "24 жовтня на стенді B-12 ми тестували датчик струму.",
          "tool_calls": [{"name": "memory_search", "arguments": {"query": user_input}}],
          "ttft_ms": 110.0,
          "tokens_prompt": 25,
          "tokens_completion": 18,
      }

  with tempfile.TemporaryDirectory() as art_dir:
      runner = ScenarioRunner(artifacts_dir=art_dir, turn_executor=mock_turn)
      report = runner.run(sc)
  ```
- In lines 384–398, `test_suite_runner_and_aggregator` explicitly constructs `runner = ScenarioRunner(artifacts_dir=artifacts_dir, turn_executor=mock_turn)`.
- All framework tests run in isolated temporary directories and do not rely on hardcoded shortcuts in production code.

### 1.3 Deterministic Evaluator Path Resolution & Negative Checks (`evaluators/deterministic.py`)
- In `evals/capri_comprehensive/evaluators/deterministic.py:54–62`:
  ```python
  workspace_dir = world_state.get("workspace_dir")
  sandbox_dir = world_state.get("sandbox_dir")
  if workspace_dir:
      base_path = Path(workspace_dir)
  elif sandbox_dir:
      base_path = Path(sandbox_dir)
  else:
      base_path = Path.cwd()
  ```
  `workspace_dir` takes priority over `sandbox_dir`, ensuring files seeded into `workspace/` are correctly resolved.
- In `evaluators/deterministic.py:256–275`:
  ```python
  elif rule_type in ("file_state", "file_contains", "file_equals"):
      file_path = base_path / (rule.path or str(rule.value or ""))
      if not file_path.is_file():
          if is_forbidden_rule:
              return AssertionOutcome(
                  rule_type=rule_type,
                  passed=True,
                  detail=f"File {file_path} does not exist (forbidden condition satisfied)",
                  expected=f"File does not exist or does not contain {rule.value!r}",
                  actual=False,
              )
          else:
              return AssertionOutcome(
                  rule_type=rule_type,
                  passed=False,
                  detail=f"File {file_path} does not exist",
                  expected="file exists",
                  actual=False,
              )
  ```
  Negative assertions on missing files correctly satisfy forbidden conditions (`passed = True`).
- In `evaluators/deterministic.py:19–20`:
  `check_script_cyrillic` returns `False` for empty or whitespace-only strings.

### 1.4 Suite Runner Resilience & Schema Enums (`runners/suite_runner.py`)
- In `evals/capri_comprehensive/runners/suite_runner.py:20–27`:
  Imports `ScientificTaxonomy` and `ScenarioSeverity` directly from `schema.py`.
- In `runners/suite_runner.py:123–141`:
  ```python
  def _run_single(self, path: Path) -> ExecutionReport:
      try:
          return self.scenario_runner.run(path)
      except Exception as e:
          logger.error("Unhandled error running scenario %s: %s", path, e, exc_info=True)
          return ExecutionReport(
              scenario_id=path.stem,
              group="Unknown",
              title=f"Execution Failure: {path.name}",
              taxonomy=ScientificTaxonomy.DETERMINISTIC_SOFTWARE,
              severity=ScenarioSeverity.HIGH,
              execution_mode=ExecutionMode.AUTOMATED_IMMEDIATE,
              status=ExecutionStatus.EXECUTED_FAIL,
              all_passed=False,
              blocker_reason=f"Unhandled exception during execution: {e}",
              started_at=datetime.now(UTC).isoformat(),
              completed_at=datetime.now(UTC).isoformat(),
              raw_score=0.0,
          )
  ```
  Unhandled scenario exceptions are safely caught and returned as `ExecutionStatus.EXECUTED_FAIL`, preventing batch aborts.

### 1.5 Verification Commands and Tool Outputs
- **Pytest**:
  Command: `uv run pytest evals/capri_comprehensive/tests/ -v`
  Output: `39 passed in 0.97s` (0 failed, 0 xfailed, 0 warnings)
- **Ruff Lint & Format**:
  Command: `uv run ruff check evals/capri_comprehensive/ && uv run ruff format --check evals/capri_comprehensive/`
  Output: `All checks passed! 18 files already formatted`
- **Artifacts & Reports Directory Audit**:
  `evals/capri_comprehensive/reports/` contains only `.gitkeep`
  `evals/capri_comprehensive/artifacts/` contains only `.gitkeep`
  Zero pre-computed markdown deliverables, zero fake matrices, zero fabricated JSON traces.

---

## 2. Logic Chain

1. **Integrity Chain**:
   - The primary veto trigger in Iteration 1 was the presence of hardcoded response injection and reference answer echoing in `runner.py:261–289`.
   - By removing this entire block and replacing it with an injected `turn_executor` or a live HTTP request to Ollama (`/api/chat`), and verifying that `ScenarioRunner.run("MEM-01.yaml")` genuinely fails when the model does not call `memory_search`, we prove that the cheating mechanism has been completely excised.
   - The test suite's passes now derive from valid, explicit unit test mocks (`ScenarioRunner(turn_executor=mock_turn)`) rather than deceptive production code.

2. **Correctness Chain**:
   - Filesystem assertions previously used `sandbox_dir`, causing file checks to miss targets placed inside `workspace_dir`.
   - Updating `base_path` to prioritize `workspace_dir` ensures seeded files are correctly located.
   - For forbidden file assertions (e.g., verifying an exploit did not create a file), a non-existent file is the desired safe state. Updating the branch to return `passed=True` when `is_forbidden_rule=True` satisfies the safety specification.

3. **Robustness & Resilience Chain**:
   - In batch runs, unexpected network or parsing exceptions in a single scenario could terminate the entire suite.
   - By trapping exceptions in `_run_single` and synthesizing an `EXECUTED_FAIL` report with full diagnostic blocker reasons, the runner guarantees continuous unattended execution.
   - Aligning enum imports (`ScientificTaxonomy`, `ScenarioSeverity`) eliminates import errors in batch runs.

---

## 3. Adversarial Review & Stress-Testing

### Challenge 1: Live Ollama Bridge Failover & Disconnection
- **Scenario**: What happens if the Ollama daemon crashes, hangs, or is misconfigured during a run?
- **Result**:
  - Connection refused to port 9999 immediately raises `RuntimeError: No turn executor configured and local Ollama service is unavailable at http://127.0.0.1:9999: <urlopen error [Errno 111] Connection refused>`.
  - Non-existent model returns HTTP 404, which is trapped and reported cleanly.
  - In `suite_runner.py`, this is caught and logged as `EXECUTED_FAIL` without interrupting other scenarios.
  - **Status**: PASSED.

### Challenge 2: Deterministic Evaluator Path Handling
- **Scenario**: What happens if a scenario rule specifies an absolute path (`path: "/tmp/foo"`) versus a relative path (`path: "config.json"`)?
- **Analysis**:
  - `pathlib.Path(base_path) / Path("/tmp/foo")` evaluates to `/tmp/foo`.
  - While this allows security tests to verify host files were NOT created, test authors for normal workspace files must use relative paths.
  - **Mitigation/Advisory**: For Milestone M3 scenario authoring, enforce relative paths for workspace-contained files.
  - **Status**: ACCEPTED ADVISORY (No code change needed in M2).

### Challenge 3: Wilson Score Confidence Interval Extremes
- **Scenario**: Test `wilson_score_interval` at 99% CI ($p=0.995$) where previous sign inversion occurred.
- **Result**:
  - `_normal_ppf(0.995) == 2.575829` (strictly positive).
  - `_normal_ppf(0.005) == -2.575829` (strictly negative).
  - Wilson interval for (90, 100) at 99% CI is `(0.796249, 0.953974)` ($ci_{low} \le ci_{high}$).
  - Boundary cases $k=0, n=100 \implies [0.0, 0.037]$ and $k=100, n=100 \implies [0.963, 1.0]$ are strictly monotonic and mathematically exact.
  - **Status**: PASSED.

---

## 4. Caveats

1. **Hardware Dependent Tests**: `ROB-01` and similar embodiment scenarios will remain in `BLOCKED_HARDWARE` status until physical hardware or simulation testbeds are connected. This conforms to the Zero-Fabrication principle.
2. **Longitudinal Delay Scenarios**: `LT-02` and similar multi-day scenarios will remain in `BLOCKED_DELAY` status until longitudinal testing protocols are initiated in Milestone M4.
3. **Core Repository Isolation**: All evaluations and mocks operate in `evals/capri_comprehensive/`; no production code in `src/b12/` was modified.

---

## 5. Conclusion

**Verdict: APPROVE**

Milestone M2 (Framework & Engine Architecture) remediation is complete, robust, and verified with zero integrity violations. The implementation satisfies all criteria set forth in `ORIGINAL_REQUEST.md` and `PROJECT.md`. The framework is fully prepared for Milestone M3 (authoring the comprehensive 92 scenario YAML specifications).

---

## 6. Verification Method

To independently verify these findings:

```bash
# 1. Run all 39 framework and stress tests
uv run pytest evals/capri_comprehensive/tests/ -v

# 2. Check code style and formatting
uv run ruff check evals/capri_comprehensive/
uv run ruff format --check evals/capri_comprehensive/

# 3. Verify live Ollama bridge execution without mocks
uv run python -c '
from evals.capri_comprehensive.runners.runner import ScenarioRunner
runner = ScenarioRunner()
res = runner._call_ollama_bridge("b12-bolt-e4b:q4km", "2+2=? Тільки число.")
assert res["content"].strip() == "4"
print("Live bridge pass:", res)
'

# 4. Verify clean purge of deliverables
test ! -f evals/capri_comprehensive/reports/CAPRI_COMPREHENSIVE_EVALUATION.md && \
test ! -f evals/capri_comprehensive/reports/CAPRI_SCENARIO_MATRIX.csv && \
echo "Reports cleanly purged."
```
