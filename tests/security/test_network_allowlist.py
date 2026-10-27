"""Owner-controlled http_fetch destinations: default deny, exact/suffix hosts, no bypass."""

import asyncio

import pytest

from b12.tools.network import host_allowed


@pytest.mark.parametrize(
    ("host", "patterns", "expected"),
    [
        ("example.com", ("example.com",), True),
        ("EXAMPLE.com.", ("example.com",), True),
        ("api.example.com", ("*.example.com",), True),
        ("example.com", ("*.example.com",), False),
        ("evil-example.com", ("*.example.com",), False),
        ("example.com.evil.com", ("example.com",), False),
        ("127.0.0.1", ("*.0.0.1",), False),
        ("127.0.0.1", ("127.0.0.1",), True),
        ("example.com", (), False),
    ],
)
def test_host_matching(host, patterns, expected):
    assert host_allowed(host, patterns) is expected


async def serve(hits):
    async def handler(reader, writer):
        await reader.readuntil(b"\r\n\r\n")
        hits.append(1)
        writer.write(b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\nContent-Type: text/plain\r\n\r\nok")
        await writer.drain()
        writer.close()

    listener = await asyncio.start_server(handler, "127.0.0.1", 0)
    return listener, listener.sockets[0].getsockname()[1]


async def test_empty_allowlist_denies_before_any_network_effect(host_factory):
    rig = host_factory()
    rig.registry.network_allow = ()
    hits = []
    listener, port = await serve(hits)
    async with listener:
        result = await rig.invoke("http_fetch", url=f"http://127.0.0.1:{port}/")
    assert result.status == "failed" and result.error_code == "network_denied"
    assert hits == [] and not result.side_effects


async def test_listed_host_is_fetched_and_other_host_is_not(host_factory):
    rig = host_factory()
    rig.registry.network_allow = ("127.0.0.1",)
    hits = []
    listener, port = await serve(hits)
    async with listener:
        ok = await rig.invoke("http_fetch", url=f"http://127.0.0.1:{port}/")
        other = await rig.invoke("http_fetch", url=f"http://localhost:{port}/")
    assert ok.status == "completed" and hits == [1]
    assert other.error_code == "network_denied"


async def test_unconfigured_registry_stays_unrestricted_for_library_use(host_factory):
    rig = host_factory()
    assert rig.registry.network_allow is None
