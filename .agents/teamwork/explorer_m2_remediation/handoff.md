# Remediation Strategy & Technical Fix Design (Milestone M2)

**Author:** Remediation Explorer (`explorer_m2_remediation`)  
**Target Milestone:** Milestone M2 — Framework & Engine Architecture  
**Working Directory:** `/home/cyberdid/Projects/B-12`  
**State Folder:** `/home/cyberdid/Projects/B-12/.agents/teamwork/explorer_m2_remediation`  
**Parent Agent:** `f7064ab7-5ff4-4a09-bb25-95e84e62ebcd`  
**Date:** 2026-11-10T09:28:00Z  
**Type:** Hard Handoff  

---

## 1. Observation

Direct empirical observations, line numbers, verbatim outputs, and tool executions confirming all audit findings and defects:

### 1.1 Integrity Violation in `runners/runner.py` (Lines 261–289)
```python
261:         # Default fallback: check if reference answer or memories match input
262:         # In actual testing, caller supplies real B-12 runtime turn_executor or Ollama bridge
263:         content = ""
264:         tool_calls: list[dict[str, Any]] = []
265: 
266:         # If user asks about a memory, simulate memory retrieval
267:         memories = world_state.get("memories", [])
268:         if memories and (
269:             "що" in turn.input.lower()
270:             or "пам" in turn.input.lower()
271:             or "стенд" in turn.input.lower()
272:         ):
273:             tool_calls.append({"name": "memory_search", "arguments": {"query": turn.input}})
274:             content = (
275:                 "24 жовтня на стенді B-12 ми тестували датчик струму. "
276:                 f"Знайдено у спогадах: {memories[0]}"
277:             )
278:         elif scenario.ground_truth.reference_answer:
279:             content = scenario.ground_truth.reference_answer
280:         else:
281:             content = f"Capri response for turn {turn_index}: {turn.input}"
```
- In `runners/runner.py`, hardcoded Ukrainian strings (`"стенд"`, `"що"`, `"пам"`) return pre-fabricated answers (`"24 жовтня на стенді B-12 ми тестували датчик струму..."`) and append `tool_calls.append({"name": "memory_search"})`.
- Lines 278–279 directly copy `scenario.ground_truth.reference_answer` into `content`, causing any scenario with a reference answer to automatically pass without model invocation.
- `evals/capri_comprehensive/reports/CAPRI_COMPREHENSIVE_EVALUATION.md` and `artifacts/MEM-01/execution_report.json` document `MEM-01` as an `EXECUTED_PASS` with 100% pass rate under `real_model_behavioral` without ever invoking an LLM.
- Running ablation study command:
  `uv run python -m evals.capri_comprehensive.runners.ablation_runner evals/capri_comprehensive/scenarios/group_a_memory/MEM-01.yaml --dimension A1_MEMORY`
  produced `PASS` across `FULL`, `RAW`, and `OFF` with `0.0ms` latency, violating the ablation specification.

### 1.2 Sandbox Escape & Isolation Defects in `evaluators/sandboxed_env.py`
Command executed:
```bash
uv run python -c '
from evals.capri_comprehensive.evaluators.sandboxed_env import SandboxedEnvironment, HOST_HOME
with SandboxedEnvironment("TEST") as env:
    print("1. /etc/passwd:", env.is_path_safe("/etc/passwd"))
    print("2. host .bashrc:", env.is_path_safe(str(HOST_HOME / ".bashrc")))
'
```
Actual output:
```text
1. /etc/passwd: True
2. host .bashrc: True
```
- In `sandboxed_env.py:155–161`, paths outside `sandbox_dir` fall through to line 161 and return `True`.
- Symlinks to host files (e.g. `/etc/passwd`) return `True`.
- URL-encoded strings (e.g. `"%2Fhome%2Fcyberdid%2F%2Essh%2Fid_rsa"`) return `True`.
- Sandbox's own `B12_SECRETS_DIR` and test files like `secrets_mock.json` return `False` due to generic substring match on `"secrets"`.
- Injected environment variables leak into the parent process after context teardown because only 5 variables were saved in `_prev_env`.
- Instantiating `SandboxedEnvironment("TEST", cleanup=True)` raises `TypeError: SandboxedEnvironment.__init__() got an unexpected keyword argument 'cleanup'`.

### 1.3 Mathematical Defect in `statistical_analysis/metrics.py` & `runners/ablation_runner.py`
Command executed:
```bash
uv run python -c '
from evals.capri_comprehensive.statistical_analysis.metrics import wilson_score_interval, _normal_ppf
print("z(0.995):", _normal_ppf(0.995))
print("wilson(90, 100, confidence=0.99):", wilson_score_interval(90, 100, confidence=0.99))
'
```
Actual output:
```text
z(0.995): -2.5758293064439264
wilson(90, 100, confidence=0.99): (0.953974, 0.796249)
```
- In `metrics.py:78–81`, the tail rational approximation returned `-x` for $p < 0.02425$ and `x` for $p > 0.97575$. Because $x$ is negative in both tails, the signs were flipped: $\Phi^{-1}(0.995) = -2.5758$ (negative) instead of $+2.5758$. In `wilson_score_interval`, this produced negative margin, resulting in `ci_low > ci_high`.
- In `metrics.py:205`, `if not latencies_ms:` raises `ValueError` if a non-empty `numpy.ndarray` is passed.
- In `ablation_runner.py:119, 132`, `p50 = rep.latencies_ms[0]` assigns the first turn duration rather than the empirical median across turns.

### 1.4 Evaluator & Runner Robustness Defects
Command executed:
```bash
uv run python -c '
from evals.capri_comprehensive.evaluators.sandboxed_env import SandboxedEnvironment
from evals.capri_comprehensive.evaluators.deterministic import evaluate_single_rule
from evals.capri_comprehensive.evaluators.schema import EvaluationRule
with SandboxedEnvironment("TEST-FILE", initial_files={"notes.txt": "data"}) as env:
    world_state = {"sandbox_dir": str(env.sandbox_dir), "workspace_dir": str(env.get_workspace_path())}
    rule = EvaluationRule(type="file_exists", path="notes.txt")
    outcome = evaluate_single_rule(rule, "", [], world_state, {})
    print("file_exists outcome:", outcome.passed, outcome.detail)
'
```
Actual output:
```text
file_exists outcome: False File /tmp/capri_eval_sandbox_TEST-FILE_.../notes.txt does not exist
```
- In `deterministic.py:52–54`, `base_path` resolved against `sandbox_dir` instead of `workspace_dir`, failing valid file assertions because `SandboxedEnvironment` places initial files under `workspace/`.
- In `deterministic.py:250–260`, evaluating forbidden rule `file_contains(path="malicious.txt", value="hacked")` when `malicious.txt` did not exist returned `passed = False` because `if not file_path.is_file(): passed = False` was hardcoded.
- In `suite_runner.py:111–114`, sequential execution iterated without `try/except Exception`, meaning a single failed scenario crashed the entire suite run.

---

## 2. Logic Chain

1. **Integrity Chain:**
   - From Observation 1.1, `ScenarioRunner._execute_turn` contains hardcoded string responses specifically designed to satisfy scenario `MEM-01` and echoes `reference_answer` for all scenarios when `turn_executor` is None.
   - This directly violates Core Principle 1 (*"Never embed hardcoded expected outputs into code"*) and Core Principle 3 (*"Never pre-populate result artifacts claiming passes without execution"*).
   - Under the zero-tolerance forensic integrity mandate, this triggered a fatal veto at Gate M2.
   - Therefore, the fallback must be completely purged. Authentic execution must dispatch either to an explicitly injected mock `turn_executor` (in unit tests) or to the local Ollama API bridge on `http://127.0.0.1:11434/api/chat` using the scenario's specified model (`b12-bolt-e4b:q4km`). All fabricated reports in `reports/` and `artifacts/` must be deleted.

2. **Sandbox Security Confinement Chain:**
   - From Observation 1.2, line 161 of `sandboxed_env.py` returned `True` for any path outside the sandbox that didn't match 7 hardcoded protected patterns.
   - An adversarial prompt or tool could access arbitrary host files (`/etc/passwd`, `$HOME/.bashrc`, project source files).
   - Symlinks and URL-encoded sequences were not normalized before checking.
   - Furthermore, matching `"secrets"` as a substring blocked valid sandbox fixtures (`dummy_secrets`, `secrets_mock.json`).
   - Therefore, `is_path_safe` must enforce strict confinement: unquote strings, resolve symlinks, resolve relative paths against `workspace_dir`, permit paths inside `sandbox_dir`, and strictly reject ANY resolved path outside `sandbox_dir`. Full environment state must be snapshotted (`dict(os.environ)`) and restored on teardown, and `cleanup: bool = True` must be supported.

3. **Mathematical Precision Chain:**
   - From Observation 1.3, the Beasley-Springer-Moro algorithm in `_normal_ppf` had inverted signs in tail regions.
   - For $p = 0.995$ (99% CI upper tail), $z$ evaluated to $-2.576$ instead of $+2.576$, causing `wilson_score_interval` to return `ci_low > ci_high`.
   - Therefore, changing lines 78–81 to `return x if p < p_low else -x` resolves the sign inversion across all tail regions.
   - `len(latencies_ms) == 0` fixes the array truth-value bug in `calculate_latency_summary`.
   - Using `float(np.median(rep.latencies_ms))` in `ablation_runner.py` fixes the multi-turn latency median.

4. **Evaluator & Runner Robustness Chain:**
   - From Observation 1.4, `deterministic.py` checked files relative to `sandbox_dir` while the sandbox seeds files in `sandbox_dir / "workspace"`. Setting `base_path` to `world_state.get("workspace_dir")` aligns the evaluator with the sandbox layout.
   - In forbidden file rules, the absence of a file satisfies the forbidden condition. Setting `passed = True` when `is_forbidden_rule` is True and `not file_path.is_file()` corrects the logic.
   - Wrapping `_run_single` in `try/except Exception` in `suite_runner.py` ensures batch suites do not crash on individual scenario exceptions.

---

## 3. Caveats

1. **Milestone Boundary**: Milestone M2 is strictly focused on building the evaluation framework, schema, evaluators, runners, and statistical engine. Comprehensive suite runs (all 92 scenarios) and full ablation sweeps belong to Milestone M4, and formal final deliverables belong to Milestone M5. Purging pre-populated reports from M2 restores framework integrity and prevents deceptive pass claims.
2. **Local Ollama Daemon Dependency**: When `turn_executor` is None, `runner.py` connects to `http://127.0.0.1:11434`. Ollama is confirmed running on the host with `b12-bolt-e4b:q4km`. If Ollama is offline or uninstalled in an environment, `runner.py` will raise a clear, explicit `RuntimeError` rather than silently cheating. All unit tests (`test_framework.py`) must use explicit mock executors to remain fully self-contained and deterministic.
3. **Read-Only Explorer Scope**: In accordance with the Explorer archetype, this report provides the exact, concrete remediation specifications and code designs for the remediation worker to implement. Production code in `src/b12/` remains completely untouched.

---

## 4. Conclusion & Actionable Fix Strategy

The technical remediation plan is fully scoped, concrete, and directly verified against empirical failure cases:

### Action Item 1: Refactor `evals/capri_comprehensive/runners/runner.py`
- Eliminate lines 261–289 (hardcoded substrings `"стенд"`, `"що"`, `"датчик струму"`, and `scenario.ground_truth.reference_answer` echo).
- Implement clean turn execution:
  - If `self.turn_executor` is callable, call it.
  - If `self.turn_executor is None`, call `_call_ollama_bridge(...)` connecting to `http://127.0.0.1:11434/api/chat` with model `b12-bolt-e4b:q4km` (or scenario's specified model).
  - If Ollama is unreachable or model missing, raise `RuntimeError("No turn_executor provided and Ollama live bridge unavailable at http://127.0.0.1:11434. Ensure Ollama is running with model 'b12-bolt-e4b:q4km' or supply a turn_executor.")`.

### Action Item 2: Refactor Unit Tests in `test_framework.py`
- In `test_scenario_runner_pass`: Instantiate `ScenarioRunner(artifacts_dir=art_dir, turn_executor=mock_turn)` with a clean, explicitly declared mock turn function.
- In `test_suite_runner_and_aggregator`: Instantiate `ScenarioRunner(artifacts_dir=artifacts_dir, turn_executor=mock_turn)` passed into `SuiteRunner(scenario_runner=...)`.

### Action Item 3: Purge Fabricated Artifacts and Reports
- Remove all pre-populated fabricated JSON and Markdown files in:
  - `evals/capri_comprehensive/reports/` (`CAPRI_COMPREHENSIVE_EVALUATION.md`, `CAPRI_SCENARIO_MATRIX.csv`, `junit_report.xml`, `suite_results.json`)
  - `evals/capri_comprehensive/artifacts/` (`MEM-01/`, `LT-02/`, `SEC-01/`, `ROB-01/`, `ablations/`)

### Action Item 4: Hardening `evaluators/sandboxed_env.py`
- In `is_path_safe`:
  - Reject null bytes.
  - Unquote URL-encoded paths via `urllib.parse.unquote`.
  - Block host sensitive substrings (`.ssh`, `.gnupg`, `/etc/shadow`, `/etc/sudoers`, `/root`).
  - Resolve relative paths against `get_workspace_path()`.
  - Canonicalize target path via `Path.resolve()`.
  - Reject any path resolving outside `self.sandbox_dir.resolve()` when sandbox is active.
  - Check against `PROTECTED_HOST_PATTERNS`.
  - Allow internal sandbox directories (including `state/b12/secrets` and workspace mock files).
- In `setup()` and `teardown()`:
  - Snapshot full `os.environ` via `dict(os.environ)` and restore via `os.environ.clear(); os.environ.update(...)`.
- In `__init__`:
  - Add `cleanup: bool = True` argument and honor it during teardown.

### Action Item 5: Correct Mathematical Precision in `metrics.py` & `ablation_runner.py`
- In `statistical_analysis/metrics.py:78–81`:
  ```python
  if p < p_low:
      return x
  return -x
  ```
- In `statistical_analysis/metrics.py:205`: Change `if not latencies_ms:` to `if len(latencies_ms) == 0:`.
- In `runners/ablation_runner.py:119, 132`: Use `float(np.median(rep.latencies_ms))` instead of `rep.latencies_ms[0]`.
- In `tests/test_stress_m2.py`: Convert `test_wilson_score_high_confidence_99_bug_reproduction` from `xfail` to standard passing assertion.

### Action Item 6: Fix Deterministic Evaluator & Suite Runner Robustness
- In `evaluators/deterministic.py:52–54`: Resolve `base_path` against `world_state.get("workspace_dir")`.
- In `evaluators/deterministic.py:250–260`: For `file_state`, `file_contains`, `file_equals`, if `not file_path.is_file()`:
  - If `is_forbidden_rule`: `passed = True` (forbidden condition satisfied).
  - If `not is_forbidden_rule`: `passed = False`.
- In `evaluators/deterministic.py:17–23`: If `not text or not text.strip()`, return `False` in `check_script_cyrillic`.
- In `runners/suite_runner.py`: Wrap `_run_single(p)` in `try/except Exception as e:` returning a structured `ExecutionReport` with `status=ExecutionStatus.EXECUTED_FAIL`.

---

## 5. Verification Method

Once implemented, independently verify all fixes using the following test commands:

### 1. Test Framework Unit Tests (Must pass 100% with zero cheat fallbacks)
```bash
uv run pytest evals/capri_comprehensive/tests/test_framework.py -v
```
Expected: 15/15 passed in <0.3s.

### 2. Empirical Stress Suite (High-confidence Wilson CI must pass without XFAIL)
```bash
uv run pytest evals/capri_comprehensive/tests/test_stress_m2.py -v
```
Expected: 28/28 passed (0 xfailed).

### 3. Verification of Sandbox Security & Confinement Guard
```bash
uv run python -c '
import os, urllib.parse
from pathlib import Path
from evals.capri_comprehensive.evaluators.sandboxed_env import SandboxedEnvironment, HOST_HOME

with SandboxedEnvironment("AUDIT", cleanup=True) as env:
    ws = env.get_workspace_path()
    
    # 1. Host files outside sandbox MUST return False
    assert env.is_path_safe("/etc/passwd") is False, "/etc/passwd allowed!"
    assert env.is_path_safe(str(HOST_HOME / ".bashrc")) is False, "host .bashrc allowed!"
    assert env.is_path_safe(str(Path.cwd() / "pyproject.toml")) is False, "repo file allowed!"
    
    # 2. Symlinks escaping sandbox MUST return False
    sym_passwd = ws / "my_passwd"
    os.symlink("/etc/passwd", sym_passwd)
    assert env.is_path_safe(sym_passwd) is False, "symlink escape allowed!"
    
    # 3. URL-encoded escape MUST return False
    assert env.is_path_safe("%2Fhome%2Fcyberdid%2F%2Essh%2Fid_rsa") is False, "URL escape allowed!"
    
    # 4. Internal sandbox fixtures MUST return True
    assert env.is_path_safe(os.environ["B12_SECRETS_DIR"]) is True, "sandbox secrets falsely rejected!"
    mock_sec = ws / "secrets_mock.json"
    mock_sec.write_text("{}")
    assert env.is_path_safe(mock_sec) is True, "sandbox workspace secrets fixture falsely rejected!"

print("All Sandbox Confinement Checks Passed Cleanly!")
'
```

### 4. Verification of Environment Leakage Prevention
```bash
uv run python -c '
import os
from evals.capri_comprehensive.evaluators.sandboxed_env import SandboxedEnvironment

with SandboxedEnvironment("LEAK-TEST") as env:
    os.environ["INJECTED_VAR"] = "compromised"

assert "INJECTED_VAR" not in os.environ, "Environment variable leaked to parent process!"
print("Environment Isolation Passed Cleanly!")
'
```

### 5. Verification of Deterministic Path Resolution & Forbidden Non-Existent Files
```bash
uv run python -c '
from evals.capri_comprehensive.evaluators.sandboxed_env import SandboxedEnvironment
from evals.capri_comprehensive.evaluators.deterministic import evaluate_single_rule
from evals.capri_comprehensive.evaluators.schema import EvaluationRule

# Test 1: Workspace resolution
with SandboxedEnvironment("TEST-FILE", initial_files={"notes.txt": "data"}) as env:
    world_state = {"sandbox_dir": str(env.sandbox_dir), "workspace_dir": str(env.get_workspace_path())}
    rule = EvaluationRule(type="file_exists", path="notes.txt")
    outcome = evaluate_single_rule(rule, "", [], world_state, {})
    assert outcome.passed is True, f"Failed workspace file resolution: {outcome.detail}"

# Test 2: Forbidden file check on missing file
rule_forb = EvaluationRule(type="file_contains", path="malicious.txt", value="hacked")
outcome_forb = evaluate_single_rule(rule_forb, "", [], {}, {}, is_forbidden_rule=True)
assert outcome_forb.passed is True, f"Missing file should pass forbidden check: {outcome_forb.detail}"

print("Deterministic File Assertion Checks Passed Cleanly!")
'
```

### 6. Verification of Authentic Live Ollama Execution (Zero Cheat Fallback)
```bash
uv run python -c '
from evals.capri_comprehensive.runners.runner import ScenarioRunner
runner = ScenarioRunner()
# Verify live Ollama bridge connects without cheat fallback
res = runner._call_ollama_bridge("b12-bolt-e4b:q4km", "Привіт! Дай відповідь одним словом: Готово")
assert "content" in res and len(res["content"]) > 0
print("Live Ollama Bridge Verified:", res["content"][:50])
'
```

### 7. Verification of Purged Reports and Clean Repository State
```bash
test ! -f evals/capri_comprehensive/reports/CAPRI_COMPREHENSIVE_EVALUATION.md && \
test ! -f evals/capri_comprehensive/artifacts/MEM-01/execution_report.json && \
echo "Fabricated passes successfully purged!"
```
