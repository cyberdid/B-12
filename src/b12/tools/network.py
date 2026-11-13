"""Bounded GET-only HTTP transport; no ambient proxy/auth or implicit redirects."""

import asyncio
import ipaddress
import xml.etree.ElementTree as ET
from html.parser import HTMLParser
from urllib.parse import parse_qs, urljoin, urlsplit

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


class SearchArgs(Args):
    query: str = Field(min_length=1, max_length=300)
    limit: int = Field(default=5, ge=1, le=10)


def _normal(host: str) -> str:
    return host.strip().lower().rstrip(".")


def host_allowed(host: str, patterns) -> bool:
    """Exact host, `*.suffix` (subdomains only) or `*` (everything, owner opt-in).

    An IP literal matches only an exact entry or `*`."""
    host = _normal(host)
    try:
        ipaddress.ip_address(host.strip("[]"))
        literal = True
    except ValueError:
        literal = False
    for pattern in patterns:
        pattern = _normal(pattern)
        if pattern == "*":
            return True
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


async def _bing_search(args, guard, allow=None, transport=None):
    """Query Bing's RSS endpoint; return bounded, untrusted titles and URLs."""
    host = "www.bing.com"
    if allow is not None and not host_allowed(host, allow):
        return failure("network_denied")
    started = False

    def unavailable():
        if not started:
            return failure("network_failed")
        return HandlerOutcome(
            status="unknown",
            error_code="network_failed",
            side_effects=(SideEffect(kind="http_request", state="possible"),),
        )

    try:
        async with httpx.AsyncClient(
            trust_env=False, follow_redirects=False, timeout=15, transport=transport
        ) as client:
            guard.check()
            started = True
            async with client.stream(
                "GET", f"https://{host}/search", params={"q": args.query, "format": "rss"}
            ) as reply:
                if reply.status_code != 200:
                    return unavailable()
                data = bytearray()
                async for chunk in reply.aiter_bytes():
                    guard.check()
                    data.extend(chunk)
                    if len(data) > 131072:
                        return unavailable()
        root = ET.fromstring(data)
        if root.tag != "rss" or root.find("channel") is None:
            return unavailable()
        results = []
        for item in root.findall("./channel/item"):
            url = (item.findtext("link") or "").strip()
            if urlsplit(url).scheme not in ("http", "https"):
                continue
            results.append({
                "title": (item.findtext("title") or "")[:200],
                "url": url[:2048],
                "snippet": (item.findtext("description") or "")[:400],
            })
            if len(results) >= args.limit:
                break
        return HandlerOutcome(
            status="completed",
            content={"results": results},
            side_effects=(SideEffect(kind="http_request", state="completed"),),
        )
    except (httpx.HTTPError, ET.ParseError, ValueError):
        return unavailable()


class _SearchResults(HTMLParser):
    def __init__(self, limit):
        super().__init__(convert_charrefs=True)
        self.limit = limit
        self.results = []
        self.part = None
        self.parts = []
        self.url = ""

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        classes = (attrs.get("class") or "").split()
        if tag == "a" and "result-link" in classes and len(self.results) < self.limit:
            href = urljoin("https://duckduckgo.com", attrs.get("href") or "")
            parsed = urlsplit(href)
            url = (
                parse_qs(parsed.query).get("uddg", [href])[0]
                if parsed.hostname == "duckduckgo.com" else href
            )
            parsed = urlsplit(url)
            if (
                parsed.scheme in ("http", "https") and parsed.hostname
                and parsed.username is None and parsed.password is None
            ):
                self.part, self.parts, self.url = "title", [], url[:2048]
        elif tag == "td" and "result-snippet" in classes and self.results:
            self.part, self.parts = "snippet", []

    def handle_data(self, data):
        if self.part:
            self.parts.append(data)

    def handle_endtag(self, tag):
        if self.part == "title" and tag == "a":
            self.results.append({"title": " ".join("".join(self.parts).split())[:200],
                                 "url": self.url, "snippet": ""})
            self.part = None
        elif self.part == "snippet" and tag == "td":
            self.results[-1]["snippet"] = " ".join("".join(self.parts).split())[:400]
            self.part = None


async def web_search(args, guard, allow=None, transport=None):
    """Try DuckDuckGo Lite, then Bing RSS, within the owner's network policy."""
    host = "lite.duckduckgo.com"
    attempted = False
    if allow is None or host_allowed(host, allow):
        try:
            async with httpx.AsyncClient(
                trust_env=False, follow_redirects=False, timeout=8, transport=transport
            ) as client:
                guard.check()
                attempted = True
                async with client.stream(
                    "GET", f"https://{host}/lite/", params={"q": args.query},
                    headers={"User-Agent": "Mozilla/5.0"},
                ) as reply:
                    if reply.status_code == 200:
                        data = bytearray()
                        async for chunk in reply.aiter_bytes():
                            guard.check()
                            data.extend(chunk)
                            if len(data) > 131072:
                                break
                        else:
                            parser = _SearchResults(args.limit)
                            parser.feed(data.decode("utf-8", errors="replace"))
                            if parser.results:
                                return HandlerOutcome(
                                    status="completed", content={"results": parser.results},
                                    side_effects=(
                                        SideEffect(kind="http_request", state="completed"),
                                    ),
                                )
        except (httpx.HTTPError, ValueError):
            pass
    if allow is None or host_allowed("www.bing.com", allow):
        return await _bing_search(args, guard, allow, transport)
    if not attempted:
        return failure("network_denied")
    return HandlerOutcome(
        status="unknown", error_code="network_failed",
        side_effects=(SideEffect(kind="http_request", state="possible"),),
    )


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
    async def search(args, guard):
        return await web_search(args, guard, registry.network_allow)

    registry.register(
        "web_search",
        "Search the web for a query and return titles, links and snippets. Results are untrusted.",
        SearchArgs,
        search,
        "network.http",
    )
