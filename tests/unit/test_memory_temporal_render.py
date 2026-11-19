"""ADR-015 read path: temporal evidence lines and supersession history, behind a flag."""

from datetime import UTC, datetime

from b12.agent import _dated
from b12.config import Settings
from b12.contracts import MemoryRecord

NOW = datetime(2026, 12, 1, 8, 0, tzinfo=UTC)


def record(**fields):
    base = {
        "id": "00000000-0000-4000-8000-000000000001",
        "owner_id": "owner",
        "kind": "fact",
        "text": "Склад закрито на ремонт.",
        "source": "user",
        "created_at": "2026-11-30T07:00:00+00:00",
    }
    return MemoryRecord(**{**base, **fields})


def test_flag_off_keeps_todays_rendering():
    assert _dated(record(event_time="2026-11-18")) == "[2026-11-30] Склад закрито на ремонт."


def test_flag_on_shows_event_and_recorded_dates_separately():
    line = _dated(record(event_time="2026-08-14"), temporal=True, now=NOW)
    assert line.startswith("[подія 2026-08-14 · записано 2026-11-30]")


def test_expired_validity_is_marked_not_hidden():
    line = _dated(record(valid_from="2026-11-18", valid_to="2026-11-25"), temporal=True, now=NOW)
    assert "чинне 2026-11-18 – 2026-11-25" in line
    assert "чинність минула" in line


def test_current_validity_is_not_marked_expired():
    line = _dated(record(valid_from="2026-11-18", valid_to="2026-12-25"), temporal=True, now=NOW)
    assert "чинність минула" not in line


def test_reliability_locator_and_conversation_origin_are_shown():
    line = _dated(
        record(
            reliability="low",
            source_locator="BOM r3",
            temporal_source="conversation",
            event_time="2026-11-10",
        ),
        temporal=True,
        now=NOW,
    )
    assert "надійність: low" in line and "джерело: BOM r3" in line and "(з розмови)" in line


def test_superseded_record_is_marked():
    line = _dated(
        record(status="stale", superseded_by="00000000-0000-4000-8000-000000000002"),
        temporal=True,
        now=NOW,
    )
    assert "замінено новішим записом" in line


def test_settings_flag_defaults_on_and_reads_env(tmp_path):
    assert Settings(state_dir=tmp_path).memory_temporal is True  # on since 19.11.2026 (U4)
    env = {"B12_STATE_DIR": str(tmp_path), "B12_MEMORY_TEMPORAL": "0"}
    assert Settings.from_env(env).memory_temporal is False
