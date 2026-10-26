"""Owner token bootstrap and request identity for the loopback API.

The owner bearer token lives only in state_dir/api/owner.token (0600 in a 0700
directory); ControlStore keeps its keyed digest. Tokens are accepted only from the
Authorization header, never URLs. Guest tokens carry an owner-chosen subset of
typed capabilities and never full execution or host-effect capabilities.
"""

import os
from dataclasses import dataclass
from pathlib import Path

from b12.contracts import Actor

HOST_CAPABILITIES = {
    "full": (
        "system.read",
        "process.read",
        "filesystem.read",
        "filesystem.write",
        "process.execute",
        "network.http",
        "memory.read",
        "memory.write",
        "memory.forget",
        "knowledge.read",
        "time.read",
    ),
    "read_only": (
        "system.read",
        "process.read",
        "filesystem.read",
        "memory.read",
        "knowledge.read",
        "time.read",
    ),
    "none": ("time.read",),
}
GUEST_CAPABILITIES = frozenset(
    {"time.read", "memory.read", "memory.write", "knowledge.read", "system.read"}
)


@dataclass(frozen=True)
class Caller:
    actor: Actor
    capabilities: tuple[str, ...]

    @property
    def owner(self) -> bool:
        return self.actor.owner


def owner_token(control, state_dir: Path, owner_id: str, capabilities: tuple[str, ...]) -> Path:
    """Return the owner token file, (re)issuing a token when it is missing or unknown."""
    directory = Path(state_dir) / "api"
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    directory.chmod(0o700)
    path = directory / "owner.token"
    if path.exists():
        resolved = control.resolve_token(path.read_text().strip())
        if resolved and resolved[0].id == owner_id and resolved[1] == capabilities:
            return path
    token = control.issue_token(owner_id, capabilities)
    temporary = directory / ".owner.token.tmp"
    fd = os.open(temporary, os.O_CREAT | os.O_TRUNC | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
    try:
        os.write(fd, token.encode() + b"\n")
        os.fsync(fd)
    finally:
        os.close(fd)
    os.replace(temporary, path)
    return path


def bearer(header: str | None) -> str | None:
    if not header or not header.startswith("Bearer "):
        return None
    return header.removeprefix("Bearer ").strip() or None
