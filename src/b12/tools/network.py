"""Bounded GET-only HTTP transport; no ambient proxy/auth or implicit redirects."""

import asyncio
import ipaddress
from urllib.parse import urlsplit

import httpx
from pydantic import Field, field_validator

from b12.tools._common import Args, body, clip, failure
from b12.tools.outcomes import HandlerOutcome, SideEffect


class FetchArgs(Args):
    url: str = Field(min_length=1, max_length=2048)
    max_bytes: int = Field(default=4096, ge=1, le=8192)

    @field_validator("url")
    @classmethod
    def _http(cls, value):
        parsed = urlsplit(value)
        if (
            parsed.scheme not in ("http", "https")
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
            or parsed.fragment
            or any(ord(c) < 32 or ord(c) == 127 for c in value)
        ):
            raise ValueError("credential-free HTTP URL required")
        _ = parsed.port
        return value


def _normal(host: str) -> str:
    return host.strip().lower().rstrip(".")


def host_allowed(host: str, patterns) -> bool:
    """Exact host or `*.suffix` (subdomains only); an IP literal needs an exact entry."""
    host = _normal(host)
    try:
        ipaddress.ip_address(host.strip("[]"))
        literal = True
    except ValueError:
        literal = False
    for pattern in patterns:
        pattern = _normal(pattern)
        if pattern.startswith("*."):
            if not literal and host.endswith(pattern[1:]) and len(host) > len(pattern) - 1:
                return True
        elif host == pattern:
            return True
    return False


async def http_fetch(args, guard, allow=None):
    if allow is not None and not host_allowed(urlsplit(args.url).hostname or "", allow):
        return failure("network_denied")
    started = False
    raw = bytearray()
    status = None
    truncated = False
    content_type = ""
    content_encoding = ""

    def outcome(state="completed", code=None):
        return HandlerOutcome(
            status=state,
            error_code=code,
            content={
                "status_code": status,
                "content_type": content_type,
                "content_encoding": content_encoding,
                **body(bytes(raw)),
            },
            truncated=truncated,
            side_effects=(
                SideEffect(
                    kind="http_request", state=("completed" if state == "completed" else "possible")
                ),
            ),
        )

    try:
        async with httpx.AsyncClient(
            trust_env=False, follow_redirects=False, timeout=None
        ) as client:
            guard.check()
            started = True
            async with client.stream(
                "GET", args.url, headers={"Accept-Encoding": "identity"}
            ) as reply:
                status = reply.status_code
                content_type = clip(reply.headers.get("content-type", ""), 256)[0]
                content_encoding = clip(reply.headers.get("content-encoding", ""), 256)[0]
                async for chunk in reply.aiter_raw(chunk_size=4096):
                    guard.check()
                    take = min(len(chunk), args.max_bytes - len(raw))
                    raw.extend(chunk[:take])
                    if take < len(chunk):
                        truncated = True
                        break
        return outcome()
    except asyncio.CancelledError:
        if started:
            return outcome("unknown", "cancelled")
        raise
    except httpx.HTTPError:
        return outcome("unknown", "network_failed") if started else failure("network_failed")


def register(registry):
    async def fetch(args, guard):
        return await http_fetch(args, guard, registry.network_allow)

    registry.register(
        "http_fetch",
        "Fetch bounded HTTP(S) GET; redirects are returned, not followed",
        FetchArgs,
        fetch,
        "network.http",
    )
