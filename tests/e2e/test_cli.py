"""Real CLI subprocesses against a loopback Ollama stand-in and temp state."""

import asyncio
import json
import os
import signal
import sys
from pathlib import Path

import pytest


@pytest.fixture
def cli(scripted_ollama, tmp_path):
    state, settings = scripted_ollama
    env = {
        "PATH": os.environ["PATH"],
        "HOME": str(tmp_path / "home"),
        "B12_STATE_DIR": str(tmp_path / "state"),
        "B12_MODEL": settings.model,
        "B12_OLLAMA_URL": settings.ollama_url,
        "B12_MODEL_PROFILE": str(settings.model_profile),
        "B12_TOKENIZER_DIR": str(settings.tokenizer_dir),
        "B12_NUM_CTX": str(settings.num_ctx),
        "B12_OUTPUT_TOKENS": str(settings.output_tokens),
    }

    async def run(*args, stdin=None, env_overrides=None, interrupt_after=None):
        process = await asyncio.create_subprocess_exec(
            sys.executable,
            "-m",
            "b12.cli",
            *args,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env={**env, **(env_overrides or {})},
        )
        if interrupt_after is not None:
            await asyncio.wait_for(interrupt_after.wait(), 10)
            await asyncio.sleep(0.2)
            process.send_signal(signal.SIGINT)
        out, err = await asyncio.wait_for(
            process.communicate(stdin.encode() if stdin else None), 60
        )
        return process.returncode, out.decode(), err.decode()

    return state, run, tmp_path


def parse(out):
    return json.loads(out)


async def test_doctor_reports_uninitialized_then_healthy(cli):
    state, run, _ = cli
    code, out, _ = await run("doctor", "--json")
    report = parse(out)
    assert code == 1 and report["initialized"] is False and report["ok"] is False
    assert report["model"]["reachable"] and report["model"]["digest_matches"]
    code, out, _ = await run("init")
    owner = parse(out)
    assert code == 0 and owner["consent"] is True
    assert parse((await run("init"))[1])["owner_id"] == owner["owner_id"]
    code, out, _ = await run("doctor", "--json")
    report = parse(out)
    assert code == 0 and report["ok"] and report["initialized"]
    assert report["state_dir"].endswith("state") and report["pending_purges"] == 0


async def test_noninteractive_turn_returns_json_and_real_effect(cli):
    state, run, tmp_path = cli
    await run("init")
    target = tmp_path / "cli-note.txt"
    state["script"] = [
        {"tool_calls": [("file_write", {"path": str(target), "text": "з CLI"})]},
        {"content": "Записав."},
    ]
    code, out, _ = await run("chat", "-m", "запиши файл", "--json")
    result = parse(out)
    assert code == 0 and result["state"] == "completed" and result["content"] == "Записав."
    assert result["tool_results"][0]["status"] == "completed"
    assert target.read_text() == "з CLI"


async def test_memory_survives_separate_processes_and_forget(cli):
    state, run, _ = cli
    await run("init")
    code, out, _ = await run("memory", "remember", "синтетичний факт про CLI")
    record = parse(out)
    assert code == 0
    code, out, _ = await run("memory", "search", "синтетичний")
    assert [r["id"] for r in parse(out)] == [record["id"]]
    code, out, _ = await run("memory", "forget", record["id"])
    assert code == 0 and parse(out)["state"] == "complete"
    assert parse((await run("memory", "search", "синтетичний"))[1]) == []
    assert parse((await run("memory", "pending"))[1]) == []


async def test_approval_flow_across_processes(cli):
    state, run, _ = cli
    await run("init")
    record = parse((await run("memory", "remember", "видалити через approval"))[1])
    state["script"] = [
        {"tool_calls": [("memory_forget", {"memory_id": record["id"]})]},
        {"content": "Забув."},
    ]
    code, out, _ = await run("chat", "-m", "забудь", "--json")
    waiting = parse(out)
    assert code == 2 and waiting["state"] == "awaiting_approval"
    pending = parse((await run("approvals"))[1])
    assert [p["operation_id"] for p in pending] == waiting["pending_operations"]
    assert pending[0]["name"] == "memory_forget"
    assert (await run("approve", waiting["pending_operations"][0]))[0] == 0
    code, out, _ = await run("resume", waiting["turn_id"], "--json")
    assert code == 0 and parse(out)["state"] == "completed"
    assert parse((await run("memory", "search", "approval"))[1]) == []


async def test_interactive_conversation_keeps_history(cli):
    state, run, _ = cli
    await run("init")
    state["script"] = [{"content": "Привіт, я B-12."}, {"content": "Добре."}]
    code, out, err = await run("chat", stdin="привіт\nяк справи\n")
    assert code == 0
    assert "Привіт, я B-12." in out and "Добре." in out
    second = [m["content"] for m in state["requests"][1]["messages"]]
    assert "привіт" in second and "Привіт, я B-12." in second


async def test_ctrl_c_cancels_turn_without_corrupting_state(cli):
    state, run, _ = cli
    await run("init")
    state["script"] = [{"content": "довга відповідь", "hang": True}, {"content": "після"}]
    code, out, _ = await run("chat", "-m", "довго", "--json", interrupt_after=state["chat_started"])
    assert code == 130 and parse(out)["state"] == "cancelled"
    assert (await run("doctor", "--json"))[0] == 0
    code, out, _ = await run("chat", "-m", "ще раз", "--json")
    assert code == 0 and parse(out)["content"] == "після"


async def test_unreachable_model_is_explicit(cli):
    _, run, _ = cli
    await run("init")
    dead = {"B12_OLLAMA_URL": "http://127.0.0.1:9"}
    code, out, _ = await run("doctor", "--json", env_overrides=dead)
    assert code == 1 and parse(out)["model"]["reachable"] is False
    code, out, _ = await run("chat", "-m", "привіт", "--json", env_overrides=dead)
    result = parse(out)
    assert code == 1 and result["state"] == "failed"
    assert result["error_code"] == "transport_error"


async def test_missing_profile_is_explicit_error(cli):
    _, run, tmp_path = cli
    code, out, _ = await run(
        "chat", "-m", "x", "--json", env_overrides={"B12_MODEL_PROFILE": str(tmp_path / "none")}
    )
    assert code == 1 and parse(out)["error"] == "profile_invalid"


async def test_tools_lists_catalog_without_secrets(cli):
    _, run, _ = cli
    code, out, _ = await run("tools")
    tools = {t["name"]: t for t in parse(out)}
    assert code == 0 and len(tools) == 14 and "run_command" in tools
    assert tools["shell_exec"]["risk"] == "arbitrary"
    assert tools["memory_forget"]["risk"] == "destructive"


def test_installed_entry_point_is_declared():
    import tomllib

    root = Path(__file__).resolve().parents[2]
    scripts = tomllib.loads((root / "pyproject.toml").read_text())["project"]["scripts"]
    assert scripts["b12"] == "b12.cli:main"


async def test_chat_startup_finishes_pending_purge_first(cli):
    state, run, _ = cli
    await run("init")
    record = parse((await run("memory", "remember", "кешований CLI факт"))[1])
    state["loaded"], state["unload_status"] = True, 500
    code, out, _ = await run("memory", "forget", record["id"])
    assert code == 3 and parse(out)["pending_stores"] == ["provider_cache"]
    assert (await run("doctor", "--json"))[0] == 1
    state["unload_status"] = 200
    state["script"] = [{"content": "ok"}]
    assert (await run("chat", "-m", "привіт", "--json"))[0] == 0
    assert parse((await run("memory", "pending"))[1]) == []


async def test_goal_lifecycle_and_autonomy_tick_across_processes(cli):
    state, run, tmp_path = cli
    await run("init")
    target = tmp_path / "goal.txt"
    code, out, _ = await run(
        "goals",
        "add",
        "Створити файл звіту",
        "--budget",
        "2",
        "--check-file",
        str(target),
        "--check-text",
        "звіт 9",
    )
    goal = parse(out)
    assert code == 0 and goal["status"] == "active"
    state["script"] = [
        {"tool_calls": [("file_write", {"path": str(target), "text": "звіт 9"})]},
        {"content": "Звіт записано."},
    ]
    code, out, _ = await run("autonomy")
    [outcome] = parse(out)
    assert code == 0 and outcome["status"] == "achieved"
    listed = parse((await run("goals", "list"))[1])
    assert listed[0]["status"] == "achieved" and listed[0]["consumed_turns"] == 1
    assert parse((await run("quiet", "on"))[1]) == {"quiet": True, "stopped": False}
    assert parse((await run("stop", "on"))[1])["stopped"] is True
