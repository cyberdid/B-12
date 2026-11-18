"""settings.verify_writes: the runtime reads a finished write back and reports it."""

from b12.auth import owner_capabilities
from b12.runtime import open_runtime


async def _write(settings, tmp_path, verify, state):
    runtime = open_runtime(
        settings.model_copy(update={"state_dir": tmp_path / f"s{verify}", "verify_writes": verify})
    )
    try:
        actor = runtime.control.create_actor(owner=True, consent=True)
        session = runtime.control.create_session(actor.id)
        task = runtime.control.create_task(session)
        grant = runtime.control.issue_grant(
            actor.id,
            session,
            owner_capabilities(runtime.settings),
            task_id=task,
            ttl_s=600,
            full_execution=True,
        )
        target = tmp_path / f"out{verify}.txt"
        state["script"] = [
            {"tool_calls": [("file_write", {"path": str(target), "text": "23.0\n"})]},
            {"content": "Записав."},
        ]
        result = await runtime.agent.turn(session, grant, "Запиши 23.0", task_id=task, timeout_s=60)
        return result.tool_results[0].content
    finally:
        runtime.close()


async def test_read_back_only_with_the_flag(scripted_ollama, tmp_path):
    state, base = scripted_ollama
    plain = await _write(base, tmp_path, False, state)
    assert "verification" not in plain
    verified = await _write(base, tmp_path, True, state)
    check = verified["verification"]
    assert check["read_back"] is True and check["matches_written"] is True
    assert check["bytes_on_disk"] == 5 and check["preview"] == "23.0\n"
