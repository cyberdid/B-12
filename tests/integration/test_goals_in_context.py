"""settings.goals_in_context: the speaker's goals reach the model as data, only with the flag."""

from b12.auth import owner_capabilities
from b12.runtime import open_runtime


async def test_goals_reach_the_model_only_with_the_flag(scripted_ollama, tmp_path):
    state, base = scripted_ollama
    for flag in (False, True):
        runtime = open_runtime(
            base.model_copy(update={"state_dir": tmp_path / str(flag), "goals_in_context": flag})
        )
        try:
            actor = runtime.control.create_actor(owner=True, consent=True)
            session = runtime.control.create_session(actor.id)
            open_goal = runtime.goals.create(actor.id, session, "Замовити батарейки AA.", "куплено")
            done = runtime.goals.create(actor.id, session, "Щодня звітувати про полив.", "звіт")
            runtime.goals.set_status(done["id"], actor.id, "abandoned", "скасовано власником")
            assert open_goal["status"] == "active"
            task = runtime.control.create_task(session)
            grant = runtime.control.issue_grant(
                actor.id, session, owner_capabilities(runtime.settings), task_id=task, ttl_s=600
            )
            state["script"] = [{"content": "Батарейки."}]
            await runtime.agent.turn(
                session, grant, "Що в мене відкрите?", task_id=task, timeout_s=60
            )
            system = state["requests"][-1]["messages"][0]["content"]
            assert ("[активна] Замовити батарейки AA." in system) is flag
            assert (
                "[скасована] Щодня звітувати про полив. (скасовано власником)" in system
            ) is flag
        finally:
            runtime.close()
