"""Installer renders a root-free user unit and private env file; nothing is enabled."""

import os
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def test_installer_renders_private_unit_without_starting(tmp_path, profile_settings):
    shim = tmp_path / "bin"
    shim.mkdir()
    calls = tmp_path / "systemctl.calls"
    (shim / "systemctl").write_text(f'#!/bin/sh\necho "$@" >> {calls}\n')
    (shim / "systemctl").chmod(0o755)
    fake_b12 = shim / "b12"
    fake_b12.write_text(f'#!/bin/sh\necho "$B12_MODEL_PROFILE $@" >> {tmp_path / "b12.calls"}\n')
    fake_b12.chmod(0o755)
    env = {
        "PATH": f"{shim}:{os.environ['PATH']}",
        "HOME": str(tmp_path / "home"),
        "XDG_CONFIG_HOME": str(tmp_path / "config"),
    }
    result = subprocess.run(
        [
            str(ROOT / "scripts/install-user-service.sh"),
            str(fake_b12),
            str(profile_settings.model_profile),
            str(profile_settings.tokenizer_dir),
            "8799",
        ],
        env=env,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    unit = (tmp_path / "config/systemd/user/b12.service").read_text()
    env_file = tmp_path / "config/b12/env"
    assert f"ExecStart={fake_b12} serve --port ${{B12_PORT}}" in unit
    assert f"EnvironmentFile={env_file}" in unit and "@" not in unit.split("[Install]")[0]
    assert oct(env_file.stat().st_mode & 0o777) == "0o600"
    assert "B12_PORT=8799" in env_file.read_text()
    assert calls.read_text().split() == ["--user", "daemon-reload"]  # never enable/start
    assert "init" in (tmp_path / "b12.calls").read_text()
    if shutil.which("systemd-analyze"):
        check = subprocess.run(
            [
                "systemd-analyze",
                "--user",
                "verify",
                str(tmp_path / "config/systemd/user/b12.service"),
            ],
            capture_output=True,
            text=True,
        )
        assert "b12.service" not in check.stderr or check.returncode == 0, check.stderr


@pytest.mark.parametrize("bad", ["relative/b12", "/does/not/exist"])
def test_installer_rejects_non_absolute_or_missing_paths(tmp_path, bad):
    result = subprocess.run(
        [str(ROOT / "scripts/install-user-service.sh"), bad, "/x", "/y"],
        env={"PATH": os.environ["PATH"], "HOME": str(tmp_path)},
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0 and "absolute" in result.stderr
