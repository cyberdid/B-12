"""Durable goals, proposals and versioned preferences.

Original intent is immutable (SQLite trigger). Budgets are consumed per background
turn and survive restart; exhaustion pauses the goal. "achieved" needs at least one
live evidence ID checked by the shared resolver, never a model claim. Payload rows
carry evidence tags so global purge removes goals/proposals and redacts preference
versions (history keeps version numbers and dates, not the forgotten payload).
"""

import json
import os
import re
import sqlite3
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlsplit
from uuid import UUID, uuid4

STATUSES = frozenset({"active", "paused", "achieved", "abandoned", "failed"})
CHECKS = frozenset({"file_contains", "file_sha256", "command_exit_zero", "http_status"})
_CONTRACT_KEYS = frozenset({"verification", "constraints", "boundaries", "stop_when"})
_BOUNDARY_KEYS = frozenset({"tools", "paths"})

_SCHEMA = """
CREATE TABLE IF NOT EXISTS goals(id TEXT PRIMARY KEY, actor_id TEXT NOT NULL,
 session_id TEXT NOT NULL, intent TEXT NOT NULL, criteria TEXT NOT NULL, check_spec TEXT,
 allowed_tools TEXT NOT NULL, status TEXT NOT NULL, status_reason TEXT,
 checkpoint TEXT, budget_turns INTEGER NOT NULL, consumed_turns INTEGER NOT NULL,
 evidence_ids TEXT NOT NULL, tags TEXT NOT NULL, created_at TEXT NOT NULL,
 updated_at TEXT NOT NULL, next_review TEXT NOT NULL, review_interval_s REAL NOT NULL,
 contract TEXT, failure_streak INTEGER NOT NULL DEFAULT 0);
CREATE TRIGGER IF NOT EXISTS goals_intent_immutable BEFORE UPDATE OF intent, criteria,
 actor_id ON goals BEGIN SELECT RAISE(ABORT, 'original intent is immutable'); END;
CREATE TABLE IF NOT EXISTS proposals(id TEXT PRIMARY KEY, actor_id TEXT NOT NULL,
 goal_id TEXT, text TEXT NOT NULL, created_at TEXT NOT NULL, delivered INTEGER NOT NULL,
 reason TEXT NOT NULL, attention_id TEXT, tags TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS preferences(id TEXT PRIMARY KEY, actor_id TEXT NOT NULL,
 key TEXT NOT NULL, version INTEGER NOT NULL, value TEXT, reason TEXT,
 evidence_ids TEXT NOT NULL, created_at TEXT NOT NULL, redacted INTEGER NOT NULL,
 UNIQUE(actor_id, key, version));
"""


def _validate_check(check: dict) -> dict:
    if not isinstance(check, dict):
        raise ValueError("unsupported trusted check")
    kind = check.get("kind")
    if kind not in CHECKS:
        raise ValueError("unsupported trusted check")
    if kind == "file_contains":
        if (
            set(check) != {"kind", "path", "text"}
            or not isinstance(check["path"], str)
            or not check["path"].startswith("/")
            or "\x00" in check["path"]
            or not isinstance(check["text"], str)
        ):
            raise ValueError("unsupported trusted check")
        return dict(check)
    if kind == "file_sha256":
        if (
            set(check) != {"kind", "path", "sha256"}
            or not isinstance(check["path"], str)
            or not check["path"].startswith("/")
            or "\x00" in check["path"]
            or not isinstance(check["sha256"], str)
            or not re.fullmatch(r"[0-9a-fA-F]{64}", check["sha256"])
        ):
            raise ValueError("unsupported trusted check")
        return {"kind": "file_sha256", "path": check["path"], "sha256": check["sha256"].lower()}
    if kind == "command_exit_zero":
        argv = check.get("argv")
        if (
            set(check) != {"kind", "argv"}
            or not isinstance(argv, (list, tuple))
            or not argv
            or not all(isinstance(arg, str) and "\x00" not in arg for arg in argv)
            or not argv[0]
        ):
            raise ValueError("unsupported trusted check")
        return {"kind": "command_exit_zero", "argv": list(argv)}
    # http_status
    url = check.get("url")
    status = check.get("status")
    if (
        set(check) != {"kind", "url", "status"}
        or not isinstance(url, str)
        or any(ord(c) < 32 or ord(c) == 127 for c in url)
        or type(status) is not int
        or not 100 <= status <= 599
    ):
        raise ValueError("unsupported trusted check")
    parsed = urlsplit(url)
    if (
        parsed.scheme not in ("http", "https")
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.fragment
    ):
        raise ValueError("unsupported trusted check")
    _ = parsed.port
    return {"kind": "http_status", "url": url, "status": status}


def _validate_contract(contract: dict) -> dict:
    if not isinstance(contract, dict) or not set(contract) <= _CONTRACT_KEYS:
        raise ValueError("unsupported goal contract")
    normalized: dict = {}
    if "verification" in contract and contract["verification"] is not None:
        verification = contract["verification"]
        if isinstance(verification, dict):
            normalized["verification"] = _validate_check(verification)
        elif isinstance(verification, str) and len(verification) <= 2000:
            normalized["verification"] = verification
        else:
            raise ValueError("invalid contract verification")
    if "constraints" in contract and contract["constraints"] is not None:
        constraints = contract["constraints"]
        if isinstance(constraints, str) and len(constraints) <= 2000:
            normalized["constraints"] = constraints
        elif isinstance(constraints, (list, tuple)) and all(
            isinstance(item, str) and len(item) <= 2000 for item in constraints
        ):
            normalized["constraints"] = list(constraints)
        else:
            raise ValueError("invalid contract constraints")
    if "boundaries" in contract and contract["boundaries"] is not None:
        boundaries = contract["boundaries"]
        if not isinstance(boundaries, dict) or not set(boundaries) <= _BOUNDARY_KEYS:
            raise ValueError("invalid contract boundaries")
        clean_bounds: dict = {}
        if "tools" in boundaries and boundaries["tools"] is not None:
            tools = boundaries["tools"]
            if not isinstance(tools, (list, tuple)) or not all(
                isinstance(name, str) and name for name in tools
            ):
                raise ValueError("invalid boundary tools")
            clean_bounds["tools"] = list(tools)
        if "paths" in boundaries and boundaries["paths"] is not None:
            paths = boundaries["paths"]
            if not isinstance(paths, (list, tuple)) or not all(
                isinstance(p, str) and p.startswith("/") and "\x00" not in p for p in paths
            ):
                raise ValueError("invalid boundary paths")
            clean_bounds["paths"] = list(paths)
        normalized["boundaries"] = clean_bounds
    if "stop_when" in contract and contract["stop_when"] is not None:
        stop_when = contract["stop_when"]
        if isinstance(stop_when, str) and len(stop_when) <= 2000:
            normalized["stop_when"] = stop_when
        elif isinstance(stop_when, (list, tuple)) and all(
            isinstance(item, str) and len(item) <= 2000 for item in stop_when
        ):
            normalized["stop_when"] = list(stop_when)
        else:
            raise ValueError("invalid contract stop_when")
    return normalized


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _ids(values) -> list[str]:
    result = list(values)
    for value in result:
        UUID(value)
    return result


class GoalStore:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.path.chmod(0o700)
        db = self.path / "goals.sqlite3"
        fd = os.open(db, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        os.close(fd)
        self.db = sqlite3.connect(db, isolation_level=None)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA secure_delete=ON")
        self.db.execute("PRAGMA journal_mode=DELETE")
        self.db.execute("PRAGMA synchronous=FULL")
        self.db.executescript(_SCHEMA)
        columns = {row[1] for row in self.db.execute("PRAGMA table_info(goals)")}
        if "priority" not in columns:  # databases created before goal priorities
            self.db.execute("ALTER TABLE goals ADD COLUMN priority INTEGER NOT NULL DEFAULT 0")
        proposal_columns = {row[1] for row in self.db.execute("PRAGMA table_info(proposals)")}
        for column in ("decision", "dedupe_key", "not_before", "expires_at"):
            if column not in proposal_columns:  # ADR-018 initiative gate
                self.db.execute(f"ALTER TABLE proposals ADD COLUMN {column} TEXT")
        self.db.execute(
            "CREATE TABLE IF NOT EXISTS muted_goals(goal_id TEXT PRIMARY KEY, "
            "actor_id TEXT NOT NULL)"
        )
        if "plan_revision" not in columns:  # ADR-017: effects are keyed per plan revision
            self.db.execute("ALTER TABLE goals ADD COLUMN plan_revision INTEGER NOT NULL DEFAULT 1")
        if "contract" not in columns:  # ADR-019: immutable goal completion contract
            self.db.execute("ALTER TABLE goals ADD COLUMN contract TEXT")
        if "failure_streak" not in columns:  # ADR-019: consecutive check failure streak
            self.db.execute(
                "ALTER TABLE goals ADD COLUMN failure_streak INTEGER NOT NULL DEFAULT 0"
            )
        trigger = self.db.execute(
            "SELECT sql FROM sqlite_master WHERE type='trigger' AND name='goals_intent_immutable'"
        ).fetchone()
        if trigger is None or "contract" not in trigger[0]:
            self.db.execute("DROP TRIGGER IF EXISTS goals_intent_immutable")
            self.db.execute(
                "CREATE TRIGGER goals_intent_immutable BEFORE UPDATE OF intent, criteria, "
                "actor_id, contract ON goals BEGIN SELECT RAISE(ABORT, "
                "'original intent is immutable'); END"
            )

    def close(self):
        self.db.close()

    @contextmanager
    def _atomic(self):
        self.db.execute("BEGIN IMMEDIATE")
        try:
            yield
            self.db.execute("COMMIT")
        except BaseException:
            self.db.execute("ROLLBACK")
            raise

    @staticmethod
    def _goal(row) -> dict:
        goal = dict(row)
        for key in ("allowed_tools", "evidence_ids", "tags"):
            goal[key] = json.loads(goal[key])
        goal["check_spec"] = json.loads(goal["check_spec"]) if goal["check_spec"] else None
        goal["contract"] = json.loads(goal["contract"]) if goal.get("contract") else None
        goal.setdefault("failure_streak", 0)
        return goal

    def create(
        self,
        actor_id: str,
        session_id: str,
        intent: str,
        criteria: str,
        *,
        allowed_tools: tuple[str, ...] = (),
        budget_turns: int = 5,
        review_interval_s: float = 3600,
        check: dict | None = None,
        tags: dict | None = None,
        priority: int = 0,
        contract: dict | None = None,
    ) -> dict:
        if not intent.strip() or len(intent) > 4000 or len(criteria) > 4000:
            raise ValueError("intent/criteria size")
        if type(budget_turns) is not int or not 1 <= budget_turns <= 100:
            raise ValueError("budget must be 1..100 turns")
        if type(priority) is not int or not 0 <= priority <= 10:
            raise ValueError("priority must be 0..10")
        normalized_check = _validate_check(check) if check is not None else None
        normalized_contract = _validate_contract(contract) if contract is not None else None
        goal_id, now = str(uuid4()), _now()
        with self._atomic():
            self.db.execute(
                # Named columns: priority, plan_revision, contract and failure_streak may sit in
                # any order in older files.
                "INSERT INTO goals(id, actor_id, session_id, intent, criteria, check_spec, "
                "allowed_tools, status, status_reason, checkpoint, budget_turns, consumed_turns, "
                "evidence_ids, tags, created_at, updated_at, next_review, review_interval_s, "
                "priority, plan_revision, contract, failure_streak) VALUES "
                "(?,?,?,?,?,?,?,'active',NULL,NULL,?,0,'[]',?,?,?,?,?,?,1,?,0)",
                (
                    goal_id,
                    actor_id,
                    session_id,
                    intent,
                    criteria,
                    json.dumps(normalized_check) if normalized_check is not None else None,
                    json.dumps(list(allowed_tools)),
                    budget_turns,
                    json.dumps(tags or {}),
                    now,
                    now,
                    now,
                    float(review_interval_s),
                    priority,
                    json.dumps(normalized_contract) if normalized_contract is not None else None,
                ),
            )
        return self.get(goal_id, actor_id)

    def get(self, goal_id: str, actor_id: str) -> dict | None:
        row = self.db.execute(
            "SELECT * FROM goals WHERE id=? AND actor_id=?", (goal_id, actor_id)
        ).fetchone()
        return self._goal(row) if row else None

    def for_actor(self, actor_id: str) -> list[dict]:
        return [
            self._goal(row)
            for row in self.db.execute(
                "SELECT * FROM goals WHERE actor_id=? ORDER BY created_at", (actor_id,)
            )
        ]

    def due(self, now: datetime) -> list[dict]:
        return [
            self._goal(row)
            for row in self.db.execute(
                "SELECT * FROM goals WHERE status='active' AND next_review<=? "
                "AND consumed_turns<budget_turns ORDER BY priority DESC, next_review",
                (now.astimezone(UTC).isoformat(),),
            )
        ]

    def checkpoint(
        self,
        goal_id: str,
        actor_id: str,
        text: str,
        next_review: datetime,
        *,
        evidence_ids=(),
    ):
        """Consume one turn of budget; exhaustion pauses the goal durably.

        The evidence the checkpoint was built from is kept on the goal, so forgetting
        any of those memories purges the goal and its checkpoint text as well.
        """
        with self._atomic():
            goal = self.get(goal_id, actor_id)
            if goal is None or goal["status"] != "active":
                raise PermissionError("goal is not active")
            consumed = goal["consumed_turns"] + 1
            exhausted = consumed >= goal["budget_turns"]
            merged = sorted(set(goal["evidence_ids"]) | set(evidence_ids))
            self.db.execute(
                "UPDATE goals SET checkpoint=?, consumed_turns=?, next_review=?, updated_at=?, "
                "status=?, status_reason=?, evidence_ids=? WHERE id=?",
                (
                    text[:4000],
                    consumed,
                    next_review.astimezone(UTC).isoformat(),
                    _now(),
                    "paused" if exhausted else "active",
                    "budget_exhausted" if exhausted else None,
                    json.dumps(merged),
                    goal_id,
                ),
            )
        return self.get(goal_id, actor_id)

    def set_status(
        self, goal_id: str, actor_id: str, status: str, reason: str, *, reopen: bool = False
    ):
        if status not in STATUSES - {"achieved"}:
            raise ValueError("use complete() for achieved")
        with self._atomic():
            goal = self.get(goal_id, actor_id)
            if not goal:
                raise KeyError("goal not found")
            if (
                goal["status"] in {"achieved", "abandoned"}
                and status != goal["status"]
                and not reopen
            ):
                raise PermissionError("reopening a closed goal requires explicit owner control")
            # ADR-017: an owner reopening is a replan; effects of the old plan are not reused.
            replan = 1 if reopen and goal["status"] in {"achieved", "abandoned"} else 0
            reset_streak = status == "active" and goal["status"] != "active"
            if reset_streak:
                self.db.execute(
                    "UPDATE goals SET status=?, status_reason=?, updated_at=?, "
                    "plan_revision=plan_revision+?, failure_streak=0 WHERE id=?",
                    (status, reason[:200], _now(), replan, goal_id),
                )
            else:
                self.db.execute(
                    "UPDATE goals SET status=?, status_reason=?, updated_at=?, "
                    "plan_revision=plan_revision+? WHERE id=?",
                    (status, reason[:200], _now(), replan, goal_id),
                )
        return self.get(goal_id, actor_id)

    def record_check(self, goal_id: str, passed: bool, *, actor_id: str | None = None) -> int:
        """Record a trusted check outcome and return the updated consecutive failure streak."""
        with self._atomic():
            if actor_id is not None:
                row = self.db.execute(
                    "SELECT failure_streak FROM goals WHERE id=? AND actor_id=?",
                    (goal_id, actor_id),
                ).fetchone()
            else:
                row = self.db.execute(
                    "SELECT failure_streak FROM goals WHERE id=?", (goal_id,)
                ).fetchone()
            if row is None:
                raise KeyError("goal not found")
            streak = 0 if passed else int(row["failure_streak"]) + 1
            self.db.execute(
                "UPDATE goals SET failure_streak=?, updated_at=? WHERE id=?",
                (streak, _now(), goal_id),
            )
        return streak

    def complete(self, goal_id: str, actor, evidence_ids, live) -> dict:
        goal = self.get(goal_id, actor.id)
        if goal is None:
            raise KeyError("goal not found")
        if goal["status"] == "abandoned":
            raise PermissionError("an abandoned goal requires explicit owner reopening")
        evidence = _ids(evidence_ids)
        if not evidence or not all(live(e) for e in evidence):
            raise PermissionError("achieved requires live verified evidence")
        with self._atomic():
            goal = self.get(goal_id, actor.id)
            if goal is None:
                raise KeyError("goal not found")
            if goal["status"] == "abandoned":
                raise PermissionError("an abandoned goal requires explicit owner reopening")
            self.db.execute(
                "UPDATE goals SET status='achieved', status_reason='verified_evidence', "
                "evidence_ids=?, updated_at=? WHERE id=?",
                (json.dumps(evidence), _now(), goal_id),
            )
        return self.get(goal_id, actor.id)

    def add_proposal(
        self,
        actor_id,
        goal_id,
        text,
        *,
        delivered,
        reason,
        attention_id,
        tags,
        decision=None,
        dedupe_key=None,
        not_before=None,
        expires_at=None,
    ):
        proposal = str(uuid4())
        self.db.execute(
            "INSERT INTO proposals(id, actor_id, goal_id, text, created_at, delivered, reason, "
            "attention_id, tags, decision, dedupe_key, not_before, expires_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                proposal,
                actor_id,
                goal_id,
                text[:4000],
                _now(),
                delivered,
                reason,
                attention_id,
                json.dumps(tags or {}),
                decision,
                dedupe_key,
                not_before.astimezone(UTC).isoformat() if not_before else None,
                expires_at.astimezone(UTC).isoformat() if expires_at else None,
            ),
        )
        return proposal

    # ADR-018 initiative gate support.
    def recent_proposal_keys(self, actor_id: str, since: datetime) -> tuple:
        return tuple(
            (row[0], datetime.fromisoformat(row[1]))
            for row in self.db.execute(
                "SELECT dedupe_key, created_at FROM proposals WHERE actor_id=? "
                "AND dedupe_key IS NOT NULL AND decision IN ('deliver','inbox','defer',"
                "'needs_owner') AND created_at>=?",
                (actor_id, since.astimezone(UTC).isoformat()),
            )
        )

    def due_deferred(self, actor_id: str, now: datetime) -> list[dict]:
        return [
            dict(row)
            for row in self.db.execute(
                "SELECT id, goal_id, expires_at FROM proposals WHERE actor_id=? "
                "AND decision='defer' AND not_before<=?",
                (actor_id, now.astimezone(UTC).isoformat()),
            )
        ]

    def settle_proposal(self, proposal_id, *, decision, reason, delivered, attention_id=None):
        self.db.execute(
            "UPDATE proposals SET decision=?, reason=?, delivered=?, attention_id=? WHERE id=?",
            (decision, reason, delivered, attention_id, proposal_id),
        )

    def set_muted(self, goal_id: str, actor_id: str, muted: bool) -> None:
        if muted:
            self.db.execute("INSERT OR REPLACE INTO muted_goals VALUES (?,?)", (goal_id, actor_id))
        else:
            self.db.execute("DELETE FROM muted_goals WHERE goal_id=?", (goal_id,))

    def is_muted(self, goal_id: str) -> bool:
        return bool(
            self.db.execute("SELECT 1 FROM muted_goals WHERE goal_id=?", (goal_id,)).fetchone()
        )

    def proposals(self, actor_id: str, *, limit: int = 50) -> list[dict]:
        return [
            dict(row)
            for row in self.db.execute(
                "SELECT id, goal_id, text, created_at, delivered, reason, attention_id, decision "
                "FROM proposals WHERE actor_id=? ORDER BY created_at DESC LIMIT ?",
                (actor_id, limit),
            )
        ]

    def set_preference(self, actor_id, key, value, reason, evidence_ids=()) -> dict:
        if not key or len(key) > 128 or not reason.strip():
            raise ValueError("preference requires a key and a reason")
        evidence = _ids(evidence_ids)
        with self._atomic():
            version = (
                self.db.execute(
                    "SELECT MAX(version) FROM preferences WHERE actor_id=? AND key=?",
                    (actor_id, key),
                ).fetchone()[0]
                or 0
            ) + 1
            self.db.execute(
                "INSERT INTO preferences VALUES (?,?,?,?,?,?,?,?,0)",
                (
                    str(uuid4()),
                    actor_id,
                    key,
                    version,
                    value,
                    reason,
                    json.dumps(evidence),
                    _now(),
                ),
            )
        return self.preference_history(actor_id, key)[-1]

    def current_preferences(self, actor_id, limit: int = 16) -> dict[str, str]:
        """The latest live value of each preference key of this actor (newest keys first)."""
        rows = self.db.execute(
            "SELECT p.key, p.value FROM preferences p WHERE p.actor_id=? AND p.redacted=0 "
            "AND p.version=(SELECT MAX(q.version) FROM preferences q "
            "WHERE q.actor_id=p.actor_id AND q.key=p.key) ORDER BY p.created_at DESC LIMIT ?",
            (actor_id, limit),
        ).fetchall()
        return {row["key"]: row["value"] for row in rows if row["value"] is not None}

    def preference_history(self, actor_id, key) -> list[dict]:
        return [
            {**dict(row), "evidence_ids": json.loads(row["evidence_ids"])}
            for row in self.db.execute(
                "SELECT key, version, value, reason, evidence_ids, created_at, redacted "
                "FROM preferences WHERE actor_id=? AND key=? ORDER BY version",
                (actor_id, key),
            )
        ]

    def current_preference(self, actor_id, key) -> dict | None:
        live = [p for p in self.preference_history(actor_id, key) if not p["redacted"]]
        return live[-1] if live else None

    def pause_for_stale_evidence(self, actor_id: str, evidence_ids) -> list[str]:
        """Pause active goals whose evidence went stale; the owner reviews and may resume."""
        targets = set(evidence_ids)
        if not targets:
            return []
        with self._atomic():
            paused = [
                row["id"]
                for row in self.db.execute(
                    "SELECT id, evidence_ids FROM goals WHERE actor_id=? AND status='active'",
                    (actor_id,),
                )
                if targets & set(json.loads(row["evidence_ids"]))
            ]
            for goal_id in paused:
                self.db.execute(
                    "UPDATE goals SET status='paused', status_reason='evidence_stale',"
                    " updated_at=? WHERE id=?",
                    (_now(), goal_id),
                )
        return paused

    def purge_evidence(self, actor_id: str, evidence_ids) -> dict:
        """Idempotent purge hook: delete tagged goals/proposals, redact preferences."""
        targets = set(evidence_ids)
        with self._atomic():
            goals = [
                row["id"]
                for row in self.db.execute(
                    "SELECT id, tags, evidence_ids FROM goals WHERE actor_id=?", (actor_id,)
                )
                if targets & (set(json.loads(row["tags"])) | set(json.loads(row["evidence_ids"])))
            ]
            for goal_id in goals:
                self.db.execute("DELETE FROM goals WHERE id=?", (goal_id,))
                self.db.execute("DELETE FROM proposals WHERE goal_id=?", (goal_id,))
            proposals = [
                row["id"]
                for row in self.db.execute(
                    "SELECT id, tags FROM proposals WHERE actor_id=?", (actor_id,)
                )
                if targets & set(json.loads(row["tags"]))
            ]
            for proposal in proposals:
                self.db.execute("DELETE FROM proposals WHERE id=?", (proposal,))
            redacted = [
                row["id"]
                for row in self.db.execute(
                    "SELECT id, evidence_ids FROM preferences WHERE actor_id=? AND redacted=0",
                    (actor_id,),
                )
                if targets & set(json.loads(row["evidence_ids"]))
            ]
            for preference in redacted:
                self.db.execute(
                    "UPDATE preferences SET value=NULL, reason=NULL, evidence_ids='[]', "
                    "redacted=1 WHERE id=?",
                    (preference,),
                )
        return {"goals": goals, "proposals": proposals, "preferences": redacted}
