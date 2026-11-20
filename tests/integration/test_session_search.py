"""settings.session_search: FTS5 SessionStore.search and conversation_search tool."""

from datetime import UTC, datetime
from uuid import uuid4

from b12.auth import GUEST_CAPABILITIES, owner_capabilities
from b12.runtime import open_runtime
from b12.sessions import SessionStore


def _turn(user: str, assistant: str = "Гаразд.") -> list[dict]:
    return [
        {"role": "user", "content": user},
        {"role": "assistant", "content": assistant},
    ]


def test_search_finds_own_past_turns_only(tmp_path):
    store = SessionStore(tmp_path / "sessions")
    try:
        actor_a, actor_b, sess_a, sess_b, turn_a, turn_b = (str(uuid4()) for _ in range(6))
        store.commit_turn(sess_a, actor_a, turn_a, _turn("Ми обрали Neovim"), tags={})
        store.commit_turn(sess_b, actor_b, turn_b, _turn("Neovim у чужому чаті"), tags={})

        matches = store.search(actor_a, "Neovim")
        assert len(matches) == 1
        match = matches[0]
        assert match["turn_id"] == turn_a
        assert match["session_id"] == sess_a
        assert match["role"] == "user"
        assert "Neovim" in match["snippet"]
        assert len(match["snippet"]) <= 240
        datetime.fromisoformat(match["created_at"])

        long_turn = str(uuid4())
        long_text = "Довгий контекст Neovim: " + ("деталь " * 60)
        store.commit_turn(sess_a, actor_a, long_turn, _turn(long_text), tags={})
        long_matches = store.search(actor_a, "деталь")
        assert len(long_matches) == 1
        assert len(long_matches[0]["snippet"]) <= 240
    finally:
        store.close()


def test_cleared_session_and_purged_turns_are_not_found(tmp_path):
    store = SessionStore(tmp_path / "sessions")
    try:
        actor, sess1, sess2, mem_id = (str(uuid4()) for _ in range(4))
        t1, t2, t3 = (str(uuid4()) for _ in range(3))

        store.commit_turn(sess1, actor, t1, _turn("Обрали сервопривод SG90"), tags={})
        assert [m["turn_id"] for m in store.search(actor, "сервопривод")] == [t1]
        store.clear_session(sess1, actor)
        assert store.search(actor, "сервопривод") == []

        store.commit_turn(sess2, actor, t2, _turn("Секретний код 9988"), tags={mem_id: "memory"})
        store.commit_turn(sess2, actor, t3, _turn("Звичайний опис камери"), tags={})
        assert store.search(actor, "9988", live=lambda eid, kind: eid != mem_id) == []

        store.purge_evidence(str(uuid4()), actor, (mem_id,))
        assert store.search(actor, "9988") == []
        assert [m["turn_id"] for m in store.search(actor, "камери")] == [t3]
        assert store.db.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    finally:
        store.close()


def test_ukrainian_prefix_matching(tmp_path):
    store = SessionStore(tmp_path / "sessions")
    try:
        actor, session, turn_id = (str(uuid4()) for _ in range(3))
        store.commit_turn(
            session,
            actor,
            turn_id,
            _turn("Ми постійно користуємося редактором для коду."),
            tags={},
        )
        matches = store.search(actor, "редактор")
        assert [m["turn_id"] for m in matches] == [turn_id]
        # Malicious or accidental FTS syntax from query is treated as plain terms, never syntax.
        assert store.search(actor, 'редактор"') == matches
        assert store.search(actor, "редактор OR казковий") == []
    finally:
        store.close()


def test_existing_store_backfills_messages_fts_on_open(tmp_path):
    path = tmp_path / "sessions"
    store = SessionStore(path)
    try:
        actor, session, turn_id = (str(uuid4()) for _ in range(3))
        store.commit_turn(session, actor, turn_id, _turn("Архівний запис про лідар"), tags={})
        with store._atomic():
            store.db.execute("DROP TABLE messages_fts")
    finally:
        store.close()

    reopened = SessionStore(path)
    try:
        assert [m["turn_id"] for m in reopened.search(actor, "лідар")] == [turn_id]
    finally:
        reopened.close()


async def test_conversation_search_tool_is_flagged_and_actor_scoped(scripted_ollama, tmp_path):
    state, base = scripted_ollama

    for flag in (False, True):
        state["requests"].clear()
        state["script"] = (
            [
                {"tool_calls": [("conversation_search", {"query": "Neovim"})]},
                {"content": "Згадав вибір редактора."},
            ]
            if flag
            else [{"content": "Гаразд."}]
        )
        runtime = open_runtime(
            base.model_copy(update={"state_dir": tmp_path / f"ss-{flag}", "session_search": flag})
        )
        try:
            owner = runtime.control.create_actor(owner=True, consent=True)
            other = runtime.control.create_actor(owner=False, consent=True)
            no_consent = runtime.control.create_actor(owner=False, consent=False)
            sess_owner = runtime.control.create_session(owner.id)
            sess_other = runtime.control.create_session(other.id)
            runtime.sessions.commit_turn(
                sess_owner, owner.id, str(uuid4()), _turn("Вчора обрали Neovim."), tags={}
            )
            runtime.sessions.commit_turn(
                sess_other, other.id, str(uuid4()), _turn("Чужий Neovim."), tags={}
            )
            missing_id = str(uuid4())
            runtime.sessions.commit_turn(
                sess_owner,
                owner.id,
                str(uuid4()),
                _turn("Секретний Neovim з видаленого спогаду."),
                tags={missing_id: "memory"},
            )

            fresh_session = runtime.control.create_session(owner.id)
            task = runtime.control.create_task(fresh_session)
            grant = runtime.control.issue_grant(
                owner.id,
                fresh_session,
                owner_capabilities(runtime.settings),
                task_id=task,
                ttl_s=600,
            )
            await runtime.agent.turn(
                fresh_session, grant, "Який редактор ми обрали?", task_id=task, timeout_s=60
            )
            if flag:
                # Non-consented actor cannot query persisted session search.
                guest_session = runtime.control.create_session(no_consent.id)
                guest_task = runtime.control.create_task(guest_session)
                guest_grant = runtime.control.issue_grant(
                    no_consent.id,
                    guest_session,
                    tuple(sorted((*GUEST_CAPABILITIES, "memory.read"))),
                    task_id=guest_task,
                    ttl_s=600,
                )
                state["script"] = [
                    {"tool_calls": [("conversation_search", {"query": "Neovim"})]},
                    {"content": "Немає доступу."},
                ]
                guest_res = await runtime.agent.turn(
                    guest_session, guest_grant, "Шукай Neovim", task_id=guest_task, timeout_s=60
                )
                assert guest_res.tool_results[0].error_code == "consent_required"
        finally:
            runtime.close()

        tool_names = [t["function"]["name"] for t in state["requests"][0]["tools"]]
        assert ("conversation_search" in tool_names) is flag
        if flag:
            tool_msg = next(m for m in state["requests"][1]["messages"] if m["role"] == "tool")
            assert "Вчора обрали Neovim" in tool_msg["content"]
            assert "Чужий Neovim" not in tool_msg["content"]
            assert "видаленого спогаду" not in tool_msg["content"]
            assert datetime.now(UTC).strftime("%Y-") in tool_msg["content"]
