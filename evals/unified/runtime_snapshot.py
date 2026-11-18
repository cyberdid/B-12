"""Build and clone a closed, synthetic B-12 runtime state for paired evaluations."""

import hashlib
import os
import shutil
from pathlib import Path

from b12.runtime import open_runtime


def _hashes(root):
    result = {}
    for directory, dirs, files in os.walk(root, followlinks=False):
        parent = Path(directory)
        for name in dirs:
            if (parent / name).is_symlink():
                raise ValueError("snapshot contains a symbolic link")
        for name in files:
            path = parent / name
            if (
                path.is_symlink()
                or not path.is_file()
                or name.endswith(("-wal", "-journal", "-shm"))
            ):
                raise ValueError("snapshot contains a link, special file or active SQLite journal")
            with path.open("rb") as source:
                result[str(path.relative_to(root))] = hashlib.file_digest(
                    source, "sha256"
                ).hexdigest()
    return result


class SyntheticRuntimeSnapshot:
    def __init__(self, path, actor_id, hashes):
        self.path = Path(path)
        self.actor_id = actor_id
        self.hashes = hashes

    @classmethod
    def create(cls, path, settings):
        path = Path(path)
        path.mkdir(mode=0o700)  # refuses any existing state
        try:
            runtime = open_runtime(
                settings.model_copy(
                    update={
                        "state_dir": path,
                        "host_access": "none",
                        "memory_enrichment": False,
                        "embedding_python": None,
                    }
                )
            )
            try:
                actor = runtime.control.create_actor(owner=True, consent=True)
                session = runtime.control.create_session(actor.id)
                runtime.memory.remember(
                    "synthetic fixture: user prefers jasmine tea", actor, source="synthetic fixture"
                )
                runtime.goals.set_preference(actor.id, "language", "uk", "synthetic fixture")
                runtime.goals.create(
                    actor.id,
                    session,
                    "synthetic fixture: review notes",
                    "synthetic fixture reviewed",
                )
            finally:
                runtime.close()
            return cls(path, actor.id, _hashes(path))
        except BaseException:
            shutil.rmtree(path)
            raise

    def clone(self, destination):
        if _hashes(self.path) != self.hashes:
            raise ValueError("source snapshot changed")
        destination = Path(destination)
        destination.mkdir(mode=0o700)
        try:
            for relative in self.hashes:
                target = destination / relative
                target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
                shutil.copyfile(self.path / relative, target, follow_symlinks=False)
                target.chmod(0o600)
            if _hashes(destination) != self.hashes:
                raise ValueError("cloned snapshot differs")
            return dict(self.hashes)
        except BaseException:
            shutil.rmtree(destination)
            raise
