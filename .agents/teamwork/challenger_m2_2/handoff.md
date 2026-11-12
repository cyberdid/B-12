# Empirical Challenge Handoff Report: Sandbox Isolation & Path Security Guards

**Agent:** Challenger 2 (Empirical Security & Adversarial Challenger)  
**Milestone:** Milestone M2: Framework & Engine Architecture  
**Working Directory:** `/home/cyberdid/Projects/B-12`  
**State Folder:** `/home/cyberdid/Projects/B-12/.agents/teamwork/challenger_m2_2/`  
**Parent Agent:** `f7064ab7-5ff4-4a09-bb25-95e84e62ebcd`  
**Target Code Under Review:** `evals/capri_comprehensive/evaluators/sandboxed_env.py`  
**Timestamp:** 2026-11-10T09:15:00Z  
**Verdict:** **REQUEST_CHANGES**  

---

## 1. Observation

Direct empirical observations, verbatim commands, line numbers, and tool execution outputs:

### 1.1 Source Code Inspection (`evals/capri_comprehensive/evaluators/sandboxed_env.py`)
- **Lines 133–139**: Substring blacklist check:
  ```python
  forbidden_substrings = [".ssh", ".gnupg", "secrets", "/etc/shadow", "/etc/sudoers", "/root"]
  for sub in forbidden_substrings:
      if sub in raw_str:
          return False
  ```
- **Lines 140–153**: Path resolution and blacklist against 7 hardcoded `PROTECTED_HOST_PATTERNS`:
  ```python
  PROTECTED_HOST_PATTERNS = [
      HOST_HOME / ".ssh",
      HOST_HOME / ".gnupg",
      HOST_HOME / ".local" / "state" / "b12" / "secrets",
      HOST_HOME / ".bash_history",
      Path("/etc/shadow"),
      Path("/etc/sudoers"),
      Path("/root"),
  ]
  ```
- **Lines 155–161**: Containment logic:
  ```python
  # If sandbox is active, ensure we don't escape outside sandbox
  if self.sandbox_dir:
      sb_resolved = self.sandbox_dir.resolve()
      if resolved == sb_resolved or sb_resolved in resolved.parents:
          return True

  return True
  ```
- **Lines 84–108**: Environment variable handling snapshots only 5 keys: `B12_SANDBOX_DIR`, `B12_STATE_DIR`, `B12_SECRETS_DIR`, `B12_WORKSPACE_DIR`, `HOME`.
- **Lines 36–49**: Constructor accepts only `scenario_id`, `initial_files`, `retain_on_failure`, `base_tmp_dir`. Does NOT accept `cleanup`.

---

### 1.2 Verbatim Empirical Test Results (Automated Audit Harness)

Command executed:
```bash
uv run python -c '
import os, shutil, urllib.parse
from pathlib import Path
from evals.capri_comprehensive.evaluators.sandboxed_env import SandboxedEnvironment, HOST_HOME

with SandboxedEnvironment("AUDIT") as env:
    ws = env.get_workspace_path()
    
    # 1. Host files outside sandbox
    print("1. /etc/passwd:", env.is_path_safe("/etc/passwd"))
    print("2. host .bashrc:", env.is_path_safe(str(HOST_HOME / ".bashrc")))
    print("3. repo file:", env.is_path_safe(str(Path.cwd() / "pyproject.toml")))
    
    # 2. Symlinks
    sym_home = ws / "host_home"
    os.symlink(str(HOST_HOME), sym_home)
    print("4. symlink to host home:", env.is_path_safe(sym_home))
    
    sym_passwd = ws / "my_passwd"
    os.symlink("/etc/passwd", sym_passwd)
    print("5. symlink to /etc/passwd:", env.is_path_safe(sym_passwd))
    
    # 3. URL-encoded payload
    print("6. %2Fhome%2Fcyberdid%2F%2Essh%2Fid_rsa:", env.is_path_safe("%2Fhome%2Fcyberdid%2F%2Essh%2Fid_rsa"))
    
    # 4. False positives on safe sandbox paths
    sb_sec = os.environ.get("B12_SECRETS_DIR")
    print("7. sandbox own B12_SECRETS_DIR:", env.is_path_safe(sb_sec))
    mock_sec = ws / "secrets_mock.json"
    mock_sec.write_text("{}")
    print("8. sandbox workspace fixture with secrets in name:", env.is_path_safe(mock_sec))
'
```

Output:
```text
1. /etc/passwd: True
2. host .bashrc: True
3. repo file: True
4. symlink to host home: True
5. symlink to /etc/passwd: True
6. %2Fhome%2Fcyberdid%2F%2Essh%2Fid_rsa: True
7. sandbox own B12_SECRETS_DIR: False
8. sandbox workspace fixture with secrets in name: False
```

---

### 1.3 Verbatim Empirical Results: Environment Variable Leakage

Command executed:
```bash
uv run python -c '
import os
from evals.capri_comprehensive.evaluators.sandboxed_env import SandboxedEnvironment

with SandboxedEnvironment("LEAK-TEST") as env:
    os.environ["INJECTED_VAR"] = "compromised"

print("INJECTED_VAR after teardown:", os.environ.get("INJECTED_VAR"))
'
```

Output:
```text
INJECTED_VAR after teardown: compromised
```

---

### 1.4 Verbatim Empirical Results: `cleanup=True` Parameter Support

Command executed:
```bash
uv run python -c '
from evals.capri_comprehensive.evaluators.sandboxed_env import SandboxedEnvironment
try:
    env = SandboxedEnvironment("TEST", cleanup=True)
except TypeError as e:
    print("TypeError:", e)
'
```

Output:
```text
TypeError: SandboxedEnvironment.__init__() got an unexpected keyword argument 'cleanup'
```

---

## 2. Logic Chain

1. **Failure of Sandbox Containment (Lines 155–161)**:
   - Observation 1.1 reveals that in `is_path_safe`, if `self.sandbox_dir` is active, it checks if `resolved == sb_resolved or sb_resolved in resolved.parents`. If true, it returns `True`.
   - Crucially, if false (the path is outside `sandbox_dir`), there is no `return False`. Execution falls through to line 161: `return True`.
   - Observation 1.2 proves empirically that `/etc/passwd`, `/home/cyberdid/.bashrc`, and `/home/cyberdid/Projects/B-12/pyproject.toml` all return `True`.
   - **Inference**: Any host path not explicitly containing one of the 6 blacklisted substrings (`.ssh`, `.gnupg`, `secrets`, `/etc/shadow`, `/etc/sudoers`, `/root`) is permitted access. This violates Requirement R4 ("Isolated Sandbox and Safety Constraints") and the interface contract in `PROJECT.md` ("Zero access to host secrets or production host").

2. **Symlink Escape to Host Filesystem**:
   - Observation 1.2 demonstrates that an agent or scenario creating a symlink inside the sandbox pointing to `/home/cyberdid` or `/etc/passwd` passes `is_path_safe` with `True`.
   - Because `resolved` resolves to `/home/cyberdid` and `/etc/passwd`, neither matches the narrow 7 paths in `PROTECTED_HOST_PATTERNS`, and the fallthrough at line 161 returns `True`.
   - **Inference**: Symlink traversal can read or reference arbitrary host user files and system configuration.

3. **URL-Encoded Path Traversal Bypass**:
   - Observation 1.2 shows that passing `"%2Fhome%2Fcyberdid%2F%2Essh%2Fid_rsa"` returns `True`.
   - The substring check looks for literal `".ssh"`. Because the string contains `"%2Essh"`, it bypasses the substring filter.
   - `Path("%2Fhome%2Fcyberdid%2F%2Essh%2Fid_rsa").resolve()` does not decode URL encoding and evaluates to a non-blacklisted path, falling through to `True`.
   - **Inference**: If downstream components (e.g. web/HTTP runners or unquoting file helpers) decode the path, the guard fails entirely.

4. **False Positive Rejection of Sandbox Fixtures**:
   - Observation 1.1 shows substring matching `if "secrets" in raw_str: return False`.
   - Observation 1.2 shows that `SandboxedEnvironment.setup()` creates `dummy_secrets = dummy_state / "secrets"` and sets `os.environ["B12_SECRETS_DIR"] = str(dummy_secrets)`.
   - When tested code evaluates `is_path_safe(os.environ["B12_SECRETS_DIR"])`, it returns `False`!
   - Furthermore, synthetic test fixtures placed inside the workspace such as `secrets_mock.json` or `fake_credentials/secrets.yaml` are marked as unsafe (`False`), preventing legitimate evaluation scenarios from using synthetic secrets fixtures.

5. **Process Pollution via Untracked Environment Variables**:
   - Observation 1.1 shows `_prev_env` only snapshots 5 hardcoded keys.
   - Observation 1.3 shows that any environment variable created or modified during the scenario run (`INJECTED_VAR`) persists in the parent process after context teardown.
   - **Inference**: Multi-scenario runs (e.g. `suite_runner.py`) will experience cross-test state leakage and cascading test pollution.

6. **API Contract Mismatch (`cleanup=True`)**:
   - Observation 1.4 confirms that passing `cleanup=True` raises `TypeError`.
   - While directory deletion works by default on normal exit and when `retain_on_failure=False`, the constructor lacks the expected parameter signature.

---

## 3. Caveats

1. **Direct Blacklisted Targets Blocked**: `is_path_safe` successfully blocks direct access to `~/.ssh/id_rsa`, `~/.gnupg`, and `/etc/shadow`, as well as path traversal containing literal `.ssh` (e.g. `../../../../home/cyberdid/.ssh/id_rsa`).
2. **Null-byte Handling Robust**: Null-byte paths correctly raise `ValueError` inside `Path.resolve()` and return `False`.
3. **Environment Cleanup for Tracked Keys**: For the 5 tracked keys (`HOME`, `B12_STATE_DIR`, `B12_SECRETS_DIR`, `B12_WORKSPACE_DIR`, `B12_SANDBOX_DIR`), restoration on both normal exit and uncaught exception was empirically verified as functioning correctly.
4. **Physical Host Modifications Avoided**: Tests were conducted strictly with synthetic temporary files, symlinks in temporary directories, and in-memory environment inspections without touching real host secrets.

---

## 4. Conclusion

The current implementation of `evals/capri_comprehensive/evaluators/sandboxed_env.py` fails adversarial review:
- **Verdict**: **REQUEST_CHANGES**
- **Overall Risk Assessment**: **CRITICAL**

### Required Changes for Worker:

1. **Fix Sandbox Containment in `is_path_safe`**:
   When `self.sandbox_dir` is active, any path whose resolved location is **NOT** within `self.sandbox_dir.resolve()` MUST return `False`.
   ```python
   if self.sandbox_dir:
       sb_resolved = self.sandbox_dir.resolve()
       if resolved == sb_resolved or sb_resolved in resolved.parents:
           return True
       return False  # MUST reject any path outside sandbox
   ```

2. **Fix False Positives on Internal Sandbox Fixtures**:
   Check containment inside the sandbox **BEFORE** applying generic substring rules like `"secrets"`. If a file is safely inside `self.sandbox_dir`, synthetic secrets files (e.g. `B12_SECRETS_DIR`, `secrets_mock.json`) should be permitted.

3. **Decode URL-Encoded Paths**:
   Apply `urllib.parse.unquote()` to `raw_str` before running substring and resolution checks.

4. **Resolve Relative Paths Relative to Sandbox Workspace**:
   If `target_path` is relative and sandbox is active, resolve it relative to `self.get_workspace_path()` instead of host process `CWD`.

5. **Full Process Environment Snapshot & Restoration**:
   In `setup()`, snapshot the entire `os.environ` (`self._full_prev_env = dict(os.environ)`), and in `teardown()`, restore the entire environment (`os.environ.clear(); os.environ.update(self._full_prev_env)`).

6. **Add `cleanup: bool = True` Parameter to `SandboxedEnvironment.__init__`**:
   Support `cleanup: bool = True` (or default to True) to avoid `TypeError` when callers specify cleanup behavior explicitly.

---

## 5. Verification Method

To independently reproduce all empirical findings:

```bash
# 1. Run the comprehensive adversarial challenge audit script
uv run python -c '
import os, urllib.parse
from pathlib import Path
from evals.capri_comprehensive.evaluators.sandboxed_env import SandboxedEnvironment, HOST_HOME

with SandboxedEnvironment("AUDIT") as env:
    ws = env.get_workspace_path()
    
    # Check host file access
    assert env.is_path_safe("/etc/passwd") is False, "FAILED: /etc/passwd allowed!"
    assert env.is_path_safe(str(HOST_HOME / ".bashrc")) is False, "FAILED: host .bashrc allowed!"
    
    # Check URL-encoded bypass
    assert env.is_path_safe("%2Fhome%2Fcyberdid%2F%2Essh%2Fid_rsa") is False, "FAILED: URL-encoded .ssh allowed!"
    
    # Check sandbox internal secrets directory
    sb_sec = os.environ.get("B12_SECRETS_DIR")
    assert env.is_path_safe(sb_sec) is True, "FAILED: sandbox own secrets dir falsely rejected!"
'

# 2. Run the environment leakage reproduction
uv run python -c '
import os
from evals.capri_comprehensive.evaluators.sandboxed_env import SandboxedEnvironment
with SandboxedEnvironment("TEST") as env:
    os.environ["LEAK_CHECK"] = "1"
assert "LEAK_CHECK" not in os.environ, "FAILED: environment variable leaked to parent process!"
'

# 3. Run the cleanup=True parameter test
uv run python -c '
from evals.capri_comprehensive.evaluators.sandboxed_env import SandboxedEnvironment
env = SandboxedEnvironment("TEST", cleanup=True)
'
```

Expected invalidation condition: Once the worker implements the required fixes, all assertions in the verification script above must pass with exit code 0.
