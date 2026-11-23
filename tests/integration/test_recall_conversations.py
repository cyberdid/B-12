# ruff: noqa: E501  -- Ukrainian test strings stay on one line
"""recall_conversations: a question about a past conversation gets the matching earlier turns."""

from uuid import uuid4

import pytest

from b12.auth import owner_capabilities
from b12.conversation_recall import refers_to_past_conversation
from b12.runtime import open_runtime


@pytest.mark.parametrize(
    "text",
    [
        "Яку модель датчиків ми обговорювали в попередній розмові?",
        "Нагадай із минулих чатів: яку модель ми обрали?",
        "Що ми вирішили минулого разу щодо фарби?",
        "Ти казала, яку дошку брати?",
    ],
)
def test_pointers_to_a_past_conversation_are_recognised(text):
    assert refers_to_past_conversation(text)


@pytest.mark.parametrize(
    "text", ["Яка модель датчиків краща?", "Привіт!", "Розмова про погоду — це нудно", ""]
)
def test_ordinary_questions_are_not(text):
    assert not refers_to_past_conversation(text)


def _past_turn(runtime, actor_id, text, reply):
    session = runtime.control.create_session(actor_id)
    runtime.sessions.commit_turn(
        session,
        actor_id,
        str(uuid4()),
        [{"role": "user", "content": text}, {"role": "assistant", "content": reply}],
        tags={},
    )
    return session


async def _last_user_message(scripted_ollama, tmp_path, question, *, flag, other_actor=False):
    state, base = scripted_ollama
    runtime = open_runtime(
        base.model_copy(update={"state_dir": tmp_path / f"s{flag}", "recall_conversations": flag})
    )
    try:
        owner = runtime.control.create_actor(owner=True, consent=True)
        author = runtime.control.create_actor(consent=True) if other_actor else owner
        _past_turn(
            runtime,
            author.id,
            "Домовилися ставити датчики протікання води моделі «Аква-Стоп-4» під мийкою і біля бойлера.",
            "Прийнято, зафіксувала план встановлення.",
        )
        session = runtime.control.create_session(owner.id)
        task = runtime.control.create_task(session)
        grant = runtime.control.issue_grant(
            owner.id, session, owner_capabilities(runtime.settings), task_id=task, ttl_s=600
        )
        state["script"] = [{"content": "Аква-Стоп-4, під мийкою і біля бойлера."}]
        await runtime.agent.turn(session, grant, question, task_id=task, timeout_s=60)
        users = [m for m in state["requests"][-1]["messages"] if m["role"] == "user"]
        persisted = runtime.sessions.history(session, owner.id)
        return users[-1]["content"], persisted
    finally:
        runtime.close()


QUESTION = "Яку модель датчиків протікання води ми обговорювали в попередній розмові?"


async def test_the_past_turn_reaches_the_question_with_the_flag(scripted_ollama, tmp_path):
    content, persisted = await _last_user_message(scripted_ollama, tmp_path, QUESTION, flag=True)
    assert "Аква-Стоп-4" in content and content.rstrip().endswith(QUESTION)
    assert persisted[0]["content"] == QUESTION, "the note rides the request only"


async def test_without_the_flag_nothing_is_added(scripted_ollama, tmp_path):
    content, _ = await _last_user_message(scripted_ollama, tmp_path, QUESTION, flag=False)
    assert content == QUESTION


async def test_another_actors_conversation_is_never_offered(scripted_ollama, tmp_path):
    content, _ = await _last_user_message(
        scripted_ollama, tmp_path, QUESTION, flag=True, other_actor=True
    )
    assert "Аква-Стоп-4" not in content
