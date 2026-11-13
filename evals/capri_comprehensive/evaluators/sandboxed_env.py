"""Sandboxed environment manager for isolated Capri scenario execution.

Enforces:
- Disposable filesystem root for each scenario execution (`/tmp/capri_eval_sandbox_*`).
- Complete isolation from host secrets (`~/.ssh`, `~/.local/state/b12/secrets`).
- Controlled fixture seeding (synthetic files, dummy documents, mock databases).
- Strict path containment checks and safe automatic cleanup.
"""

from __future__ import annotations

import os
import shutil
import tempfile
import urllib.parse
import uuid
from pathlib import Path
from typing import Any

# Capture true host home before any sandbox env changes
HOST_HOME = Path.home().resolve()

PROTECTED_HOST_PATTERNS = [
    HOST_HOME / ".ssh",
    HOST_HOME / ".gnupg",
    HOST_HOME / ".local" / "state" / "b12" / "secrets",
    HOST_HOME / ".bash_history",
    Path("/etc/shadow"),
    Path("/etc/sudoers"),
    Path("/root"),
]


# A fixture whose content starts with this is created as a symbolic link to the rest.
SYMLINK_PREFIX = "symlink -> "


class SandboxedEnvironment:
    """Manages an ephemeral, isolated filesystem directory for a scenario run."""

    def __init__(
        self,
        scenario_id: str,
        initial_files: dict[str, str] | None = None,
        retain_on_failure: bool = False,
        cleanup: bool = True,
        base_tmp_dir: str | None = None,
    ):
        self.scenario_id = scenario_id
        self.initial_files = initial_files or {}
        self.retain_on_failure = retain_on_failure
        self.cleanup = cleanup
        self.base_tmp_dir = base_tmp_dir
        self.sandbox_dir: Path | None = None
        self._full_prev_env: dict[str, str] = {}
        self.is_active = False

    def __enter__(self) -> SandboxedEnvironment:
        self.setup()
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        failed = exc_type is not None
        self.teardown(failed=failed)

    def setup(self) -> Path:
        """Create sandbox directory, set environment variables, and populate initial files."""
        # Snapshot full environment before any modifications
        self._full_prev_env = dict(os.environ)

        unique_token = uuid.uuid4().hex[:8]
        dir_name = f"capri_eval_sandbox_{self.scenario_id}_{unique_token}"
        if self.base_tmp_dir:
            Path(self.base_tmp_dir).mkdir(parents=True, exist_ok=True)
            self.sandbox_dir = Path(tempfile.mkdtemp(prefix=f"{dir_name}_", dir=self.base_tmp_dir))
        else:
            self.sandbox_dir = Path(tempfile.mkdtemp(prefix=f"{dir_name}_"))

        # Setup internal directories
        dummy_home = self.sandbox_dir / "home" / "sandbox_user"
        dummy_home.mkdir(parents=True, exist_ok=True)
        dummy_state = self.sandbox_dir / "state" / "b12"
        dummy_state.mkdir(parents=True, exist_ok=True)
        dummy_secrets = dummy_state / "secrets"
        dummy_secrets.mkdir(parents=True, exist_ok=True)
        (self.sandbox_dir / "workspace").mkdir(parents=True, exist_ok=True)

        # Seed initial files
        for rel_path, content in self.initial_files.items():
            target_path = self.sandbox_dir / "workspace" / rel_path.lstrip("/")
            target_path.parent.mkdir(parents=True, exist_ok=True)
            if content.startswith(SYMLINK_PREFIX):
                # "symlink -> /etc/passwd" means a real link, not a file with that text (SEC-08).
                target_path.symlink_to(content.removeprefix(SYMLINK_PREFIX).strip())
            else:
                target_path.write_text(content, encoding="utf-8")

        # Save and override environment variables for sandbox containment
        env_overrides = {
            "B12_SANDBOX_DIR": str(self.sandbox_dir),
            "B12_STATE_DIR": str(dummy_state),
            "B12_SECRETS_DIR": str(dummy_secrets),
            "B12_WORKSPACE_DIR": str(self.sandbox_dir / "workspace"),
            "HOME": str(dummy_home),
        }
        for k, v in env_overrides.items():
            os.environ[k] = v

        self.is_active = True
        return self.sandbox_dir

    def teardown(self, failed: bool = False) -> None:
        """Restore environment and remove sandbox directory unless retain_on_failure is True."""
        # Restore full process environment
        if hasattr(self, "_full_prev_env") and self._full_prev_env:
            os.environ.clear()
            os.environ.update(self._full_prev_env)
            self._full_prev_env.clear()

        # Clean directory
        if self.sandbox_dir and self.sandbox_dir.exists():
            if not self.cleanup:
                pass
            elif failed and self.retain_on_failure:
                # Retain for post-mortem debugging
                pass
            else:
                try:
                    shutil.rmtree(self.sandbox_dir, ignore_errors=True)
                except Exception:
                    pass

        self.is_active = False

    def get_workspace_path(self) -> Path:
        if not self.sandbox_dir:
            raise RuntimeError("Sandbox is not active")
        return self.sandbox_dir / "workspace"

    def is_path_safe(self, target_path: str | Path) -> bool:
        """Check if target_path is safe and confined to sandbox.

        Invariants:
        1. Null bytes in target_path are strictly rejected.
        2. URL-encoded sequences are unquoted before evaluation.
        3. Host-level sensitive substrings (.ssh, .gnupg, /etc/shadow, /etc/sudoers, /root)
           are strictly rejected.
        4. If sandbox is active:
           - Relative paths are resolved relative to sandbox workspace.
           - Canonical target path (with all symlinks resolved) MUST reside strictly
             within self.sandbox_dir.resolve(). Any path resolving outside is rejected.
           - Target path must not resolve to any PROTECTED_HOST_PATTERNS.
        5. If sandbox is not active:
           - Any path touching PROTECTED_HOST_PATTERNS is rejected.
        """
        raw_str = str(target_path)
        if "\x00" in raw_str:
            return False

        unquoted = urllib.parse.unquote(raw_str)
        if "\x00" in unquoted:
            return False

        # Block explicit host secrets substrings
        forbidden_host_substrings = [".ssh", ".gnupg", "/etc/shadow", "/etc/sudoers", "/root"]
        for sub in forbidden_host_substrings:
            if sub in unquoted:
                return False

        try:
            p = Path(os.path.expanduser(unquoted)) if unquoted.startswith("~") else Path(unquoted)

            # If relative and sandbox is active, resolve against workspace
            if not p.is_absolute() and self.sandbox_dir:
                target = self.get_workspace_path() / p
            else:
                target = p

            resolved = target.resolve()
        except Exception:
            return False
        # Python 3.13 no longer raises on a symlink loop: the result is still a symlink.
        if resolved.is_symlink():
            return False

        # Check against protected host paths
        for protected in PROTECTED_HOST_PATTERNS:
            try:
                prot_resolved = protected.resolve()
                if resolved == prot_resolved or prot_resolved in resolved.parents:
                    return False
            except Exception:
                continue

        # If sandbox is active, enforce strict confinement
        if self.sandbox_dir:
            sb_resolved = self.sandbox_dir.resolve()
            if resolved == sb_resolved or sb_resolved in resolved.parents:
                return True
            return False  # Strict reject for any path outside sandbox

        return True
