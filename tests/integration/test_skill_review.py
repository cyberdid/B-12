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

        def review(request):
            # The model must see the current text to keep the unchanged steps (gemma, M116).
            assert "380 °C, жало 2 мм." in request["messages"][-1]["content"]
            return _reply(_skill(turn_id, "solder-xt60", "400 °C, жало 3 мм."))

        state["script"] = [review]
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
        outcome = await SkillReviewer(runtime).review(actor)
        assert (outcome["state"], outcome["reason"], outcome["not_staged"]) == (
            "skipped",
            "duplicate",
            1,
        )
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


async def test_scheduler_runs_skill_review_for_idle_consented_actors(scripted_ollama, tmp_path):
    from b12.autonomy import Scheduler

    state, base = scripted_ollama
    runtime = _runtime(base, tmp_path, memory_review=False)
    scheduler = Scheduler(runtime)
    try:
        actor = runtime.control.create_actor(owner=True, consent=True)
        guest = runtime.control.create_actor(owner=False, consent=False)
        turn_id = _commit(runtime, actor, PROCEDURE)
        state["script"] = [_reply(_skill(turn_id))]
        outcomes = await scheduler.review_skills_idle()
        staged = [o for o in outcomes if o.get("state") == "staged"]
        assert [o["actor_id"] for o in staged] == [actor.id]
        assert guest.id not in {o.get("actor_id") for o in staged}
        assert len(runtime.skills.list_pending()) == 1
    finally:
        scheduler.close()
        runtime.close()


async def test_scheduler_skill_review_is_off_without_the_flag(scripted_ollama, tmp_path):
    from b12.autonomy import Scheduler

    state, base = scripted_ollama
    runtime = _runtime(base, tmp_path, skill_review=False)
    scheduler = Scheduler(runtime)
    try:
        actor = runtime.control.create_actor(owner=True, consent=True)
        _commit(runtime, actor, PROCEDURE)
        assert await scheduler.review_skills_idle() == []
    finally:
        scheduler.close()
        runtime.close()


async def test_scheduler_run_calls_skill_review_after_memory_review(
    scripted_ollama, tmp_path, monkeypatch
):
    import asyncio

    from b12.autonomy import Scheduler

    _, base = scripted_ollama
    runtime = _runtime(base, tmp_path, scheduler_tick_s=0.01)
    scheduler = Scheduler(runtime)
    order: list[str] = []
    stop = asyncio.Event()

    def step(name, last=False):
        async def run():
            order.append(name)
            if last:
                stop.set()
            return []

        return run

    monkeypatch.setattr(scheduler, "tick", step("tick"))
    monkeypatch.setattr(scheduler, "reflect_idle", step("reflect"))
    monkeypatch.setattr(scheduler, "review_memory_idle", step("memory"))
    monkeypatch.setattr(scheduler, "review_skills_idle", step("skills"))
    monkeypatch.setattr(scheduler, "curate_skills_idle", step("curate", last=True))
    try:
        await asyncio.wait_for(scheduler.run(stop), timeout=5)
        assert order == ["tick", "reflect", "memory", "skills", "curate"]
    finally:
        scheduler.close()
        runtime.close()


# --- final review fixes (24.11.2026) ---


async def test_review_does_not_mark_skills_used(scripted_ollama, tmp_path):
    """Reading skill text for the review must not reset the curator's staleness clock."""
    from b12.skill_review import SkillReviewer

    state, base = scripted_ollama
    runtime = _runtime(base, tmp_path)
    try:
        actor = runtime.control.create_actor(owner=True, consent=True)
        _seed_skill(runtime)
        before = runtime.skills.show("solder-xt60").get("last_used_at")
        _commit(runtime, actor, PROCEDURE)
        state["script"] = [_reply()]
        await SkillReviewer(runtime).review(actor)
        assert runtime.skills.show("solder-xt60").get("last_used_at") == before
    finally:
        runtime.close()


async def test_every_skill_name_is_listed_even_past_the_text_budget(scripted_ollama, tmp_path):
    from b12.skill_review import SkillReviewer

    state, base = scripted_ollama
    runtime = _runtime(base, tmp_path)
    try:
        actor = runtime.control.create_actor(owner=True, consent=True)
        names = [f"skill-{i}" for i in range(5)]
        for name in names:
            target = runtime.skills.path / name
            target.mkdir(parents=True)
            (target / "SKILL.md").write_text(
                f"---\nname: {name}\ndescription: Опис {name}\n---\n" + "крок " * 600,
                encoding="utf-8",
            )
        _commit(runtime, actor, PROCEDURE)

        def review(request):
            batch = request["messages"][-1]["content"]
            assert all(name in batch for name in names)
            return _reply()

        state["script"] = [review]
        assert (await SkillReviewer(runtime).review(actor))["reason"] == "no_candidates"
    finally:
        runtime.close()


async def test_a_batch_that_keeps_failing_is_skipped_after_three_attempts(
    scripted_ollama, tmp_path
):
    from b12.skill_review import SkillReviewer

    state, base = scripted_ollama
    runtime = _runtime(base, tmp_path)
    try:
        actor = runtime.control.create_actor(owner=True, consent=True)
        _commit(runtime, actor, PROCEDURE)
        outcomes = []
        for _ in range(3):
            state["script"] = [{"content": "не JSON"}]
            outcomes.append(await SkillReviewer(runtime).review(actor))
        assert [o["state"] for o in outcomes] == ["rejected"] * 3
        assert outcomes[-1].get("gave_up") is True
        before = len(state["requests"])
        assert await SkillReviewer(runtime).review(actor) == {
            "state": "skipped",
            "reason": "no_turns",
        }
        assert len(state["requests"]) == before
    finally:
        runtime.close()


async def test_only_owners_are_reviewed(scripted_ollama, tmp_path):
    from b12.skill_review import SkillReviewer

    state, base = scripted_ollama
    runtime = _runtime(base, tmp_path)
    try:
        guest = runtime.control.create_actor(owner=False, consent=True)
        _commit(runtime, guest, PROCEDURE)
        before = len(state["requests"])
        assert await SkillReviewer(runtime).review(guest) == {
            "state": "skipped",
            "reason": "owner_only",
        }
        assert len(state["requests"]) == before
    finally:
        runtime.close()


async def test_an_owner_turn_cancels_a_running_review(scripted_ollama, tmp_path):
    import asyncio
    import time

    from b12.auth import owner_capabilities
    from b12.skill_review import SkillReviewer

    state, base = scripted_ollama
    runtime = _runtime(base, tmp_path)
    try:
        actor = runtime.control.create_actor(owner=True, consent=True)
        turn_id = _commit(runtime, actor, PROCEDURE)

        async def slow_review(request):
            await asyncio.sleep(5)
            return _reply(_skill(turn_id))

        state["script"] = [slow_review, {"content": "Привіт!"}]
        review = asyncio.create_task(SkillReviewer(runtime).review(actor))
        while not state["requests"]:
            await asyncio.sleep(0.02)
        session = runtime.control.create_session(actor.id)
        task = runtime.control.create_task(session)
        grant = runtime.control.issue_grant(
            actor.id, session, owner_capabilities(runtime.settings), task_id=task
        )
        started = time.monotonic()
        result = await runtime.agent.turn(session, grant, "Привіт", task_id=task, timeout_s=30)
        assert result.state == "completed" and time.monotonic() - started < 4
        outcome = await review
        assert outcome == {"state": "failed", "reason": "cancelled"}
        assert runtime.skills.list_pending() == []
    finally:
        runtime.close()


async def test_a_turn_cleared_during_the_review_is_not_proposed(scripted_ollama, tmp_path):
    from b12.skill_review import SkillReviewer

    state, base = scripted_ollama
    runtime = _runtime(base, tmp_path)
    try:
        actor = runtime.control.create_actor(owner=True, consent=True)
        turn_id = _commit(runtime, actor, PROCEDURE)
        session = runtime.sessions.db.execute(
            "SELECT session_id FROM turns WHERE turn_id=?", (turn_id,)
        ).fetchone()["session_id"]

        def clear_mid_call(request):
            runtime.sessions.clear_session(session, actor.id)
            return _reply(_skill(turn_id))

        state["script"] = [clear_mid_call]
        outcome = await SkillReviewer(runtime).review(actor)
        assert outcome["state"] != "staged"
        assert runtime.skills.list_pending() == []
    finally:
        runtime.close()


async def test_long_description_is_shortened_and_kept_on_one_line(scripted_ollama, tmp_path):
    from b12.skill_review import SkillReviewer
    from b12.skills import MAX_DESCRIPTION_LEN

    state, base = scripted_ollama
    runtime = _runtime(base, tmp_path)
    try:
        actor = runtime.control.create_actor(owner=True, consent=True)
        turn_id = _commit(runtime, actor, PROCEDURE)
        item = _skill(turn_id)
        item["description"] = "Як перевести ESP32-C3 у режим прошивки\nname: other " + "і " * 40
        state["script"] = [_reply(item)]
        outcome = await SkillReviewer(runtime).review(actor)
        assert outcome["state"] == "staged"
        content = runtime.skills.list_pending()[0]["content"]
        description = content.split("description: ", 1)[1].split("\n", 1)[0]
        assert len(description) <= MAX_DESCRIPTION_LEN
        # The newline is gone, so no extra frontmatter key can start a line.
        assert [line for line in content.splitlines() if line.startswith("name:")] == [
            "name: flash-esp32c3"
        ]
    finally:
        runtime.close()


async def test_items_that_are_not_staged_are_counted(scripted_ollama, tmp_path):
    from b12.skill_review import SkillReviewer

    state, base = scripted_ollama
    runtime = _runtime(base, tmp_path)
    try:
        actor = runtime.control.create_actor(owner=True, consent=True)
        turn_id = _commit(runtime, actor, PROCEDURE)
        state["script"] = [
            _reply(_skill(turn_id, "one"), _skill(turn_id, "two"), _skill(turn_id, "three"))
        ]
        outcome = await SkillReviewer(runtime).review(actor)
        assert outcome["count"] == 2 and outcome["not_staged"] == 1
    finally:
        runtime.close()
