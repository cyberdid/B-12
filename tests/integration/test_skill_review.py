"""Background skill review (spec 2026-11-24-skill-review-design.md): learned procedures become
skill proposals in the approval queue, never active skills."""

import json
from uuid import uuid4

from b12.runtime import open_runtime

PROCEDURE = (
    "Нарешті прошив ESP32-C3: затиснути BOOT, коротко натиснути RESET, відпустити BOOT і шити "
    "на 460800 бод — на 921600 падає."
)


def _runtime(base, tmp_path, **flags):
    update = {
        "state_dir": tmp_path / "state",
        "skills": True,
        "skill_review": True,
        "output_tokens": 2048,
    }
    update.update(flags)
    return open_runtime(base.model_copy(update=update))


def _commit(runtime, actor, user_text, answer="Добре."):
    session = runtime.control.create_session(actor.id)
    turn_id = str(uuid4())
    runtime.sessions.commit_turn(
        session,
        actor.id,
        turn_id,
        [{"role": "user", "content": user_text}, {"role": "assistant", "content": answer}],
        tags={},
    )
    return turn_id


def _reply(*skills):
    return {"content": json.dumps({"skills": list(skills)}, ensure_ascii=False)}


def _skill(turn_id, name="flash-esp32c3", body="1. Затиснути BOOT.\n2. Шити на 460800 бод."):
    return {"name": name, "description": "Прошивка ESP32-C3", "body": body, "turn_id": turn_id}


def _seed_skill(runtime, name="solder-xt60"):
    target = runtime.skills.path / name
    target.mkdir(parents=True)
    (target / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: Як я паяю XT60\n---\n380 °C, жало 2 мм.\n",
        encoding="utf-8",
    )


async def test_review_stages_a_procedure_as_skill_proposal(scripted_ollama, tmp_path):
    from b12.skill_review import PROMPT, SkillReviewer

    state, base = scripted_ollama
    runtime = _runtime(base, tmp_path)
    try:
        actor = runtime.control.create_actor(owner=True, consent=True)
        _seed_skill(runtime)
        turn_id = _commit(runtime, actor, PROCEDURE)

        def review(request):
            assert PROMPT in request["messages"][0]["content"]
            batch = request["messages"][-1]["content"]
            assert turn_id in batch and "solder-xt60" in batch
            return _reply(_skill(turn_id))

        state["script"] = [review]
        outcome = await SkillReviewer(runtime).review(actor)
        assert outcome["state"] == "staged" and outcome["names"] == ["flash-esp32c3"]
        (pending,) = runtime.skills.list_pending()
        assert pending["name"] == "flash-esp32c3" and pending["turn_id"] == turn_id
        assert pending["action"] == "create"
        assert pending["content"].startswith("---\nname: flash-esp32c3\n")
        assert not (runtime.skills.path / "flash-esp32c3" / "SKILL.md").exists()
    finally:
        runtime.close()


async def test_existing_skill_name_becomes_update(scripted_ollama, tmp_path):
    from b12.skill_review import SkillReviewer

    state, base = scripted_ollama
    runtime = _runtime(base, tmp_path)
    try:
        actor = runtime.control.create_actor(owner=True, consent=True)
        _seed_skill(runtime)
        turn_id = _commit(runtime, actor, "Тепер паяю XT60 на 400 °C жалом 3 мм.")
        state["script"] = [_reply(_skill(turn_id, "solder-xt60", "400 °C, жало 3 мм."))]
        outcome = await SkillReviewer(runtime).review(actor)
        assert outcome["state"] == "staged"
        assert runtime.skills.list_pending()[0]["action"] == "update"
    finally:
        runtime.close()


async def test_empty_list_advances_cursor(scripted_ollama, tmp_path):
    from b12.skill_review import SkillReviewer

    state, base = scripted_ollama
    runtime = _runtime(base, tmp_path)
    try:
        actor = runtime.control.create_actor(owner=True, consent=True)
        _commit(runtime, actor, "Мій принтер — Bambu Lab P1S.")
        state["script"] = [_reply()]
        assert await SkillReviewer(runtime).review(actor) == {
            "state": "skipped",
            "reason": "no_candidates",
        }
        before = len(state["requests"])
        assert await SkillReviewer(runtime).review(actor) == {
            "state": "skipped",
            "reason": "no_turns",
        }
        assert len(state["requests"]) == before
    finally:
        runtime.close()


async def test_invalid_output_keeps_cursor(scripted_ollama, tmp_path):
    from b12.skill_review import SkillReviewer

    state, base = scripted_ollama
    runtime = _runtime(base, tmp_path)
    try:
        actor = runtime.control.create_actor(owner=True, consent=True)
        turn_id = _commit(runtime, actor, PROCEDURE)
        state["script"] = [{"content": "не JSON"}]
        assert await SkillReviewer(runtime).review(actor) == {
            "state": "rejected",
            "reason": "invalid_output",
        }
        state["script"] = [_reply(_skill(turn_id))]
        assert (await SkillReviewer(runtime).review(actor))["state"] == "staged"
    finally:
        runtime.close()


async def test_foreign_turn_id_rejects_batch(scripted_ollama, tmp_path):
    from b12.skill_review import SkillReviewer

    state, base = scripted_ollama
    runtime = _runtime(base, tmp_path)
    try:
        actor = runtime.control.create_actor(owner=True, consent=True)
        turn_id = _commit(runtime, actor, PROCEDURE)
        state["script"] = [_reply(_skill(turn_id), _skill(str(uuid4()), "other-skill"))]
        assert (await SkillReviewer(runtime).review(actor))["state"] == "rejected"
        assert runtime.skills.list_pending() == []
    finally:
        runtime.close()


async def test_pending_name_is_not_staged_twice(scripted_ollama, tmp_path):
    from b12.skill_review import SkillReviewer

    state, base = scripted_ollama
    runtime = _runtime(base, tmp_path)
    try:
        actor = runtime.control.create_actor(owner=True, consent=True)
        first = _commit(runtime, actor, PROCEDURE)
        state["script"] = [_reply(_skill(first))]
        assert (await SkillReviewer(runtime).review(actor))["state"] == "staged"
        second = _commit(runtime, actor, PROCEDURE)
        state["script"] = [_reply(_skill(second))]
        assert await SkillReviewer(runtime).review(actor) == {
            "state": "skipped",
            "reason": "duplicate",
        }
        assert len(runtime.skills.list_pending()) == 1
    finally:
        runtime.close()


async def test_invalid_skill_name_skips_only_that_item(scripted_ollama, tmp_path):
    from b12.skill_review import SkillReviewer

    state, base = scripted_ollama
    runtime = _runtime(base, tmp_path)
    try:
        actor = runtime.control.create_actor(owner=True, consent=True)
        turn_id = _commit(runtime, actor, PROCEDURE)
        state["script"] = [_reply(_skill(turn_id, "bad name/x"), _skill(turn_id))]
        outcome = await SkillReviewer(runtime).review(actor)
        assert outcome["state"] == "staged" and outcome["names"] == ["flash-esp32c3"]
    finally:
        runtime.close()


async def test_goal_turns_are_not_reviewed(scripted_ollama, tmp_path):
    from b12.auth import owner_capabilities
    from b12.skill_review import SkillReviewer

    state, base = scripted_ollama
    runtime = _runtime(base, tmp_path)
    try:
        actor = runtime.control.create_actor(owner=True, consent=True)
        session = runtime.control.create_session(actor.id)
        task = runtime.control.create_task(session)
        runtime.control.link_task_goal(task, str(uuid4()), 1)
        grant = runtime.control.issue_grant(
            actor.id, session, owner_capabilities(runtime.settings), task_id=task
        )
        state["script"] = [{"content": "Ціль виконана."}]
        await runtime.agent.turn(session, grant, PROCEDURE, task_id=task, timeout_s=60)
        before = len(state["requests"])
        assert await SkillReviewer(runtime).review(actor) == {
            "state": "skipped",
            "reason": "no_turns",
        }
        assert len(state["requests"]) == before
    finally:
        runtime.close()


async def test_skills_off_or_flag_off_skips(scripted_ollama, tmp_path):
    from b12.skill_review import SkillReviewer

    state, base = scripted_ollama
    for index, flags in enumerate(({"skills": False}, {"skill_review": False})):
        runtime = _runtime(base, tmp_path / str(index), **flags)
        try:
            actor = runtime.control.create_actor(owner=True, consent=True)
            _commit(runtime, actor, PROCEDURE)
            before = len(state["requests"])
            assert await SkillReviewer(runtime).review(actor) == {
                "state": "skipped",
                "reason": "skills_off",
            }
            assert len(state["requests"]) == before
        finally:
            runtime.close()


async def test_invalidation_during_review_discards_result(scripted_ollama, tmp_path):
    from b12.skill_review import SkillReviewer

    state, base = scripted_ollama
    runtime = _runtime(base, tmp_path)
    try:
        actor = runtime.control.create_actor(owner=True, consent=True)
        turn_id = _commit(runtime, actor, PROCEDURE)

        async def invalidate_mid_call(request):
            for item in runtime.agent.active.values():
                item.invalidated = True
            return _reply(_skill(turn_id))

        state["script"] = [invalidate_mid_call]
        assert (await SkillReviewer(runtime).review(actor))["state"] == "rejected"
        assert runtime.skills.list_pending() == []
    finally:
        runtime.close()
