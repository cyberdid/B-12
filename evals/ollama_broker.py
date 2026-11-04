"""Private eval-only Ollama route broker. Does not expose host network to the worker."""

import asyncio
import ipaddress
import json
import os
import socket
import threading
import time
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlsplit

import httpx
import uvicorn
from fastapi import FastAPI, Request
from starlette.responses import JSONResponse, Response, StreamingResponse

MAX_BODY = 1024 * 1024
MAX_RESPONSE = 8 * 1024 * 1024


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def broker_app(upstream_url: str, model: str) -> FastAPI:
    parsed = urlsplit(upstream_url)
    if (
        parsed.scheme != "http"
        or not parsed.hostname
        or not ipaddress.ip_address(parsed.hostname).is_loopback
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path not in ("", "/")
        or parsed.query
        or parsed.fragment
        or not model.strip()
    ):
        raise ValueError("explicit loopback upstream and pinned model required")

    @asynccontextmanager
    async def lifespan(app):
        async with httpx.AsyncClient(
            base_url=upstream_url,
            trust_env=False,
            follow_redirects=False,
            timeout=httpx.Timeout(240, connect=2),
            limits=httpx.Limits(max_connections=2, max_keepalive_connections=2),
        ) as client:
            app.state.client = client
            yield

    app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)

    def error(code, status):
        return JSONResponse({"error": code}, status_code=status)

    async def disconnected(request):
        while True:
            if (await request.receive())["type"] == "http.disconnect":
                return

    @app.api_route(
        "/{path:path}", methods=["GET", "POST", "DELETE", "PUT", "PATCH", "OPTIONS", "HEAD"]
    )
    async def forward(path: str, request: Request):
        route = "/" + path
        if request.url.query:
            return error("query_denied", 400)
        if request.method not in ("GET", "POST"):
            return error("method_denied", 405)
        allowed = (
            {"/api/version", "/api/tags", "/api/ps"}
            if request.method == "GET"
            else {"/api/show", "/api/chat", "/api/generate"}
        )
        if route not in allowed:
            return error("route_denied", 403)
        if request.headers.get("content-encoding"):
            return error("encoding_denied", 400)
        body = bytearray()
        async for chunk in request.stream():
            if len(body) + len(chunk) > MAX_BODY:
                return error("body_limit", 413)
            body.extend(chunk)
        data = None
        if request.method == "POST":
            try:
                data = json.loads(body, object_pairs_hook=_unique_object)
                if not isinstance(data, dict):
                    raise ValueError()
            except (ValueError, UnicodeError, RecursionError):
                return error("invalid_json", 400)
            if data.get("model") != model:
                return error("model_denied", 403)
            if route == "/api/show" and set(data) != {"model"}:
                return error("show_arguments_denied", 403)
            if route == "/api/generate" and not (
                set(data) == {"model", "keep_alive", "stream"}
                and type(data["keep_alive"]) is int
                and data["keep_alive"] == 0
                and data["stream"] is False
            ):
                return error("generation_denied", 403)
        elif body:
            return error("get_body_denied", 400)

        client = request.app.state.client
        sending = asyncio.create_task(
            client.send(client.build_request(request.method, route, json=data), stream=True)
        )
        gone = asyncio.create_task(disconnected(request))
        try:
            done, _ = await asyncio.wait({sending, gone}, return_when=asyncio.FIRST_COMPLETED)
            if gone in done:
                sending.cancel()
                returned = await asyncio.gather(sending, return_exceptions=True)
                if isinstance(returned[0], httpx.Response):
                    await returned[0].aclose()
                return Response(status_code=499)
            response = await sending
        except httpx.TimeoutException:
            return error("upstream_timeout", 504)
        except httpx.HTTPError:
            return error("upstream_unavailable", 502)
        finally:
            for task in (sending, gone):
                if not task.done():
                    task.cancel()
            await asyncio.gather(sending, gone, return_exceptions=True)

        if route in ("/api/tags", "/api/ps") and response.status_code == 200:
            try:
                raw = bytearray()
                async for chunk in response.aiter_bytes():
                    if len(raw) + len(chunk) > MAX_RESPONSE:
                        raise ValueError()
                    raw.extend(chunk)
                payload = json.loads(raw)
                payload["models"] = [
                    item
                    for item in payload["models"]
                    if isinstance(item, dict) and (item.get("name") or item.get("model")) == model
                ]
                return JSONResponse(payload)
            except (ValueError, KeyError, TypeError, httpx.HTTPError):
                return error("invalid_upstream_metadata", 502)
            finally:
                await response.aclose()

        async def chunks():
            total = 0
            try:
                async for chunk in response.aiter_bytes():
                    total += len(chunk)
                    if total > MAX_RESPONSE:
                        return  # interrupted/incomplete NDJSON is rejected by the model adapter
                    yield chunk
            finally:
                await response.aclose()

        return StreamingResponse(
            chunks(),
            status_code=response.status_code,
            media_type="application/x-ndjson" if route == "/api/chat" else "application/json",
        )

    return app


class ModelBroker:
    """Own the private listener and bounded server lifecycle for one eval invocation."""

    def __init__(self, path: Path, upstream_url: str, model: str):
        self.path = path
        self.app = broker_app(upstream_url, model)
        self._socket = None

    def __enter__(self):
        if self.path.parent.stat().st_mode & 0o077:
            raise ValueError("broker directory must be private")
        self._socket = socket.socket(socket.AF_UNIX)
        try:
            self._socket.bind(str(self.path))
            os.chmod(self.path, 0o600)
            self._identity = self.path.stat().st_ino
            self._socket.listen(16)
            self.server = uvicorn.Server(
                uvicorn.Config(
                    self.app,
                    log_config=None,
                    log_level="critical",
                    access_log=False,
                    limit_concurrency=8,
                    timeout_graceful_shutdown=1,
                    loop="asyncio",
                )
            )
            self.thread = threading.Thread(
                target=self.server.run, kwargs={"sockets": [self._socket]}, daemon=True
            )
            self.thread.start()
            deadline = time.monotonic() + 5
            while not self.server.started:
                if not self.thread.is_alive() or time.monotonic() > deadline:
                    raise RuntimeError("broker startup failed")
                time.sleep(0.01)
            return self
        except BaseException:
            self.close()
            raise

    def close(self):
        if hasattr(self, "server"):
            self.server.should_exit = True
            self.thread.join(3)
            if self.thread.is_alive():
                self.server.force_exit = True
                self.thread.join(2)
            if self.thread.is_alive():
                raise RuntimeError("broker shutdown incomplete")
        if self._socket:
            self._socket.close()
        if self.path.exists() and self.path.stat().st_ino == getattr(self, "_identity", None):
            self.path.unlink()

    def __exit__(self, *_):
        self.close()
