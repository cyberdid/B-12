"""Task D1: ADR-019 goal completion contract, trusted checks, boundaries, failure streak."""

import asyncio
import hashlib
import json
import sqlite3
import subprocess
import sys
from datetime import UTC, datetime, timedelta

import pytest

from b12.auth import owner_capabilities
from b12.autonomy import Scheduler, check_passes
from b12.config import Settings
from b12.goals import GoalStore
from b12.runtime import open_runtime

CAPS = ("filesystem.read", "filesystem.write", "memory.read", "memory.write", "time.read")


_CLOCK_REF: list = []


class Clock:
    """A pinned clock: the test must not depend on the wall-clock time of day."""

    def __init__(self):
        self.now = datetime(2026, 11, 21, 10, 0, tzinfo=UTC)
        _CLOCK_REF[:] = [self]

    def __call__(self):
        return self.now


@pytest.fixture(autouse=True)
def _pin_goal_clock(monkeypatch):
    """GoalStore stamps goals and proposals with real time; pin them to the test clock."""
    from b12 import goals as goals_module

    _CLOCK_REF.clear()

    def now():
        if _CLOCK_REF:
            return _CLOCK_REF[0].now.isoformat()
        return datetime(2026, 11, 21, 10, 0, tzinfo=UTC).isoformat()

    monkeypatch.setattr(goals_module, "_now", now)


def _open_rig(scripted_ollama, tmp_path, **setting_updates):
    state, base = scripted_ollama
    settings = base.model_copy(
        update={
            "state_dir": tmp_path / "state",
            "goal_contract": True,
            **setting_updates,
        }
    )
    clock = Clock()
    runtime = open_runtime(settings)
    runtime.attention.clock = clock
    runtime.agent.clock = clock
    scheduler = Scheduler(runtime, clock=clock)
    actor = runtime.control.create_actor(owner=True, consent=True)
    return state, runtime, scheduler, actor, clock


def test_command_exit_zero_runs_only_allowlisted_argv(tmp_path, monkeypatch):
    marker = tmp_path / "executed.txt"
    script = f"from pathlib import Path; Path({str(marker)!r}).write_text('x')"
    argv = [sys.executable, "-c", script]
    spec = {"kind": "command_exit_zero", "argv": argv}

    called = []
    real_run = subprocess.run

    def spy_run(*args, **kwargs):
        called.append((args, kwargs))
        return real_run(*args, **kwargs)

    monkeypatch.setattr(subprocess, "run", spy_run)

    # Not in allowlist -> False, never executed.
    settings_empty = Settings(state_dir=tmp_path / "s1", goal_check_commands=())
    assert check_passes(spec, settings_empty) is False
    assert called == []
    assert not marker.exists()

    # Exact tuple in allowlist -> runs with shell=False, timeout=60.
    settings_allowed = Settings(state_dir=tmp_path / "s2", goal_check_commands=(tuple(argv),))
    assert check_passes(spec, settings_allowed) is True
    assert marker.exists()
    assert len(called) == 1
    assert called[0][1]["shell"] is False
    assert called[0][1]["timeout"] == 60

    # Non-zero exit code -> False.
    fail_argv = [sys.executable, "-c", "import sys; sys.stderr.write('boom\\n'); sys.exit(2)"]
    settings_fail = Settings(state_dir=tmp_path / "s3", goal_check_commands=(tuple(fail_argv),))
    assert check_passes({"kind": "command_exit_zero", "argv": fail_argv}, settings_fail) is False


async def test_file_sha256_check(scripted_ollama, tmp_path):
    target = tmp_path / "artifact.bin"
    payload = b"verified-bytes-42"
    digest = hashlib.sha256(payload).hexdigest()
    spec = {"kind": "file_sha256", "path": str(target), "sha256": digest}

    assert check_passes(spec) is False
    target.write_bytes(b"wrong")
    assert check_passes(spec) is False
    target.write_bytes(payload)
    assert check_passes(spec) is True
    assert check_passes({**spec, "sha256": digest.upper()}) is True

    # End-to-end in Scheduler when goal_contract=True.
    state, runtime, scheduler, actor, clock = _open_rig(scripted_ollama, tmp_path)
    try:
        out = tmp_path / "goal-output.txt"
        out_text = "exact-goal-text"
        out_hash = hashlib.sha256(out_text.encode("utf-8")).hexdigest()
        session = runtime.control.create_session(actor.id)
        goal = runtime.goals.create(
            actor.id,
            session,
            "Записати точний артефакт",
            "хеш збігається",
            allowed_tools=CAPS,
            contract={
                "verification": {"kind": "file_sha256", "path": str(out), "sha256": out_hash}
            },
        )
        state["script"] = [
            {"tool_calls": [("file_write", {"path": str(out), "text": out_text})]},
            {"content": "Записано."},
        ]
        [outcome] = await scheduler.tick()
        assert outcome["status"] == "achieved"
        assert runtime.goals.get(goal["id"], actor.id)["status"] == "achieved"
    finally:
        scheduler.close()
        runtime.close()


async def test_http_status_check_respects_network_allow(tmp_path):
    async def handler(reader, writer):
        await reader.readuntil(b"\r\n\r\n")
        writer.write(b"HTTP/1.1 204 No Content\r\nContent-Length: 0\r\nConnection: close\r\n\r\n")
        await writer.drain()
        writer.close()

    server = await asyncio.start_server(handler, "127.0.0.1", 0)
    async with server:
        port = server.sockets[0].getsockname()[1]
        spec = {"kind": "http_status", "url": f"http://127.0.0.1:{port}/health", "status": 204}
        denied_settings = Settings(state_dir=tmp_path / "s1", network_allow=())
        allowed_settings = Settings(state_dir=tmp_path / "s2", network_allow=("127.0.0.1",))
        wrong_status = {
            "kind": "http_status",
            "url": f"http://127.0.0.1:{port}/health",
            "status": 200,
        }

        assert await asyncio.to_thread(check_passes, spec, denied_settings) is False
        assert await asyncio.to_thread(check_passes, spec, allowed_settings) is True
        assert await asyncio.to_thread(check_passes, wrong_status, allowed_settings) is False


async def test_call_outside_boundaries_is_refused_before_prepare(
    scripted_ollama, tmp_path, monkeypatch
):
    allowed_dir = tmp_path / "allowed"
    allowed_dir.mkdir()
    allowed_file = allowed_dir / "ok.txt"
    allowed_file.write_text("allowed-content", encoding="utf-8")

    outside_dir = tmp_path / "allowed_evil"
    outside_dir.mkdir()
    outside_file = outside_dir / "secret.txt"
    outside_file.write_text("secret-content", encoding="utf-8")

    escape_link = allowed_dir / "escape.txt"
    escape_link.symlink_to(outside_file)

    state, runtime, scheduler, actor, clock = _open_rig(scripted_ollama, tmp_path)
    try:
        prepare_calls = []
        real_prepare = runtime.control.prepare

        def spy_prepare(context, call, *args, **kwargs):
            prepare_calls.append(call.name)
            return real_prepare(context, call, *args, **kwargs)

        monkeypatch.setattr(runtime.control, "prepare", spy_prepare)

        session = runtime.control.create_session(actor.id)
        contract = {
            "verification": "read allowed file only",
            "constraints": ["never modify files", "stay inside allowed"],
            "boundaries": {"tools": ["file_read"], "paths": [str(allowed_dir)]},
            "stop_when": "allowed file is missing",
        }
        runtime.goals.create(
            actor.id,
            session,
            "Прочитати дозволений файл",
            "текст прочитано",
            allowed_tools=CAPS,
            contract=contract,
        )
        state["script"] = [
            {"tool_calls": [("file_write", {"path": str(allowed_dir / "w.txt"), "text": "x"})]},
            {"tool_calls": [("file_read", {"path": str(outside_file)})]},
            {"tool_calls": [("file_read", {"path": str(escape_link)})]},
            {"tool_calls": [("file_read", {"path": str(allowed_file)})]},
            {"content": "Прочитано."},
        ]
        [outcome] = await scheduler.tick()
        assert outcome["state"] == "completed"

        # Only the valid in-boundary file_read reached control.prepare!
        assert prepare_calls == ["file_read"]
        assert not (allowed_dir / "w.txt").exists()

        # Verify system prompt exposed all 4 contract sections and tools were narrowed.
        first_req = state["requests"][0]
        system = first_req["messages"][0]["content"]
        for key in ("verification", "constraints", "boundaries", "stop_when"):
            assert key in system
        offered = [t["function"]["name"] for t in first_req.get("tools", [])]
        assert offered == ["file_read"]

        # Verify tool messages / requests saw outside_goal_boundaries for refused calls.
        all_tool_msgs = [
            json.loads(m["content"])
            for m in state["requests"][-1]["messages"]
            if m["role"] == "tool"
        ]
        assert [m["error_code"] for m in all_tool_msgs[:3]] == [
            "outside_goal_boundaries",
            "outside_goal_boundaries",
            "outside_goal_boundaries",
        ]
        assert all_tool_msgs[3]["status"] == "completed"
    finally:
        scheduler.close()
        runtime.close()


async def test_goal_blocked_marker_pauses_with_needs_owner(scripted_ollama, tmp_path):
    state, runtime, scheduler, actor, clock = _open_rig(scripted_ollama, tmp_path)
    try:
        session = runtime.control.create_session(actor.id)
        goal = runtime.goals.create(
            actor.id,
            session,
            "Оновити конфіг API",
            "оновлено",
            allowed_tools=CAPS,
            contract={"stop_when": "потрібен ключ доступу"},
        )
        state["script"] = [{"content": "[GOAL_BLOCKED] Потрібен токен від власника"}]
        [outcome] = await scheduler.tick()
        stored = runtime.goals.get(goal["id"], actor.id)
        assert stored["status"] == "paused"
        assert "needs_owner" in stored["status_reason"]
        assert "Потрібен токен від власника" in stored["status_reason"]
        assert outcome["status"] == "paused"
        assert outcome["initiative_decision"] == "needs_owner"
        assert outcome["delivered"] is False
        [proposal] = runtime.goals.proposals(actor.id)
        assert proposal["decision"] == "needs_owner"
        assert proposal["delivered"] == 0

        # Direct Agent.turn path also pauses with needs_owner when goal_contract is True.
        goal2 = runtime.goals.create(
            actor.id,
            session,
            "Пряма перевірка",
            "готово",
            allowed_tools=CAPS,
        )
        task2 = runtime.control.create_task(session)
        runtime.control.link_task_goal(task2, goal2["id"], goal2["plan_revision"])
        grant2 = runtime.control.issue_grant(
            actor.id, session, owner_capabilities(runtime.settings), task_id=task2, ttl_s=600
        )
        state["script"] = [{"content": "[GOAL_BLOCKED] Відсутній файл ліцензії"}]
        await runtime.agent.turn(session, grant2, "Виконай крок.", task_id=task2, timeout_s=60)
        stored2 = runtime.goals.get(goal2["id"], actor.id)
        assert stored2["status"] == "paused"
        assert "needs_owner" in stored2["status_reason"]
        assert "Відсутній файл ліцензії" in stored2["status_reason"]
    finally:
        scheduler.close()
        runtime.close()


async def test_three_failed_checks_pause_the_goal(scripted_ollama, tmp_path):
    fail_code = "import sys; sys.stderr.write('err-tail-marker\\n'); sys.exit(1)"
    fail_argv = [sys.executable, "-c", fail_code]
    state, runtime, scheduler, actor, clock = _open_rig(
        scripted_ollama, tmp_path, goal_check_commands=(tuple(fail_argv),)
    )
    try:
        session = runtime.control.create_session(actor.id)
        goal = runtime.goals.create(
            actor.id,
            session,
            "Досягти зеленого тесту",
            "код виходу 0",
            allowed_tools=CAPS,
            budget_turns=10,
            review_interval_s=60,
            check={"kind": "command_exit_zero", "argv": fail_argv},
        )
        for expected_streak in (1, 2):
            state["script"] = [{"content": f"Спроба {expected_streak}."}]
            [outcome] = await scheduler.tick()
            current = runtime.goals.get(goal["id"], actor.id)
            assert outcome["status"] == "active"
            assert current["status"] == "active"
            assert current["failure_streak"] == expected_streak
            clock.now += timedelta(seconds=61)

        # Second turn should have received the failing check output tail from the first turn.
        assert "err-tail-marker" in state["requests"][1]["messages"][-1]["content"]

        state["script"] = [{"content": "Спроба 3."}]
        [third] = await scheduler.tick()
        paused = runtime.goals.get(goal["id"], actor.id)
        assert third["status"] == "paused"
        assert paused["status"] == "paused"
        assert paused["status_reason"] == "check_failed_3x"
        assert paused["failure_streak"] == 3
        assert third["initiative_decision"] == "needs_owner"
        assert third["delivered"] is False

        # Goal no longer runs on subsequent ticks while paused.
        clock.now += timedelta(seconds=61)
        assert await scheduler.tick() == []

        # record_check resets streak to 0 when passed=True.
        assert runtime.goals.record_check(goal["id"], True) == 0
    finally:
        scheduler.close()
        runtime.close()


def test_contract_is_immutable(tmp_path):
    store = GoalStore(tmp_path / "goals")
    try:
        goal = store.create(
            "owner",
            "session",
            "Незмінний контракт",
            "готово",
            contract={
                "verification": "exit 0",
                "constraints": ["no secrets"],
                "boundaries": {"tools": ["file_read"], "paths": ["/tmp"]},
                "stop_when": "error",
            },
        )
        assert goal["contract"]["verification"] == "exit 0"
        assert goal["failure_streak"] == 0
        with pytest.raises(sqlite3.IntegrityError):
            store.db.execute("UPDATE goals SET contract='{}' WHERE id=?", (goal["id"],))
    finally:
        store.close()

    # Migrating an older DB without contract/failure_streak adds columns & upgrades trigger.
    db = sqlite3.connect(tmp_path / "goals" / "goals.sqlite3")
    db.execute("DROP TRIGGER goals_intent_immutable")
    db.execute("ALTER TABLE goals DROP COLUMN contract")
    db.execute("ALTER TABLE goals DROP COLUMN failure_streak")
    db.execute(
        "CREATE TRIGGER goals_intent_immutable BEFORE UPDATE OF intent, criteria, actor_id "
        "ON goals BEGIN SELECT RAISE(ABORT, 'original intent is immutable'); END"
    )
    db.commit()
    db.close()

    migrated = GoalStore(tmp_path / "goals")
    try:
        g2 = migrated.create(
            "owner", "session", "Після міграції", "ok", contract={"stop_when": "x"}
        )
        with pytest.raises(sqlite3.IntegrityError):
            migrated.db.execute("UPDATE goals SET contract=NULL WHERE id=?", (g2["id"],))
    finally:
        migrated.close()


async def test_goal_contract_flag_off_keeps_legacy_behavior(scripted_ollama, tmp_path):
    outside = tmp_path / "outside.txt"
    outside.write_text("legacy-read", encoding="utf-8")
    state, runtime, scheduler, actor, clock = _open_rig(
        scripted_ollama, tmp_path, goal_contract=False
    )
    try:
        session = runtime.control.create_session(actor.id)
        goal = runtime.goals.create(
            actor.id,
            session,
            "Стара поведінка",
            "готово",
            allowed_tools=CAPS,
            contract={"boundaries": {"tools": ["current_time"], "paths": ["/nonexistent"]}},
        )
        state["script"] = [
            {"tool_calls": [("file_read", {"path": str(outside)})]},
            {"content": "[GOAL_BLOCKED] не повинно ставити на паузу при вимкненому прапорці"},
        ]
        [outcome] = await scheduler.tick()
        assert outcome["status"] == "active"
        assert runtime.goals.get(goal["id"], actor.id)["status"] == "active"
        system = state["requests"][0]["messages"][0]["content"]
        assert "boundaries" not in system
        tool_msg = next(
            json.loads(m["content"])
            for m in state["requests"][1]["messages"]
            if m["role"] == "tool"
        )
        assert tool_msg["status"] == "completed"
    finally:
        scheduler.close()
        runtime.close()


def test_cli_goals_add_supports_contract_options(tmp_path, monkeypatch, capsys):
    from b12.cli import main

    state_dir = tmp_path / "cli-state"
    monkeypatch.setenv("B12_STATE_DIR", str(state_dir))
    assert main(["init"]) == 0
    capsys.readouterr()

    exit_code = main(
        [
            "goals",
            "add",
            "Перевірити контракт через CLI",
            "--verify-kind",
            "file_sha256",
            "--verify-arg",
            str(tmp_path / "out.txt"),
            "--verify-arg",
            "a" * 64,
            "--constraints",
            "не змінювати конфіг",
            "--boundary-tool",
            "file_read",
            "--boundary-path",
            str(tmp_path),
            "--stop-when",
            "файл відсутній",
        ]
    )
    assert exit_code == 0
    created = json.loads(capsys.readouterr().out)
    assert created["check_spec"] == {
        "kind": "file_sha256",
        "path": str(tmp_path / "out.txt"),
        "sha256": "a" * 64,
    }
    assert created["contract"] == {
        "verification": {
            "kind": "file_sha256",
            "path": str(tmp_path / "out.txt"),
            "sha256": "a" * 64,
        },
        "constraints": ["не змінювати конфіг"],
        "boundaries": {"tools": ["file_read"], "paths": [str(tmp_path)]},
        "stop_when": "файл відсутній",
    }


def test_run_u2_u3_accepts_goal_contract_flag(tmp_path, monkeypatch):
    from evals.unified.run_u2_u3 import RUNTIME_FLAGS, main

    assert "goal_contract" in RUNTIME_FLAGS
    monkeypatch.delenv("B12_EVAL_SANDBOX", raising=False)
    manifest = tmp_path / "m.json"
    manifest.write_text('{"scenarios": []}')
    with pytest.raises(SystemExit) as stop:
        main([str(manifest), "X", str(tmp_path / "out"), "--goal-contract"])
    assert stop.value.code == 2
