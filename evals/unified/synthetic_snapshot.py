"""Create a small synthetic B-12 memory store without reading user state."""

import hashlib
import os
import re
from pathlib import Path

from b12.contracts import Actor
from b12.memory import MemoryStore


def create(path: Path, actor_id: str) -> str:
    if not re.fullmatch(r"actor_synthetic_[a-zA-Z0-9_]{1,40}", actor_id):
        raise ValueError("actor must use a synthetic identifier")
    path = Path(path)
    fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    os.close(fd)
    try:
        store = MemoryStore(path)
        try:
            store.remember(
                "synthetic fixture: user prefers jasmine tea",
                Actor(id=actor_id, consent=True),
                source="synthetic fixture",
            )
        finally:
            store.close()
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except BaseException:
        path.unlink(missing_ok=True)
        raise


class SyntheticSnapshot:
    """A newly generated, closed synthetic MemoryStore and its initial byte hash."""

    def __init__(self, path, digest):
        self.path = Path(path)
        self.digest = digest

    @classmethod
    def create(cls, path, actor_id):
        digest = create(path, actor_id)
        return cls(path, digest)

    def clone(self, destination: Path) -> str:
        # Open stores can have uncheckpointed WAL pages; a byte copy would omit them.
        if Path(str(self.path) + "-wal").exists():
            raise ValueError("source has a WAL; close the store before cloning")
        data = self.path.read_bytes()
        if hashlib.sha256(data).hexdigest() != self.digest:
            raise ValueError("snapshot hash mismatch")
        destination = Path(destination)
        fd = os.open(destination, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        try:
            with os.fdopen(fd, "wb") as out:
                out.write(data)
            digest = hashlib.sha256(destination.read_bytes()).hexdigest()
            if digest != self.digest:
                raise ValueError("clone hash mismatch")
            return digest
        except BaseException:
            destination.unlink(missing_ok=True)
            raise
