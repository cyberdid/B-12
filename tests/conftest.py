"""Small local profile: byte-level BPE without merges, no model/download."""

import hashlib
import json

import pytest
from tokenizers import Tokenizer, models, pre_tokenizers

from b12.config import Settings


@pytest.fixture
def profile_settings(tmp_path):
    assets = tmp_path / "assets"
    assets.mkdir()
    alphabet = sorted(pre_tokenizers.ByteLevel.alphabet())
    tokenizer = Tokenizer(models.BPE({char: i for i, char in enumerate(alphabet)}, []))
    tokenizer.pre_tokenizer = pre_tokenizers.ByteLevel(add_prefix_space=False, use_regex=False)
    tokenizer.save(str(assets / "tokenizer.json"))
    (assets / "tokenizer_config.json").write_text('{"bos_token":"","eos_token":""}')
    (assets / "chat_template.jinja").write_text(
        "{% for m in messages %}{{m.role}}:{{m.content}}"
        "{{m.tool_calls | default([]) | tojson}};{% endfor %}"
        "{{tools | tojson}}assistant:"
    )
    profile = {
        "renderer": "hf-jinja-v1",
        "revision": "synthetic-v1",
        "model": "test-model",
        "server_version": "test-1",
        "manifest_digest": "a" * 64,
        "native_template_sha256": hashlib.sha256(b"{{ .Prompt }}").hexdigest(),
        "files": {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in assets.iterdir()},
        "safety_tokens": 8,
        "inline_reasoning": [["<think>", "</think>"]],
    }
    path = tmp_path / "profile.json"
    path.write_text(json.dumps(profile))
    return Settings(
        state_dir=tmp_path / "state",
        model="test-model",
        model_profile=path,
        tokenizer_dir=assets,
        num_ctx=256,
        output_tokens=32,
    )


@pytest.fixture
def host_factory(tmp_path):
    """Real stores and owner control; host effects stay in this test's temp root."""
    import importlib.util
    import time
    from types import SimpleNamespace
    from uuid import uuid4

    rigs = []

    def factory(*, timeout_s=2, full_execution=True, capabilities=None, purge=None, revision=True):
        assert importlib.util.find_spec("b12.tools.filesystem") is not None, (
            "host tools are missing"
        )
        from b12.contracts import ToolCall
        from b12.control import ControlStore
        from b12.memory import MemoryStore
        from b12.retrieval import KnowledgeIndex
        from b12.tools import register_host_tools
        from b12.tools.filesystem import BackupStore
        from b12.tools.registry import ToolRegistry

        root = tmp_path / str(uuid4())
        root.mkdir()
        control = ControlStore(root / "control")
        actor = control.create_actor(owner=True, consent=True)
        session = control.create_session(actor.id)
        task = control.create_task(session)
        caps = capabilities or (
            "system.read",
            "process.read",
            "filesystem.read",
            "filesystem.write",
            "process.execute",
            "network.http",
            "memory.read",
            "memory.write",
            "memory.forget",
            "knowledge.read",
            "time.read",
        )
        grant = control.issue_grant(
            actor.id, session, caps, task_id=task, full_execution=full_execution
        )
        ctx = control.begin_turn(session, grant, task_id=task, deadline=time.monotonic() + 10)
        memory = MemoryStore(root / "memory.sqlite3")
        knowledge = KnowledgeIndex(root / "knowledge")
        backups = BackupStore(root / "backups")
        captured_revision = memory.deletion_revision(actor)
        registry = ToolRegistry(control, timeout_s=timeout_s)
        register_host_tools(
            registry,
            backups=backups,
            memory=memory,
            knowledge=knowledge,
            purge=purge,
            memory_revision=revision
            if callable(revision)
            else ((lambda context: captured_revision) if revision else None),
        )

        async def invoke(name, *, call_id=None, **arguments):
            call = ToolCall(id=call_id or str(uuid4()), name=name, arguments=arguments)
            return await registry.execute(call, ctx)

        rig = SimpleNamespace(
            root=root,
            control=control,
            actor=actor,
            context=ctx,
            registry=registry,
            memory=memory,
            knowledge=knowledge,
            backups=backups,
            invoke=invoke,
        )
        rigs.append(rig)
        return rig

    yield factory
    for rig in reversed(rigs):
        rig.backups.close()
        rig.knowledge.close()
        rig.memory.close()
        rig.control.close()


@pytest.fixture
async def scripted_ollama(profile_settings):
    """Real loopback HTTP + NDJSON Ollama stand-in driven by a per-request script.

    Each script entry is a dict {"content", "tool_calls", "delay", "hang"} or a callable
    (request_payload) -> dict. Prompt counts use the same pinned synthetic profile.
    """
    import asyncio
    import inspect

    from b12.model_profile import ModelProfile

    settings = profile_settings.model_copy(update={"num_ctx": 32768, "output_tokens": 512})
    profile = ModelProfile(settings)
    state = {
        "script": [],
        "requests": [],
        "loaded": False,
        "unloads": 0,
        "unload_status": 200,
        "chat_started": asyncio.Event(),
    }
    handlers = set()

    def frame(value):
        return json.dumps(value, ensure_ascii=False).encode() + b"\n"

    async def respond(writer, status, payload):
        body = json.dumps(payload).encode()
        writer.write(
            f"HTTP/1.1 {status} OK\r\nContent-Length: {len(body)}\r\n"
            "Connection: close\r\n\r\n".encode()
            + body
        )
        await writer.drain()

    async def handle(reader, writer):
        handlers.add(asyncio.current_task())
        try:
            header = await reader.readuntil(b"\r\n\r\n")
            path = header.split(b" ")[1].decode()
            length = next(
                (
                    int(line.split(b":")[1])
                    for line in header.split(b"\r\n")
                    if line.lower().startswith(b"content-length:")
                ),
                0,
            )
            body = json.loads(await reader.readexactly(length)) if length else {}
            if path.endswith("/api/version"):
                await respond(writer, 200, {"version": "test-1"})
            elif path.endswith("/api/tags"):
                await respond(writer, 200, {"models": [{"name": "test-model", "digest": "a" * 64}]})
            elif path.endswith("/api/show"):
                await respond(writer, 200, {"template": "{{ .Prompt }}"})
            elif path.endswith("/api/ps"):
                running = [{"name": "test-model", "model": "test-model"}] if state["loaded"] else []
                await respond(writer, 200, {"models": running})
            elif path.endswith("/api/generate"):
                if state["unload_status"] == 200 and body.get("keep_alive") == 0:
                    state["loaded"] = False
                    state["unloads"] += 1
                await respond(writer, state["unload_status"], {"done_reason": "unload"})
            elif path.endswith("/api/chat"):
                state["requests"].append(body)
                state["loaded"] = True
                state["chat_started"].set()
                step = state["script"].pop(0) if state["script"] else {"content": "Готово."}
                if callable(step):
                    step = step(body)
                    if inspect.isawaitable(step):
                        step = await step
                writer.write(b"HTTP/1.1 200 OK\r\nConnection: close\r\n\r\n")
                content = step.get("content", "")
                for piece in [content[i : i + 8] for i in range(0, len(content), 8)]:
                    writer.write(
                        frame({"message": {"role": "assistant", "content": piece}, "done": False})
                    )
                    await writer.drain()
                if step.get("hang"):
                    await reader.read(1)
                    return
                if step.get("tool_calls"):
                    calls = [
                        {
                            "function": {"name": call[0], "arguments": call[1]},
                            **({"id": call[2]} if len(call) > 2 else {}),
                        }
                        for call in step["tool_calls"]
                    ]
                    writer.write(
                        frame(
                            {
                                "message": {
                                    "role": "assistant",
                                    "content": "",
                                    "tool_calls": calls,
                                },
                                "done": False,
                            }
                        )
                    )
                count = profile.count(body["messages"], body.get("tools", []))
                writer.write(
                    frame(
                        {
                            "message": {"role": "assistant", "content": ""},
                            "done": True,
                            "done_reason": "stop",
                            "prompt_eval_count": count,
                            "eval_count": 3,
                        }
                    )
                )
                await writer.drain()
        except (ConnectionError, asyncio.IncompleteReadError):
            pass
        finally:
            writer.close()
            handlers.discard(asyncio.current_task())

    server = await asyncio.start_server(handle, "127.0.0.1", 0)
    settings = settings.model_copy(
        update={"ollama_url": f"http://127.0.0.1:{server.sockets[0].getsockname()[1]}"}
    )
    yield state, settings
    server.close()
    for task in list(handlers):
        task.cancel()
    await asyncio.gather(*handlers, return_exceptions=True)
    await server.wait_closed()


@pytest.fixture
async def api(scripted_ollama, tmp_path):
    import httpx

    from b12.api import create_app
    from b12.cli import Owner
    from b12.runtime import open_runtime

    state, settings = scripted_ollama
    settings = settings.model_copy(update={"state_dir": tmp_path / "state"})
    bootstrap = open_runtime(settings)
    actor = bootstrap.control.create_actor(owner=True, consent=True)
    bootstrap.control.set_meta("owner_actor", actor.id)
    bootstrap.control.set_meta("cli_session", bootstrap.control.create_session(actor.id))
    assert Owner(bootstrap).initialized
    bootstrap.close()
    app = create_app(settings, allowed_hosts=("testserver",), port=80)
    async with app.router.lifespan_context(app):
        token = (settings.state_dir / "api" / "owner.token").read_text().strip()
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            yield state, client, token, app, tmp_path
