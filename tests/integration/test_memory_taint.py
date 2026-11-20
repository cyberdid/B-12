"""Task A2: per-turn network taint for memory writes."""

import asyncio

import pytest

from b12.auth import owner_capabilities
from b12.runtime import open_runtime


async def _start_http(body: bytes = b"server=frankfurt"):
    async def handle(reader, writer):
        await reader.readuntil(b"\r\n\r\n")
        writer.write(
            b"HTTP/1.1 200 OK\r\nContent-Length: "
            + str(len(body)).encode()
            + b"\r\nConnection: close\r\n\r\n"
            + body
        )
        await writer.drain()
        writer.close()
        await writer.wait_closed()

    return await asyncio.start_server(handle, "127.0.0.1", 0)


@pytest.mark.parametrize("flag", [False, True])
async def test_store_after_http_fetch_is_unverified(scripted_ollama, tmp_path, flag):
    state, base = scripted_ollama
    note = tmp_path / "local.txt"
    note.write_text("локальний текст", encoding="utf-8")
    server = await _start_http()
    async with server:
        port = server.sockets[0].getsockname()[1]
        runtime = open_runtime(
            base.model_copy(
                update={
                    "state_dir": tmp_path / f"state-{flag}",
                    "network_allow": ("127.0.0.1",),
                    "memory_taint": flag,
                }
            )
        )
        try:
            actor = runtime.control.create_actor(owner=True, consent=True)
            session = runtime.control.create_session(actor.id)
            task = runtime.control.create_task(session)
            grant = runtime.control.issue_grant(
                actor.id, session, owner_capabilities(runtime.settings), task_id=task, ttl_s=600
            )
            state["script"] = [
                {"tool_calls": [("http_fetch", {"url": f"http://127.0.0.1:{port}/"})]},
                {"tool_calls": [("file_read", {"path": str(note)})]},
                {"tool_calls": [("memory_store", {"text": "Сервер у Франкфурті"})]},
                {"content": "Зберегла."},
            ]
            result = await runtime.agent.turn(
                session,
                grant,
                "Перевір сервер і файл, збережи локацію.",
                task_id=task,
                timeout_s=60,
            )
            assert result.state == "completed"
            [record] = runtime.memory.search("Франкфурті", actor)
            if flag:
                assert record.reliability == "unverified"
                assert record.source == "network_turn"
            else:
                assert record.reliability is None
                assert record.source != "network_turn"

            # Whatever reliability the model explicitly supplies, taint overrides it.
            if flag:
                task2 = runtime.control.create_task(session)
                grant2 = runtime.control.issue_grant(
                    actor.id,
                    session,
                    owner_capabilities(runtime.settings),
                    task_id=task2,
                    ttl_s=600,
                )
                state["script"] = [
                    {"tool_calls": [("http_fetch", {"url": f"http://127.0.0.1:{port}/"})]},
                    {
                        "tool_calls": [
                            (
                                "memory_store",
                                {"text": "Порт сервера 8443", "reliability": "high"},
                            )
                        ]
                    },
                    {"content": "Записано."},
                ]
                await runtime.agent.turn(
                    session, grant2, "Перевір і запиши порт.", task_id=task2, timeout_s=60
                )
                [overridden] = runtime.memory.search("8443", actor)
                assert overridden.reliability == "unverified"
                assert overridden.source == "network_turn"
        finally:
            runtime.close()


async def test_taint_does_not_leak_into_the_next_turn(scripted_ollama, tmp_path):
    state, base = scripted_ollama
    server = await _start_http()
    async with server:
        port = server.sockets[0].getsockname()[1]
        runtime = open_runtime(
            base.model_copy(
                update={
                    "state_dir": tmp_path / "state",
                    "network_allow": ("127.0.0.1",),
                    "memory_taint": True,
                }
            )
        )
        try:
            actor = runtime.control.create_actor(owner=True, consent=True)
            session = runtime.control.create_session(actor.id)
            task1 = runtime.control.create_task(session)
            grant1 = runtime.control.issue_grant(
                actor.id, session, owner_capabilities(runtime.settings), task_id=task1, ttl_s=600
            )
            state["script"] = [
                {"tool_calls": [("http_fetch", {"url": f"http://127.0.0.1:{port}/"})]},
                {"content": "Перевірила."},
            ]
            await runtime.agent.turn(
                session, grant1, "Перевір адресу.", task_id=task1, timeout_s=60
            )
            assert runtime.agent._tainted == set()

            task2 = runtime.control.create_task(session)
            grant2 = runtime.control.issue_grant(
                actor.id, session, owner_capabilities(runtime.settings), task_id=task2, ttl_s=600
            )
            state["script"] = [
                {"tool_calls": [("memory_store", {"text": "Локальний факт від власника"})]},
                {"content": "Зберегла."},
            ]
            await runtime.agent.turn(
                session, grant2, "Запам'ятай локальний факт.", task_id=task2, timeout_s=60
            )
            [record] = runtime.memory.search("Локальний", actor)
            assert record.reliability is None
            assert record.source != "network_turn"
            assert runtime.agent._tainted == set()
        finally:
            runtime.close()


async def test_denied_network_call_and_cancelled_turn_behavior(scripted_ollama, tmp_path):
    state, base = scripted_ollama
    server = await _start_http()
    async with server:
        port = server.sockets[0].getsockname()[1]
        runtime = open_runtime(
            base.model_copy(
                update={
                    "state_dir": tmp_path / "state",
                    "network_allow": (),
                    "memory_taint": True,
                }
            )
        )
        try:
            actor = runtime.control.create_actor(owner=True, consent=True)
            session = runtime.control.create_session(actor.id)
            task1 = runtime.control.create_task(session)
            grant1 = runtime.control.issue_grant(
                actor.id, session, owner_capabilities(runtime.settings), task_id=task1, ttl_s=600
            )
            state["script"] = [
                {"tool_calls": [("http_fetch", {"url": f"http://127.0.0.1:{port}/"})]},
                {"tool_calls": [("memory_store", {"text": "Факт без доступу до мережі"})]},
                {"content": "Готово."},
            ]
            await runtime.agent.turn(
                session, grant1, "Спробуй мережу.", task_id=task1, timeout_s=60
            )
            [record] = runtime.memory.search("без доступу", actor)
            assert record.reliability is None
            assert record.source != "network_turn"
        finally:
            runtime.close()

        runtime2 = open_runtime(
            base.model_copy(
                update={
                    "state_dir": tmp_path / "state2",
                    "network_allow": ("127.0.0.1",),
                    "memory_taint": True,
                }
            )
        )
        try:
            actor2 = runtime2.control.create_actor(owner=True, consent=True)
            session2 = runtime2.control.create_session(actor2.id)
            task2 = runtime2.control.create_task(session2)
            grant2 = runtime2.control.issue_grant(
                actor2.id, session2, owner_capabilities(runtime2.settings), task_id=task2, ttl_s=600
            )
            cancel = asyncio.Event()
            state["script"] = [
                {"tool_calls": [("http_fetch", {"url": f"http://127.0.0.1:{port}/"})]},
                {"content": "чекаю", "hang": True},
            ]

            async def cancel_on_second_request():
                while len(state["requests"]) < 2:
                    await asyncio.sleep(0.01)
                cancel.set()

            canceller = asyncio.create_task(cancel_on_second_request())
            result = await runtime2.agent.turn(
                session2, grant2, "Завантаж сторінку.", task_id=task2, cancel=cancel, timeout_s=60
            )
            await canceller
            assert result.state == "cancelled"
            assert runtime2.agent._tainted == set()
        finally:
            runtime2.close()
