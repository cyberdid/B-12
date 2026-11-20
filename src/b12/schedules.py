"""ADR-022 owner schedules: wall-clock occurrence math and durable run ledger.

Schedules live in `goals.sqlite3` alongside goals and proposals. Claims insert into
`schedule_runs` with PRIMARY KEY (schedule_id, occurrence), so restarts never execute
one occurrence twice and `unknown` outcomes are never blindly retried.
"""

from __future__ import annotations

import json
import os
import re
import sqlite3
from contextlib import contextmanager
from datetime import UTC, datetime, time, timedelta
from pathlib import Path
from uuid import uuid4
from zoneinfo import ZoneInfo

from b12.audio.voice_guards import normalize

_TIME_RE = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)$")
_RETRY_DELAYS_MIN = (5, 15, 30)
_MIN_CATCHUP = timedelta(minutes=2)
_MAX_CATCHUP = timedelta(hours=2)
_STATUSES = frozenset({"active", "paused", "completed"})
_OUTCOMES = frozenset(
    {
        "started",
        "completed",
        "silent",
        "missed",
        "unknown",
        "failed",
        "transport_failed",
        "cancelled",
        "paused",
    }
)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS schedules(
 id TEXT PRIMARY KEY,
 actor_id TEXT NOT NULL,
 session_id TEXT NOT NULL,
 spec TEXT NOT NULL,
 prompt TEXT NOT NULL,
 tz TEXT NOT NULL,
 allowed_tools TEXT NOT NULL,
 budget_turns INTEGER NOT NULL DEFAULT 1,
 status TEXT NOT NULL DEFAULT 'active',
 status_reason TEXT,
 next_run TEXT,
 retry_at TEXT,
 retry_count INTEGER NOT NULL DEFAULT 0,
 failure_streak INTEGER NOT NULL DEFAULT 0,
 last_run_at TEXT,
 last_outcome TEXT,
 tags TEXT NOT NULL DEFAULT '{}',
 created_at TEXT NOT NULL,
 updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS schedules_due ON schedules(status, next_run, retry_at);
CREATE TABLE IF NOT EXISTS schedule_runs(
 schedule_id TEXT NOT NULL,
 occurrence TEXT NOT NULL,
 outcome TEXT NOT NULL,
 turn_id TEXT,
 error_code TEXT,
 claimed_at TEXT NOT NULL,
 finished_at TEXT,
 PRIMARY KEY(schedule_id, occurrence)
);
CREATE TABLE IF NOT EXISTS intents(
 id TEXT PRIMARY KEY,
 actor_id TEXT NOT NULL,
 keywords TEXT NOT NULL,
 text TEXT NOT NULL,
 expires_at TEXT NOT NULL,
 fires_left INTEGER NOT NULL DEFAULT 3,
 cooldown_s INTEGER NOT NULL DEFAULT 86400,
 last_fired_at TEXT,
 status TEXT NOT NULL DEFAULT 'active',
 created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS intents_actor ON intents(actor_id, status);
"""


def _clock() -> datetime:
    return datetime.now(UTC)


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ValueError("timezone-aware datetime required")
    return value


def validate_spec(spec: dict) -> dict:
    """Validate and normalize a schedule specification without external cron dependencies."""
    if not isinstance(spec, dict):
        raise ValueError("schedule spec must be a dict")
    kind = spec.get("kind")
    if kind == "daily":
        raw_time = spec.get("time")
        if not isinstance(raw_time, str) or not _TIME_RE.fullmatch(raw_time):
            raise ValueError("daily schedule requires time in HH:MM format")
        raw_weekdays = spec.get("weekdays")
        if raw_weekdays is None:
            weekdays = [0, 1, 2, 3, 4, 5, 6]
        else:
            if not isinstance(raw_weekdays, list | tuple) or not raw_weekdays:
                raise ValueError("daily schedule weekdays must be a non-empty list of 0..6")
            if any(type(day) is not int or not 0 <= day <= 6 for day in raw_weekdays):
                raise ValueError("weekdays must be integers 0..6")
            weekdays = sorted(set(raw_weekdays))
        return {"kind": "daily", "time": raw_time, "weekdays": weekdays}
    if kind == "once":
        raw_at = spec.get("at")
        if not isinstance(raw_at, str) or not raw_at.strip():
            raise ValueError("once schedule requires an ISO datetime in 'at'")
        parsed = datetime.fromisoformat(raw_at)
        if parsed.tzinfo is None and "T" not in raw_at and " " not in raw_at:
            raise ValueError("once schedule 'at' must include time")
        return {"kind": "once", "at": raw_at}
    if kind == "interval":
        minutes = spec.get("minutes")
        if type(minutes) is not int or minutes < 1:
            raise ValueError("interval schedule requires integer minutes >= 1")
        return {"kind": "interval", "minutes": minutes}
    raise ValueError(f"unsupported schedule kind: {kind!r}")


def next_occurrence(spec: dict, after: datetime, tz: str) -> datetime | None:
    """Compute the next wall-clock occurrence strictly after `after` in `ZoneInfo(tz)`."""
    _aware(after)
    zone = ZoneInfo(tz)
    kind = spec.get("kind") if isinstance(spec, dict) else None
    after_utc = after.astimezone(UTC)
    if kind == "daily":
        normalized = validate_spec(
            {**spec, "weekdays": spec.get("weekdays", [0, 1, 2, 3, 4, 5, 6])}
        )
        if not spec.get("weekdays", [0]):
            return None
        weekdays = set(normalized["weekdays"])
        hh, mm = map(int, normalized["time"].split(":"))
        target_time = time(hh, mm)
        local_after = after.astimezone(zone)
        for offset in range(15):
            day = local_after.date() + timedelta(days=offset)
            if day.weekday() not in weekdays:
                continue
            cand = datetime.combine(day, target_time, tzinfo=zone)
            # Normalize spring-forward gaps while keeping exact wall clock on normal/DST days.
            resolved = cand.astimezone(UTC).astimezone(zone)
            if resolved.astimezone(UTC) > after_utc:
                return resolved
        return None
    if kind == "once":
        normalized = validate_spec(spec)
        at = datetime.fromisoformat(normalized["at"])
        if at.tzinfo is None:
            at = at.replace(tzinfo=zone)
        else:
            at = at.astimezone(zone)
        return at if at.astimezone(UTC) > after_utc else None
    if kind == "interval":
        normalized = validate_spec(spec)
        # Interval schedules count true elapsed UTC minutes, avoiding DST wall-clock jumps.
        return (after_utc + timedelta(minutes=normalized["minutes"])).astimezone(zone)
    raise ValueError(f"unsupported schedule kind: {kind!r}")


def catchup_window(spec: dict) -> timedelta:
    """Catch-up limit: clamp(period / 2, 2 min, 2 h)."""
    kind = spec.get("kind")
    if kind == "interval":
        period = timedelta(minutes=spec["minutes"])
        return max(_MIN_CATCHUP, min(_MAX_CATCHUP, period / 2))
    return _MAX_CATCHUP


class ScheduleStore:
    def __init__(self, path: Path, *, clock=_clock):
        self.clock = clock
        target = Path(path)
        if target.suffix == ".sqlite3":
            self.path = target.parent
            db = target
        else:
            self.path = target
            db = self.path / "goals.sqlite3"
        self.path.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.path.chmod(0o700)
        fd = os.open(db, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        os.close(fd)
        self.db = sqlite3.connect(db, isolation_level=None)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA busy_timeout=5000")
        self.db.execute("PRAGMA secure_delete=ON")
        self.db.execute("PRAGMA journal_mode=DELETE")
        self.db.execute("PRAGMA synchronous=FULL")
        self.db.executescript(_SCHEMA)
        with self._atomic():
            now_iso = _aware(self.clock()).astimezone(UTC).isoformat()
            # Crashed runs left in 'started' become 'unknown' and are never retried.
            self.db.execute(
                "UPDATE schedule_runs SET outcome='unknown', finished_at=COALESCE(finished_at, ?) "
                "WHERE outcome='started'",
                (now_iso,),
            )

    def close(self) -> None:
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
    def _row(row) -> dict:
        item = dict(row)
        item["spec"] = json.loads(item["spec"])
        item["allowed_tools"] = json.loads(item["allowed_tools"])
        item["tags"] = json.loads(item["tags"])
        return item

    def _now_iso(self, now: datetime | None = None) -> str:
        ts = self.clock() if now is None else now
        return _aware(ts).astimezone(UTC).isoformat()

    def add(
        self,
        actor_id: str,
        session_id: str,
        spec: dict,
        prompt: str,
        *,
        tz: str,
        allowed_tools: tuple[str, ...] = (),
        budget_turns: int = 1,
        now: datetime | None = None,
        tags: dict | None = None,
    ) -> dict:
        if not isinstance(prompt, str) or not prompt.strip() or len(prompt) > 4000:
            raise ValueError("schedule prompt must be 1..4000 characters")
        if type(budget_turns) is not int or not 1 <= budget_turns <= 100:
            raise ValueError("budget_turns must be 1..100")
        zone = ZoneInfo(tz)
        clean_spec = validate_spec(spec)
        if clean_spec["kind"] == "once":
            at = datetime.fromisoformat(clean_spec["at"])
            if at.tzinfo is None:
                at = at.replace(tzinfo=zone)
            if now is not None and at.astimezone(UTC) <= _aware(now).astimezone(UTC):
                raise ValueError("once schedule time must be after now")
            first_run = at.astimezone(UTC).isoformat()
        else:
            ref = _aware(self.clock() if now is None else now)
            nxt = next_occurrence(clean_spec, ref, tz)
            first_run = nxt.astimezone(UTC).isoformat() if nxt is not None else None
        sched_id = str(uuid4())
        created = self._now_iso(now)
        with self._atomic():
            self.db.execute(
                "INSERT INTO schedules(id, actor_id, session_id, spec, prompt, tz, allowed_tools, "
                "budget_turns, status, status_reason, next_run, retry_at, retry_count, "
                "failure_streak, last_run_at, last_outcome, tags, created_at, updated_at) "
                "VALUES (?,?,?,?,?,?,?,?,'active',NULL,?,NULL,0,0,NULL,NULL,?,?,?)",
                (
                    sched_id,
                    actor_id,
                    session_id,
                    json.dumps(clean_spec, ensure_ascii=False),
                    prompt.strip(),
                    tz,
                    json.dumps(list(allowed_tools)),
                    budget_turns,
                    first_run,
                    json.dumps(tags or {}),
                    created,
                    created,
                ),
            )
        return self.get(sched_id, actor_id)

    def get(self, schedule_id: str, actor_id: str | None = None) -> dict | None:
        if actor_id is None:
            row = self.db.execute("SELECT * FROM schedules WHERE id=?", (schedule_id,)).fetchone()
        else:
            row = self.db.execute(
                "SELECT * FROM schedules WHERE id=? AND actor_id=?", (schedule_id, actor_id)
            ).fetchone()
        return self._row(row) if row else None

    def list(self, actor_id: str | None = None) -> list[dict]:
        if actor_id is None:
            rows = self.db.execute("SELECT * FROM schedules ORDER BY created_at")
        else:
            rows = self.db.execute(
                "SELECT * FROM schedules WHERE actor_id=? ORDER BY created_at", (actor_id,)
            )
        return [self._row(row) for row in rows]

    def due(self, now: datetime) -> list[dict]:
        now_iso = _aware(now).astimezone(UTC).isoformat()
        rows = self.db.execute(
            "SELECT * FROM schedules WHERE status='active' AND "
            "((next_run IS NOT NULL AND next_run <= ?) OR "
            "(retry_at IS NOT NULL AND retry_at <= ?)) "
            "ORDER BY COALESCE(retry_at, next_run), created_at",
            (now_iso, now_iso),
        )
        return [self._row(row) for row in rows]

    def runs(self, schedule_id: str) -> list[dict]:
        return [
            dict(row)
            for row in self.db.execute(
                "SELECT * FROM schedule_runs WHERE schedule_id=? ORDER BY claimed_at",
                (schedule_id,),
            )
        ]

    def claim(self, schedule_id: str, occurrence: str, *, now: datetime | None = None) -> bool:
        """Atomically claim `(schedule_id, occurrence)` via PRIMARY KEY; False on duplicate."""
        with self._atomic():
            sched = self.get(schedule_id)
            if sched is None or sched["status"] != "active":
                return False
            claimed_at = self._now_iso(now)
            try:
                self.db.execute(
                    "INSERT INTO schedule_runs(schedule_id, occurrence, outcome, claimed_at) "
                    "VALUES (?, ?, 'started', ?)",
                    (schedule_id, occurrence, claimed_at),
                )
            except sqlite3.IntegrityError:
                return False
            if occurrence == sched["next_run"]:
                occ_dt = datetime.fromisoformat(occurrence)
                nxt = next_occurrence(sched["spec"], occ_dt, sched["tz"])
                next_iso = nxt.astimezone(UTC).isoformat() if nxt is not None else None
                self.db.execute(
                    "UPDATE schedules SET next_run=?, retry_at=NULL, updated_at=? WHERE id=?",
                    (next_iso, claimed_at, schedule_id),
                )
            elif sched["retry_at"] and occurrence in (
                sched["retry_at"],
                f"retry:{sched['retry_at']}",
            ):
                self.db.execute(
                    "UPDATE schedules SET retry_at=NULL, updated_at=? WHERE id=?",
                    (claimed_at, schedule_id),
                )
            return True

    def skip_missed(self, schedule_id: str, occurrence: str, *, now: datetime) -> bool:
        """Record an expired occurrence as `missed` and advance `next_run` past the window."""
        now = _aware(now).astimezone(UTC)
        now_iso = now.isoformat()
        with self._atomic():
            sched = self.get(schedule_id)
            if sched is None:
                return False
            inserted = True
            try:
                self.db.execute(
                    "INSERT INTO schedule_runs(schedule_id, occurrence, outcome, claimed_at, "
                    "finished_at) VALUES (?, ?, 'missed', ?, ?)",
                    (schedule_id, occurrence, now_iso, now_iso),
                )
            except sqlite3.IntegrityError:
                inserted = False
            spec = sched["spec"]
            status = sched["status"]
            reason = sched["status_reason"]
            if spec["kind"] == "once":
                next_iso = None
                status = "completed"
                reason = "missed"
            elif spec["kind"] == "daily":
                occ_dt = datetime.fromisoformat(occurrence).astimezone(UTC)
                after = max(occ_dt, now - catchup_window(spec))
                nxt = next_occurrence(spec, after, sched["tz"])
                next_iso = nxt.astimezone(UTC).isoformat() if nxt is not None else None
            else:
                nxt = next_occurrence(spec, now, sched["tz"])
                next_iso = nxt.astimezone(UTC).isoformat() if nxt is not None else None
            self.db.execute(
                "UPDATE schedules SET next_run=?, retry_at=NULL, retry_count=0, status=?, "
                "status_reason=?, last_outcome='missed', updated_at=? WHERE id=?",
                (next_iso, status, reason, now_iso, schedule_id),
            )
            return inserted

    def finish(
        self,
        schedule_id: str,
        occurrence: str,
        outcome: str,
        *,
        now: datetime | None = None,
        turn_id: str | None = None,
        error_code: str | None = None,
    ) -> dict:
        if outcome not in _OUTCOMES - {"started"}:
            raise ValueError(f"unsupported schedule outcome: {outcome!r}")
        ts = _aware(self.clock() if now is None else now).astimezone(UTC)
        ts_iso = ts.isoformat()
        with self._atomic():
            sched = self.get(schedule_id)
            if sched is None:
                raise KeyError("schedule_not_found")
            self.db.execute(
                "UPDATE schedule_runs SET outcome=?, turn_id=COALESCE(?, turn_id), error_code=?, "
                "finished_at=? WHERE schedule_id=? AND occurrence=?",
                (outcome, turn_id, error_code, ts_iso, schedule_id, occurrence),
            )
            status = sched["status"]
            status_reason = sched["status_reason"]
            retry_at = sched["retry_at"]
            retry_count = sched["retry_count"]
            failure_streak = sched["failure_streak"]
            last_run_at = ts_iso
            if outcome in ("completed", "silent"):
                failure_streak = 0
                retry_at = None
                retry_count = 0
                if sched["next_run"] is None:
                    status = "completed"
                    status_reason = outcome
            elif outcome == "missed":
                retry_at = None
                retry_count = 0
                if sched["next_run"] is None:
                    status = "completed"
                    status_reason = "missed"
            elif outcome == "transport_failed":
                if retry_count < len(_RETRY_DELAYS_MIN):
                    delay = timedelta(minutes=_RETRY_DELAYS_MIN[retry_count])
                    retry_at = (ts + delay).isoformat()
                    retry_count += 1
                else:
                    retry_at = None
                    retry_count = 0
                    failure_streak += 1
                    if failure_streak >= 3:
                        status = "paused"
                        status_reason = "failure_streak"
                    elif sched["next_run"] is None:
                        status = "paused"
                        status_reason = "transport_failed"
            elif outcome in ("failed", "unknown"):
                retry_at = None
                retry_count = 0
                failure_streak += 1
                if failure_streak >= 3:
                    status = "paused"
                    status_reason = "failure_streak"
                elif sched["next_run"] is None:
                    status = "paused"
                    status_reason = outcome
            elif outcome == "cancelled":
                retry_at = None
                retry_count = 0
                if sched["next_run"] is None and status == "active":
                    status = "paused"
                    status_reason = "owner_stop"
            elif outcome == "paused":
                retry_at = None
                retry_count = 0
                status = "paused"
                status_reason = error_code or "approval_pending"
            self.db.execute(
                "UPDATE schedules SET status=?, status_reason=?, retry_at=?, retry_count=?, "
                "failure_streak=?, last_run_at=?, last_outcome=?, updated_at=? WHERE id=?",
                (
                    status,
                    status_reason,
                    retry_at,
                    retry_count,
                    failure_streak,
                    last_run_at,
                    outcome,
                    ts_iso,
                    schedule_id,
                ),
            )
        return self.get(schedule_id)

    def pause(
        self, schedule_id: str, actor_id: str | None = None, *, reason: str = "owner_control"
    ) -> dict:
        with self._atomic():
            sched = self.get(schedule_id, actor_id)
            if sched is None:
                raise KeyError("schedule_not_found")
            self.db.execute(
                "UPDATE schedules SET status='paused', status_reason=?, retry_at=NULL, "
                "updated_at=? WHERE id=?",
                (reason[:200], self._now_iso(), schedule_id),
            )
        return self.get(schedule_id, actor_id)

    def resume(
        self, schedule_id: str, actor_id: str | None = None, *, now: datetime | None = None
    ) -> dict:
        ref = _aware(self.clock() if now is None else now).astimezone(UTC)
        with self._atomic():
            sched = self.get(schedule_id, actor_id)
            if sched is None:
                raise KeyError("schedule_not_found")
            next_iso = sched["next_run"]
            if next_iso is None or datetime.fromisoformat(next_iso).astimezone(UTC) <= ref:
                nxt = next_occurrence(sched["spec"], ref, sched["tz"])
                next_iso = nxt.astimezone(UTC).isoformat() if nxt is not None else None
            self.db.execute(
                "UPDATE schedules SET status='active', status_reason=NULL, failure_streak=0, "
                "retry_at=NULL, retry_count=0, next_run=?, updated_at=? WHERE id=?",
                (next_iso, ref.isoformat(), schedule_id),
            )
        return self.get(schedule_id, actor_id)

    def remove(self, schedule_id: str, actor_id: str | None = None) -> bool:
        with self._atomic():
            sched = self.get(schedule_id, actor_id)
            if sched is None:
                return False
            self.db.execute("DELETE FROM schedule_runs WHERE schedule_id=?", (schedule_id,))
            self.db.execute("DELETE FROM schedules WHERE id=?", (schedule_id,))
            return True

    @staticmethod
    def _intent(row) -> dict:
        item = dict(row)
        item["keywords"] = json.loads(item["keywords"])
        return item

    @staticmethod
    def _intent_matches(tokens: list[str], keywords: list[str]) -> bool:
        for keyword in keywords:
            kw_tokens = normalize(keyword).split()
            if not kw_tokens:
                continue
            if len(kw_tokens) == 1:
                if kw_tokens[0] in tokens:
                    return True
                continue
            width = len(kw_tokens)
            for idx in range(len(tokens) - width + 1):
                if tokens[idx : idx + width] == kw_tokens:
                    return True
        return False

    def add_intent(
        self,
        actor_id: str,
        keywords: list[str] | tuple[str, ...],
        text: str,
        *,
        days: int = 90,
        fires_left: int = 3,
        cooldown_s: int = 86400,
        now: datetime | None = None,
    ) -> dict:
        cleaned_keywords = [kw.strip() for kw in keywords if isinstance(kw, str) and normalize(kw)]
        if not cleaned_keywords:
            raise ValueError("at least one non-empty keyword is required")
        if not isinstance(text, str) or not text.strip() or len(text) > 4000:
            raise ValueError("intent text must be 1..4000 characters")
        if type(days) is not int or days < 1:
            raise ValueError("days must be a positive integer")
        if type(fires_left) is not int or fires_left < 1:
            raise ValueError("fires_left must be a positive integer")
        if type(cooldown_s) is not int or cooldown_s < 0:
            raise ValueError("cooldown_s must be a non-negative integer")
        ts = _aware(self.clock() if now is None else now).astimezone(UTC)
        intent_id = str(uuid4())
        expires_at = (ts + timedelta(days=days)).isoformat()
        with self._atomic():
            self.db.execute(
                "INSERT INTO intents(id, actor_id, keywords, text, expires_at, fires_left, "
                "cooldown_s, last_fired_at, status, created_at) "
                "VALUES (?,?,?,?,?,?,?,NULL,'active',?)",
                (
                    intent_id,
                    actor_id,
                    json.dumps(cleaned_keywords, ensure_ascii=False),
                    text.strip(),
                    expires_at,
                    fires_left,
                    cooldown_s,
                    ts.isoformat(),
                ),
            )
            row = self.db.execute("SELECT * FROM intents WHERE id=?", (intent_id,)).fetchone()
        return self._intent(row)

    def list_intents(self, actor_id: str | None = None) -> list[dict]:
        if actor_id is None:
            rows = self.db.execute("SELECT * FROM intents ORDER BY created_at")
        else:
            rows = self.db.execute(
                "SELECT * FROM intents WHERE actor_id=? ORDER BY created_at", (actor_id,)
            )
        return [self._intent(row) for row in rows]

    def remove_intent(self, intent_id: str, actor_id: str | None = None) -> bool:
        with self._atomic():
            if actor_id is None:
                cur = self.db.execute("DELETE FROM intents WHERE id=?", (intent_id,))
            else:
                cur = self.db.execute(
                    "DELETE FROM intents WHERE id=? AND actor_id=?", (intent_id, actor_id)
                )
            return cur.rowcount > 0

    def match_intents(
        self,
        actor_id: str,
        user_text: str,
        *,
        now: datetime | None = None,
        limit: int = 3,
    ) -> list[dict]:
        """Rule-based whole-word keyword match; updates budget and cooldown atomically."""
        if not isinstance(user_text, str):
            return []
        tokens = normalize(user_text).split()
        if not tokens or limit < 1:
            return []
        ts = _aware(self.clock() if now is None else now).astimezone(UTC)
        ts_iso = ts.isoformat()
        matched: list[dict] = []
        with self._atomic():
            rows = self.db.execute(
                "SELECT * FROM intents WHERE actor_id=? AND status='active' ORDER BY created_at",
                (actor_id,),
            ).fetchall()
            for row in rows:
                exp_dt = datetime.fromisoformat(row["expires_at"]).astimezone(UTC)
                if ts >= exp_dt:
                    self.db.execute("UPDATE intents SET status='expired' WHERE id=?", (row["id"],))
                    continue
                if row["fires_left"] <= 0:
                    self.db.execute(
                        "UPDATE intents SET status='exhausted' WHERE id=?", (row["id"],)
                    )
                    continue
                if row["last_fired_at"]:
                    last_dt = datetime.fromisoformat(row["last_fired_at"]).astimezone(UTC)
                    if (ts - last_dt).total_seconds() < row["cooldown_s"]:
                        continue
                keywords = json.loads(row["keywords"])
                if not self._intent_matches(tokens, keywords):
                    continue
                fires_left = row["fires_left"] - 1
                new_status = "active" if fires_left > 0 else "exhausted"
                self.db.execute(
                    "UPDATE intents SET fires_left=?, last_fired_at=?, status=? WHERE id=?",
                    (fires_left, ts_iso, new_status, row["id"]),
                )
                updated = self.db.execute(
                    "SELECT * FROM intents WHERE id=?", (row["id"],)
                ).fetchone()
                matched.append(self._intent(updated))
                if len(matched) >= limit:
                    break
        return matched
