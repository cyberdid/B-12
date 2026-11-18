import socket

import pytest


def test_networkless_entrypoint_bridges_broker_before_running_suite(monkeypatch, tmp_path):
    from evals.capri_comprehensive.runners import run_networkless_runtime_suite as entry

    socket_path = tmp_path / "model.sock"
    with socket.socket(socket.AF_UNIX) as broker_socket:
        broker_socket.bind(str(socket_path))
    calls = []

    class FakeBridge:
        def __init__(self, path, *, host, port):
            calls.append(("init", path, host, port))

        def __enter__(self):
            calls.append(("enter",))
            return self

        def __exit__(self, *_):
            calls.append(("exit",))

    monkeypatch.setattr(entry, "SocketBridge", FakeBridge)
    monkeypatch.setattr(entry.run_runtime_suite, "main", lambda ids: calls.append(("run", ids)))
    monkeypatch.setenv("B12_EVAL_SANDBOX", "1")
    monkeypatch.setenv("B12_EVAL_BROKER_SOCKET", str(socket_path))
    monkeypatch.setenv("B12_EVAL_OLLAMA_URL", "http://127.0.0.1:11434")

    entry.main(["MEM-01"])

    assert calls == [
        ("init", socket_path, "127.0.0.1", 11434),
        ("enter",),
        ("run", ["MEM-01"]),
        ("exit",),
    ]


def test_transport_check_verifies_models_without_running_scenarios(monkeypatch, tmp_path, capsys):
    from evals.capri_comprehensive.runners import run_networkless_runtime_suite as entry

    socket_path = tmp_path / "model.sock"
    with socket.socket(socket.AF_UNIX) as broker_socket:
        broker_socket.bind(str(socket_path))
    calls = []

    class FakeBridge:
        def __init__(self, path, *, host, port):
            calls.append(("init", path, host, port))

        def __enter__(self):
            calls.append(("enter",))
            return self

        def __exit__(self, *_):
            calls.append(("exit",))

    class FakeResponse:
        def raise_for_status(self):
            pass

        def json(self):
            return {
                "models": [
                    {"name": "b12-bolt-e4b:q4km"},
                    {"name": "gemma4:12b"},
                ]
            }

    class FakeClient:
        def __init__(self, **kwargs):
            calls.append(("client", kwargs))

        def __enter__(self):
            return self

        def __exit__(self, *_):
            pass

        def get(self, route):
            calls.append(("get", route))
            return FakeResponse()

    monkeypatch.setattr(entry, "SocketBridge", FakeBridge)
    monkeypatch.setattr(entry.httpx, "Client", FakeClient)
    monkeypatch.setenv("B12_EVAL_SANDBOX", "1")
    monkeypatch.setenv("B12_EVAL_BROKER_SOCKET", str(socket_path))
    monkeypatch.setenv("B12_EVAL_OLLAMA_URL", "http://127.0.0.1:11434")
    monkeypatch.setenv("B12_EVAL_MODEL", "gemma4:12b")

    entry.main(["--transport-check"])

    assert ("get", "/api/tags") in calls
    assert not any(call[0] == "run" for call in calls)
    assert "networkless model transport passed" in capsys.readouterr().out


@pytest.mark.parametrize(
    "variable,value",
    [
        ("B12_EVAL_SANDBOX", None),
        ("B12_EVAL_BROKER_SOCKET", None),
        ("B12_EVAL_OLLAMA_URL", "http://example.com:11434"),
    ],
)
def test_networkless_entrypoint_refuses_untrusted_transport(monkeypatch, tmp_path, variable, value):
    from evals.capri_comprehensive.runners import run_networkless_runtime_suite as entry

    socket_path = tmp_path / "model.sock"
    with socket.socket(socket.AF_UNIX) as broker_socket:
        broker_socket.bind(str(socket_path))
    monkeypatch.setenv("B12_EVAL_SANDBOX", "1")
    monkeypatch.setenv("B12_EVAL_BROKER_SOCKET", str(socket_path))
    monkeypatch.setenv("B12_EVAL_OLLAMA_URL", "http://127.0.0.1:11434")
    if value is None:
        monkeypatch.delenv(variable, raising=False)
    else:
        monkeypatch.setenv(variable, value)

    with pytest.raises(SystemExit):
        entry.main([])
