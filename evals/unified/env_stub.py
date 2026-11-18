"""Eval-only stub for a scenario's `synthetic_environment` (disk, memory, uptime, local ports).

Without it, families such as C11/C12/C51-C54 read the real sandbox and their oracle is
unreachable for every model (found 18.11.2026). `stub_environment(registry, env)` wraps the
registered handlers in place for one run:

- `system_info` returns its real fields plus the synthetic ones;
- `run_command` answers `df`, `free` and `uptime` with realistic output built from the
  synthetic numbers, and `curl`/`wget`/`nc` aimed at a declared 127.0.0.1:<port> with the
  declared behaviour (HTTP 200 body or connection refused); anything else runs normally;
- `http_fetch` to a declared port gets the declared behaviour.

Returns the list of stubbed keys for the record. Never used outside evaluation.
"""

import dataclasses
import re
import shlex
from urllib.parse import urlsplit

from b12.tools._common import failure
from b12.tools.outcomes import HandlerOutcome

PORT = re.compile(r"127\.0\.0\.1:(\d+)")


def _df(values):
    total, free = values["disk_root_total_gib"], values["disk_root_free_gib"]
    used = total - free
    percent = round(100 * used / total)
    return (
        "Filesystem      Size  Used Avail Use% Mounted on\n"
        f"/dev/nvme0n1p5  {total:.0f}G  {used:.0f}G   {free:.0f}G  {percent}% /\n"
    )


def _free(values):
    total, available = values["ram_total_gib"], values["ram_available_gib"]
    used = total - available
    return (
        "               total        used        free      shared  buff/cache   available\n"
        f"Mem:           {total:.1f}Gi       {used:.1f}Gi       {available / 2:.1f}Gi"
        f"       0.5Gi       {available / 2:.1f}Gi       {available:.1f}Gi\n"
    )


def _uptime(values):
    hours = values["uptime_hours"]
    days, rest = divmod(int(hours * 60), 24 * 60)
    return (
        f" 10:00:00 up {days} days, {rest // 60}:{rest % 60:02d},  1 user,  "
        "load average: 0.20, 0.18, 0.15\n"
    )


RENDERERS = {
    "df": ("disk_root_free_gib", _df),
    "free": ("ram_available_gib", _free),
    "uptime": ("uptime_hours", _uptime),
}


def _command_outcome(stdout, *, exit_code=0, stderr=""):
    return HandlerOutcome(
        content={
            "pid": 0,
            "exit_code": exit_code,
            "command_succeeded": exit_code == 0,
            "stdout": stdout,
            "stderr": stderr,
            "cleanup_confirmed": True,
        }
    )


def _service(behaviour):
    """(reachable, body) from a declared behaviour string."""
    if "connection_refused" in behaviour:
        return False, ""
    body = behaviour.split("body:", 1)[1].strip() if "body:" in behaviour else "ok"
    return True, body


def stub_environment(registry, env):
    if not env:
        return []
    tools = registry._tools
    system_values = env.get("system_info", {}) or {}
    services = {int(m.group(1)): v for k, v in env.items() if (m := PORT.fullmatch(k))}
    stubbed = []

    def wrap(name, make):
        if name in tools:
            tool = tools[name]
            tools[name] = dataclasses.replace(tool, handler=make(tool.handler))
            stubbed.append(name)

    if system_values:

        def make_info(original):
            async def handler(args, guard):
                outcome = await original(args, guard)
                if outcome.status != "completed":
                    return outcome
                return outcome.model_copy(
                    update={"content": {**(outcome.content or {}), **system_values}}
                )

            return handler

        wrap("system_info", make_info)

    if system_values or services:

        def make_command(original):
            async def handler(args, guard):
                guard.check()
                try:
                    words = shlex.split(args.command)
                except ValueError:
                    words = args.command.split()
                head = words[0].rsplit("/", 1)[-1] if words else ""
                if head in RENDERERS and RENDERERS[head][0] in system_values:
                    return _command_outcome(RENDERERS[head][1](system_values))
                port = PORT.search(args.command)
                if head in {"curl", "wget", "nc"} and port and int(port.group(1)) in services:
                    reachable, body = _service(services[int(port.group(1))])
                    if reachable:
                        return _command_outcome(body + "\n")
                    return _command_outcome(
                        "",
                        exit_code=7,
                        stderr=f"curl: (7) Failed to connect to 127.0.0.1 port {port.group(1)}: "
                        "Connection refused\n",
                    )
                return await original(args, guard)

            return handler

        wrap("run_command", make_command)

    if services:

        def make_fetch(original):
            async def handler(args, guard, *rest, **kwargs):
                parts = urlsplit(args.url)
                if parts.hostname == "127.0.0.1" and parts.port in services:
                    guard.check()
                    reachable, body = _service(services[parts.port])
                    if not reachable:
                        return failure(ConnectionRefusedError(111, "Connection refused"))
                    return HandlerOutcome(
                        content={
                            "status_code": 200,
                            "content_type": "text/plain",
                            "content_encoding": "",
                            "text": body,
                        }
                    )
                return await original(args, guard, *rest, **kwargs)

            return handler

        wrap("http_fetch", make_fetch)
    return stubbed
