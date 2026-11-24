"""Between-turn model switching: local Ollama models with a profile, subscription CLIs (ADR-023)."""

import asyncio
import json
import shutil

import pytest

from b12.runtime import open_runtime


def _share(tmp_path, base):
    """A share dir with the test profile and its tokenizer, as ~/.local/share/b12 holds them."""
    share = tmp_path / "share"
    if share.exists():
        return share
    profile = json.loads(base.model_profile.read_text())
    (share / "profiles").mkdir(parents=True)
    (share / "profiles" / "test.json").write_text(json.dumps(profile))
    shutil.copytree(base.tokenizer_dir, share / "tokenizers" / "test" / profile["revision"])
    return share


def _which(*available):
    return lambda name: f"/usr/bin/{name}" if name in available else None


def _switch(runtime, tmp_path, base, *clis):
    from b12.model_switch import ModelSwitch

    return ModelSwitch(runtime, share=_share(tmp_path, base), which=_which(*clis))


async def test_catalog_lists_local_models_with_a_profile_and_cloud_clis(scripted_ollama, tmp_path):
    state, base = scripted_ollama
    state["tags"].append({"name": "no-profile:7b", "digest": "c" * 64})
    runtime = open_runtime(base.model_copy(update={"state_dir": tmp_path / "state"}))
    try:
        switch = _switch(runtime, tmp_path, base, "codex", "claude")
        ids = [c.id for c in await switch.catalog()]
        assert "local:test-model" in ids and "local:no-profile:7b" not in ids
        assert "codex:gpt-6-luna" in ids and "claude:claude-opus-5-5" in ids
        assert not any(i.startswith("agy:") for i in ids)
        cloud = next(c for c in await switch.catalog() if c.id == "codex:gpt-6-luna")
        assert (cloud.kind, cloud.location) == ("cloud", "хмара")
    finally:
        runtime.close()


async def test_switch_to_cloud_and_back(scripted_ollama, tmp_path):
    from b12.cloud_model import CliModel
    from b12.model import OllamaModel

    _, base = scripted_ollama
    runtime = open_runtime(base.model_copy(update={"state_dir": tmp_path / "state"}))
    try:
        switch = _switch(runtime, tmp_path, base, "codex")
        await switch.switch("codex:gpt-6-luna")
        assert isinstance(runtime.agent.model, CliModel)
        assert runtime.agent.settings.num_ctx == 200000
        assert runtime.agent.builder.settings.output_tokens == 16384
        assert switch.active_id == "codex:gpt-6-luna"
        await switch.switch("local:test-model")
        assert isinstance(runtime.agent.model, OllamaModel)
        assert runtime.agent.settings.num_ctx == base.num_ctx
        assert runtime.control.get_meta("active_model") == "local:test-model"
    finally:
        runtime.close()


async def test_switch_waits_for_the_running_model_call(scripted_ollama, tmp_path):
    _, base = scripted_ollama
    runtime = open_runtime(base.model_copy(update={"state_dir": tmp_path / "state"}))
    try:
        switch = _switch(runtime, tmp_path, base, "codex")
        await runtime.agent.model_lock.acquire()
        pending = asyncio.create_task(switch.switch("codex:gpt-6-luna"))
        await asyncio.sleep(0.1)
        assert not pending.done() and switch.active_id.startswith("local:")
        runtime.agent.model_lock.release()
        await pending
        assert switch.active_id == "codex:gpt-6-luna"
    finally:
        runtime.close()


async def test_unknown_model_is_refused_and_nothing_changes(scripted_ollama, tmp_path):
    _, base = scripted_ollama
    runtime = open_runtime(base.model_copy(update={"state_dir": tmp_path / "state"}))
    try:
        switch = _switch(runtime, tmp_path, base)
        model = runtime.agent.model
        with pytest.raises(KeyError):
            await switch.switch("codex:gpt-6-luna")  # codex is not installed here
        assert runtime.agent.model is model
    finally:
        runtime.close()


async def test_local_warm_up_pulls_a_missing_model_with_progress(scripted_ollama, tmp_path):
    state, base = scripted_ollama
    state["tags"][:] = []  # the profile's model is not downloaded yet
    state["pull"] = [{"status": "pulling", "total": 100, "completed": 40}]
    runtime = open_runtime(base.model_copy(update={"state_dir": tmp_path / "state"}))
    try:
        switch = _switch(runtime, tmp_path, base)
        seen = []
        switch.on_status = lambda s: seen.append((s["state"], s.get("progress")))
        await switch.warm_up(next(c for c in switch.local_choices() if c.model == "test-model"))
        assert ("pulling", 0.4) in seen
        assert seen[-1][0] == "ready"
        status = await switch.status()
        assert status["state"] == "ready" and status["vram_mb"] == 6144
        assert state["pulled"] == ["test-model"]
    finally:
        runtime.close()


async def test_active_model_is_restored_after_restart(scripted_ollama, tmp_path):
    from b12.cloud_model import CliModel

    _, base = scripted_ollama
    settings = base.model_copy(update={"state_dir": tmp_path / "state"})
    runtime = open_runtime(settings)
    try:
        await _switch(runtime, tmp_path, base, "claude").switch("claude:claude-sonnet-5-5")
    finally:
        runtime.close()
    runtime = open_runtime(settings)
    try:
        switch = _switch(runtime, tmp_path, base, "claude")
        switch.restore()
        assert switch.active_id == "claude:claude-sonnet-5-5"
        assert isinstance(runtime.agent.model, CliModel)
    finally:
        runtime.close()


async def test_a_model_not_downloaded_is_marked_in_the_catalog(scripted_ollama, tmp_path):
    state, base = scripted_ollama
    state["tags"][:] = []
    runtime = open_runtime(base.model_copy(update={"state_dir": tmp_path / "state"}))
    try:
        switch = _switch(runtime, tmp_path, base)
        (local,) = [c for c in await switch.catalog() if c.kind == "local"]
        assert "не завантажено" in local.warning
    finally:
        runtime.close()
