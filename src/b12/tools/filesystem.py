"""Full-host filesystem within OS permissions, atomic writes and managed backups.

No path-root sandbox is claimed. Parent symlinks use OS resolution; a pinned
parent directory fd anchors writes. Leaf symlink/nonregular writes are refused.
BackupStore is an internal trusted managed-copy store, never a model control API.
"""

import asyncio
import base64
import hashlib
import hmac
import json
import os
import secrets
import sqlite3
import stat
from pathlib import Path
from uuid import UUID, uuid4

from pydantic import Field, field_validator

from b12.control import ControlError
from b12.tools._common import AbsolutePath, Args, body, clip, failure
from b12.tools.outcomes import HandlerOutcome, SideEffect


def _metadata(fd):
    info = os.fstat(fd)
    names = os.listxattr(fd)
    if len(names) > 64:
        raise ValueError("extended metadata limit")
    attrs = {}
    total = 0
    for name in names:
        value = os.getxattr(fd, name)
        total += len(name.encode()) + len(value)
        if total > 65536:
            raise ValueError("extended metadata limit")
        attrs[name] = value
    return info, attrs


class BackupStore:
    def __init__(self, path: Path):
        self.path = Path(path).absolute()
        if self.path.is_symlink():
            raise ValueError("managed root cannot be symlink")
        self.path.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.path.chmod(0o700)
        self.objects = self.path / "objects"
        if self.objects.is_symlink():
            raise ValueError("managed objects cannot be symlink")
        self.objects.mkdir(mode=0o700, exist_ok=True)
        self.objects.chmod(0o700)
        db_path = self.path / "copies.sqlite3"
        fd = os.open(db_path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        os.fchmod(fd, 0o600)
        os.close(fd)
        self.db = sqlite3.connect(db_path)
        self.db.row_factory = sqlite3.Row
        self.db.executescript("""
            PRAGMA secure_delete=ON; PRAGMA synchronous=FULL;
            CREATE TABLE IF NOT EXISTS secret(key BLOB NOT NULL);
            CREATE TABLE IF NOT EXISTS sources(owner TEXT,identity BLOB,source_id TEXT,
                PRIMARY KEY(owner,identity));
            CREATE TABLE IF NOT EXISTS copies(artifact_id TEXT PRIMARY KEY,owner TEXT,
                source_id TEXT,source_path TEXT,turn_id TEXT,operation_id TEXT,
                bytes INTEGER,state TEXT,metadata TEXT);
            CREATE TABLE IF NOT EXISTS staging(artifact_id TEXT PRIMARY KEY,owner TEXT,
                source_id TEXT,path TEXT,parent_dev INTEGER,parent_ino INTEGER,
                turn_id TEXT,operation_id TEXT,state TEXT);
            CREATE TABLE IF NOT EXISTS tombstones(owner TEXT,kind TEXT,id TEXT,
                PRIMARY KEY(owner,kind,id));
        """)
        with self.db:
            if not self.db.execute("SELECT 1 FROM secret").fetchone():
                self.db.execute("INSERT INTO secret VALUES (?)", (secrets.token_bytes(32),))
        self._key = self.db.execute("SELECT key FROM secret").fetchone()[0]

    def close(self):
        self.db.close()

    def _file(self, artifact_id):
        UUID(artifact_id)
        return self.objects / artifact_id

    def inventory(self, actor_id: str) -> list[dict]:
        """Trusted control inventory: opaque provenance only, no paths or payload."""
        return [
            dict(row)
            for row in self.db.execute(
                "SELECT artifact_id,source_id,turn_id,operation_id,bytes,state "
                "FROM copies WHERE owner=?",
                (actor_id,),
            )
        ] + [
            dict(row)
            for row in self.db.execute(
                "SELECT artifact_id,source_id,turn_id,operation_id,NULL AS bytes,state "
                "FROM staging WHERE owner=?",
                (actor_id,),
            )
        ]

    def stage(self, source_path, temp_path, parent_stat, guard):
        """Track same-directory staging payload before its first OS write."""
        owner, turn = guard.context.actor_id, guard.context.turn_id
        identity = hmac.new(self._key, source_path.encode(), hashlib.sha256).digest()
        guard.check()
        with self.db:
            row = self.db.execute(
                "SELECT source_id FROM sources WHERE owner=? AND identity=?", (owner, identity)
            ).fetchone()
            source = row[0] if row else str(uuid4())
            if self.db.execute(
                "SELECT 1 FROM tombstones WHERE owner=? AND "
                "((kind='source' AND id=?) OR (kind='turn' AND id=?))",
                (owner, source, turn),
            ).fetchone():
                raise PermissionError("managed source tombstoned")
            self.db.execute(
                "INSERT OR IGNORE INTO sources VALUES (?,?,?)", (owner, identity, source)
            )
            artifact = str(uuid4())
            self.db.execute(
                "INSERT INTO staging VALUES (?,?,?,?,?,?,?,?, 'staging')",
                (
                    artifact,
                    owner,
                    source,
                    temp_path,
                    parent_stat.st_dev,
                    parent_stat.st_ino,
                    turn,
                    guard.operation_id,
                ),
            )
        return artifact

    def finish_stage(self, artifact, *, removed):
        with self.db:
            if removed:
                self.db.execute("DELETE FROM staging WHERE artifact_id=?", (artifact,))
            else:
                self.db.execute(
                    "UPDATE staging SET state='deleting' WHERE artifact_id=?", (artifact,)
                )

    def open_copy(self, actor_id: str, artifact_id: str):
        """Trusted restore primitive. Application must authorize before using it."""
        row = self.db.execute(
            "SELECT state FROM copies WHERE owner=? AND artifact_id=?", (actor_id, artifact_id)
        ).fetchone()
        if not row or row[0] != "ready":
            raise PermissionError("copy unavailable")
        return os.fdopen(os.open(self._file(artifact_id), os.O_RDONLY | os.O_NOFOLLOW), "rb")

    def copy_metadata(self, actor_id, artifact_id):
        row = self.db.execute(
            "SELECT metadata FROM copies WHERE owner=? AND artifact_id=? AND state='ready'",
            (actor_id, artifact_id),
        ).fetchone()
        if not row:
            raise PermissionError("copy unavailable")
        return json.loads(row[0])

    async def capture(self, source_fd: int, source_path: str, guard) -> str:
        owner, turn = guard.context.actor_id, guard.context.turn_id
        identity = hmac.new(self._key, source_path.encode(), hashlib.sha256).digest()
        guard.check()
        info, attrs = _metadata(source_fd)
        metadata = json.dumps(
            {
                "mode": stat.S_IMODE(info.st_mode),
                "uid": info.st_uid,
                "gid": info.st_gid,
                "xattrs": {
                    name: base64.b64encode(value).decode("ascii") for name, value in attrs.items()
                },
            }
        )
        with self.db:
            source = self.db.execute(
                "SELECT source_id FROM sources WHERE owner=? AND identity=?", (owner, identity)
            ).fetchone()
            source_id = source[0] if source else str(uuid4())
            if self.db.execute(
                "SELECT 1 FROM tombstones WHERE owner=? AND ((kind='source' AND id=?) "
                "OR (kind='turn' AND id=?))",
                (owner, source_id, turn),
            ).fetchone():
                raise PermissionError("managed source tombstoned")
            self.db.execute(
                "INSERT OR IGNORE INTO sources VALUES (?,?,?)", (owner, identity, source_id)
            )
            artifact = str(uuid4())
            self.db.execute(
                "INSERT INTO copies VALUES (?,?,?,?,?,?,0,'copying',?)",
                (
                    artifact,
                    owner,
                    source_id,
                    source_path,
                    turn,
                    guard.operation_id,
                    metadata,
                ),
            )
        output = None
        try:
            guard.check()
            output = os.open(self._file(artifact), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            count = 0
            os.lseek(source_fd, 0, os.SEEK_SET)
            while True:
                guard.check()
                chunk = os.read(source_fd, 65536)
                if not chunk:
                    break
                count += len(chunk)
                if count > 64 * 1024 * 1024:
                    raise ValueError("backup size limit")
                guard.check()
                view = memoryview(chunk)
                while view:
                    written = os.write(output, view)
                    view = view[written:]
                await asyncio.sleep(0)
            guard.check()
            os.fsync(output)
            os.close(output)
            output = None
            guard.check()
            with self.db:
                self.db.execute(
                    "UPDATE copies SET bytes=?,state='ready' WHERE artifact_id=?", (count, artifact)
                )
            return artifact
        except BaseException:
            if output is not None:
                os.close(output)
            # Cleanup of an already-created managed copy is allowed after cancellation.
            try:
                self._file(artifact).unlink(missing_ok=True)
            except OSError:
                with self.db:
                    self.db.execute(
                        "UPDATE copies SET state='deleting',source_path=NULL WHERE artifact_id=?",
                        (artifact,),
                    )
            else:
                with self.db:
                    self.db.execute("DELETE FROM copies WHERE artifact_id=?", (artifact,))
            raise

    def purge(self, actor_id: str, *, artifact_ids=(), source_ids=(), turn_ids=()) -> dict:
        """Idempotent Task7 hook. Never deletes the unmanaged original source file.

        Source/turn tombstones prevent late copies. Owner control must invalidate
        active turns first; this primitive itself does not claim global R05.
        """
        for value in (*artifact_ids, *source_ids, *turn_ids):
            UUID(value)
        selected = [
            r
            for r in self.db.execute("SELECT * FROM copies WHERE owner=?", (actor_id,))
            if r["artifact_id"] in artifact_ids
            or r["source_id"] in source_ids
            or r["turn_id"] in turn_ids
        ]
        with self.db:
            self.db.executemany(
                "INSERT OR IGNORE INTO tombstones VALUES (?,?,?)",
                (
                    (actor_id, kind, value)
                    for kind, values in (("source", source_ids), ("turn", turn_ids))
                    for value in values
                ),
            )
            for row in selected:
                self.db.execute(
                    "UPDATE copies SET state='deleting',source_path=NULL WHERE artifact_id=?",
                    (row["artifact_id"],),
                )
        deleted, pending = [], []
        for row in selected:
            try:
                self._file(row["artifact_id"]).unlink(missing_ok=True)
            except OSError:
                pending.append(row["artifact_id"])
            else:
                with self.db:
                    self.db.execute("DELETE FROM copies WHERE artifact_id=?", (row["artifact_id"],))
                deleted.append(row["artifact_id"])
        stages = [
            r
            for r in self.db.execute("SELECT * FROM staging WHERE owner=?", (actor_id,))
            if r["artifact_id"] in artifact_ids
            or r["source_id"] in source_ids
            or r["turn_id"] in turn_ids
        ]
        for row in stages:
            try:
                parent = Path(row["path"]).parent.stat()
                if (parent.st_dev, parent.st_ino) != (row["parent_dev"], row["parent_ino"]):
                    raise PermissionError("staging parent relocated")
                Path(row["path"]).unlink(missing_ok=True)
            except OSError:
                self.finish_stage(row["artifact_id"], removed=False)
                pending.append(row["artifact_id"])
            else:
                self.finish_stage(row["artifact_id"], removed=True)
                deleted.append(row["artifact_id"])
        return {
            "state": "pending" if pending else "complete",
            "deleted_ids": deleted,
            "pending_ids": pending,
        }


class PathArgs(Args):
    path: AbsolutePath


class ListArgs(PathArgs):
    limit: int = Field(default=30, ge=1, le=50)


class ReadArgs(PathArgs):
    max_bytes: int = Field(default=4096, ge=1, le=8192)
    offset: int = Field(default=0, ge=0)


class SearchArgs(PathArgs):
    query: str = Field(min_length=1, max_length=128)
    limit: int = Field(default=10, ge=1, le=20)


class WriteArgs(PathArgs):
    text: str = Field(max_length=65536)
    overwrite: bool = False

    @field_validator("text")
    @classmethod
    def _bytes(cls, value):
        if len(value.encode()) > 65536:
            raise ValueError("write limit")
        return value


async def file_list(args, guard):
    try:
        guard.check()
        entries = []
        truncated = False
        with os.scandir(args.path) as iterator:
            for entry in iterator:
                guard.check()
                if len(entries) == args.limit:
                    truncated = True
                    break
                name, cut = clip(entry.name, 128)
                truncated |= cut
                entries.append(
                    {
                        "name": name,
                        "directory": entry.is_dir(follow_symlinks=False),
                        "symlink": entry.is_symlink(),
                    }
                )
        return HandlerOutcome(content={"entries": entries}, truncated=truncated)
    except OSError as exc:
        return failure(exc)


async def file_read(args, guard):
    try:
        guard.check()
        fd = os.open(args.path, os.O_RDONLY | os.O_NONBLOCK)
        with os.fdopen(fd, "rb", buffering=0) as stream:
            if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
                return failure("unsupported")
            guard.check()
            stream.seek(args.offset)
            raw = stream.read(args.max_bytes + 1)
        return HandlerOutcome(
            content={**body(raw[: args.max_bytes]), "bytes_read": min(len(raw), args.max_bytes)},
            truncated=len(raw) > args.max_bytes,
        )
    except OSError as exc:
        return failure(exc)


async def file_search(args, guard):
    matches, truncated, seen = [], False, 0
    stack = [(Path(args.path), 0)]
    try:
        while stack:
            folder, depth = stack.pop()
            guard.check()
            with os.scandir(folder) as iterator:
                for entry in iterator:
                    seen += 1
                    if seen > 1000:
                        truncated = True
                        stack.clear()
                        break
                    guard.check()
                    if entry.is_dir(follow_symlinks=False) and depth < 8:
                        stack.append((Path(entry.path), depth + 1))
                    elif entry.is_file(follow_symlinks=False):
                        try:
                            fd = os.open(entry.path, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW)
                            with os.fdopen(fd, "rb") as stream:
                                if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
                                    continue
                                raw = stream.read(8193)
                        except OSError:
                            continue
                        truncated |= len(raw) > 8192
                        if b"\x00" in raw:
                            continue
                        for line, text in enumerate(
                            raw[:8192].decode("utf-8", "replace").splitlines(), 1
                        ):
                            if args.query in text:
                                if len(matches) == args.limit:
                                    return HandlerOutcome(
                                        content={"matches": matches}, truncated=True
                                    )
                                snippet, cut = clip(text, 128)
                                relative, path_cut = clip(
                                    os.path.relpath(entry.path, args.path), 128
                                )
                                truncated |= cut or path_cut
                                matches.append({"path": relative, "line": line, "text": snippet})
                    await asyncio.sleep(0)
        return HandlerOutcome(content={"matches": matches}, truncated=truncated)
    except OSError as exc:
        return failure(exc)


async def file_write(args, guard, backups):
    parent_fd = source_fd = temp_fd = None
    temp_name = stage_id = None
    started = replaced = False

    def cleanup_temp():
        nonlocal temp_fd, temp_name, stage_id
        removed = True
        if temp_fd is not None:
            os.close(temp_fd)
            temp_fd = None
        if temp_name and parent_fd is not None:
            try:
                os.unlink(temp_name, dir_fd=parent_fd)
            except FileNotFoundError:
                temp_name = None
            except OSError:
                removed = False
            else:
                temp_name = None
        if stage_id:
            try:
                backups.finish_stage(stage_id, removed=removed)
            except sqlite3.Error:
                removed = False
            if removed:
                stage_id = None
        return removed

    def uncertain(code):
        cleanup = cleanup_temp()
        artifacts = tuple(
            item["artifact_id"]
            for item in backups.inventory(guard.context.actor_id)
            if item["operation_id"] == guard.operation_id
        )
        return HandlerOutcome(
            status="unknown",
            error_code=code,
            content={"target_replaced": replaced, "cleanup_confirmed": cleanup},
            side_effects=(
                SideEffect(kind="file_write", state="possible", artifact_ids=artifacts[:64]),
            ),
        )

    try:
        guard.check()
        path = Path(args.path)
        parent_fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        parent_path = os.readlink(f"/proc/self/fd/{parent_fd}")
        source_path = str(Path(parent_path) / path.name)
        try:
            before = os.stat(path.name, dir_fd=parent_fd, follow_symlinks=False)
        except FileNotFoundError:
            before = None
        if before and not stat.S_ISREG(before.st_mode):
            return failure("unsupported")
        if before and not args.overwrite:
            return failure("permission_denied")
        if before and before.st_size > 64 * 1024 * 1024:
            return failure("unsupported")
        if before:
            guard.check()
            source_fd = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=parent_fd)
            if (os.fstat(source_fd).st_dev, os.fstat(source_fd).st_ino) != (
                before.st_dev,
                before.st_ino,
            ):
                return failure("permission_denied")
            _, attrs = _metadata(source_fd)
        temp_name = ".b12-" + str(uuid4())
        stage_id = backups.stage(
            source_path, str(Path(parent_path) / temp_name), os.fstat(parent_fd), guard
        )
        guard.check()
        temp_fd = os.open(temp_name, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600, dir_fd=parent_fd)
        started = True
        raw = args.text.encode()
        for offset in range(0, len(raw), 16384):
            guard.check()
            view = memoryview(raw[offset : offset + 16384])
            while view:
                count = os.write(temp_fd, view)
                view = view[count:]
            await asyncio.sleep(0)
        guard.check()
        if before:
            guard.check()
            os.fchown(temp_fd, before.st_uid, before.st_gid)
            guard.check()
            os.fchmod(temp_fd, stat.S_IMODE(before.st_mode))
            for name in os.listxattr(temp_fd):
                if name not in attrs:
                    guard.check()
                    os.removexattr(temp_fd, name)
            for name, value in attrs.items():
                guard.check()
                os.setxattr(temp_fd, name, value)
            if stat.S_IMODE(os.fstat(temp_fd).st_mode) != stat.S_IMODE(before.st_mode):
                raise PermissionError("metadata preservation failed")
        os.fsync(temp_fd)
        os.close(temp_fd)
        temp_fd = None
        artifact = await backups.capture(source_fd, source_path, guard) if before else None
        guard.check()
        try:
            current = os.stat(path.name, dir_fd=parent_fd, follow_symlinks=False)
        except FileNotFoundError:
            current = None

        def fingerprint(item):
            return (
                (item.st_dev, item.st_ino, item.st_mtime_ns, item.st_ctime_ns, item.st_size)
                if item
                else None
            )

        if fingerprint(current) != fingerprint(before):
            raise PermissionError("concurrent target change")
        guard.check()
        if before:
            os.replace(temp_name, path.name, src_dir_fd=parent_fd, dst_dir_fd=parent_fd)
            replaced = True
        else:
            os.link(
                temp_name,
                path.name,
                src_dir_fd=parent_fd,
                dst_dir_fd=parent_fd,
                follow_symlinks=False,
            )
            replaced = True
            os.unlink(temp_name, dir_fd=parent_fd)
        temp_name = None
        os.fsync(parent_fd)
        if not cleanup_temp():
            return uncertain("cleanup_failed")
        return HandlerOutcome(
            content={"bytes_written": len(raw), "backup_id": artifact},
            side_effects=(
                SideEffect(
                    kind="file_write",
                    state="completed",
                    artifact_ids=(artifact,) if artifact else (),
                ),
            ),
        )
    except (OSError, ValueError) as exc:
        if not started:
            return failure(exc if isinstance(exc, OSError) else "unsupported")
        return uncertain("handler_failed")
    except (asyncio.CancelledError, ControlError):
        if not started:
            raise
        return uncertain("cancelled")
    finally:
        cleanup_temp()
        for fd in (source_fd, parent_fd):
            if fd is not None:
                os.close(fd)


def register(registry, backups):
    registry.register(
        "file_list", "List bounded directory entries", ListArgs, file_list, "filesystem.read"
    )
    registry.register(
        "file_read",
        "Read bounded UTF-8 or base64 file bytes",
        ReadArgs,
        file_read,
        "filesystem.read",
    )
    registry.register(
        "file_search",
        "Search literal text in bounded regular-file traversal",
        SearchArgs,
        file_search,
        "filesystem.read",
    )

    async def write(args, guard):
        return await file_write(args, guard, backups)

    registry.register(
        "file_write",
        "Atomic reversible write with managed overwrite backup",
        WriteArgs,
        write,
        "filesystem.write",
    )
