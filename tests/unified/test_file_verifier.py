"""Independent file evidence for synthetic evaluation tasks."""

import hashlib
import importlib.util
from pathlib import Path

import pytest

PATH = Path(__file__).resolve().parents[2] / "evals/unified/file_verifier.py"


@pytest.fixture
def verifier():
    assert PATH.exists(), "file verifier is missing"
    spec = importlib.util.spec_from_file_location("file_verifier", PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_verified_only_after_expected_bytes_exist(verifier, tmp_path):
    digest = hashlib.sha256(b"synthetic").hexdigest()
    assert verifier.verify_file(tmp_path, "out.txt", digest) == "missing"
    (tmp_path / "out.txt").write_bytes(b"wrong")
    assert verifier.verify_file(tmp_path, "out.txt", digest) == "mismatch"
    (tmp_path / "out.txt").write_bytes(b"synthetic")
    assert verifier.verify_file(tmp_path, "out.txt", digest) == "verified"


def test_escape_and_symlink_do_not_count_as_evidence(verifier, tmp_path):
    digest = hashlib.sha256(b"synthetic").hexdigest()
    (tmp_path / "link").symlink_to("/etc/passwd")
    assert verifier.verify_file(tmp_path, "link", digest) == "invalid_path"
    assert verifier.verify_file(tmp_path, "../outside", digest) == "invalid_path"
    assert verifier.verify_file(tmp_path, "/etc/passwd", digest) == "invalid_path"
