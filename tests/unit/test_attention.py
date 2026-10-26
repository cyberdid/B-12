"""Deterministic initiative policy; the clock is injected only at the time boundary."""

from datetime import UTC, datetime, timedelta

import pytest


class Clock:
    def __init__(self, start):
        self.now = start

    def __call__(self):
        return self.now

    def advance(self, **delta):
        self.now += timedelta(**delta)


def kyiv_noon():
    # 12:00 Europe/Kyiv (UTC+2 in late October after DST end) — outside quiet hours.
    return datetime(2026, 10, 27, 10, 0, tzinfo=UTC)


@pytest.fixture
def policy(tmp_path, profile_settings):
    from b12.attention import AttentionPolicy

    clock = Clock(kyiv_noon())
    settings = profile_settings.model_copy(update={"state_dir": tmp_path / "state"})
    store = AttentionPolicy(tmp_path / "attention", settings, clock=clock)
    yield store, clock, settings
    store.close()


def test_hour_cap_and_cooldown_bound_nonurgent_initiatives(policy):
    store, clock, _ = policy
    actor = "actor-1"
    for index in range(3):
        decision = store.decide(actor)
        assert decision.allowed, decision.reason
        store.record(actor, decision)
        assert store.decide(actor).reason == ("cooldown" if index < 2 else "hour_cap")
        clock.advance(minutes=11)
    assert store.decide(actor).reason == "hour_cap"
    clock.advance(minutes=30)
    assert store.decide(actor).allowed


def test_quiet_hours_block_background_speech_but_not_direct_or_urgent(policy):
    store, clock, _ = policy
    clock.now = datetime(2026, 10, 27, 22, 30, tzinfo=UTC)  # 00:30 Kyiv
    assert store.decide("a").reason == "quiet_hours"
    assert store.decide("a", urgent=True).allowed
    assert store.direct_reply_allowed("a")


def test_quiet_mode_and_owner_stop_are_distinct_and_persist(policy, tmp_path):
    from b12.attention import AttentionPolicy

    store, clock, settings = policy
    store.set_quiet("a", True)
    assert store.decide("a").reason == "quiet_mode"
    assert store.execution_allowed("a")
    store.set_quiet("a", False)
    store.set_stopped("a", True)
    assert store.decide("a").reason == "owner_stop"
    assert not store.execution_allowed("a")
    store.close()
    reopened = AttentionPolicy(tmp_path / "attention", settings, clock=clock)
    assert reopened.decide("a").reason == "owner_stop"
    reopened.set_stopped("a", False)
    assert reopened.decide("a").allowed
    reopened.close()


def test_ignored_proposals_back_off_exponentially_and_reset_on_engagement(policy):
    store, clock, _ = policy
    decision = store.decide("a")
    proposal = store.record("a", decision)
    store.feedback(proposal, "ignored")
    clock.advance(minutes=11)
    assert store.decide("a").reason == "backoff"
    clock.advance(minutes=10)  # 21 min since: 2x cooldown passed
    second = store.record("a", store.decide("a"))
    store.feedback(second, "ignored")
    clock.advance(minutes=21)
    assert store.decide("a").reason == "backoff"  # now needs 4x cooldown
    clock.advance(minutes=20)
    third = store.record("a", store.decide("a"))
    store.feedback(third, "engaged")
    clock.advance(minutes=20)  # base cooldown passed; first proposal left the hour window
    assert store.decide("a").allowed


def test_initiative_log_survives_restart_for_hour_cap(policy, tmp_path):
    from b12.attention import AttentionPolicy

    store, clock, settings = policy
    for _ in range(3):
        store.record("a", store.decide("a"))
        clock.advance(minutes=11)
    store.close()
    reopened = AttentionPolicy(tmp_path / "attention", settings, clock=clock)
    assert reopened.decide("a").reason == "hour_cap"
    reopened.close()


def test_recording_a_denied_decision_is_rejected(policy):
    store, _, _ = policy
    store.record("a", store.decide("a"))
    with pytest.raises(PermissionError):
        store.record("a", store.decide("a"))
