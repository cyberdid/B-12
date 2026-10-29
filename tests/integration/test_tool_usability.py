"""Regressions from the 29.10.2026 conversation pass: descriptions, argv, prompt rules."""

from b12.agent import SYSTEM_PROMPT


def test_key_tool_descriptions_name_their_arguments(host_factory):
    rig = host_factory()
    catalog = {tool["name"]: tool["description"] for tool in rig.registry.catalog()}
    assert "text" in catalog["memory_store"]
    assert "query" in catalog["memory_search"]
    assert "memory_id" in catalog["memory_forget"]
    assert "executable" in catalog["shell_exec"] and "argv" in catalog["shell_exec"]
    assert "Store memory using" not in catalog["memory_store"]  # technical phrasing is gone


async def test_shell_argv_with_the_program_name_still_runs_the_program(host_factory, tmp_path):
    rig = host_factory()
    target = tmp_path / "three.txt"
    target.write_text("a\nb\nc\n")
    direct = await rig.invoke(
        "shell_exec",
        executable="/usr/bin/wc",
        argv=["wc", "-l", str(target)],
        cwd=str(tmp_path),
        declared_effects=["read-only count"],
    )
    assert direct.content["command_succeeded"] is True and "3" in direct.content["stdout"]
    via_sh = await rig.invoke(
        "shell_exec",
        executable="/bin/sh",
        argv=["wc", "-l", str(target)],
        cwd=str(tmp_path),
        declared_effects=["read-only count"],
    )
    assert via_sh.content["command_succeeded"] is True and "3" in via_sh.content["stdout"]


def test_system_prompt_forbids_writing_calls_as_text_and_guessed_numbers():
    assert "не пиши виклик" in SYSTEM_PROMPT.lower()
    assert "кількост" in SYSTEM_PROMPT.lower() and "не рахував" in SYSTEM_PROMPT.lower()
    assert "чи бажаєте" in SYSTEM_PROMPT.lower() or "питання" in SYSTEM_PROMPT.lower()


async def test_run_command_takes_a_full_terminal_line_with_pipes(host_factory, tmp_path):
    rig = host_factory()
    (tmp_path / "a.txt").write_text("alpha\nbeta\ngamma\n")
    result = await rig.invoke(
        "run_command",
        command=f"grep -n a {tmp_path}/a.txt | wc -l",
        cwd=str(tmp_path),
        declared_effects=["read-only count"],
    )
    assert result.status == "completed" and result.content["command_succeeded"] is True
    assert result.content["stdout"].strip() == "3"


async def test_run_command_reports_exit_status_and_bounds_output(host_factory, tmp_path):
    rig = host_factory()
    failed = await rig.invoke(
        "run_command", command="exit 3", cwd=str(tmp_path), declared_effects=["noop"]
    )
    assert failed.content["exit_code"] == 3 and failed.content["command_succeeded"] is False
    big = await rig.invoke(
        "run_command",
        command="head -c 20000 /dev/zero | tr '\\0' 'x'",
        cwd=str(tmp_path),
        declared_effects=["read-only output"],
    )
    assert len(big.content["stdout"].encode()) <= 4096


def test_prompt_tells_the_model_to_grep_large_files_not_read_them_in_chunks():
    text = SYSTEM_PROMPT.lower()
    assert "run_command" in text and "grep" in text
