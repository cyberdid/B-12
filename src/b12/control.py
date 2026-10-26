"""Private server-owned control state. Methods are trusted control-plane APIs.

Never expose these mutators, resume_turn or credentials to model/client bodies.
Authentication and content-session integration belong to the application factory.
SQLite serializes approval consumption and dispatch. There is no OS sandbox here.
"""

import asyncio
import hashlib
import hmac
import json
import math
import os
import secrets
import sqlite3
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from uuid import uuid4

from b12.contracts import Actor, ToolCall, _json_value

_ERROR_CODES = frozenset(
    {
        "invalid_context",
        "consent_required",
        "grant_revoked",
        "grant_expired",
        "stale_control",
        "cancelled",
        "deadline_exceeded",
        "capability_denied",
        "replay_blocked",
        "approval_denied",
        "approval_expired",
        "approval_mismatch",
        "approval_unavailable",
        "origin_mismatch",
        "unknown_tool",
        "invalid_arguments",
        "cancel_mismatch",
        "operation_not_active",
        "handler_failed",
        "interrupted",
        "invalid_handler_outcome",
    }
)


class ControlError(Exception):
    """Sanitized machine code; never includes input or exception text."""

    def __init__(self, code: str):
        self.code = code if type(code) is str and code in _ERROR_CODES else "handler_failed"
        super().__init__(self.code)


@dataclass(frozen=True, slots=True)
class ExecutionContext:
    actor_id: str
    session_id: str
    turn_id: str
    task_id: str | None
    grant_id: str
    control_revision: int
    deadline: float
    cancel: asyncio.Event = field(repr=False, compare=False)
    credential: str = field(repr=False)


def arguments_digest(arguments: dict) -> str:
    """Exact finite-JSON binding; store only in private expiring approval state."""
    _json_value(arguments)
    data = json.dumps(
        arguments, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    ).encode()
    return hashlib.sha256(data).hexdigest()


_SCHEMA = """
CREATE TABLE IF NOT EXISTS secrets(key BLOB NOT NULL);
CREATE TABLE IF NOT EXISTS actors(id TEXT PRIMARY KEY, owner INTEGER NOT NULL,
 consent INTEGER NOT NULL, revision INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS sessions(id TEXT PRIMARY KEY, actor_id TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS tasks(id TEXT PRIMARY KEY, session_id TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS grants(id TEXT PRIMARY KEY, actor_id TEXT NOT NULL,
 session_id TEXT NOT NULL, task_id TEXT, capabilities TEXT NOT NULL,
 expires_at REAL NOT NULL, revoked INTEGER NOT NULL, full_execution INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS turns(id TEXT PRIMARY KEY, actor_id TEXT NOT NULL,
 session_id TEXT NOT NULL, task_id TEXT, grant_id TEXT NOT NULL,
 revision INTEGER NOT NULL, credential TEXT NOT NULL, cancelled INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS operations(id TEXT PRIMARY KEY, call_key TEXT UNIQUE NOT NULL,
 name TEXT NOT NULL, state TEXT NOT NULL, error_code TEXT, turn_id TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS approvals(operation_id TEXT PRIMARY KEY, digest TEXT,
 capability TEXT NOT NULL, revision INTEGER NOT NULL, expires_at REAL NOT NULL,
 decision TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS audit(sequence INTEGER PRIMARY KEY,
 operation_id TEXT NOT NULL, name TEXT NOT NULL, state TEXT NOT NULL, error_code TEXT);
CREATE TRIGGER IF NOT EXISTS audit_no_update BEFORE UPDATE ON audit
 BEGIN SELECT RAISE(ABORT, 'append only'); END;
CREATE TRIGGER IF NOT EXISTS audit_no_delete BEFORE DELETE ON audit
 BEGIN SELECT RAISE(ABORT, 'append only'); END;
"""


class ControlStore:
    """Dedicated managed directory (0700), DB/journal (0600), same-thread API.

    IDs are server-generated, never names/paths. Permanent audit contains only
    generated operation IDs, trusted registry names and fixed state/error codes.
    Call identity is a keyed control lookup, never an argument/payload hash.
    """

    def __init__(self, path: Path):
        self.path = Path(path).absolute()
        if self.path.is_symlink():
            raise ValueError("control directory cannot be a symlink")
        missing = []
        parent = self.path
        while not parent.exists():
            missing.append(parent)
            parent = parent.parent
        for directory in reversed(missing):
            directory.mkdir(mode=0o700)
        self.path.chmod(0o700)
        db_path = self.path / "control.sqlite3"
        fd = os.open(db_path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        os.fchmod(fd, 0o600)
        os.close(fd)
        self._runtime: dict[str, tuple[float, asyncio.Event]] = {}
        self.db = sqlite3.connect(db_path)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA secure_delete=ON")
        self.db.execute("PRAGMA journal_mode=DELETE")
        self.db.execute("PRAGMA synchronous=FULL")
        self.db.executescript(_SCHEMA)
        with self._atomic():
            if not self.db.execute("SELECT 1 FROM secrets").fetchone():
                self.db.execute("INSERT INTO secrets VALUES (?)", (secrets.token_bytes(32),))
            self._key = self.db.execute("SELECT key FROM secrets").fetchone()[0]
            # Reopening never retries an effect. Conservatively label abandoned starts.
            for row in self.db.execute("SELECT * FROM operations WHERE state='started'").fetchall():
                self._transition(row["id"], "unknown", "interrupted")
            self._expire_approvals()

    @contextmanager
    def _atomic(self):
        self.db.execute("BEGIN IMMEDIATE")
        try:
            yield
            self.db.commit()
        except BaseException:
            self.db.rollback()
            raise

    def close(self):
        self.db.close()

    def create_actor(self, *, owner: bool = False, consent: bool = False) -> Actor:
        actor = Actor(id=str(uuid4()), owner=owner, consent=consent)
        with self._atomic():
            self.db.execute(
                "INSERT INTO actors VALUES (?,?,?,1)", (actor.id, actor.owner, actor.consent)
            )
        return actor

    def actor_ids(self) -> list[str]:
        return [row[0] for row in self.db.execute("SELECT id FROM actors ORDER BY rowid")]

    def resolve_actor(self, actor_id: str) -> Actor:
        row = self.db.execute("SELECT * FROM actors WHERE id=?", (actor_id,)).fetchone()
        if row is None:
            raise ControlError("invalid_context")
        return Actor(id=row["id"], owner=bool(row["owner"]), consent=bool(row["consent"]))

    def create_session(self, actor_id: str) -> str:
        self.resolve_actor(actor_id)
        session = str(uuid4())
        with self._atomic():
            self.db.execute("INSERT INTO sessions VALUES (?,?)", (session, actor_id))
        return session

    def create_task(self, session_id: str) -> str:
        if not self.db.execute("SELECT 1 FROM sessions WHERE id=?", (session_id,)).fetchone():
            raise ControlError("invalid_context")
        task = str(uuid4())
        with self._atomic():
            self.db.execute("INSERT INTO tasks VALUES (?,?)", (task, session_id))
        return task

    def issue_grant(
        self,
        actor_id: str,
        session_id: str,
        capabilities: tuple[str, ...],
        *,
        task_id: str | None = None,
        ttl_s: float = 3600,
        full_execution: bool = False,
    ) -> str:
        actor = self.resolve_actor(actor_id)
        session = self.db.execute(
            "SELECT actor_id FROM sessions WHERE id=?", (session_id,)
        ).fetchone()
        task = self.db.execute("SELECT session_id FROM tasks WHERE id=?", (task_id,)).fetchone()
        if (
            not session
            or session[0] != actor_id
            or (task_id and (not task or task[0] != session_id))
        ):
            raise PermissionError("grant_binding")
        if type(full_execution) is not bool or (
            full_execution and (not task_id or not actor.owner)
        ):
            raise PermissionError("owner_control_required")
        if (
            not isinstance(capabilities, tuple)
            or not capabilities
            or any(type(c) is not str or not c or not c.isascii() for c in capabilities)
        ):
            raise ValueError("invalid capabilities")
        if not math.isfinite(ttl_s) or ttl_s <= 0:
            raise ValueError("invalid expiry")
        grant = str(uuid4())
        with self._atomic():
            self.db.execute(
                "INSERT INTO grants VALUES (?,?,?,?,?,?,0,?)",
                (
                    grant,
                    actor_id,
                    session_id,
                    task_id,
                    json.dumps(capabilities),
                    time.time() + ttl_s,
                    full_execution,
                ),
            )
        return grant

    def set_consent(self, actor_id: str, consent: bool):
        if type(consent) is not bool:
            raise ValueError("consent must be boolean")
        self.resolve_actor(actor_id)
        with self._atomic():
            self.db.execute(
                "UPDATE actors SET consent=?,revision=revision+1 WHERE id=?", (consent, actor_id)
            )

    def revoke_grant(self, grant_id: str):
        with self._atomic():
            self.db.execute("UPDATE grants SET revoked=1 WHERE id=?", (grant_id,))
            self.db.execute(
                "UPDATE actors SET revision=revision+1 WHERE id=("
                "SELECT actor_id FROM grants WHERE id=?)",
                (grant_id,),
            )

    def begin_turn(
        self,
        session_id: str,
        grant_id: str,
        *,
        task_id: str | None = None,
        deadline: float,
        cancel: asyncio.Event | None = None,
    ) -> ExecutionContext:
        session = self.db.execute("SELECT * FROM sessions WHERE id=?", (session_id,)).fetchone()
        grant = self.db.execute("SELECT * FROM grants WHERE id=?", (grant_id,)).fetchone()
        if (
            not session
            or not grant
            or grant["session_id"] != session_id
            or grant["actor_id"] != session["actor_id"]
            or grant["task_id"] != task_id
        ):
            raise PermissionError("grant_binding")
        actor = self.db.execute(
            "SELECT * FROM actors WHERE id=?", (session["actor_id"],)
        ).fetchone()
        turn, token = str(uuid4()), secrets.token_urlsafe(32)
        with self._atomic():
            self.db.execute(
                "INSERT INTO turns VALUES (?,?,?,?,?,?,?,0)",
                (turn, actor["id"], session_id, task_id, grant_id, actor["revision"], token),
            )
        return self._context(turn, deadline, cancel)

    def _context(self, turn_id, deadline, cancel):
        if type(deadline) not in (float, int) or not math.isfinite(deadline):
            raise ValueError("finite monotonic deadline required")
        if cancel is not None and not isinstance(cancel, asyncio.Event):
            raise ValueError("asyncio.Event required")
        row = self.db.execute("SELECT * FROM turns WHERE id=?", (turn_id,)).fetchone()
        if not row:
            raise ControlError("invalid_context")
        event = cancel if cancel is not None else asyncio.Event()
        self._runtime[turn_id] = (deadline, event)
        return ExecutionContext(
            row["actor_id"],
            row["session_id"],
            row["id"],
            row["task_id"],
            row["grant_id"],
            row["revision"],
            deadline,
            event,
            row["credential"],
        )

    def resume_turn(
        self, turn_id: str, *, deadline: float, cancel: asyncio.Event | None = None
    ) -> ExecutionContext:
        """Trusted factory only: retrieve original identity, never refresh revision."""
        return self._context(turn_id, deadline, cancel)

    def check(self, ctx: ExecutionContext, capability: str | None = None) -> sqlite3.Row:
        if type(ctx) is not ExecutionContext:
            raise ControlError("invalid_context")
        runtime = self._runtime.get(ctx.turn_id)
        if runtime is None or runtime[0] != ctx.deadline or runtime[1] is not ctx.cancel:
            raise ControlError("invalid_context")
        turn = self.db.execute("SELECT * FROM turns WHERE id=?", (ctx.turn_id,)).fetchone()
        if not turn or any(
            turn[key] != getattr(ctx, key)
            for key in ("actor_id", "session_id", "task_id", "grant_id")
        ):
            raise ControlError("invalid_context")
        if (
            not hmac.compare_digest(turn["credential"], ctx.credential)
            or turn["revision"] != ctx.control_revision
        ):
            raise ControlError("invalid_context")
        session = self.db.execute(
            "SELECT actor_id FROM sessions WHERE id=?", (ctx.session_id,)
        ).fetchone()
        if not session or session[0] != ctx.actor_id:
            raise ControlError("invalid_context")
        actor = self.db.execute("SELECT * FROM actors WHERE id=?", (ctx.actor_id,)).fetchone()
        grant = self.db.execute("SELECT * FROM grants WHERE id=?", (ctx.grant_id,)).fetchone()
        if (
            not actor
            or not grant
            or (grant["actor_id"], grant["session_id"], grant["task_id"])
            != (ctx.actor_id, ctx.session_id, ctx.task_id)
        ):
            raise ControlError("invalid_context")
        if not actor["consent"]:
            raise ControlError("consent_required")
        if grant["revoked"]:
            raise ControlError("grant_revoked")
        if time.time() >= grant["expires_at"]:
            raise ControlError("grant_expired")
        if actor["revision"] != ctx.control_revision:
            raise ControlError("stale_control")
        if turn["cancelled"] or ctx.cancel.is_set():
            raise ControlError("cancelled")
        if time.monotonic() >= ctx.deadline:
            raise ControlError("deadline_exceeded")
        if capability is not None and capability not in json.loads(grant["capabilities"]):
            raise ControlError("capability_denied")
        return grant

    def _call_key(self, ctx, call):
        identity = json.dumps(
            [ctx.actor_id, ctx.session_id, ctx.turn_id, call.id], separators=(",", ":")
        ).encode()
        return hmac.new(self._key, identity, hashlib.sha256).hexdigest()

    def _transition(self, operation_id, state, code=None):
        self.db.execute(
            "UPDATE operations SET state=?,error_code=? WHERE id=?", (state, code, operation_id)
        )
        row = self.db.execute("SELECT name FROM operations WHERE id=?", (operation_id,)).fetchone()
        self.db.execute(
            "INSERT INTO audit(operation_id,name,state,error_code) VALUES (?,?,?,?)",
            (operation_id, row[0], state, code),
        )

    def _expire_approvals(self):
        now = time.time()
        expired = self.db.execute(
            "SELECT o.id FROM operations o JOIN approvals a ON a.operation_id=o.id "
            "WHERE a.expires_at<=? AND a.decision IN ('pending','approved','expired') "
            "AND o.state IN ('proposed','approved')",
            (now,),
        ).fetchall()
        for row in expired:
            self._transition(row["id"], "failed", "approval_expired")
        self.db.execute(
            "UPDATE approvals SET digest=NULL,decision='expired' "
            "WHERE expires_at<=? AND digest IS NOT NULL",
            (now,),
        )

    def expire_approvals(self):
        """Maintenance hook: erase expired private digests even on rejected dispatch."""
        with self._atomic():
            self._expire_approvals()

    def prepare(
        self,
        ctx: ExecutionContext,
        call: ToolCall,
        capability: str,
        arbitrary: bool,
        *,
        approval_ttl_s: float = 300,
        approval_required: bool = False,
    ) -> tuple[str, str]:
        """Atomic check/propose/approval consumption/start. Never invokes handlers."""
        self.expire_approvals()
        with self._atomic():
            grant = self.check(ctx, capability)
            self._expire_approvals()
            key = self._call_key(ctx, call)
            row = self.db.execute("SELECT * FROM operations WHERE call_key=?", (key,)).fetchone()
            if row and row["state"] not in ("proposed", "approved"):
                raise ControlError(
                    row["error_code"]
                    if row["error_code"] in ("approval_denied", "approval_expired")
                    else "replay_blocked"
                )
            if row and row["name"] != call.name:
                raise ControlError("approval_mismatch")
            operation = row["id"] if row else str(uuid4())
            if not row:
                self.db.execute(
                    "INSERT INTO operations VALUES (?,?,?,'proposed',NULL,?)",
                    (operation, key, call.name, ctx.turn_id),
                )
                self._transition(operation, "proposed")
            needs_approval = approval_required or (
                arbitrary and not (grant["full_execution"] and ctx.task_id)
            )
            if needs_approval:
                approval = self.db.execute(
                    "SELECT * FROM approvals WHERE operation_id=?", (operation,)
                ).fetchone()
                if approval is None:
                    self.db.execute(
                        "INSERT INTO approvals VALUES (?,?,?,?,?,'pending')",
                        (
                            operation,
                            arguments_digest(call.arguments),
                            capability,
                            ctx.control_revision,
                            time.time() + approval_ttl_s,
                        ),
                    )
                    return operation, "approval_pending"
                if approval["decision"] == "denied":
                    raise ControlError("approval_denied")
                if approval["decision"] == "expired":
                    raise ControlError("approval_expired")
                if (
                    approval["digest"] != arguments_digest(call.arguments)
                    or approval["capability"] != capability
                    or approval["revision"] != ctx.control_revision
                ):
                    raise ControlError("approval_mismatch")
                if approval["decision"] != "approved":
                    return operation, "approval_pending"
                self.db.execute(
                    "UPDATE approvals SET digest=NULL,decision='consumed' WHERE operation_id=?",
                    (operation,),
                )
            self.check(ctx, capability)
            self._transition(operation, "started")
            return operation, "started"

    def cancel_turn(self, turn_id: str):
        """Trusted durable cancellation; also erase pending private approvals."""
        with self._atomic():
            self.db.execute("UPDATE turns SET cancelled=1 WHERE id=?", (turn_id,))
            rows = self.db.execute(
                "SELECT id,state FROM operations WHERE turn_id=? "
                "AND state IN ('proposed','approved','started')",
                (turn_id,),
            ).fetchall()
            for row in rows:
                self._transition(
                    row["id"], "unknown" if row["state"] == "started" else "cancelled", "cancelled"
                )
                self.db.execute(
                    "UPDATE approvals SET digest=NULL,decision='cancelled' WHERE operation_id=?",
                    (row["id"],),
                )
        runtime = self._runtime.get(turn_id)
        if runtime:
            runtime[1].set()

    def decide_approval(self, operation_id: str, approve: bool):
        """Authenticated owner control only. No model flag can call this API."""
        if type(approve) is not bool:
            raise ValueError("literal decision required")
        self.expire_approvals()
        with self._atomic():
            row = self.db.execute(
                "SELECT * FROM approvals WHERE operation_id=?", (operation_id,)
            ).fetchone()
            if not row or row["decision"] != "pending":
                raise ControlError("approval_unavailable")
            self.db.execute(
                "UPDATE approvals SET decision=?,digest=CASE WHEN ? THEN digest "
                "ELSE NULL END WHERE operation_id=?",
                ("approved" if approve else "denied", approve, operation_id),
            )
            self._transition(
                operation_id,
                "approved" if approve else "failed",
                None if approve else "approval_denied",
            )

    def finish(self, operation_id: str, state: str, code: str | None = None):
        with self._atomic():
            row = self.db.execute(
                "SELECT state FROM operations WHERE id=?", (operation_id,)
            ).fetchone()
            if row and row[0] == "started":
                self._transition(operation_id, state, code)
                return True
            return False

    def operation(self, ctx: ExecutionContext, call: ToolCall) -> dict | None:
        self.check(ctx)
        row = self.db.execute(
            "SELECT id,name,state,error_code FROM operations WHERE call_key=?",
            (self._call_key(ctx, call),),
        ).fetchone()
        return dict(row) if row else None

    def audit_events(self) -> list[dict]:
        return [
            dict(row)
            for row in self.db.execute(
                "SELECT sequence,operation_id,name,state,error_code FROM audit ORDER BY sequence"
            )
        ]
