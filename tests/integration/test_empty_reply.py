"""An empty reply that used the whole output budget is hidden reasoning, not an answer."""

from b12.auth import owner_capabilities
from b12.runtime import open_runtime


async def _turn(scripted_ollama, tmp_path, script):
    state, base = scripted_ollama
    runtime = open_runtime(base.model_copy(update={"state_dir": tmp_path / "s"}))
    try:
        owner = runtime.control.create_actor(owner=True, consent=True)
        session = runtime.control.create_session(owner.id)
        task = runtime.control.create_task(session)
        grant = runtime.control.issue_grant(
            owner.id, session, owner_capabilities(runtime.settings), task_id=task, ttl_s=600
        )
        state["script"] = list(script)
        result = await runtime.agent.turn(
            session, grant, "Як я паяю XT60?", task_id=task, timeout_s=60
        )
        return result, state["requests"]
    finally:
        runtime.close()


SPENT = {"content": "", "done_reason": "length", "eval_count": 512}


async def test_a_spent_empty_reply_is_retried_once_with_reasoning_allowed(
    scripted_ollama, tmp_path
):
    result, requests = await _turn(scripted_ollama, tmp_path, [SPENT, {"content": "При 380 °C."}])
    assert result.state == "completed" and result.content == "При 380 °C."
    assert [r["think"] for r in requests] == [False, True]
    assert requests[1]["messages"] == requests[0]["messages"], "no nudge, the same request"


async def test_reasoning_is_allowed_for_one_request_only(scripted_ollama, tmp_path):
    result, requests = await _turn(
        scripted_ollama,
        tmp_path,
        [SPENT, {"content": "", "tool_calls": [("system_info", {})]}, {"content": "Готово."}],
    )
    assert result.state == "completed"
    assert [r["think"] for r in requests] == [False, True, False]


async def test_the_retry_happens_once(scripted_ollama, tmp_path):
    _, requests = await _turn(scripted_ollama, tmp_path, [SPENT, SPENT, {"content": "Добре."}])
    assert [r["think"] for r in requests][:2] == [False, True]
    assert all(r["think"] is False for r in requests[2:])


async def test_an_empty_stop_reply_keeps_the_old_nudge(scripted_ollama, tmp_path):
    result, requests = await _turn(
        scripted_ollama, tmp_path, [{"content": ""}, {"content": "При 380 °C."}]
    )
    assert result.content == "При 380 °C."
    assert [r["think"] for r in requests] == [False, False]
    assert "Відповідь порожня" in requests[1]["messages"][-1]["content"]
