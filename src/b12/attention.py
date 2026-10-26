"""Deterministic initiative policy: quiet hours/mode, cooldown, hour cap, backoff, stop.

Applies to nonurgent background speech only. A direct user request is always
answerable; quiet mode silences initiative but does not pause execution; owner stop
pauses background execution. The initiative log persists, so a restart cannot reset
the hour cap. Only proposal IDs, timestamps and feedback codes are stored here.
"""

import os
import sqlite3
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, time, timedelta
from pathlib import Path
from uuid import uuid4
from zoneinfo import ZoneInfo

MAX_BACKOFF = timedelta(hours=4)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS flags(actor_id TEXT PRIMARY KEY, quiet INTEGER NOT NULL,
 stopped INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS initiatives(id TEXT PRIMARY KEY, actor_id TEXT NOT NULL,
 created_at TEXT NOT NULL, urgent INTEGER NOT NULL, feedback TEXT);
CREATE INDEX IF NOT EXISTS initiatives_actor ON initiatives(actor_id, created_at);
"""


@dataclass(frozen=True)
class Decision:
    allowed: bool
    reason: str
    urgent: bool = False


def _clock() -> datetime:
    return datetime.now(UTC)


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ValueError("timezone-aware clock required")
    return value.astimezone(UTC)


class AttentionPolicy:
    def __init__(self, path: Path, settings, *, clock: Callable[[], datetime] = _clock):
        self.path = Path(path)
        self.path.mkdir(mode=0o700, parents=True, exist_ok=True)
        db = self.path / "attention.sqlite3"
        fd = os.open(db, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        os.close(fd)
        self.db = sqlite3.connect(db, isolation_level=None)
        self.db.execute("PRAGMA synchronous=FULL")
        self.db.executescript(_SCHEMA)
        self.settings, self.clock = settings, clock
        self.zone = ZoneInfo(settings.timezone)

    def close(self):
        self.db.close()

    def _flags(self, actor_id) -> tuple[bool, bool]:
        row = self.db.execute(
            "SELECT quiet, stopped FROM flags WHERE actor_id=?", (actor_id,)
        ).fetchone()
        return (bool(row[0]), bool(row[1])) if row else (False, False)

    def _set(self, actor_id, column, value: bool):
        if type(value) is not bool:
            raise ValueError("literal boolean required")
        quiet, stopped = self._flags(actor_id)
        values = {"quiet": quiet, "stopped": stopped, column: value}
        self.db.execute(
            "INSERT OR REPLACE INTO flags VALUES (?,?,?)",
            (actor_id, values["quiet"], values["stopped"]),
        )

    def set_quiet(self, actor_id: str, quiet: bool):
        self._set(actor_id, "quiet", quiet)

    def set_stopped(self, actor_id: str, stopped: bool):
        self._set(actor_id, "stopped", stopped)

    def state(self, actor_id: str) -> dict:
        quiet, stopped = self._flags(actor_id)
        return {"quiet": quiet, "stopped": stopped}

    def execution_allowed(self, actor_id: str) -> bool:
        return not self._flags(actor_id)[1]

    def direct_reply_allowed(self, actor_id: str) -> bool:
        return True  # quiet hours/mode never block an answer to a direct request

    def _quiet_hours(self, now: datetime) -> bool:
        local = now.astimezone(self.zone).time()
        start = time.fromisoformat(self.settings.quiet_start)
        end = time.fromisoformat(self.settings.quiet_end)
        return start <= local or local < end if start > end else start <= local < end

    def _ignored_streak(self, actor_id) -> int:
        streak = 0
        for (feedback,) in self.db.execute(
            "SELECT feedback FROM initiatives WHERE actor_id=? AND urgent=0 "
            "ORDER BY created_at DESC",
            (actor_id,),
        ):
            if feedback not in ("ignored", "dismissed"):
                break
            streak += 1
        return streak

    def decide(self, actor_id: str, *, urgent: bool = False) -> Decision:
        now = _utc(self.clock())
        quiet, stopped = self._flags(actor_id)
        if stopped:
            return Decision(False, "owner_stop", urgent)
        if urgent:
            return Decision(True, "urgent", True)
        if quiet:
            return Decision(False, "quiet_mode")
        if self._quiet_hours(now):
            return Decision(False, "quiet_hours")
        recent = [
            datetime.fromisoformat(row[0])
            for row in self.db.execute(
                "SELECT created_at FROM initiatives WHERE actor_id=? AND urgent=0 "
                "AND created_at>? ORDER BY created_at",
                (actor_id, (now - timedelta(hours=1)).isoformat()),
            )
        ]
        if len(recent) >= self.settings.initiative_hour_cap:
            return Decision(False, "hour_cap")
        last = self.db.execute(
            "SELECT MAX(created_at) FROM initiatives WHERE actor_id=? AND urgent=0", (actor_id,)
        ).fetchone()[0]
        if last is not None:
            streak = self._ignored_streak(actor_id)
            wait = min(
                timedelta(seconds=self.settings.initiative_cooldown_s) * (2**streak), MAX_BACKOFF
            )
            if now - datetime.fromisoformat(last) < wait:
                return Decision(False, "backoff" if streak else "cooldown")
        return Decision(True, "allowed")

    def record(self, actor_id: str, decision: Decision) -> str:
        """Persist an initiative that was actually delivered; denied decisions are refused."""
        if not isinstance(decision, Decision) or not decision.allowed:
            raise PermissionError("initiative not allowed")
        proposal = str(uuid4())
        self.db.execute(
            "INSERT INTO initiatives VALUES (?,?,?,?,NULL)",
            (proposal, actor_id, _utc(self.clock()).isoformat(), decision.urgent),
        )
        return proposal

    def feedback(self, proposal_id: str, outcome: str):
        if outcome not in ("engaged", "ignored", "dismissed"):
            raise ValueError("unknown feedback")
        self.db.execute("UPDATE initiatives SET feedback=? WHERE id=?", (outcome, proposal_id))
