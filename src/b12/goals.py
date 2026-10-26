"""Durable goals, proposals and versioned preferences.

Original intent is immutable (SQLite trigger). Budgets are consumed per background
turn and survive restart; exhaustion pauses the goal. "achieved" needs at least one
live evidence ID checked by the shared resolver, never a model claim. Payload rows
carry evidence tags so global purge removes goals/proposals and redacts preference
versions (history keeps version numbers and dates, not the forgotten payload).
"""

import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

STATUSES = frozenset({"active", "paused", "achieved", "abandoned", "failed"})
CHECKS = frozenset({"file_contains"})

_SCHEMA = """
CREATE TABLE IF NOT EXISTS goals(id TEXT PRIMARY KEY, actor_id TEXT NOT NULL,
 session_id TEXT NOT NULL, intent TEXT NOT NULL, criteria TEXT NOT NULL, check_spec TEXT,
 allowed_tools TEXT NOT NULL, status TEXT NOT NULL, status_reason TEXT,
 checkpoint TEXT, budget_turns INTEGER NOT NULL, consumed_turns INTEGER NOT NULL,
 evidence_ids TEXT NOT NULL, tags TEXT NOT NULL, created_at TEXT NOT NULL,
 updated_at TEXT NOT NULL, next_review TEXT NOT NULL, review_interval_s REAL NOT NULL);
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
    ) -> dict:
        if not intent.strip() or len(intent) > 4000 or len(criteria) > 4000:
            raise ValueError("intent/criteria size")
        if type(budget_turns) is not int or not 1 <= budget_turns <= 100:
            raise ValueError("budget must be 1..100 turns")
        if check is not None and (
            not isinstance(check, dict)
            or check.get("kind") not in CHECKS
            or set(check) != {"kind", "path", "text"}
            or not str(check["path"]).startswith("/")
        ):
            raise ValueError("unsupported trusted check")
        goal_id, now = str(uuid4()), _now()
        with self._atomic():
            self.db.execute(
                "INSERT INTO goals VALUES (?,?,?,?,?,?,?,'active',NULL,NULL,?,0,'[]',?,?,?,?,?)",
                (
                    goal_id,
                    actor_id,
                    session_id,
                    intent,
                    criteria,
                    json.dumps(check) if check else None,
                    json.dumps(list(allowed_tools)),
                    budget_turns,
                    json.dumps(tags or {}),
                    now,
                    now,
                    now,
                    float(review_interval_s),
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
                "AND consumed_turns<budget_turns ORDER BY next_review",
                (now.astimezone(UTC).isoformat(),),
            )
        ]

    def checkpoint(self, goal_id: str, actor_id: str, text: str, next_review: datetime):
        """Consume one turn of budget; exhaustion pauses the goal durably."""
        with self._atomic():
            goal = self.get(goal_id, actor_id)
            if goal is None or goal["status"] != "active":
                raise PermissionError("goal is not active")
            consumed = goal["consumed_turns"] + 1
            exhausted = consumed >= goal["budget_turns"]
            self.db.execute(
                "UPDATE goals SET checkpoint=?, consumed_turns=?, next_review=?, updated_at=?, "
                "status=?, status_reason=? WHERE id=?",
                (
                    text[:4000],
                    consumed,
                    next_review.astimezone(UTC).isoformat(),
                    _now(),
                    "paused" if exhausted else "active",
                    "budget_exhausted" if exhausted else None,
                    goal_id,
                ),
            )
        return self.get(goal_id, actor_id)

    def set_status(self, goal_id: str, actor_id: str, status: str, reason: str):
        if status not in STATUSES - {"achieved"}:
            raise ValueError("use complete() for achieved")
        with self._atomic():
            if not self.get(goal_id, actor_id):
                raise KeyError("goal not found")
            self.db.execute(
                "UPDATE goals SET status=?, status_reason=?, updated_at=? WHERE id=?",
                (status, reason[:200], _now(), goal_id),
            )
        return self.get(goal_id, actor_id)

    def complete(self, goal_id: str, actor, evidence_ids, live) -> dict:
        evidence = _ids(evidence_ids)
        if not evidence or not all(live(e) for e in evidence):
            raise PermissionError("achieved requires live verified evidence")
        with self._atomic():
            goal = self.get(goal_id, actor.id)
            if goal is None:
                raise KeyError("goal not found")
            self.db.execute(
                "UPDATE goals SET status='achieved', status_reason='verified_evidence', "
                "evidence_ids=?, updated_at=? WHERE id=?",
                (json.dumps(evidence), _now(), goal_id),
            )
        return self.get(goal_id, actor.id)

    def add_proposal(self, actor_id, goal_id, text, *, delivered, reason, attention_id, tags):
        proposal = str(uuid4())
        self.db.execute(
            "INSERT INTO proposals VALUES (?,?,?,?,?,?,?,?,?)",
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
            ),
        )
        return proposal

    def proposals(self, actor_id: str, *, limit: int = 50) -> list[dict]:
        return [
            dict(row)
            for row in self.db.execute(
                "SELECT id, goal_id, text, created_at, delivered, reason, attention_id "
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
