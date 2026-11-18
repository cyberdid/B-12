"""The synthetic-environment stub answers declared probes and leaves the rest alone."""

import asyncio
from types import SimpleNamespace

from evals.unified.env_stub import stub_environment


class Guard:
    def check(self):
        pass


class Registry:
    def __init__(self):
        from b12.tools.registry import _Tool

        async def real(args, guard, *rest, **kwargs):
            from b12.tools.outcomes import HandlerOutcome

            return HandlerOutcome(content={"real": True, "command": getattr(args, "command", "")})

        def tool(name):
            return _Tool(
                name=name,
                description="d",
                model=None,
                handler=real,
                capability="c",
                risk="read_only",
                schema={},
            )

        self._tools = {n: tool(n) for n in ("system_info", "run_command", "http_fetch")}


def call(registry, name, **args):
    return asyncio.run(registry._tools[name].handler(SimpleNamespace(**args), Guard()))


def test_disk_uptime_and_free_are_rendered_from_synthetic_values():
    registry = Registry()
    env = {
        "system_info": {
            "disk_root_free_gib": 31.0,
            "disk_root_total_gib": 410.0,
            "uptime_hours": 52.5,
            "ram_total_gib": 32.0,
            "ram_available_gib": 12.4,
        }
    }
    assert set(stub_environment(registry, env)) == {"system_info", "run_command"}
    assert "31G" in call(registry, "run_command", command="df -h /").content["stdout"]
    assert "up 2 days, 4:30" in call(registry, "run_command", command="uptime").content["stdout"]
    assert "12.4Gi" in call(registry, "run_command", command="free -h").content["stdout"]
    info = call(registry, "system_info").content
    assert info["real"] is True and info["disk_root_free_gib"] == 31.0
    assert call(registry, "run_command", command="ls /sandbox").content["real"] is True


def test_declared_ports_answer_or_refuse():
    registry = Registry()
    stub_environment(
        registry,
        {
            "127.0.0.1:9100": "http 200 for any path; body: status=ok",
            "127.0.0.1:7070": "connection_refused_for_any_path_or_probe",
        },
    )
    ok = call(registry, "run_command", command="curl -s http://127.0.0.1:9100/health")
    assert ok.content["stdout"].strip() == "status=ok" and ok.content["exit_code"] == 0
    refused = call(registry, "run_command", command="curl http://127.0.0.1:7070")
    assert refused.content["exit_code"] == 7 and "Connection refused" in refused.content["stderr"]
    fetched = call(registry, "http_fetch", url="http://127.0.0.1:9100/")
    assert fetched.content["text"] == "status=ok"
    assert call(registry, "http_fetch", url="http://127.0.0.1:7070/").status == "failed"
    assert call(registry, "http_fetch", url="http://127.0.0.1:5000/").content["real"] is True
