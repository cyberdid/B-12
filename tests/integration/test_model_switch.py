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
        assert isinstance(runtime.agent.model.inner, OllamaModel)  # gated until warmed up
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


# --- final review fixes (24.11.2026) ---


async def test_a_turn_keeps_its_model_when_the_owner_switches_mid_turn(
    scripted_ollama, tmp_path, monkeypatch
):
    from b12 import model_switch
    from b12.auth import owner_capabilities

    class NeverCalled:
        def __init__(self, *args, **kwargs):
            pass

        async def chat(self, *args, **kwargs):
            raise AssertionError("the running turn must not move to the new model")

        async def unload(self, **_):
            return True

    monkeypatch.setattr(model_switch, "CliModel", NeverCalled)
    state, base = scripted_ollama
    runtime = open_runtime(base.model_copy(update={"state_dir": tmp_path / "state"}))
    try:
        switch = _switch(runtime, tmp_path, base, "codex")
        cloud = next(c for c in model_switch.CLOUD if c.id == "codex:gpt-6-luna")
        actor = runtime.control.create_actor(owner=True, consent=True)
        session = runtime.control.create_session(actor.id)
        task = runtime.control.create_task(session)
        grant = runtime.control.issue_grant(
            actor.id, session, owner_capabilities(runtime.settings), task_id=task
        )

        def first_round(request):
            # The worst case: the switch lands between two model rounds of one turn.
            switch._apply(cloud)
            return {"tool_calls": [("current_time", {})]}

        state["script"] = [first_round, {"content": "Зараз ранок."}]
        result = await runtime.agent.turn(session, grant, "Котра година?", task_id=task)
        assert (result.state, result.error_code) == ("completed", None)
        assert len(state["requests"]) == 2  # both rounds went to the local model
        assert isinstance(runtime.agent.model, NeverCalled)  # the next turn uses the new one
    finally:
        runtime.close()


async def test_switching_away_from_a_local_model_unloads_it(scripted_ollama, tmp_path):
    state, base = scripted_ollama
    runtime = open_runtime(base.model_copy(update={"state_dir": tmp_path / "state"}))
    try:
        state["loaded"] = True
        await _switch(runtime, tmp_path, base, "codex").switch("codex:gpt-6-luna")
        assert state["unloads"] == 1 and state["loaded"] is False
    finally:
        runtime.close()


async def test_a_broken_saved_choice_does_not_stop_the_runtime(scripted_ollama, tmp_path):
    _, base = scripted_ollama
    settings = base.model_copy(update={"state_dir": tmp_path / "state"})
    runtime = open_runtime(settings)
    runtime.control.set_meta("active_model", "local:test-model")
    runtime.close()
    switch_share = _share(tmp_path, base)
    for path in (switch_share / "tokenizers").rglob("tokenizer.json"):
        path.write_text("{}")  # corrupt the profile's tokenizer
    runtime = open_runtime(settings)
    try:
        from b12.model_switch import ModelSwitch

        switch = ModelSwitch(runtime, share=switch_share, which=_which())
        # Rebuild from the (corrupted) share dir, not the configured profile.
        switch.base = switch.base.model_copy(update={"model_profile": None, "tokenizer_dir": None})
        switch.active_id = "local:other"
        switch.restore()  # must not raise
        assert runtime.control.get_meta("active_model") in (None, "")
    finally:
        runtime.close()


async def test_a_turn_during_warm_up_waits_and_a_failed_warm_up_is_readable(
    scripted_ollama, tmp_path
):
    from b12.model_errors import ModelError
    from b12.model_switch import _Gated

    class Inner:
        async def chat(self, request, **_):
            return "answered"

        async def unload(self, **_):
            return True

    ready, failure = asyncio.Event(), []
    gated = _Gated(Inner(), ready, lambda: failure[0] if failure else None)
    call = asyncio.create_task(gated.chat(object()))
    await asyncio.sleep(0.05)
    assert not call.done()
    ready.set()
    assert await call == "answered"
    failure.append("помилка завантаження")
    with pytest.raises(ModelError, match="model_unavailable"):
        await gated.chat(object())


async def test_warm_up_reports_a_digest_that_differs_from_the_profile(scripted_ollama, tmp_path):
    state, base = scripted_ollama
    state["tags"][:] = [{"name": "test-model", "digest": "f" * 64}]
    runtime = open_runtime(base.model_copy(update={"state_dir": tmp_path / "state"}))
    try:
        switch = _switch(runtime, tmp_path, base)
        await switch.warm_up(next(c for c in switch.local_choices() if c.model == "test-model"))
        status = await switch.status()
        assert status["state"] == "error" and "профіл" in status["detail"]
    finally:
        runtime.close()


async def test_switching_to_cloud_cancels_a_running_warm_up(scripted_ollama, tmp_path):
    _, base = scripted_ollama
    runtime = open_runtime(base.model_copy(update={"state_dir": tmp_path / "state"}))
    try:
        switch = _switch(runtime, tmp_path, base, "codex")
        never = asyncio.Event()
        switch._warm = asyncio.create_task(never.wait())
        await switch.switch("codex:gpt-6-luna")
        await asyncio.sleep(0)
        assert switch._warm is None or switch._warm.cancelled()
        assert (await switch.status())["state"] == "ready"
    finally:
        runtime.close()


# --- real TUI run on the owner's laptop (24.11.2026) ---


async def test_warm_up_loads_with_the_turn_context_and_waits_until_loaded(
    scripted_ollama, tmp_path
):
    """The warm-up used Ollama's default context, so the first turn reloaded the model and timed
    out on the 8 GB GPU; status said ready before the model was in memory."""
    state, base = scripted_ollama
    runtime = open_runtime(base.model_copy(update={"state_dir": tmp_path / "state"}))
    try:
        switch = _switch(runtime, tmp_path, base)
        await switch.warm_up(next(c for c in switch.local_choices() if c.model == "test-model"))
        (body,) = state["generated"]
        assert body["options"]["num_ctx"] == base.num_ctx
        assert (await switch.status())["state"] == "ready" and state["loaded"]
    finally:
        runtime.close()


async def test_status_reports_the_part_running_on_the_cpu(scripted_ollama, tmp_path):
    state, base = scripted_ollama
    state["loaded"], state["ps_size"] = True, 10 * 1024**3  # 6 of 10 GB on the GPU
    runtime = open_runtime(base.model_copy(update={"state_dir": tmp_path / "state"}))
    try:
        status = await _switch(runtime, tmp_path, base).status()
        assert status["cpu_share"] == 0.4
    finally:
        runtime.close()


async def test_a_failed_restore_leaves_a_notice_for_the_owner(scripted_ollama, tmp_path):
    from b12.model_switch import ModelSwitch

    _, base = scripted_ollama
    runtime = open_runtime(base.model_copy(update={"state_dir": tmp_path / "state"}))
    try:
        runtime.control.set_meta("active_model", "codex:gpt-6-luna")
        switch = ModelSwitch(runtime, share=_share(tmp_path, base), which=_which())
        switch.restore()  # codex is not installed here
        assert "gpt-6-luna" in switch.notice
    finally:
        runtime.close()
