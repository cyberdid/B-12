"""ADR-021 procedural memory: SkillStore, skills index, and skill_view (F1)."""

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
