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
            memory_revision=(lambda context: captured_revision) if revision else None,
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
