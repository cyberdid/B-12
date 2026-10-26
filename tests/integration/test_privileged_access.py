"""Owner-granted wide access: forget without approval and sudo behind exact approval."""

import json
import stat
import sys
from uuid import uuid4

from b12.contracts import PurgeReceipt


class Purge:
    def __init__(self):
        self.calls = []

    async def purge(self, memory_id, context, guard):
        self.calls.append(memory_id)
        return PurgeReceipt(
            operation_id=str(uuid4()), target_ids=(memory_id,), state="complete", pending_stores=()
        )


def fake_sudo(tmp_path):
    record = tmp_path / "sudo-argv.json"
    script = tmp_path / "fake-sudo"
    script.write_text(
        f"#!{sys.executable}\nimport json,sys\n"
        f"open({str(record)!r},'w').write(json.dumps(sys.argv[1:]))\nprint('sudo-ok')\n"
    )
    script.chmod(script.stat().st_mode | stat.S_IEXEC)
    return script, record


async def test_forget_requires_approval_unless_owner_exempts_it(host_factory):
    purge = Purge()
    rig = host_factory(purge=purge, full_execution=True)
    memory_id = str(uuid4())
    pending = await rig.invoke("memory_forget", call_id="f1", memory_id=memory_id)
    assert pending.status == "approval_pending" and purge.calls == []
    rig.registry.approval_exempt.add("memory_forget")
    done = await rig.invoke("memory_forget", call_id="f2", memory_id=memory_id)
    assert done.status == "completed" and purge.calls == [memory_id]


async def test_exemption_is_per_tool_and_never_covers_sudo(host_factory, tmp_path):
    sudo, record = fake_sudo(tmp_path)
    rig = host_factory(
        purge=Purge(),
        sudo_path=str(sudo),
        capabilities=("memory.forget", "process.sudo", "time.read"),
    )
    rig.registry.approval_exempt.add("memory_forget")
    result = await rig.invoke(
        "sudo_exec",
        executable="/bin/echo",
        argv=["x"],
        cwd=str(rig.root),
        declared_effects=["noop"],
    )
    assert result.status == "approval_pending" and not record.exists()


async def test_sudo_runs_only_after_exact_approval_with_non_interactive_flags(
    host_factory, tmp_path
):
    sudo, record = fake_sudo(tmp_path)
    rig = host_factory(
        sudo_path=str(sudo),
        full_execution=True,
        capabilities=("process.sudo", "time.read"),
    )
    args = dict(
        executable="/bin/echo",
        argv=["hi", "there"],
        cwd=str(rig.root),
        declared_effects=["print text as root"],
    )
    pending = await rig.invoke("sudo_exec", call_id="s1", **args)
    assert pending.status == "approval_pending" and not record.exists()
    rig.control.decide_approval(pending.content["operation_id"], True)
    altered = await rig.invoke("sudo_exec", call_id="s1", **{**args, "argv": ["evil"]})
    assert altered.status != "completed" and not record.exists()
    approved = await rig.invoke("sudo_exec", call_id="s1", **args)
    assert approved.status == "completed" and "sudo-ok" in approved.content["stdout"]
    assert json.loads(record.read_text()) == ["-n", "--", "/bin/echo", "hi", "there"]
    assert approved.side_effects[0]["kind"] == "process_execution"


async def test_sudo_is_hidden_and_denied_without_the_capability(host_factory, tmp_path):
    sudo, record = fake_sudo(tmp_path)
    rig = host_factory(sudo_path=str(sudo), capabilities=("time.read", "process.execute"))
    assert "sudo_exec" not in {s["function"]["name"] for s in rig.registry.schemas(rig.context)}
    result = await rig.invoke(
        "sudo_exec", executable="/bin/echo", argv=[], cwd=str(rig.root), declared_effects=["x"]
    )
    assert result.error_code == "capability_denied" and not record.exists()


async def test_sudo_requires_an_absolute_executable_and_cwd(host_factory, tmp_path):
    sudo, _ = fake_sudo(tmp_path)
    rig = host_factory(sudo_path=str(sudo), capabilities=("process.sudo",))
    result = await rig.invoke(
        "sudo_exec", executable="echo", argv=[], cwd=str(rig.root), declared_effects=["x"]
    )
    assert result.error_code == "invalid_arguments"


async def test_sudo_tool_is_not_registered_unless_enabled(host_factory):
    rig = host_factory()
    assert "sudo_exec" not in {t["name"] for t in rig.registry.catalog()}


def test_settings_and_owner_capabilities_follow_access_choices(tmp_path):
    from b12.auth import owner_capabilities
    from b12.config import Settings

    base = {"B12_STATE_DIR": str(tmp_path)}
    default = Settings.from_env(base)
    assert default.sudo_access == "off" and default.forget_requires_approval is True
    assert "process.sudo" not in owner_capabilities(default)
    wide = Settings.from_env(
        {**base, "B12_SUDO_ACCESS": "approval", "B12_FORGET_REQUIRES_APPROVAL": "false"}
    )
    assert wide.sudo_access == "approval" and wide.forget_requires_approval is False
    assert "process.sudo" in owner_capabilities(wide)
    read_only = Settings.from_env(
        {**base, "B12_SUDO_ACCESS": "approval", "B12_HOST_ACCESS": "read_only"}
    )
    assert "process.sudo" not in owner_capabilities(read_only)


def test_guests_can_never_hold_the_sudo_capability():
    from b12.auth import GUEST_CAPABILITIES

    assert "process.sudo" not in GUEST_CAPABILITIES and "memory.forget" not in GUEST_CAPABILITIES


async def test_runtime_wires_exemption_and_sudo_from_settings(scripted_ollama, tmp_path):
    from b12.runtime import open_runtime

    _, base = scripted_ollama
    settings = base.model_copy(
        update={
            "state_dir": tmp_path / "state",
            "sudo_access": "approval",
            "forget_requires_approval": False,
        }
    )
    runtime = open_runtime(settings)
    try:
        assert runtime.registry.approval_exempt == {"memory_forget"}
        assert "sudo_exec" in {t["name"] for t in runtime.registry.catalog()}
    finally:
        runtime.close()
