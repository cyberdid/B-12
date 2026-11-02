from uuid import uuid4

from b12.sessions import SessionStore


def test_cancelled_waiting_turn_leaves_no_checkpoint(tmp_path):
    """Regression: cancelling a turn that waited for approval kept its checkpoint."""
    from b12.agent import Agent

    sessions = SessionStore(tmp_path / "sessions")
    turn, session, actor = str(uuid4()), str(uuid4()), str(uuid4())
    sessions.save_checkpoint(turn, session, actor, {"round": 3}, tags={})
    assert sessions.load_checkpoint(turn, actor) is not None
    Agent.discard_waiting(sessions, {}, turn, actor)
    assert sessions.load_checkpoint(turn, actor) is None
