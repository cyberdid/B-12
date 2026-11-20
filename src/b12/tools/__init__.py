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
    memory_temporal=False,
    memory_as_of=False,
    memory_scoped=False,
    verify_writes=False,
    memory_grounding=False,
    memory_taint=False,
    turn_tainted=None,
    sessions=None,
    resolver=None,
    session_search=False,
):
    """Register all concrete host tools; caller owns/closes injected stores.

    memory_revision resolves the ORIGINAL turn's canonical deletion revision.
    Missing memory/revision/global-purge ports return coordinator_unavailable.
    No model field can supply these ports or authorize a grant/approval.
    """
    from b12.tools import conversation, filesystem, network, notes, process
    from b12.tools import memory as memory_tools

    filesystem.register(registry, backups, verify_writes=verify_writes)
    notes.register(registry)
    process.register(registry)
    if sudo or sudo_path:
        process.register_sudo(registry, sudo_path)
    network.register(registry)
    if session_search:
        conversation.register(registry, sessions=sessions, resolver=resolver)
    memory_tools.register(
        registry,
        memory=memory,
        knowledge=knowledge,
        purge=purge,
        memory_revision=memory_revision,
        temporal=memory_temporal,
        as_of=memory_as_of,
        scoped=memory_scoped,
        grounding=memory_grounding,
        taint=memory_taint,
        turn_tainted=turn_tainted,
    )
