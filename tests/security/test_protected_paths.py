"""Owner state/config roots are unreachable through typed tool arguments."""


async def test_filesystem_and_process_arguments_cannot_name_protected_roots(host_factory):
    rig = host_factory()
    secret = rig.root / "protected"
    secret.mkdir()
    (secret / "owner.token").write_text("token")
    rig.registry.protected_paths = (str(secret),)
    for name, args in [
        ("file_read", {"path": str(secret / "owner.token")}),
        ("file_list", {"path": str(secret)}),
        ("file_write", {"path": str(secret / "x"), "text": "y", "overwrite": True}),
    ]:
        result = await rig.invoke(name, **args)
        assert result.error_code == "path_protected", name
    assert (secret / "owner.token").read_text() == "token"


async def test_symlink_alias_and_traversal_are_resolved(host_factory):
    rig = host_factory()
    secret = rig.root / "protected"
    secret.mkdir()
    (secret / "owner.token").write_text("token")
    alias = rig.root / "alias"
    alias.symlink_to(secret, target_is_directory=True)
    rig.registry.protected_paths = (str(secret),)
    via_link = await rig.invoke("file_read", path=str(alias / "owner.token"))
    via_dots = await rig.invoke(
        "file_read", path=str(rig.root / "x" / ".." / "protected" / "owner.token")
    )
    assert via_link.error_code == via_dots.error_code == "path_protected"


async def test_shell_argv_and_cwd_naming_protected_root_are_refused(host_factory):
    rig = host_factory()
    secret = rig.root / "protected"
    secret.mkdir()
    rig.registry.protected_paths = (str(secret),)
    by_arg = await rig.invoke(
        "shell_exec",
        executable="/bin/cat",
        argv=[str(secret / "owner.token")],
        cwd=str(rig.root),
        declared_effects=["read"],
    )
    by_cwd = await rig.invoke(
        "shell_exec",
        executable="/bin/ls",
        argv=[],
        cwd=str(secret),
        declared_effects=["read"],
    )
    assert by_arg.error_code == by_cwd.error_code == "path_protected"


async def test_sibling_paths_and_unconfigured_registry_are_unaffected(host_factory):
    rig = host_factory()
    ok = rig.root / "ok.txt"
    ok.write_text("fine")
    assert (await rig.invoke("file_read", path=str(ok))).status == "completed"
    rig.registry.protected_paths = (str(rig.root / "protected"),)
    assert (await rig.invoke("file_read", path=str(ok))).status == "completed"
