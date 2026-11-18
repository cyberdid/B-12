import importlib.util
import tempfile
import unittest
from pathlib import Path

from b12.contracts import Actor
from b12.memory import MemoryStore

PATH = Path(__file__).resolve().parents[2] / "evals/unified/synthetic_snapshot.py"


class SyntheticSnapshotTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def module(self):
        if not PATH.exists():
            self.fail("synthetic snapshot builder is missing")
        spec = importlib.util.spec_from_file_location("synthetic_snapshot", PATH)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod

    def test_generated_memory_uses_runtime_store_and_actor_scope(self):
        mod = self.module()
        path = self.root / "one.db"
        digest = mod.create(path, "actor_synthetic_1")
        self.assertEqual(len(digest), 64)
        store = MemoryStore(path)
        try:
            actor = Actor(id="actor_synthetic_1", consent=True)
            other = Actor(id="actor_synthetic_2", consent=True)
            self.assertEqual(len(store.search("synthetic", actor)), 1)
            self.assertEqual(store.search("synthetic", other), [])
        finally:
            store.close()

    def test_existing_file_is_never_overwritten(self):
        path = self.root / "existing.db"
        path.write_text("preserve")
        with self.assertRaises(FileExistsError):
            self.module().create(path, "actor_synthetic_1")
        self.assertEqual(path.read_text(), "preserve")

    def test_rejects_unmarked_actor(self):
        with self.assertRaises(ValueError):
            self.module().create(self.root / "one.db", "owner")

    def test_verified_clones_are_identical_and_isolated(self):
        mod = self.module()
        snapshot = mod.SyntheticSnapshot.create(self.root / "source.db", "actor_synthetic_1")
        first = self.root / "first.db"
        second = self.root / "second.db"
        self.assertEqual(snapshot.clone(first), snapshot.digest)
        self.assertEqual(snapshot.clone(second), snapshot.digest)
        first.write_bytes(b"changed")
        self.assertEqual(second.read_bytes(), snapshot.path.read_bytes())

    def test_modified_source_and_existing_clone_are_rejected(self):
        mod = self.module()
        snapshot = mod.SyntheticSnapshot.create(self.root / "source.db", "actor_synthetic_1")
        dest = self.root / "dest.db"
        dest.write_bytes(b"keep")
        with self.assertRaises(FileExistsError):
            snapshot.clone(dest)
        self.assertEqual(dest.read_bytes(), b"keep")
        snapshot.path.write_bytes(b"altered")
        with self.assertRaises(ValueError):
            snapshot.clone(self.root / "other.db")
        self.assertFalse((self.root / "other.db").exists())

    def test_clone_rejects_uncheckpointed_wal(self):
        mod = self.module()
        snapshot = mod.SyntheticSnapshot.create(self.root / "source.db", "actor_synthetic_1")
        Path(str(snapshot.path) + "-wal").touch()
        with self.assertRaises(ValueError):
            snapshot.clone(self.root / "other.db")
        self.assertFalse((self.root / "other.db").exists())

    def test_clone_is_readable_by_runtime_memory_store(self):
        mod = self.module()
        snapshot = mod.SyntheticSnapshot.create(self.root / "source.db", "actor_synthetic_1")
        path = self.root / "copy.db"
        snapshot.clone(path)
        store = MemoryStore(path)
        try:
            self.assertEqual(
                len(store.search("synthetic", Actor(id="actor_synthetic_1", consent=True))), 1
            )
        finally:
            store.close()
