"""Typed tools and explicit application-owned host dependency registration."""


def register_host_tools(
    registry,
    *,
    backups,
    memory=None,
    knowledge=None,
    purge=None,
    memory_revision=None,
    sudo=False,
    sudo_path=None,
):
    """Register all 13 concrete host tools; caller owns/closes injected stores.

    memory_revision resolves the ORIGINAL turn's canonical deletion revision.
    Missing memory/revision/global-purge ports return coordinator_unavailable.
    No model field can supply these ports or authorize a grant/approval.
    """
    from b12.tools import filesystem, network, process
    from b12.tools import memory as memory_tools

    filesystem.register(registry, backups)
    process.register(registry)
    if sudo or sudo_path:
        process.register_sudo(registry, sudo_path)
    network.register(registry)
    memory_tools.register(
        registry, memory=memory, knowledge=knowledge, purge=purge, memory_revision=memory_revision
    )
