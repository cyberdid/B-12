"""ADR-021 procedural memory: SkillStore, skills index, skill_view, proposals, curator (F1-F2)."""

import asyncio
import hashlib
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from b12.auth import GUEST_CAPABILITIES, owner_capabilities
from b12.runtime import open_runtime


def _write_skill(root: Path, name: str, text: str, *, extra_files: dict[str, str] | None = None):
    skill_dir = root / name
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(text, encoding="utf-8")
    for rel, body in (extra_files or {}).items():
        target = skill_dir / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(body, encoding="utf-8")
    return skill_dir


def _skill_md(name: str, description: str, body: str = "## Procedure\n1. Check logs.\n") -> str:
    return f"---\nname: {name}\ndescription: {description}\n---\n\n{body}"


async def test_view_refuses_paths_outside_the_skill(scripted_ollama, tmp_path):
    from b12.skills import SkillStore

    skills_dir = tmp_path / "skills"
    store = SkillStore(skills_dir)
    skill_dir = _write_skill(
        skills_dir,
        "deploy-check",
        _skill_md("deploy-check", "Verify unit health after deploy", "## Procedure\nRun checks.\n"),
        extra_files={"references/checklist.md": "- verify systemd\n"},
    )
    outside = tmp_path / "secret.txt"
    outside.write_text("TOP_SECRET", encoding="utf-8")
    (skill_dir / "escape-link.md").symlink_to(outside)
    escape_dir = skill_dir / "references" / "linked-dir"
    escape_dir.symlink_to(tmp_path)
    symlink_skill = skills_dir / "linked-skill"
    symlink_skill.symlink_to(tmp_path)

    assert "## Procedure" in store.view("deploy-check")
    assert "verify systemd" in store.view("deploy-check", "references/checklist.md")

    bad_paths = [
        "../secret.txt",
        "references/../../secret.txt",
        "/etc/passwd",
        str(outside),
        "escape-link.md",
        "references/linked-dir/secret.txt",
        ".",
        "references",
        "references\\checklist.md",
    ]
    for bad in bad_paths:
        with pytest.raises(ValueError, match="path outside skill"):
            store.view("deploy-check", bad)

    with pytest.raises(ValueError, match="path outside skill"):
        store.view("linked-skill")
    with pytest.raises(ValueError, match="path outside skill"):
        store.view("../secret.txt")

    # Tool-level execution with skills=True refuses outside paths and reads valid files.
    state, base = scripted_ollama
    state_dir = tmp_path / "rt-state"
    rt_skills = state_dir / "skills"
    _write_skill(
        rt_skills,
        "deploy-check",
        _skill_md("deploy-check", "Verify unit health after deploy", "## Procedure\nRun checks.\n"),
        extra_files={"references/checklist.md": "- verify systemd\n"},
    )
    (rt_skills / "deploy-check" / "escape.md").symlink_to(outside)

    runtime = open_runtime(base.model_copy(update={"state_dir": state_dir, "skills": True}))
    try:
        actor = runtime.control.create_actor(owner=True, consent=True)
        session = runtime.control.create_session(actor.id)
        task = runtime.control.create_task(session)
        grant = runtime.control.issue_grant(
            actor.id, session, owner_capabilities(runtime.settings), task_id=task, ttl_s=600
        )
        state["script"] = [
            {
                "tool_calls": [
                    ("skill_view", {"name": "deploy-check", "path": "../secret.txt"}, "c1"),
                    ("skill_view", {"name": "deploy-check", "path": "escape.md"}, "c2"),
                    ("skill_view", {"name": "deploy-check", "path": "/etc/passwd"}, "c3"),
                    (
                        "skill_view",
                        {"name": "deploy-check", "path": "references/checklist.md"},
                        "c4",
                    ),
                ]
            },
            {"content": "Перевірив навичку."},
        ]
        result = await runtime.agent.turn(
            session, grant, "Покажи чекліст deploy-check", task_id=task, timeout_s=60
        )
        assert result.state == "completed"
        by_id = {r.call_id: r for r in result.tool_results}
        assert by_id["c1"].status == "failed" and by_id["c1"].error_code == "permission_denied"
        assert by_id["c2"].status == "failed" and by_id["c2"].error_code == "permission_denied"
        assert by_id["c3"].status == "failed" and by_id["c3"].error_code == "permission_denied"
        assert by_id["c4"].status == "completed"
        assert "verify systemd" in by_id["c4"].content["text"]
        assert "TOP_SECRET" not in str(by_id["c1"].content)
        assert "TOP_SECRET" not in str(by_id["c2"].content)
    finally:
        runtime.close()


async def test_index_lists_active_skills_only_with_the_flag(scripted_ollama, tmp_path):
    from b12.agent import OWNER_SPEAKER
    from b12.skills import SkillStore

    state, base = scripted_ollama

    async def run_with_flag(*, skills_flag: bool, stable_prefix: bool = False):
        state["requests"].clear()
        state_dir = tmp_path / f"state-{skills_flag}-{stable_prefix}"
        store = SkillStore(state_dir / "skills")
        for idx in range(23):
            _write_skill(
                store.path,
                f"skill-{idx:02d}",
                _skill_md(f"skill-{idx:02d}", f"Опис процедури номер {idx:02d}"),
            )
        _write_skill(
            store.path,
            "zzz-stale",
            _skill_md("zzz-stale", "Застаріла процедура"),
        )
        _write_skill(
            store.path,
            "zzz-forgotten",
            _skill_md("zzz-forgotten", "Втрачена процедура"),
        )
        _write_skill(
            store.path / ".archive",
            "zzz-archived",
            _skill_md("zzz-archived", "Архівна процедура"),
        )
        store.set_status("zzz-stale", "stale")
        store.set_status("zzz-forgotten", "source_forgotten")

        listed = {item["name"]: item for item in store.list()}
        assert listed["skill-00"]["status"] == "active"
        assert listed["zzz-stale"]["status"] == "stale"
        assert listed["zzz-forgotten"]["status"] == "source_forgotten"
        assert listed["zzz-archived"]["status"] == "archived"

        runtime = open_runtime(
            base.model_copy(
                update={
                    "state_dir": state_dir,
                    "skills": skills_flag,
                    "stable_prefix": stable_prefix,
                }
            )
        )
        try:
            owner = runtime.control.create_actor(owner=True, consent=True)
            session = runtime.control.create_session(owner.id)
            task = runtime.control.create_task(session)
            grant = runtime.control.issue_grant(
                owner.id, session, owner_capabilities(runtime.settings), task_id=task, ttl_s=600
            )
            state["script"] = [{"content": "Привіт."}]
            await runtime.agent.turn(session, grant, "Привіт", task_id=task, timeout_s=60)
            owner_req = state["requests"][-1]

            guest = runtime.control.create_actor(owner=False, consent=True)
            guest_sess = runtime.control.create_session(guest.id)
            guest_task = runtime.control.create_task(guest_sess)
            guest_grant = runtime.control.issue_grant(
                guest.id,
                guest_sess,
                tuple(sorted((*GUEST_CAPABILITIES, "memory.read"))),
                task_id=guest_task,
                ttl_s=600,
            )
            state["script"] = [{"content": "Вітаю."}]
            await runtime.agent.turn(
                guest_sess, guest_grant, "Привіт", task_id=guest_task, timeout_s=60
            )
            guest_req = state["requests"][-1]
            return runtime, owner_req, guest_req
        finally:
            runtime.close()

    # Flag off: no skills index, no skill_view tool.
    _, off_owner, _ = await run_with_flag(skills_flag=False)
    off_sys = off_owner["messages"][0]["content"]
    off_tools = {t["function"]["name"] for t in off_owner.get("tools", [])}
    assert "skill_view" not in off_tools
    assert "skill-00" not in off_sys
    assert "Опис процедури" not in off_sys

    # Flag on: active skills index (max 20) after stable prefix, skill_view offered (memory.read).
    rt_on, on_owner, on_guest = await run_with_flag(skills_flag=True, stable_prefix=True)
    on_sys = on_owner["messages"][0]["content"]
    on_tools = {t["function"]["name"] for t in on_owner.get("tools", [])}
    assert "skill_view" in on_tools
    catalog = {t["name"]: t for t in rt_on.registry.catalog()}
    assert catalog["skill_view"]["capability"] == "memory.read"

    stable_head = (
        f"{rt_on.agent.system_prompt} {OWNER_SPEAKER} Домашня тека власника: {Path.home()}."
    )
    assert on_sys.startswith(stable_head)
    tail = on_sys[len(stable_head) :]
    assert "skill-00" in tail
    assert "skill-19" in tail
    assert "skill-20" not in tail  # capped at 20 active skills
    assert "zzz-stale" not in on_sys
    assert "zzz-forgotten" not in on_sys
    assert "zzz-archived" not in on_sys

    # Guest never sees the owner's skills index.
    guest_sys = on_guest["messages"][0]["content"]
    assert "skill-00" not in guest_sys


async def test_invalid_frontmatter_is_not_indexed(scripted_ollama, tmp_path):
    from b12.skills import SkillStore

    state, base = scripted_ollama
    state_dir = tmp_path / "state"
    skills_dir = state_dir / "skills"
    store = SkillStore(skills_dir)

    _write_skill(skills_dir, "valid-60", _skill_md("valid-60", "a" * 60))
    _write_skill(skills_dir, "too-long", _skill_md("too-long", "a" * 61))
    _write_skill(skills_dir, "no-frontmatter", "# Just a heading\nNo YAML here.\n")
    _write_skill(skills_dir, "missing-name", "---\ndescription: Valid desc\n---\n\nBody\n")
    _write_skill(skills_dir, "missing-desc", "---\nname: missing-desc\n---\n\nBody\n")
    _write_skill(skills_dir, "empty-desc", '---\nname: empty-desc\ndescription: ""\n---\n\nBody\n')

    listed = store.list()
    assert listed == [{"name": "valid-60", "description": "a" * 60, "status": "active"}]
    assert [s["name"] for s in store.index()] == ["valid-60"]

    runtime = open_runtime(base.model_copy(update={"state_dir": state_dir, "skills": True}))
    try:
        owner = runtime.control.create_actor(owner=True, consent=True)
        session = runtime.control.create_session(owner.id)
        task = runtime.control.create_task(session)
        grant = runtime.control.issue_grant(
            owner.id, session, owner_capabilities(runtime.settings), task_id=task, ttl_s=600
        )
        state["script"] = [{"content": "Гаразд."}]
        await runtime.agent.turn(session, grant, "Привіт", task_id=task, timeout_s=60)
        system = state["requests"][-1]["messages"][0]["content"]
        assert "valid-60" in system
        for bad in ("too-long", "no-frontmatter", "missing-name", "missing-desc", "empty-desc"):
            assert bad not in system
    finally:
        runtime.close()


async def test_skill_propose_stages_and_never_writes(scripted_ollama, tmp_path):
    state, base = scripted_ollama
    state_dir = tmp_path / "state"
    runtime = open_runtime(base.model_copy(update={"state_dir": state_dir, "skills": True}))
    try:
        catalog = {t["name"]: t for t in runtime.registry.catalog()}
        assert catalog["skill_propose"]["capability"] == "memory.write"

        owner = runtime.control.create_actor(owner=True, consent=True)
        session = runtime.control.create_session(owner.id)
        task = runtime.control.create_task(session)
        grant = runtime.control.issue_grant(
            owner.id, session, owner_capabilities(runtime.settings), task_id=task, ttl_s=600
        )
        proposed_md = _skill_md(
            "backup-verify", "Verify state snapshot integrity", "## Procedure\n1. Run verify.\n"
        )
        state["script"] = [
            {"tool_calls": [("skill_propose", {"name": "backup-verify", "content": proposed_md})]},
            {"content": "Пропозицію навички збережено на схвалення."},
        ]
        result = await runtime.agent.turn(
            session, grant, "Збережи процедуру перевірки бекапу", task_id=task, timeout_s=60
        )
        assert result.state == "completed"
        assert result.tool_results[0].status == "completed"
        pending_id = result.tool_results[0].content["pending_id"]

        # SKILL.md must NEVER be written directly by skill_propose.
        assert not (state_dir / "skills" / "backup-verify" / "SKILL.md").exists()
        assert runtime.skills.list() == []
        pending_dir = state_dir / "skills" / ".pending"
        assert pending_dir.is_dir()
        pending_files = list(pending_dir.iterdir())
        assert len(pending_files) == 1
        pending = runtime.skills.list_pending()
        assert len(pending) == 1
        assert pending[0]["id"] == pending_id
        assert pending[0]["name"] == "backup-verify"
        assert pending[0]["turn_id"] == result.turn_id
        assert pending[0]["session_id"] == session
        assert "+## Procedure" in runtime.skills.diff(pending_id)

        # Guest cannot stage skill proposals.
        guest = runtime.control.create_actor(owner=False, consent=True)
        guest_sess = runtime.control.create_session(guest.id)
        guest_task = runtime.control.create_task(guest_sess)
        guest_grant = runtime.control.issue_grant(
            guest.id, guest_sess, tuple(sorted(GUEST_CAPABILITIES)), task_id=guest_task, ttl_s=600
        )
        state["script"] = [
            {"tool_calls": [("skill_propose", {"name": "guest-skill", "content": proposed_md})]},
            {"content": "Заборонено."},
        ]
        guest_res = await runtime.agent.turn(
            guest_sess, guest_grant, "Додай навичку", task_id=guest_task, timeout_s=60
        )
        assert guest_res.tool_results[0].status == "failed"
        assert guest_res.tool_results[0].error_code == "permission_denied"
        assert len(runtime.skills.list_pending()) == 1
    finally:
        runtime.close()


def test_approve_writes_and_ledgers_hashes(tmp_path):
    from b12.skills import SkillStore

    skills_dir = tmp_path / "skills"
    store = SkillStore(skills_dir)

    v1 = _skill_md("log-audit", "Check journal errors safely", "## Procedure\n1. Check logs.\n")
    v2 = _skill_md("log-audit", "Check journal errors safely", "## Procedure\n1. Run grep.\n")
    h1 = hashlib.sha256(v1.encode("utf-8")).hexdigest()
    h2 = hashlib.sha256(v2.encode("utf-8")).hexdigest()

    p1 = store.propose("log-audit", v1, turn_id="turn-1", session_id="sess-1", actor_id="owner-1")
    assert not (skills_dir / "log-audit" / "SKILL.md").exists()
    store.approve(p1)
    assert (skills_dir / "log-audit" / "SKILL.md").read_text(encoding="utf-8") == v1
    assert store.list_pending() == []

    p2 = store.propose("log-audit", v2, turn_id="turn-2", session_id="sess-1", actor_id="owner-1")
    assert (skills_dir / "log-audit" / "SKILL.md").read_text(encoding="utf-8") == v1
    store.approve(p2)
    assert (skills_dir / "log-audit" / "SKILL.md").read_text(encoding="utf-8") == v2

    p3 = store.propose("rejected-skill", v1, turn_id="turn-3")
    assert store.reject(p3) is True
    assert not (skills_dir / "rejected-skill" / "SKILL.md").exists()

    ledger_path = skills_dir / ".ledger.jsonl"
    assert ledger_path.is_file()
    entries = [json.loads(line) for line in ledger_path.read_text(encoding="utf-8").splitlines()]
    approvals = [e for e in entries if e["action"] == "approve"]
    assert len(approvals) == 2
    assert approvals[0]["name"] == "log-audit"
    assert approvals[0]["sha256_before"] is None
    assert approvals[0]["sha256_after"] == h1
    assert approvals[0]["turn_id"] == "turn-1"
    assert approvals[0]["actor"]
    datetime.fromisoformat(approvals[0]["at"])

    assert approvals[1]["name"] == "log-audit"
    assert approvals[1]["sha256_before"] == h1
    assert approvals[1]["sha256_after"] == h2
    assert approvals[1]["turn_id"] == "turn-2"


def test_curator_marks_stale_then_archives_and_spares_pinned(tmp_path):
    from b12.skills import SkillStore

    t0 = datetime(2026, 11, 1, 10, 0, tzinfo=UTC)
    now_ref = [t0]
    skills_dir = tmp_path / "skills"
    store = SkillStore(skills_dir, clock=lambda: now_ref[0])

    s_stale = _skill_md("ephemeral-task", "Temporary procedure")
    s_pinned = _skill_md("pinned-task", "Important owner procedure")
    p_stale = store.propose("ephemeral-task", s_stale, turn_id="t-1")
    p_pinned = store.propose("pinned-task", s_pinned, turn_id="t-2")
    store.approve(p_stale)
    store.approve(p_pinned)
    store.pin("pinned-task")

    # Day 10: still active.
    store.curate(t0 + timedelta(days=10))
    by_name = {item["name"]: item for item in store.list()}
    assert by_name["ephemeral-task"]["status"] == "active"
    assert by_name["pinned-task"]["status"] == "active"

    # Day 14+: unpinned becomes stale; pinned stays active.
    store.curate(t0 + timedelta(days=15))
    by_name = {item["name"]: item for item in store.list()}
    assert by_name["ephemeral-task"]["status"] == "stale"
    assert by_name["pinned-task"]["status"] == "active"

    # Day 30+: unpinned moves to skills/.archive/; pinned is untouched.
    store.curate(t0 + timedelta(days=31))
    assert not (skills_dir / "ephemeral-task").exists()
    assert (skills_dir / ".archive" / "ephemeral-task" / "SKILL.md").is_file()
    assert (skills_dir / "pinned-task" / "SKILL.md").is_file()
    by_name = {item["name"]: item for item in store.list()}
    assert by_name["ephemeral-task"]["status"] == "archived"
    assert by_name["pinned-task"]["status"] == "active"
    assert [item["name"] for item in store.index()] == ["pinned-task"]


async def test_forgetting_the_source_session_marks_source_forgotten(scripted_ollama, tmp_path):
    state, base = scripted_ollama
    state_dir = tmp_path / "state"
    runtime = open_runtime(base.model_copy(update={"state_dir": state_dir, "skills": True}))
    try:
        owner = runtime.control.create_actor(owner=True, consent=True)
        sess_source = runtime.control.create_session(owner.id)
        sess_other = runtime.control.create_session(owner.id)
        task = runtime.control.create_task(sess_source)
        grant = runtime.control.issue_grant(
            owner.id, sess_source, owner_capabilities(runtime.settings), task_id=task, ttl_s=600
        )
        skill_text = _skill_md("session-derived", "Procedure from cleared session")
        state["script"] = [
            {"tool_calls": [("skill_propose", {"name": "session-derived", "content": skill_text})]},
            {"content": "Запропоновано."},
        ]
        res = await runtime.agent.turn(
            sess_source, grant, "Запиши навичку", task_id=task, timeout_s=60
        )
        pending_id = res.tool_results[0].content["pending_id"]
        runtime.skills.approve(pending_id)

        keep_text = _skill_md("other-derived", "Procedure from other session")
        keep_pid = runtime.skills.propose(
            "other-derived",
            keep_text,
            turn_id="other-turn",
            session_id=sess_other,
            actor_id=owner.id,
        )
        runtime.skills.approve(keep_pid)

        assert {s["name"]: s["status"] for s in runtime.skills.list()} == {
            "session-derived": "active",
            "other-derived": "active",
        }

        # Clearing the source session must NOT silently delete SKILL.md; it marks source_forgotten
        # and notifies the owner.
        runtime.sessions.clear_session(sess_source, owner.id)
        skill_file = state_dir / "skills" / "session-derived" / "SKILL.md"
        assert skill_file.is_file()
        assert skill_file.read_text(encoding="utf-8") == skill_text

        statuses = {s["name"]: s["status"] for s in runtime.skills.list()}
        assert statuses == {"session-derived": "source_forgotten", "other-derived": "active"}
        assert [s["name"] for s in runtime.skills.index()] == ["other-derived"]

        proposals = runtime.goals.proposals(owner.id)
        assert any(
            p["reason"] == "source_forgotten" and "session-derived" in p["text"] for p in proposals
        )
    finally:
        runtime.close()


async def test_skills_cli_and_scheduler_curate(scripted_ollama, tmp_path, monkeypatch, capsys):
    from b12.agent import _Active
    from b12.autonomy import Scheduler
    from b12.cli import main as cli_main

    state, base = scripted_ollama
    state_dir = tmp_path / "state"
    t0 = datetime(2026, 11, 1, 10, 0, tzinfo=UTC)
    clock_now = [t0]

    # Off by default: curate_skills_idle is a no-op.
    off_rt = open_runtime(base.model_copy(update={"state_dir": tmp_path / "off", "skills": False}))
    off_sched = Scheduler(off_rt, clock=lambda: clock_now[0])
    try:
        assert await off_sched.curate_skills_idle() == []
    finally:
        off_sched.close()
        off_rt.close()

    # Initialize owner and stage a skill via SkillStore, then exercise CLI.
    rt = open_runtime(base.model_copy(update={"state_dir": state_dir, "skills": True}))
    try:
        owner = rt.control.create_actor(owner=True, consent=True)
        sess = rt.control.create_session(owner.id)
        rt.control.set_meta("owner_actor", owner.id)
        rt.control.set_meta("cli_session", sess)
        p1 = rt.skills.propose(
            "cli-skill",
            _skill_md("cli-skill", "CLI tested skill"),
            turn_id="cli-turn-1",
            session_id=sess,
            actor_id=owner.id,
        )
        p2 = rt.skills.propose(
            "drop-skill",
            _skill_md("drop-skill", "Rejected CLI skill"),
            turn_id="cli-turn-2",
            session_id=sess,
            actor_id=owner.id,
        )
    finally:
        rt.close()

    monkeypatch.setenv("B12_STATE_DIR", str(state_dir))
    monkeypatch.setenv("B12_MODEL", base.model)
    monkeypatch.setenv("B12_OLLAMA_URL", base.ollama_url)
    monkeypatch.setenv("B12_MODEL_PROFILE", str(base.model_profile))
    monkeypatch.setenv("B12_TOKENIZER_DIR", str(base.tokenizer_dir))
    monkeypatch.setenv("B12_NUM_CTX", str(base.num_ctx))
    monkeypatch.setenv("B12_OUTPUT_TOKENS", str(base.output_tokens))

    assert await asyncio.to_thread(cli_main, ["skills", "pending"]) == 0
    pending_out = json.loads(capsys.readouterr().out)
    assert {item["id"] for item in pending_out} == {p1, p2}

    assert await asyncio.to_thread(cli_main, ["skills", "diff", p1]) == 0
    diff_out = json.loads(capsys.readouterr().out)
    assert "cli-skill" in diff_out["diff"]

    assert await asyncio.to_thread(cli_main, ["skills", "approve", p1]) == 0
    assert json.loads(capsys.readouterr().out)["name"] == "cli-skill"

    assert await asyncio.to_thread(cli_main, ["skills", "reject", p2]) == 0
    assert json.loads(capsys.readouterr().out) == {"rejected": p2}

    assert await asyncio.to_thread(cli_main, ["skills", "list"]) == 0
    assert json.loads(capsys.readouterr().out) == [
        {"name": "cli-skill", "description": "CLI tested skill", "status": "active"}
    ]

    assert await asyncio.to_thread(cli_main, ["skills", "pin", "cli-skill"]) == 0
    assert json.loads(capsys.readouterr().out)["pinned"] is True

    assert await asyncio.to_thread(cli_main, ["skills", "show", "cli-skill"]) == 0
    shown = json.loads(capsys.readouterr().out)
    assert shown["pinned"] is True and "CLI tested skill" in shown["content"]

    assert await asyncio.to_thread(cli_main, ["skills", "unpin", "cli-skill"]) == 0
    assert json.loads(capsys.readouterr().out)["pinned"] is False

    # Scheduler weekly idle curate with _busy and owner_stop guards.
    rt2 = open_runtime(base.model_copy(update={"state_dir": state_dir, "skills": True}))
    sched2 = Scheduler(rt2, clock=lambda: clock_now[0])
    try:
        # Busy actor blocks curate.
        rt2.agent.active["busy-turn"] = _Active(owner.id, asyncio.Event())
        busy = await sched2.curate_skills_idle()
        assert busy == [{"actor_id": owner.id, "state": "skipped", "reason": "actor_busy"}]
        del rt2.agent.active["busy-turn"]

        # Owner stop blocks curate.
        rt2.attention.set_stopped(owner.id, True)
        stopped = await sched2.curate_skills_idle()
        assert stopped == [{"actor_id": owner.id, "state": "skipped", "reason": "owner_stop"}]
        rt2.attention.set_stopped(owner.id, False)

        # Idle curate runs and stamps weekly interval.
        first = await sched2.curate_skills_idle()
        assert len(first) == 1 and first[0]["state"] == "curated"
        clock_now[0] = t0 + timedelta(days=3)
        assert await sched2.curate_skills_idle() == []

        # After 15 days (>=7d interval AND >=14d unused), weekly curate marks cli-skill stale.
        clock_now[0] = t0 + timedelta(days=15)
        meta = rt2.skills._load_meta()
        meta["cli-skill"]["last_used_at"] = t0.isoformat()
        rt2.skills._save_meta(meta)
        later = await sched2.curate_skills_idle()
        assert later[0]["marked_stale"] == ["cli-skill"]
    finally:
        sched2.close()
        rt2.close()

    # Clearing CLI session reports the newly source_forgotten skill in CLI JSON output.
    assert await asyncio.to_thread(cli_main, ["session", "clear"]) == 0
    cleared_out = json.loads(capsys.readouterr().out)
    assert cleared_out["cleared"] == sess
    assert cleared_out["source_forgotten_skills"] == ["cli-skill"]
