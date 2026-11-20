"""settings.preference_rules: stated answer preferences from memory reach the prompt as rules."""

from datetime import UTC, datetime

from b12.auth import owner_capabilities
from b12.runtime import open_runtime

PINNED = datetime(2026, 12, 1, 8, 0, tzinfo=UTC)


async def _system(base, tmp_path, flag, setup):
    runtime = open_runtime(
        base.model_copy(update={"state_dir": tmp_path / str(flag), "preference_rules": flag})
    )
    try:
        runtime.agent.clock = lambda: PINNED
        actor = runtime.control.create_actor(owner=True, consent=True)
        setup(runtime, actor)
        session = runtime.control.create_session(actor.id)
        task = runtime.control.create_task(session)
        grant = runtime.control.issue_grant(
            actor.id, session, owner_capabilities(runtime.settings), task_id=task, ttl_s=600
        )
        await runtime.agent.turn(session, grant, "Що таке ШІМ?", task_id=task, timeout_s=60)
    finally:
        runtime.close()


async def test_current_stated_preferences_become_rules_only_with_the_flag(
    scripted_ollama, tmp_path
):
    state, base = scripted_ollama

    def setup(runtime, actor):
        runtime.memory.remember(
            "Пояснюй технічне коротко, без формул.", actor, kind="preference", origin="explicit"
        )
        runtime.memory.remember(
            "Під час дієти не пропонуй солодкого.",
            actor,
            kind="preference",
            valid_to="2026-11-25",
        )
        runtime.memory.remember(
            "Схоже, власник любить довгі пояснення.", actor, kind="preference", origin="inferred"
        )
        runtime.memory.remember("Код домофона 4512.", actor)

    for flag in (False, True):
        state["script"] = [{"content": "ШІМ — це керування потужністю імпульсами."}]
        await _system(base, tmp_path, flag, setup)
        system = state["requests"][-1]["messages"][0]["content"]
        rules = system.split("Вподобання співрозмовника щодо форми відповіді")
        assert (len(rules) == 2) is flag
        if flag:
            assert "Пояснюй технічне коротко, без формул." in rules[1]
            assert "солодкого" not in rules[1]  # expired
            assert "довгі пояснення" not in rules[1]  # inferred, not stated
            assert "4512" not in rules[1]  # not a preference


async def test_query_placement_puts_rules_beside_the_question_and_never_persists_them(
    scripted_ollama, tmp_path
):
    state, base = scripted_ollama

    def seed(runtime, actor):
        runtime.memory.remember(
            "Пояснюй технічне коротко, без формул.", actor, kind="preference", origin="explicit"
        )

    for label, pref_rules, script, prompt in (
        ("off", False, [{"content": "Відповідь."}], "Що таке ШІМ?"),
        (
            "single",
            True,
            [{"content": "ШІМ — це керування потужністю імпульсами."}],
            "Що таке ШІМ?",
        ),
        (
            "tool_round",
            True,
            [
                {"tool_calls": [("memory_search", {"query": "нічогонезнайдеться"})]},
                {"content": "Коротко: ШІМ керує середнім струмом."},
            ],
            "Розкажи про ШІМ",
        ),
    ):
        state["requests"].clear()
        state["script"] = script
        runtime = open_runtime(
            base.model_copy(
                update={
                    "state_dir": tmp_path / label,
                    "preference_rules": pref_rules,
                    "preference_placement": "query",
                }
            )
        )
        try:
            runtime.agent.clock = lambda: PINNED
            actor = runtime.control.create_actor(owner=True, consent=True)
            seed(runtime, actor)
            session = runtime.control.create_session(actor.id)
            task = runtime.control.create_task(session)
            grant = runtime.control.issue_grant(
                actor.id, session, owner_capabilities(runtime.settings), task_id=task, ttl_s=600
            )
            await runtime.agent.turn(session, grant, prompt, task_id=task, timeout_s=60)
            history = runtime.sessions.history(session, actor.id)
        finally:
            runtime.close()

        assert history[0]["content"] == prompt
        for req in state["requests"]:
            msgs = req["messages"]
            assert "Вподобання співрозмовника" not in msgs[0]["content"]
            user_msg = next(m for m in reversed(msgs) if m["role"] == "user")
            if pref_rules:
                assert "Вподобання співрозмовника щодо форми відповіді" in user_msg["content"]
                assert "Пояснюй технічне коротко, без формул." in user_msg["content"]
                assert user_msg["content"].endswith(prompt)
            else:
                assert user_msg["content"] == prompt
