"""Unit tests for ADR-022 wall-clock scheduling and ScheduleStore persistence."""

from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from b12.schedules import ScheduleStore, catchup_window, next_occurrence


def test_daily_weekdays_skip_weekend():
    kyiv = ZoneInfo("Europe/Kyiv")
    # Friday 2026-10-23 08:00 local -> next Mon..Fri occurrence is Monday 2026-10-26 08:00
    spec = {"kind": "daily", "time": "08:00", "weekdays": [0, 1, 2, 3, 4]}
    friday_at_8 = datetime(2026, 10, 23, 8, 0, tzinfo=kyiv)
    nxt = next_occurrence(spec, friday_at_8, "Europe/Kyiv")
    assert nxt == datetime(2026, 10, 26, 8, 0, tzinfo=kyiv)
    assert nxt.weekday() == 0

    # Saturday 10:00 -> Monday 08:00
    saturday = datetime(2026, 10, 24, 10, 0, tzinfo=kyiv)
    assert next_occurrence(spec, saturday, "Europe/Kyiv") == datetime(
        2026, 10, 26, 8, 0, tzinfo=kyiv
    )

    # Friday 07:59 -> same Friday 08:00
    friday_before = datetime(2026, 10, 23, 7, 59, tzinfo=kyiv)
    assert next_occurrence(spec, friday_before, "Europe/Kyiv") == datetime(
        2026, 10, 23, 8, 0, tzinfo=kyiv
    )


def test_kyiv_dst_change_keeps_wall_clock():
    kyiv = ZoneInfo("Europe/Kyiv")
    # 2026-10-25: Europe/Kyiv switches EEST (+03:00) -> EET (+02:00) at 04:00 local.
    spec = {"kind": "daily", "time": "08:00", "weekdays": [0, 1, 2, 3, 4, 5, 6]}
    before_dst = datetime(2026, 10, 24, 8, 0, tzinfo=kyiv)  # 05:00 UTC
    after_dst = next_occurrence(spec, before_dst, "Europe/Kyiv")
    assert after_dst is not None
    assert (after_dst.year, after_dst.month, after_dst.day) == (2026, 10, 25)
    assert (after_dst.hour, after_dst.minute) == (8, 0)
    assert after_dst.utcoffset() == timedelta(hours=2)
    assert after_dst.astimezone(UTC) - before_dst.astimezone(UTC) == timedelta(hours=25)

    # Spring-forward 2026-03-29: EET (+02:00) -> EEST (+03:00) at 03:00 local.
    before_spring = datetime(2026, 3, 28, 8, 0, tzinfo=kyiv)
    after_spring = next_occurrence(spec, before_spring, "Europe/Kyiv")
    assert after_spring is not None
    assert (after_spring.year, after_spring.month, after_spring.day) == (2026, 3, 29)
    assert (after_spring.hour, after_spring.minute) == (8, 0)
    assert after_spring.utcoffset() == timedelta(hours=3)
    assert after_spring.astimezone(UTC) - before_spring.astimezone(UTC) == timedelta(hours=23)


def test_once_and_interval_occurrences_and_catchup_windows():
    kyiv = ZoneInfo("Europe/Kyiv")
    once_spec = {"kind": "once", "at": "2026-11-25T09:30:00+02:00"}
    assert next_occurrence(
        once_spec, datetime(2026, 11, 25, 9, 0, tzinfo=kyiv), "Europe/Kyiv"
    ) == datetime(2026, 11, 25, 9, 30, tzinfo=kyiv)
    assert (
        next_occurrence(once_spec, datetime(2026, 11, 25, 9, 30, tzinfo=kyiv), "Europe/Kyiv")
        is None
    )

    interval_spec = {"kind": "interval", "minutes": 30}
    # Elapsed 30 min across fall-back at 03:30+03:00 (00:30 UTC) -> 01:00 UTC (03:00+02:00 fold=1).
    fall_after = datetime(2026, 10, 25, 3, 30, fold=0, tzinfo=kyiv)
    nxt = next_occurrence(interval_spec, fall_after, "Europe/Kyiv")
    assert nxt.astimezone(UTC) - fall_after.astimezone(UTC) == timedelta(minutes=30)

    assert catchup_window({"kind": "interval", "minutes": 1}) == timedelta(minutes=2)
    assert catchup_window({"kind": "interval", "minutes": 30}) == timedelta(minutes=15)
    assert catchup_window({"kind": "interval", "minutes": 600}) == timedelta(hours=2)
    assert catchup_window({"kind": "daily", "time": "08:00", "weekdays": [0]}) == timedelta(hours=2)
    assert catchup_window(once_spec) == timedelta(hours=2)


def test_schedule_store_crud_and_failure_streak(tmp_path):
    now = datetime(2026, 11, 20, 10, 0, tzinfo=UTC)
    store = ScheduleStore(tmp_path / "goals", clock=lambda: now)
    try:
        sched = store.add(
            "actor-1",
            "sess-1",
            {"kind": "interval", "minutes": 60},
            "Перевірити статус",
            tz="Europe/Kyiv",
            allowed_tools=("time.read",),
        )
        assert sched["status"] == "active"
        assert sched["failure_streak"] == 0
        assert len(store.list("actor-1")) == 1

        paused = store.pause(sched["id"], "actor-1")
        assert paused["status"] == "paused"
        assert store.due(now + timedelta(hours=2)) == []

        resumed = store.resume(sched["id"], "actor-1", now=now)
        assert resumed["status"] == "active"

        # 3 consecutive failures pause the schedule.
        for i in range(3):
            due_at = now + timedelta(hours=i + 1)
            [due] = store.due(due_at)
            occ = due["next_run"]
            assert store.claim(due["id"], occ) is True
            updated = store.finish(due["id"], occ, "failed", now=due_at, error_code="err")
            if i < 2:
                assert updated["status"] == "active"
                assert updated["failure_streak"] == i + 1
            else:
                assert updated["status"] == "paused"
                assert updated["failure_streak"] == 3

        assert store.remove(sched["id"], "actor-1") is True
        assert store.list("actor-1") == []
        with pytest.raises(KeyError):
            store.pause(sched["id"], "actor-1")
    finally:
        store.close()
