"""Real HTTP/Unix/TCP transport; no host model or inference requests."""

import json
import os
import socket
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from uuid import uuid4

import httpx
import pytest

MODEL = "b12-test:pinned"


@pytest.fixture
def upstream():
    calls = []
    entered, disconnected, release = threading.Event(), threading.Event(), threading.Event()
    behavior = {}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def do_GET(self):
            calls.append(("GET", self.path, None))
            if behavior.get("redirect"):
                self.send_response(302)
                self.send_header("Location", "/api/delete")
                self.end_headers()
                return
            self.send_response(200)
            self.end_headers()
            if behavior.get("invalid_metadata"):
                self.wfile.write(b"[]")
                return
            self.wfile.write(json.dumps({"models": [{"name": MODEL}, {"name": "other"}]}).encode())

        def do_POST(self):
            data = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            calls.append(("POST", self.path, data))
            entered.set()
            if data.get("messages") == [{"role": "user", "content": "slow headers"}]:
                self.connection.settimeout(2)
                if self.connection.recv(1) == b"":
                    disconnected.set()
                return
            self.send_response(200)
            self.end_headers()
            if behavior.get("large_response"):
                try:
                    self.wfile.write(b"x" * (9 * 1024 * 1024))
                except (BrokenPipeError, ConnectionResetError):
                    pass
                return
            if self.path == "/api/chat":
                self.wfile.write(b'{"message":{"content":"first"}}\n')
                self.wfile.flush()
                self.connection.settimeout(0.02)
                until = time.monotonic() + 3
                while not release.is_set() and time.monotonic() < until:
                    try:
                        if self.connection.recv(1) == b"":
                            disconnected.set()
                            return
                    except TimeoutError:
                        pass
                self.wfile.write(b'{"done":true}\n')
            else:
                self.wfile.write(b'{"ok":true}')

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server.daemon_threads = True
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_port}", calls, entered, disconnected, release, behavior
    release.set()
    server.shutdown()
    server.server_close()
    thread.join(2)


@pytest.fixture
def broker(tmp_path, upstream):
    from evals.ollama_broker import ModelBroker

    with ModelBroker(tmp_path / "model.sock", upstream[0], MODEL) as running:
        yield running


def client(broker):
    return httpx.Client(
        transport=httpx.HTTPTransport(uds=str(broker.path)), base_url="http://model", timeout=2
    )


def test_metadata_filters_unrelated_models_and_forwards_pinned_show(broker):
    with client(broker) as c:
        assert c.get("/api/tags").json() == {"models": [{"name": MODEL}]}
        assert c.post("/api/show", json={"model": MODEL}).json() == {"ok": True}


@pytest.mark.parametrize(
    "method,path,body",
    [
        ("POST", "/api/delete", {"model": MODEL}),
        ("POST", "/api/chat", {"model": "other"}),
        ("POST", "/api/generate", {"model": MODEL, "keep_alive": 0, "prompt": "hi"}),
        ("POST", "/api/generate", {"model": MODEL, "keep_alive": 1}),
        ("GET", "/api/tags?url=http://other", None),
        ("DELETE", "/api/show", {"model": MODEL}),
    ],
)
def test_disallowed_requests_never_reach_upstream(broker, upstream, method, path, body):
    with client(broker) as c:
        assert c.request(method, path, json=body).status_code in (400, 403, 405)
    assert upstream[1] == []


def test_unload_accepts_only_empty_generation_for_pinned_model(broker, upstream):
    body = {"model": MODEL, "keep_alive": 0, "stream": False}
    with client(broker) as c:
        assert c.post("/api/generate", json=body).status_code == 200
    assert upstream[1] == [("POST", "/api/generate", body)]


def test_oversized_and_malformed_bodies_never_reach_upstream(broker, upstream):
    with client(broker) as c:
        assert c.post("/api/chat", content=b"x" * (1024 * 1024 + 1)).status_code == 413
        assert c.post("/api/chat", content=b"not-json").status_code == 400
        duplicate = b'{"model":"other","model":"b12-test:pinned"}'
        assert c.post("/api/chat", content=duplicate).status_code == 400
    assert upstream[1] == []


def test_first_stream_chunk_arrives_before_upstream_finishes(broker, upstream):
    with client(broker) as c:
        with c.stream("POST", "/api/chat", json={"model": MODEL, "messages": []}) as response:
            chunks = response.iter_bytes()
            assert b'"first"' in next(chunks)
            assert not upstream[4].is_set()
            upstream[4].set()
            assert b'"done":true' in b"".join(chunks)


def test_client_disconnect_closes_upstream_stream(broker, upstream):
    with client(broker) as c:
        with c.stream("POST", "/api/chat", json={"model": MODEL, "messages": []}) as response:
            assert next(response.iter_bytes())
    assert upstream[3].wait(1), "broker retained upstream after client disconnected"


def test_client_disconnect_before_headers_cancels_upstream(broker, upstream):
    with client(broker) as c:
        with pytest.raises(httpx.ReadTimeout):
            c.post(
                "/api/chat",
                json={"model": MODEL, "messages": [{"role": "user", "content": "slow headers"}]},
                timeout=0.15,
            )
    assert upstream[2].is_set()
    assert upstream[3].wait(1), "upstream request was not cancelled before headers"


def test_private_socket_is_removed_on_broker_shutdown(tmp_path, upstream):
    from evals.ollama_broker import ModelBroker

    path = tmp_path / "broker.sock"
    with ModelBroker(path, upstream[0], MODEL):
        assert path.stat().st_mode & 0o777 == 0o600
    assert not path.exists()


def test_loopback_bridge_preserves_real_http_stream(broker, upstream):
    from evals.socket_bridge import SocketBridge

    with SocketBridge(broker.path, port=0) as bridge:
        with httpx.Client(base_url=f"http://127.0.0.1:{bridge.port}", timeout=2) as c:
            assert c.get("/api/ps").json() == {"models": [{"name": MODEL}]}
            with c.stream("POST", "/api/chat", json={"model": MODEL}) as response:
                chunks = response.iter_bytes()
                assert b'"first"' in next(chunks)
                upstream[4].set()
                assert b'"done":true' in b"".join(chunks)
    with pytest.raises(OSError):
        socket.create_connection(("127.0.0.1", bridge.port), timeout=0.2)


def test_bridge_shutdown_closes_an_active_relay(broker, upstream):
    from evals.socket_bridge import SocketBridge

    with httpx.Client(timeout=2) as c:
        with SocketBridge(broker.path, port=0) as bridge:
            response = c.stream(
                "POST", f"http://127.0.0.1:{bridge.port}/api/chat", json={"model": MODEL}
            )
            opened = response.__enter__()
            assert next(opened.iter_bytes())
        assert upstream[3].wait(1), "active relay survived bridge shutdown"
        response.__exit__(None, None, None)


def test_broker_does_not_follow_or_expose_upstream_redirect(broker, upstream):
    upstream[5]["redirect"] = True
    with client(broker) as c:
        response = c.get("/api/version")
    assert response.status_code == 302
    assert "location" not in response.headers
    assert upstream[1] == [("GET", "/api/version", None)]


def test_broker_refuses_public_socket_directory_and_preserves_existing_file(tmp_path, upstream):
    from evals.ollama_broker import ModelBroker

    public = tmp_path / "public"
    public.mkdir(mode=0o755)
    with pytest.raises(ValueError, match="private"):
        with ModelBroker(public / "socket", upstream[0], MODEL):
            pass
    path = tmp_path / "occupied"
    path.write_text("keep this file")
    with pytest.raises(OSError):
        with ModelBroker(path, upstream[0], MODEL):
            pass
    assert path.read_text() == "keep this file"


def test_upstream_failure_returns_fixed_error(tmp_path):
    from evals.ollama_broker import ModelBroker

    # A bound, non-listening local socket makes connection refusal deterministic.
    with socket.socket() as unavailable:
        unavailable.bind(("127.0.0.1", 0))
        url = f"http://127.0.0.1:{unavailable.getsockname()[1]}"
        with ModelBroker(tmp_path / "refused.sock", url, MODEL) as running:
            with client(running) as c:
                response = c.get("/api/version")
    assert response.status_code == 502
    assert response.json() == {"error": "upstream_unavailable"}


def test_upstream_metadata_is_validated_and_response_bytes_are_bounded(broker, upstream):
    upstream[5]["invalid_metadata"] = True
    with client(broker) as c:
        response = c.get("/api/tags")
        assert response.status_code == 502
        assert response.json() == {"error": "invalid_upstream_metadata"}
        upstream[5].clear()
        upstream[5]["large_response"] = True
        response = c.post("/api/chat", json={"model": MODEL})
        assert response.status_code == 200
        assert 0 < len(response.content) <= 8 * 1024 * 1024
        assert b'"done":true' not in response.content


def test_broker_shutdown_cancels_active_stream(tmp_path, upstream):
    from evals.ollama_broker import ModelBroker

    running = ModelBroker(tmp_path / "active.sock", upstream[0], MODEL).__enter__()
    try:
        with client(running) as c:
            with c.stream("POST", "/api/chat", json={"model": MODEL}) as response:
                assert next(response.iter_bytes())
                running.close()
                assert upstream[3].wait(1)
        assert not running.path.exists()
        assert not running.thread.is_alive()
    finally:
        running.close()


@pytest.mark.skipif(os.environ.get("B12_DOCKER_TEST") != "1", reason="opt-in Docker transport test")
def test_networkless_container_reaches_only_broker_routes(tmp_path, upstream):
    from evals.ollama_broker import ModelBroker

    channel = tmp_path / "channel"
    channel.mkdir(mode=0o700)
    bridge_code = Path(__file__).resolve().parents[2] / "evals/socket_bridge.py"
    script = """import http.client,json,runpy
from pathlib import Path
bridge=runpy.run_path('/bridge.py')['SocketBridge']
with bridge(Path('/broker/model.sock')):
 c=http.client.HTTPConnection('127.0.0.1',11434,timeout=2)
 c.request('GET','/api/tags'); r=c.getresponse()
 assert json.loads(r.read()) == {'models':[{'name':'b12-test:pinned'}]}
 c.request('POST','/api/delete',body='{}',headers={'Content-Type':'application/json'})
 r=c.getresponse();assert r.status==403;r.read()
 c.request('POST','/api/chat',body='{"model":"b12-test:pinned"}',headers={'Content-Type':'application/json'})
 r=c.getresponse();first=r.read1(65536)
 assert b'"first"' in first and b'"done"' not in first
 c.close()
print('container metadata, route denial, streaming: passed')
"""
    name = "b12-transport-test-" + uuid4().hex
    args = [
        "docker",
        "run",
        "--rm",
        "--pull",
        "never",
        "--name",
        name,
        "--network",
        "none",
        "--cap-drop",
        "ALL",
        "--security-opt",
        "no-new-privileges",
        "--read-only",
        "--user",
        f"{os.getuid()}:{os.getgid()}",
        "--pids-limit",
        "64",
        "--memory",
        "256m",
        "--cpus",
        "1",
        "--tmpfs",
        "/tmp:rw,nosuid,nodev,size=32m",
        "--mount",
        f"type=bind,src={channel},dst=/broker,readonly",
        "--mount",
        f"type=bind,src={bridge_code},dst=/bridge.py,readonly",
        "python@sha256:34386ef0cb081344d7ec1c103ba398e6e9f64e9ab3a1509accc92a4e24a07258",
        "python",
        "-c",
        script,
    ]
    with ModelBroker(channel / "model.sock", upstream[0], MODEL):
        try:
            result = subprocess.run(args, text=True, capture_output=True, timeout=15)
            assert result.returncode == 0, result.stderr
            assert upstream[3].wait(1), "container disconnect did not close host upstream"
            assert [call[1] for call in upstream[1]] == ["/api/tags", "/api/chat"]
        finally:
            subprocess.run(["docker", "rm", "-f", name], capture_output=True, timeout=5)
