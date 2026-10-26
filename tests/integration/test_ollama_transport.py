"""Exercise real HTTP sockets and NDJSON parsing; no mocked transport/parser."""

import asyncio
import json
import time
from dataclasses import replace

import pytest

from b12.context import ContextBuilder
from b12.model import ModelError, OllamaModel


@pytest.fixture
async def wire_server(profile_settings):
    state = {
        "chunks": [],
        "requests": [],
        "paths": [],
        "closed": asyncio.Event(),
        "chat_started": asyncio.Event(),
        "version": "test-1",
        "status": 200,
        "delay": 0,
        "prompt_count": 0,
        "manifest": "a" * 64,
    }
    handlers = set()

    async def handle(reader, writer):
        task = asyncio.current_task()
        handlers.add(task)
        try:
            header = await reader.readuntil(b"\r\n\r\n")
            path = header.split(b" ")[1].decode()
            state["paths"].append(path)
            length = next(
                (
                    int(line.split(b":")[1])
                    for line in header.split(b"\r\n")
                    if line.lower().startswith(b"content-length:")
                ),
                0,
            )
            body = await reader.readexactly(length)
            if path.endswith("/api/chat"):
                state["requests"].append(json.loads(body))
                state["chat_started"].set()
                writer.write(f"HTTP/1.1 {state['status']} OK\r\nConnection: close\r\n\r\n".encode())
                await writer.drain()
                for chunk in state["chunks"]:
                    if isinstance(chunk, float):
                        # A disconnected client ends the delay promptly and observably.
                        try:
                            await asyncio.wait_for(reader.read(1), chunk)
                            break
                        except TimeoutError:
                            continue
                    writer.write(chunk)
                    await writer.drain()
                if state["delay"]:
                    await asyncio.wait_for(reader.read(1), state["delay"])
                state["closed"].set()
            else:
                if path.endswith("/api/version"):
                    response = {"version": state["version"]}
                elif path.endswith("/api/tags"):
                    response = {"models": [{"name": "test-model", "digest": state["manifest"]}]}
                else:
                    response = {"template": "{{ .Prompt }}"}
                payload = json.dumps(response).encode()
                writer.write(
                    b"HTTP/1.1 200 OK\r\nContent-Length: "
                    + str(len(payload)).encode()
                    + b"\r\nConnection: close\r\n\r\n"
                    + payload
                )
                await writer.drain()
        except (ConnectionError, asyncio.IncompleteReadError):
            state["closed"].set()
        finally:
            writer.close()
            await writer.wait_closed()
            handlers.discard(task)

    server = await asyncio.start_server(handle, "127.0.0.1", 0)
    profile_settings.ollama_url = f"http://127.0.0.1:{server.sockets[0].getsockname()[1]}"
    request = ContextBuilder(profile_settings).build("S", [{"role": "user", "content": "hi"}])
    state["prompt_count"] = request.input_tokens
    yield state, profile_settings, request
    server.close()
    await server.wait_closed()
    for task in list(handlers):
        task.cancel()
    await asyncio.gather(*handlers, return_exceptions=True)


def line(value):
    return json.dumps(value, ensure_ascii=False).encode() + b"\n"


def delta(content="", **message):
    return line({"message": {"role": "assistant", "content": content, **message}, "done": False})


def done(count, **extra):
    return line(
        {
            "message": {"role": "assistant", "content": ""},
            "done": True,
            "done_reason": "stop",
            "prompt_eval_count": count,
            "eval_count": 5,
            "total_duration": 1000,
            **extra,
        }
    )


async def test_streams_exact_snapshot_and_sanitizes_reasoning_before_callback(wire_server):
    state, settings, request = wire_server
    state["chunks"] = [
        delta("<th", thinking="hidden native reasoning"),
        delta("ink>secret"),
        delta("</thi"),
        delta("nk>Привіт "),
        delta("🤖"),
        done(request.input_tokens, thinking="hidden", arbitrary="content copy"),
    ]
    received = []

    async def callback(text):
        received.append(text)

    reply = await OllamaModel(settings).chat(request, on_delta=callback)
    assert reply.content == "Привіт 🤖"
    assert "".join(received) == "Привіт 🤖"
    assert state["requests"] == [request.payload()]
    assert state["requests"][0]["options"]["num_ctx"] == 256
    assert reply.metrics["prompt_eval_count"] == request.input_tokens
    assert reply.metrics["ttft_s"] >= 0
    assert not any(
        word in json.dumps(reply.model_dump()) for word in ("hidden", "secret", "arbitrary")
    )


@pytest.mark.parametrize(
    ("chunks", "code"),
    [
        ([b"{not json}\n"], "malformed_ndjson"),
        ([b'{"done":'], "malformed_ndjson"),
        ([delta("ok")], "missing_done"),
        ([line({"done": "true"})], "invalid_terminal"),
        ([line({"error": "secret provider details"})], "provider_error"),
        ([line({"done": True})], "invalid_terminal"),
        (
            [delta(tool_calls=[{"function": {"name": "run", "arguments": "bad json"}}])],
            "invalid_tool_call",
        ),
        ([delta(tool_calls=[{"function": {"name": "run", "arguments": []}}])], "invalid_tool_call"),
    ],
)
async def test_faults_have_distinct_sanitized_codes(wire_server, chunks, code):
    state, settings, request = wire_server
    state["chunks"] = chunks
    with pytest.raises(ModelError) as result:
        await OllamaModel(settings).chat(request)
    assert result.value.code == code
    assert "secret" not in str(result.value)


async def test_http_failure_is_separate(wire_server):
    state, settings, request = wire_server
    state["status"] = 503
    with pytest.raises(ModelError, match="http_error"):
        await OllamaModel(settings).chat(request)


@pytest.mark.parametrize("mode", ["event", "deadline", "task"])
async def test_cancel_while_blocked_on_next_chunk_closes_socket_promptly(wire_server, mode):
    state, settings, request = wire_server
    state["chunks"] = [delta("first"), 10.0, delta("too late"), done(request.input_tokens)]
    event = asyncio.Event()
    seen = asyncio.Event()

    async def callback(text):
        seen.set()

    deadline = time.monotonic() + 0.15 if mode == "deadline" else None
    task = asyncio.create_task(
        OllamaModel(settings).chat(request, on_delta=callback, cancel=event, deadline=deadline)
    )
    await asyncio.wait_for(seen.wait(), 1)
    started = time.monotonic()
    if mode == "event":
        event.set()
    elif mode == "task":
        task.cancel()
    expected = asyncio.CancelledError if mode == "task" else ModelError
    with pytest.raises(expected) as result:
        await asyncio.wait_for(task, 1)
    if mode != "task":
        assert result.value.code == ("cancelled" if mode == "event" else "deadline_exceeded")
    await asyncio.wait_for(state["closed"].wait(), 1)
    assert time.monotonic() - started < 1


async def test_incremental_native_object_calls_preserve_ids_and_assign_missing_ids(wire_server):
    state, settings, request = wire_server
    state["chunks"] = [
        delta(
            tool_calls=[
                {
                    "id": "opaque/provider:42",
                    "function": {"index": 0, "name": "run", "arguments": {"a": 1}},
                }
            ]
        ),
        delta(tool_calls=[{"function": {"index": 0, "name": "run", "arguments": {"b": 2}}}]),
        delta(tool_calls=[{"function": {"index": 1, "name": "other", "arguments": {}}}]),
        done(request.input_tokens),
    ]
    reply = await OllamaModel(settings).chat(request)
    assert len(reply.tool_calls) == 2
    assert reply.tool_calls[0].id == "opaque/provider:42"
    assert reply.tool_calls[0].arguments == {"a": 1, "b": 2}
    assert reply.tool_calls[1].id and reply.tool_calls[1].id != reply.tool_calls[0].id
    assert reply.tool_calls[1].name == "other"


@pytest.mark.parametrize("change", ["settings", "profile", "manifest", "version", "fingerprint"])
async def test_changes_invalidate_admission_before_chat(wire_server, change):
    state, settings, request = wire_server
    if change == "settings":
        settings.num_ctx = 512
    elif change == "profile":
        path = settings.tokenizer_dir / "chat_template.jinja"
        path.write_text("changed")
    elif change == "manifest":
        state["manifest"] = "b" * 64
    elif change == "version":
        state["version"] = "different"
    else:
        request = replace(request, output_reserve=1)
    with pytest.raises(ModelError):
        await OllamaModel(settings).chat(request)
    assert state["requests"] == []


async def test_prompt_count_mismatch_is_not_silently_accepted(wire_server):
    state, settings, request = wire_server
    state["chunks"] = [done(request.input_tokens - 1)]
    with pytest.raises(ModelError, match="context_mismatch"):
        await OllamaModel(settings).chat(request)


async def test_unterminated_inline_thinking_does_not_leak(wire_server):
    state, settings, request = wire_server
    state["chunks"] = [delta("<think>secret"), done(request.input_tokens)]
    received = []

    async def collect(text):
        received.append(text)

    with pytest.raises(ModelError, match="unterminated_reasoning"):
        await OllamaModel(settings).chat(request, on_delta=collect)
    assert received == []


async def test_provider_output_over_reserve_fails(wire_server):
    state, settings, request = wire_server
    state["chunks"] = [done(request.input_tokens, eval_count=33)]
    with pytest.raises(ModelError, match="output_limit"):
        await OllamaModel(settings).chat(request)


async def test_public_output_is_bounded_before_callback(wire_server):
    state, settings, request = wire_server
    state["chunks"] = [delta("x" * 100), done(request.input_tokens)]
    received = []

    async def collect(text):
        received.append(text)

    with pytest.raises(ModelError, match="output_limit"):
        await OllamaModel(settings).chat(request, on_delta=collect)
    assert received == []


async def test_split_utf8_and_ndjson_frames_are_reassembled(wire_server):
    state, settings, request = wire_server
    raw = delta("Привіт") + done(request.input_tokens)
    state["chunks"] = [bytes([byte]) for byte in raw]
    reply = await OllamaModel(settings).chat(request)
    assert reply.content == "Привіт"


async def test_callback_exception_closes_stream_and_is_sanitized(wire_server):
    state, settings, request = wire_server
    state["chunks"] = [delta("hi"), 10.0]

    async def callback(text):
        raise ValueError("private callback state")

    with pytest.raises(ModelError, match="callback_error") as result:
        await OllamaModel(settings).chat(request, on_delta=callback)
    assert "private" not in str(result.value)
    await asyncio.wait_for(state["closed"].wait(), 1)


async def test_precancelled_request_does_not_reach_provider(wire_server):
    state, settings, request = wire_server
    cancel = asyncio.Event()
    cancel.set()
    with pytest.raises(ModelError, match="cancelled"):
        await OllamaModel(settings).chat(request, cancel=cancel)
    assert state["requests"] == []


@pytest.mark.parametrize(
    "chunks",
    [
        [
            delta(tool_calls=[{"function": {"index": 0, "name": "run", "arguments": {"a": 1}}}]),
            delta(tool_calls=[{"function": {"index": 0, "name": "run", "arguments": {"a": 2}}}]),
        ],
        [delta(tool_calls=[{"function": {"index": -1, "name": "run", "arguments": {}}}])],
    ],
)
async def test_conflicting_native_calls_are_rejected(wire_server, chunks):
    state, settings, request = wire_server
    state["chunks"] = chunks
    with pytest.raises(ModelError, match="invalid_tool_call"):
        await OllamaModel(settings).chat(request)


async def test_oversized_unterminated_jsonl_frame_is_bounded(wire_server):
    state, settings, request = wire_server
    state["chunks"] = [b'{"message":{"thinking":"' + b"x" * (1024 * 1024), 10.0]
    with pytest.raises(ModelError, match="output_limit"):
        await OllamaModel(settings).chat(request)
    await asyncio.wait_for(state["closed"].wait(), 1)


async def test_unbounded_stream_of_small_frames_is_bounded(wire_server):
    state, settings, request = wire_server
    frame = delta(thinking="x" * 65536)
    state["chunks"] = [frame] * 129 + [10.0]
    received = []

    async def collect(text):
        received.append(text)

    with pytest.raises(ModelError, match="output_limit"):
        await OllamaModel(settings).chat(request, on_delta=collect)
    assert received == []
    await asyncio.wait_for(state["closed"].wait(), 1)


@pytest.mark.parametrize("malformation", ["images", "orphan"])
async def test_forged_snapshot_is_rejected_before_http_post(wire_server, malformation):
    state, settings, request = wire_server
    messages = request.payload()["messages"]
    if malformation == "images":
        messages[-1]["images"] = ["unbudgeted"]
    else:
        messages.append({"role": "tool", "tool_name": "run", "content": "result"})
    count = ContextBuilder(settings).profile.count(messages, [])
    request = replace(request, messages=messages, input_tokens=count, input_upper_bound=count + 8)
    request = replace(request, fingerprint=request._fingerprint())
    state["chunks"] = [done(count)]
    with pytest.raises(ModelError, match="admission_invalid"):
        await OllamaModel(settings).chat(request)
    assert state["requests"] == []


async def test_sync_callback_is_rejected_without_execution_or_http(wire_server):
    state, settings, request = wire_server
    state["chunks"] = [delta("hi"), done(request.input_tokens)]
    executed = []

    def callback(text):
        executed.append(text)
        time.sleep(0.3)

    with pytest.raises(ModelError, match="invalid_callback"):
        await OllamaModel(settings).chat(
            request, on_delta=callback, deadline=time.monotonic() + 0.1
        )
    assert executed == []
    assert state["paths"] == []


@pytest.mark.parametrize("mode", ["event", "deadline", "task"])
async def test_cooperative_async_callback_is_cancelled_and_joined(wire_server, mode):
    state, settings, request = wire_server
    state["chunks"] = [delta("hi"), done(request.input_tokens), 10.0]
    cancel, started, stopped = asyncio.Event(), asyncio.Event(), asyncio.Event()
    effects = []

    async def callback(text):
        started.set()
        try:
            await asyncio.Event().wait()
            effects.append("late side effect")
        finally:
            stopped.set()

    deadline = time.monotonic() + 0.2 if mode == "deadline" else None
    task = asyncio.create_task(
        OllamaModel(settings).chat(request, on_delta=callback, cancel=cancel, deadline=deadline)
    )
    await asyncio.wait_for(started.wait(), 1)
    if mode == "event":
        cancel.set()
    elif mode == "task":
        task.cancel()
    expected = asyncio.CancelledError if mode == "task" else ModelError
    with pytest.raises(expected) as result:
        await asyncio.wait_for(task, 1)
    if mode != "task":
        assert result.value.code == ("cancelled" if mode == "event" else "deadline_exceeded")
    assert stopped.is_set()
    assert effects == []
    await asyncio.wait_for(state["closed"].wait(), 1)


async def test_deadline_is_rechecked_before_success_even_if_async_callback_misbehaves(wire_server):
    state, settings, request = wire_server
    state["chunks"] = [delta("hi") + done(request.input_tokens)]

    async def callback(text):
        # Violates cooperative contract deliberately: late SUCCESS must still be impossible.
        time.sleep(0.2)

    with pytest.raises(ModelError, match="deadline_exceeded"):
        await OllamaModel(settings).chat(
            request, on_delta=callback, deadline=time.monotonic() + 0.1
        )


async def test_callback_cancellation_prevents_later_buffered_callbacks(wire_server):
    state, settings, request = wire_server
    state["chunks"] = [delta("first") + delta("later") + done(request.input_tokens)]
    cancel, received = asyncio.Event(), []

    async def callback(text):
        received.append(text)
        cancel.set()

    with pytest.raises(ModelError, match="cancelled"):
        await OllamaModel(settings).chat(request, on_delta=callback, cancel=cancel)
    assert received == ["first"]


@pytest.mark.parametrize("reason", [[], {}, True])
async def test_malformed_terminal_reason_is_structured_and_closes_transport(wire_server, reason):
    state, settings, request = wire_server
    state["chunks"] = [done(request.input_tokens, done_reason=reason), 10.0]
    with pytest.raises(ModelError) as result:
        await OllamaModel(settings).chat(request)
    assert result.value.code == "invalid_terminal"
    await asyncio.wait_for(state["closed"].wait(), 1)
