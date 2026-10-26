"""Operations: managed snapshots, deletion-ledger replay, runtime lock, redacted logs.

Snapshots live in state_dir/snapshots/<id>/ (0700) with a SHA-256 manifest and an
inventory. SQLite files are copied with the online backup API; the owner API token,
logs, locks and the service directory are never copied. Every global purge appends a
payload-free entry (operation, actor, target IDs) to state_dir/service/deletions.jsonl
and is applied to every managed snapshot; restore replays the ledger before the
restored state can serve data. Unmanaged copies (external disks, FS snapshots) are
outside this guarantee.
"""

import fcntl
import hashlib
import json
import logging
import logging.handlers
import os
import shutil
import sqlite3
import traceback
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

SKIP = {"snapshots", "service", "api", "logs", "scheduler.lock", "runtime.lock"}


def _private(path: Path) -> Path:
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    path.chmod(0o700)
    return path


def _files(root: Path):
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root)
        if relative.parts[0] in SKIP or str(relative) == "MANIFEST.json":
            continue
        if not path.is_file() or path.is_symlink():
            continue
        if path.name.endswith(("-wal", "-shm", "-journal")) or path.name.startswith(".b12-"):
            continue
        yield path, relative


def _manifest(root: Path) -> dict:
    return {
        str(relative): hashlib.sha256(path.read_bytes()).hexdigest()
        for path, relative in _files(root)
    }


class RuntimeLock:
    """Exclusive owner of a state directory for serving/restoring."""

    def __init__(self, state_dir: Path):
        self.fd = os.open(Path(state_dir) / "runtime.lock", os.O_CREAT | os.O_RDWR, 0o600)
        try:
            fcntl.flock(self.fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            os.close(self.fd)
            raise RuntimeError("state directory is in use by a running B-12") from None

    def release(self):
        if self.fd is not None:
            fcntl.flock(self.fd, fcntl.LOCK_UN)
            os.close(self.fd)
            self.fd = None


class Operations:
    def __init__(self, state_dir: Path):
        self.state = Path(state_dir)
        self.snapshots = _private(self.state / "snapshots")
        self.service = _private(self.state / "service")
        self.inventory_path = self.service / "snapshots.json"
        self.ledger_path = self.service / "deletions.jsonl"

    # --- inventory -------------------------------------------------------------
    def inventory(self) -> list[dict]:
        if not self.inventory_path.exists():
            return []
        return json.loads(self.inventory_path.read_text())

    def _write_inventory(self, items):
        temporary = self.service / ".snapshots.json.tmp"
        fd = os.open(temporary, os.O_CREAT | os.O_TRUNC | os.O_WRONLY, 0o600)
        with os.fdopen(fd, "w") as handle:
            json.dump(items, handle, indent=2)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, self.inventory_path)

    # --- ledger ----------------------------------------------------------------
    def record_deletion(self, operation_id: str, actor_id: str, target_ids) -> None:
        known = {entry["operation_id"] for entry in self.deletions()}
        if operation_id in known:
            return
        entry = {
            "operation_id": operation_id,
            "actor_id": actor_id,
            "target_ids": list(target_ids),
            "at": datetime.now(UTC).isoformat(),
        }
        fd = os.open(self.ledger_path, os.O_CREAT | os.O_APPEND | os.O_WRONLY, 0o600)
        try:
            os.write(fd, (json.dumps(entry) + "\n").encode())
            os.fsync(fd)
        finally:
            os.close(fd)

    def deletions(self) -> list[dict]:
        if not self.ledger_path.exists():
            return []
        return [json.loads(line) for line in self.ledger_path.read_text().splitlines() if line]

    # --- snapshots ---------------------------------------------------------------
    def create_snapshot(self, *, kind: str = "manual") -> dict:
        snapshot_id = str(uuid4())
        target = _private(self.snapshots / snapshot_id)
        for path, relative in _files(self.state):
            destination = target / relative
            _private(destination.parent)
            if path.suffix == ".sqlite3":
                source = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
                copy = sqlite3.connect(destination)
                try:
                    source.backup(copy)
                finally:
                    copy.close()
                    source.close()
                os.chmod(destination, 0o600)
            else:
                shutil.copy2(path, destination)
                os.chmod(destination, 0o600)
        manifest = _manifest(target)
        (target / "MANIFEST.json").write_text(json.dumps(manifest, indent=2))
        entry = {
            "id": snapshot_id,
            "kind": kind,
            "created_at": datetime.now(UTC).isoformat(),
            "files": len(manifest),
            "deletions_applied": len(self.deletions()),
        }
        self._write_inventory([*self.inventory(), entry])
        return entry

    def verify(self, snapshot_id: str) -> dict:
        root = self.snapshots / snapshot_id
        recorded = json.loads((root / "MANIFEST.json").read_text())
        actual = _manifest(root)
        bad = sorted(k for k in recorded.keys() | actual.keys() if recorded.get(k) != actual.get(k))
        integrity = {}
        for name in recorded:
            if name.endswith(".sqlite3"):
                connection = sqlite3.connect(f"file:{root / name}?mode=ro", uri=True)
                try:
                    integrity[name] = connection.execute("PRAGMA integrity_check").fetchone()[0]
                finally:
                    connection.close()
        return {
            "id": snapshot_id,
            "ok": not bad and all(v == "ok" for v in integrity.values()),
            "mismatched": bad,
            "integrity": integrity,
        }

    def delete_snapshot(self, snapshot_id: str) -> None:
        shutil.rmtree(self.snapshots / snapshot_id)
        self._write_inventory([s for s in self.inventory() if s["id"] != snapshot_id])

    def purge_snapshots(self, operation_id: str, actor_id: str, target_ids) -> list[str]:
        """Apply a global purge inside every managed snapshot, then re-seal manifests."""
        from b12.contracts import Actor
        from b12.goals import GoalStore
        from b12.memory import MemoryStore
        from b12.sessions import SessionStore
        from b12.tools.filesystem import BackupStore

        touched = []
        for entry in self.inventory():
            root = self.snapshots / entry["id"]
            memory_db = root / "memory" / "memory.sqlite3"
            actor = Actor(id=actor_id)
            if memory_db.exists():
                memory = MemoryStore(memory_db)
                try:
                    for target in target_ids:
                        try:
                            memory.begin_purge(target, actor)
                        except KeyError:
                            pass
                finally:
                    memory.close()
            turns: list[str] = []
            if (root / "sessions").exists():
                sessions = SessionStore(root / "sessions")
                try:
                    turns = sessions.purge_evidence(operation_id, actor_id, tuple(target_ids))
                finally:
                    sessions.close()
            if (root / "goals").exists():
                goals = GoalStore(root / "goals")
                try:
                    goals.purge_evidence(actor_id, target_ids)
                finally:
                    goals.close()
            if (root / "backups").exists() and turns:
                backups = BackupStore(root / "backups")
                try:
                    backups.purge(actor_id, turn_ids=tuple(turns))
                finally:
                    backups.close()
            for leftover in root.rglob("*"):
                if leftover.name.endswith(("-wal", "-shm", "-journal")):
                    leftover.unlink()
            (root / "MANIFEST.json").write_text(json.dumps(_manifest(root), indent=2))
            touched.append(entry["id"])
        return touched

    async def restore(self, snapshot_id: str, settings) -> dict:
        """Offline restore: lock, verify, keep a pre-restore snapshot, swap, replay ledger."""
        from b12.runtime import open_runtime

        lock = RuntimeLock(self.state)
        try:
            check = self.verify(snapshot_id)
            if not check["ok"]:
                raise RuntimeError("snapshot failed verification")
            safety = self.create_snapshot(kind="pre_restore")
            for path, _ in list(_files(self.state)):
                path.unlink()
            source = self.snapshots / snapshot_id
            for path, relative in _files(source):
                destination = self.state / relative
                _private(destination.parent)
                shutil.copy2(path, destination)
                os.chmod(destination, 0o600)
            runtime = open_runtime(settings)
            replayed = []
            try:
                for entry in self.deletions():
                    actor_ids = set(runtime.control.actor_ids())
                    if entry["actor_id"] not in actor_ids:
                        continue
                    actor = runtime.control.resolve_actor(entry["actor_id"])
                    for target in entry["target_ids"]:
                        if runtime.memory.is_live(target, actor):
                            receipt = await runtime.purge.forget(target, actor.id)
                            replayed.append({"target": target, "state": receipt.state})
                await runtime.purge.resume()
            finally:
                runtime.close()
            return {"restored": snapshot_id, "pre_restore": safety["id"], "replayed": replayed}
        finally:
            lock.release()


class RedactingFormatter(logging.Formatter):
    """Exception messages may contain payload: log only type and code locations."""

    def formatException(self, exc_info):
        _, value, tb = exc_info
        frames = [f"{Path(f.filename).name}:{f.lineno}" for f in traceback.extract_tb(tb)]
        return f"{type(value).__name__} at {' > '.join(frames[-6:])}"

    def format(self, record):
        record.msg = str(record.msg)[:500]
        record.args = ()
        return super().format(record)


def configure_logging(state_dir: Path) -> Path:
    directory = _private(Path(state_dir) / "logs")
    path = directory / "b12.log"
    handler = logging.handlers.RotatingFileHandler(path, maxBytes=1_000_000, backupCount=3)
    handler.setFormatter(RedactingFormatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
    root = logging.getLogger("b12")
    root.handlers = [handler]
    root.setLevel(logging.INFO)
    os.chmod(path, 0o600)
    return path
