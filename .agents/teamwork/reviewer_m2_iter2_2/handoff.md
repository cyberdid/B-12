# Handoff Report — Reviewer 2: Milestone M2 (Iteration 2 Gate)

**Author:** Reviewer 2 (`reviewer_m2_iter2_2`)  
**Roles:** Reviewer & Adversarial Critic  
**Target Milestone:** Milestone M2 — Framework & Engine Architecture (Remediation Verification)  
**Working Directory:** `/home/cyberdid/Projects/B-12`  
**State Folder:** `/home/cyberdid/Projects/B-12/.agents/teamwork/reviewer_m2_iter2_2`  
**Parent Agent:** `f7064ab7-5ff4-4a09-bb25-95e84e62ebcd`  
**Date:** 2026-11-10T11:42:30Z  
**Type:** Hard Handoff  
**Verdict:** **APPROVE**

---

## 1. Observation

Direct empirical observations, code inspection, line numbers, and tool execution outputs gathered during the evaluation of `evals/capri_comprehensive/evaluators/sandboxed_env.py` and the test suite:

### 1.1 Sandbox Confinement & Closure of Fallthrough Escape
- **File**: `evals/capri_comprehensive/evaluators/sandboxed_env.py:184–191`
- **Code**:
  ```python
  # If sandbox is active, enforce strict confinement
  if self.sandbox_dir:
      sb_resolved = self.sandbox_dir.resolve()
      if resolved == sb_resolved or sb_resolved in resolved.parents:
          return True
      return False  # Strict reject for any path outside sandbox

  return True
  ```
- **Direct Test Observation**: In the unpatched Iteration 1 implementation, paths outside `sandbox_dir` fell through to `return True`. In this remediated code, when `self.sandbox_dir` is active, any path where `sb_resolved != resolved` and `sb_resolved not in resolved.parents` strictly hits line 189: `return False`.
- **Empirical Execution**:
  ```bash
  uv run python -c '
  from evals.capri_comprehensive.evaluators.sandboxed_env import SandboxedEnvironment, HOST_HOME
  with SandboxedEnvironment("TEST_VERIFY", cleanup=True) as env:
      assert env.is_path_safe("/etc/passwd") is False
      assert env.is_path_safe(str(HOST_HOME / ".bashrc")) is False
      assert env.is_path_safe("/tmp") is False
      assert env.is_path_safe("/root") is False
      assert env.is_path_safe("/bin/sh") is False
  print("Fallthrough escape verified CLOSED.")
  '
  ```
  Output: `Fallthrough escape verified CLOSED.`

### 1.2 Symlink Canonicalization & URL Unquoting
- **File**: `evals/capri_comprehensive/evaluators/sandboxed_env.py:148–174`
- **Code**:
  ```python
  raw_str = str(target_path)
  if "\x00" in raw_str:
      return False

  unquoted = urllib.parse.unquote(raw_str)
  if "\x00" in unquoted:
      return False

  forbidden_host_substrings = [".ssh", ".gnupg", "/etc/shadow", "/etc/sudoers", "/root"]
  for sub in forbidden_host_substrings:
      if sub in unquoted:
          return False

  try:
      p = Path(os.path.expanduser(unquoted)) if unquoted.startswith("~") else Path(unquoted)

      if not p.is_absolute() and self.sandbox_dir:
          target = self.get_workspace_path() / p
      else:
          target = p

      resolved = target.resolve()
  except Exception:
      return False
  ```
- **Direct Test Observation**:
  - Symlinks pointing outside the sandbox (e.g. `workspace / sym_passwd -> /etc/passwd`) resolve to `/etc/passwd`. Because `/etc/passwd` does not have `sandbox_dir.resolve()` in its parent hierarchy, it evaluates to `False`.
  - Chained symlinks, broken symlinks pointing outside, and symlink loops (`a -> b -> a`) are caught and evaluate to `False`.
  - URL-encoded strings (e.g., `%2e%2e%2f%2e%2e%2fetc%2fpasswd`) are unquoted via `urllib.parse.unquote` to `../../etc/passwd` and evaluated against the canonical sandbox boundary, returning `False`.
  - Null bytes (`\x00` and `%00`) in raw and unquoted strings are explicitly blocked before filesystem inspection.

### 1.3 Environment Variable Snapshotting & Restoration
- **File**: `evals/capri_comprehensive/evaluators/sandboxed_env.py:51, 64–66, 104–111`
- **Code**:
  ```python
  # In __init__:
  self._full_prev_env: dict[str, str] = {}

  # In setup():
  self._full_prev_env = dict(os.environ)

  # In teardown():
  if hasattr(self, "_full_prev_env") and self._full_prev_env:
      os.environ.clear()
      os.environ.update(self._full_prev_env)
      self._full_prev_env.clear()
  ```
- **Direct Test Observation**:
  - `dict(os.environ)` captures a full snapshot of the process environment table.
  - In `teardown()`, calling `os.environ.clear()` followed by `os.environ.update(self._full_prev_env)` completely purges any environment variables added during the scenario run and restores modified or deleted keys to their exact prior values.
  - Calling `teardown()` repeatedly is safe and idempotent because `self._full_prev_env.clear()` empties the snapshot after the first restore.

### 1.4 Constructor Support for `cleanup: bool = True`
- **File**: `evals/capri_comprehensive/evaluators/sandboxed_env.py:37–48, 113–124`
- **Code**:
  ```python
  def __init__(
      self,
      scenario_id: str,
      initial_files: dict[str, str] | None = None,
      retain_on_failure: bool = False,
      cleanup: bool = True,
      base_tmp_dir: str | None = None,
  ):
      ...
      self.cleanup = cleanup
  ...
  # In teardown():
  if self.sandbox_dir and self.sandbox_dir.exists():
      if not self.cleanup:
          pass
      elif failed and self.retain_on_failure:
          pass
      else:
          try:
              shutil.rmtree(self.sandbox_dir, ignore_errors=True)
          except Exception:
              pass
  ```
- **Direct Test Observation**: Passing `cleanup=True` (or relying on default `cleanup=True`) deletes `self.sandbox_dir` upon exit. Passing `cleanup=False` retains `self.sandbox_dir` on disk. If an exception occurs and `retain_on_failure=True`, the directory is preserved for post-mortem analysis.

### 1.5 Safe Accessibility of Internal Sandbox Fixtures
- **File**: `evals/capri_comprehensive/evaluators/sandboxed_env.py:75–89, 185–188`
- **Direct Test Observation**:
  - `dummy_home` (`sandbox_dir/home/sandbox_user`), `dummy_state` (`sandbox_dir/state/b12`), and `dummy_secrets` (`dummy_state/secrets`) are created inside `sandbox_dir`.
  - Initial files (e.g. `secrets_mock.json`, `config/test.json`) seeded in `sandbox_dir/workspace` resolve within `sandbox_dir`.
  - `is_path_safe` allows all these internal paths because `sb_resolved in resolved.parents` is `True`.
  - The previous false-positive rejection of internal files containing the substring `"secrets"` has been resolved: host secrets are protected via `PROTECTED_HOST_PATTERNS` and outer boundary checks, while internal sandbox mock secrets are correctly accessible.

### 1.6 Verification Test Suite Execution
- **Command 1**: `uv run pytest evals/capri_comprehensive/tests/test_framework.py -v`
  - Output: `15 passed in 0.18s`
- **Command 2**: `uv run pytest evals/capri_comprehensive/tests/ -v`
  - Output: `39 passed in 0.95s`
- **Command 3**: `uv run ruff check evals/capri_comprehensive/ && uv run ruff format --check evals/capri_comprehensive/`
  - Output: `All checks passed!`, `18 files already formatted`

---

## 2. Logic Chain

1. **Closure of Path Escape (Observation 1.1)**:
   - In Iteration 1, the sandbox evaluator returned `True` for any path that fell through the checks, permitting access to `/etc/passwd` and host configuration files.
   - The remediated implementation introduces lines 185–189: if `self.sandbox_dir` is active, it strictly requires `resolved == sb_resolved or sb_resolved in resolved.parents`. All paths resolving outside return `False`.
   - Because `Path.resolve()` canonicalizes symlinks and normalizes directory traversals, any attempt to access files outside the sandbox returns `False`.
   - Therefore, the fallthrough escape is closed and verified.

2. **Defense Against Symlink and Encoding Attacks (Observation 1.2)**:
   - Adversaries can attempt to bypass path checks using symlinks to host files, URL encoding (`%2e%2e`), or null byte termination (`%00`).
   - Line 149 and 153 reject `\x00` in both raw and decoded strings.
   - Line 152 decodes URL encoding via `urllib.parse.unquote`, normalizing `%2e%2e` into `..`.
   - Line 171 executes `target.resolve()`, which follows symlink chains to their physical destination.
   - If the canonical destination lies outside `sandbox_dir`, line 189 rejects it. If symlinks loop or are broken, line 173 catches the exception and returns `False`.
   - Therefore, symlink canonicalization and URL unquoting defenses are sound and complete.

3. **Process State Isolation (Observation 1.3)**:
   - Test scenarios modify environment variables (`B12_SANDBOX_DIR`, `HOME`, etc.) and may spawn tools that inject keys.
   - By capturing `dict(os.environ)` in `setup()` and performing `os.environ.clear()` followed by `os.environ.update()` in `teardown()`, the environment is restored to its exact initial state on both clean exits and exception exits.
   - Therefore, zero environment pollution or leakage occurs across sequential test scenario runs.

4. **Lifecycle and Fixture Usability (Observations 1.4 & 1.5)**:
   - Scenarios need ephemeral sandboxes by default (`cleanup=True`) and debugging retention when instructed (`cleanup=False` or `retain_on_failure=True`).
   - The constructor signature accepts `cleanup: bool = True`, eliminating previous `TypeError` exceptions.
   - Synthetic mock files and internal directories (`secrets_mock.json`, `state/b12/secrets/`) reside strictly within `sandbox_dir`, ensuring they pass `is_path_safe` without triggering false alarms.
   - Therefore, scenario execution is safe, ergonomic, and fully functional.

5. **Integrity Audit**:
   - We inspected `sandboxed_env.py` and the test files for hardcoded test outputs, dummy implementations, and self-certifying artifacts.
   - `sandboxed_env.py` contains genuine path resolution and confinement logic.
   - Fabricated reports and artifacts in `reports/` and `artifacts/` have been eradicated.
   - All 39 test assertions pass genuinely.

---

## 3. Caveats & Adversarial Challenges

1. **Multithreading Concurrency Hazard in `suite_runner.py`**:
   - `suite_runner.py:103` implements parallel batch execution using `ThreadPoolExecutor(max_workers=max_workers)`.
   - In Python, `os.environ` is process-global across all threads.
   - If scenarios are executed concurrently in multiple threads within the same process, calling `os.environ.clear()` and mutating environment variables inside `SandboxedEnvironment` will cause thread race conditions.
   - *Mitigation / Recommendation*: In Milestone M4, batch execution across scenarios must either run sequentially (`parallel=False`, which is the current safe default) or use `ProcessPoolExecutor` where each worker runs in an isolated process with its own separate `os.environ`.
2. **Inactive Sandbox State**:
   - If a caller instantiates `SandboxedEnvironment` but does not invoke `__enter__` or `setup()`, `self.sandbox_dir` remains `None`. In this inactive state, `is_path_safe` checks only `PROTECTED_HOST_PATTERNS`.
   - All runners in `capri_comprehensive` use context managers (`with SandboxedEnvironment(...) as env:`), which guarantees `setup()` is called before any path evaluation.
3. **Core Repository Separation**:
   - No production code in `src/b12/` was touched. All changes remain confined to `evals/capri_comprehensive/`.

---

## 4. Conclusion

The security boundaries, sandbox isolation, and lifecycle management in `evals/capri_comprehensive/evaluators/sandboxed_env.py` have been remediated with high technical quality:
1. **Fallthrough escape is closed**: Any path outside `sandbox_dir.resolve()` strictly returns `False`.
2. **Symlink canonicalization & URL unquoting**: Confirmed resilient against traversal, symlink escapes, and null-byte injection.
3. **Environment restoration**: Full `dict(os.environ)` snapshot and restoration verified with zero leaks.
4. **Constructor cleanup**: `cleanup: bool = True` supported and verified.
5. **Fixture accessibility**: Internal mock files and secrets remain safely accessible within the sandbox.
6. **Integrity verified**: Zero hardcoded mocks, zero fabricated deliverables, 100% tests passing (`39 passed in 0.95s`).

**Definitive Verdict**: **APPROVE**

---

## 5. Verification Method

To independently reproduce and verify this review:

1. **Run Framework Test Suite**:
   ```bash
   uv run pytest evals/capri_comprehensive/tests/test_framework.py -v
   ```
   *Expected Output*: `15 passed in ~0.2s`

2. **Run Full Evaluation & Stress Test Suite**:
   ```bash
   uv run pytest evals/capri_comprehensive/tests/ -v
   ```
   *Expected Output*: `39 passed in ~1.0s`

3. **Verify Sandbox Boundary Confinement Script**:
   ```bash
   uv run python -c '
   from evals.capri_comprehensive.evaluators.sandboxed_env import SandboxedEnvironment, HOST_HOME
   import os

   with SandboxedEnvironment("VERIFY_AUDIT", cleanup=True) as env:
       # Outer paths must be False
       assert env.is_path_safe("/etc/passwd") is False
       assert env.is_path_safe(str(HOST_HOME / ".bashrc")) is False
       assert env.is_path_safe("%2e%2e%2f%2e%2e%2fetc%2fpasswd") is False

       # Internal paths must be True
       ws = env.get_workspace_path()
       assert env.is_path_safe(ws / "mock_file.txt") is True
       assert env.is_path_safe(env.sandbox_dir / "state" / "b12" / "secrets") is True

   print("Sandbox confinement independently verified: PASS")
   '
   ```
