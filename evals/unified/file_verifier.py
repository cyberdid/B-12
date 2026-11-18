"""Verify a synthetic file by hash, without following symlinks below a trusted root."""

import hashlib
import os
import re
import stat
from pathlib import Path


def verify_file(root, relative_path, expected_sha256):
    if not isinstance(expected_sha256, str) or not re.fullmatch(r"[0-9a-f]{64}", expected_sha256):
        raise ValueError("expected hash must be lowercase SHA-256")
    path = Path(relative_path)
    if path.is_absolute() or not path.parts or any(p in (".", "..") for p in path.parts):
        return "invalid_path"
    opened = []
    try:
        directory = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        opened.append(directory)
        for component in path.parts[:-1]:
            directory = os.open(
                component, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=directory
            )
            opened.append(directory)
        fd = os.open(path.parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
        opened.append(fd)
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            return "invalid_path"
        with os.fdopen(os.dup(fd), "rb") as source:
            actual = hashlib.file_digest(source, "sha256").hexdigest()
        return "verified" if actual == expected_sha256 else "mismatch"
    except FileNotFoundError:
        return "missing"
    except OSError:
        return "invalid_path"
    finally:
        for fd in reversed(opened):
            os.close(fd)
