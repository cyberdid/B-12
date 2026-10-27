"""Local owner CLI. Running it is the trusted local control channel for the owner.

Settings: optional TOML (--config, else $XDG_CONFIG_HOME/b12/config.toml), with
B12_* environment values taking precedence. Exit codes: 0 completed/ok,
1 failed/error, 2 waiting for approval, 3 purge still pending, 130 cancelled.
"""

import argparse
import asyncio
import json
import os
import signal
import sys
import tomllib
from pathlib import Path

import httpx

from b12.auth import owner_capabilities
from b12.config import Settings
from b12.model_errors import ModelError

_EXIT = {"completed": 0, "failed": 1, "awaiting_approval": 2, "cancelled": 130}


def load_settings(config: str | None = None) -> Settings:
    environ = dict(os.environ)
    base = Path(environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")
    path = Path(config) if config else base / "b12" / "config.toml"
    if config or path.exists():
        for key, value in tomllib.loads(path.read_text()).items():
            text = ",".join(map(str, value)) if isinstance(value, list) else str(value)
            environ.setdefault(f"B12_{key.upper()}", text)
    return Settings.from_env(environ)


def emit_json(value) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2))


def turn_json(result) -> dict:
    return {
        "turn_id": result.turn_id,
        "session_id": result.session_id,
        "state": result.state,
        "content": result.content,
        "error_code": result.error_code,
        "pending_operations": list(result.pending_operations),
        "persisted": result.persisted,
        "tool_results": [r.model_dump(mode="json") for r in result.tool_results],
    }


class Owner:
    """Owner identity and default CLI session stored in ControlStore metadata."""

    def __init__(self, runtime):
        self.runtime = runtime
        control = runtime.control
        self.actor_id = control.get_meta("owner_actor")
        self.session_id = control.get_meta("cli_session")

    @property
    def initialized(self) -> bool:
        return self.actor_id is not None

    def actor(self):
        return self.runtime.control.resolve_actor(self.actor_id)

    def grant(self, timeout_s: float) -> tuple[str, str]:
        control, access = self.runtime.control, self.runtime.settings.host_access
        task = control.create_task(self.session_id)
        grant = control.issue_grant(
            self.actor_id,
            self.session_id,
            owner_capabilities(self.runtime.settings),
            task_id=task,
            ttl_s=timeout_s + 3600,
            full_execution=access == "full",
        )
        return grant, task


def open_or_fail(settings):
    from b12.runtime import open_runtime

    try:
        return open_runtime(settings)
    except ModelError as exc:
        emit_json({"error": exc.code})
        raise SystemExit(1) from None


async def check_model(settings) -> dict:
    from b12.model import OllamaModel
    from b12.model_profile import ModelProfile

    report = {"reachable": False, "version": None, "digest_matches": False}
    try:
        profile = ModelProfile(settings)
    except ModelError as exc:
        report["error"] = exc.code
        return report
    try:
        async with httpx.AsyncClient(
            base_url=settings.ollama_url.rstrip("/") + "/", timeout=5, trust_env=False
        ) as client:
            report["version"] = (await client.get("api/version")).json().get("version")
            report["reachable"] = True
            await OllamaModel._check_deployment(client, profile)
            report["digest_matches"] = True
    except ModelError as exc:
        report["error"] = exc.code
    except (httpx.HTTPError, ValueError):
        report["error"] = "transport_error"
    return report


async def cmd_doctor(args, settings) -> int:
    report = {"state_dir": str(settings.state_dir), "model": await check_model(settings)}
    try:
        runtime = open_or_fail(settings)
    except SystemExit:
        return 1
    try:
        owner = Owner(runtime)
        report["initialized"] = owner.initialized
        report["consent"] = owner.actor().consent if owner.initialized else None
        report["pending_purges"] = sum(
            len(runtime.memory.pending_purges(runtime.control.resolve_actor(actor_id)))
            for actor_id in runtime.control.actor_ids()
        )
        report["pending_approvals"] = len(runtime.control.pending_approvals())
        report["tools"] = len(runtime.registry.catalog())
    finally:
        runtime.close()
    report["ok"] = bool(
        report["initialized"] and report["model"]["digest_matches"] and not report["pending_purges"]
    )
    emit_json(report)
    return 0 if report["ok"] else 1


async def cmd_init(args, settings) -> int:
    runtime = open_or_fail(settings)
    try:
        owner = Owner(runtime)
        if not owner.initialized:
            actor = runtime.control.create_actor(owner=True, consent=not args.no_consent)
            session = runtime.control.create_session(actor.id)
            runtime.control.set_meta("owner_actor", actor.id)
            runtime.control.set_meta("cli_session", session)
            owner = Owner(runtime)
        emit_json(
            {
                "owner_id": owner.actor_id,
                "session_id": owner.session_id,
                "consent": owner.actor().consent,
            }
        )
    finally:
        runtime.close()
    return 0


def require_owner(runtime) -> Owner:
    owner = Owner(runtime)
    if not owner.initialized:
        emit_json({"error": "not_initialized", "hint": "run: b12 init"})
        runtime.close()
        raise SystemExit(1)
    return owner


class Console:
    """Human-readable streaming: reply text on stdout, tool activity on stderr."""

    def __init__(self, quiet: bool):
        self.quiet = quiet

    async def __call__(self, event):
        if self.quiet:
            return
        if event.type == "text_delta":
            sys.stdout.write(event.data["text"])
            sys.stdout.flush()
        elif event.type == "tool_started":
            print(f"[інструмент] {event.data['name']} …", file=sys.stderr)
        elif event.type == "tool_result":
            print(f"[інструмент] {event.data['name']} → {event.data['status']}", file=sys.stderr)
        elif event.type in ("turn_completed", "turn_failed", "turn_cancelled"):
            sys.stdout.write("\n")
            sys.stdout.flush()


async def run_with_interrupt(function, *args, **kwargs):
    """SIGINT sets the turn's cancellation event instead of killing the process."""
    cancel = asyncio.Event()
    loop = asyncio.get_running_loop()
    loop.add_signal_handler(signal.SIGINT, cancel.set)
    try:
        return await function(*args, cancel=cancel, **kwargs)
    finally:
        loop.remove_signal_handler(signal.SIGINT)


async def interactive_approvals(runtime, result, console, timeout_s):
    while result.state == "awaiting_approval":
        approvals = {a["operation_id"]: a for a in runtime.control.pending_approvals()}
        operation = result.pending_operations[0]
        name = approvals.get(operation, {}).get("name", "?")
        print(f"Дозволити {name}? [y/N] ", end="", file=sys.stderr, flush=True)
        answer = (await asyncio.to_thread(sys.stdin.readline)).strip().lower()
        runtime.control.decide_approval(operation, answer in ("y", "yes", "т", "так"))
        result = await run_with_interrupt(
            runtime.agent.resume, result.turn_id, on_event=console, timeout_s=timeout_s
        )
    return result


async def cmd_chat(args, settings) -> int:
    runtime = open_or_fail(settings)
    try:
        owner = require_owner(runtime)
        await runtime.purge.resume()
        from b12.tools.mcp import attach_catalog

        await attach_catalog(runtime)
        try:
            return await _converse(args, runtime, owner)
        finally:
            from b12.tools.mcp import close_servers

            await close_servers(runtime)
    finally:
        runtime.close()


async def _converse(args, runtime, owner) -> int:
    if args.message is not None:
        grant, task = owner.grant(args.timeout)
        console = Console(quiet=args.json)
        result = await run_with_interrupt(
            runtime.agent.turn,
            owner.session_id,
            grant,
            args.message,
            task_id=task,
            on_event=console,
            timeout_s=args.timeout,
        )
        if args.json:
            emit_json(turn_json(result))
        return _EXIT[result.state]
    console = Console(quiet=False)
    while True:
        print("ти> ", end="", file=sys.stderr, flush=True)
        line = await asyncio.to_thread(sys.stdin.readline)
        if not line:
            return 0
        if not line.strip():
            continue
        grant, task = owner.grant(args.timeout)
        print("B-12> ", end="", flush=True)
        result = await run_with_interrupt(
            runtime.agent.turn,
            owner.session_id,
            grant,
            line.strip(),
            task_id=task,
            on_event=console,
            timeout_s=args.timeout,
        )
        result = await interactive_approvals(runtime, result, console, args.timeout)
        if result.state != "completed":
            print(f"[{result.state}: {result.error_code}]", file=sys.stderr)


async def cmd_resume(args, settings) -> int:
    runtime = open_or_fail(settings)
    try:
        require_owner(runtime)
        result = await run_with_interrupt(
            runtime.agent.resume, args.turn_id, on_event=Console(quiet=args.json)
        )
        if args.json:
            emit_json(turn_json(result))
        return _EXIT[result.state]
    finally:
        runtime.close()


async def cmd_decide(args, settings, approve: bool) -> int:
    from b12.control import ControlError

    runtime = open_or_fail(settings)
    try:
        require_owner(runtime)
        try:
            runtime.control.decide_approval(args.operation_id, approve)
        except ControlError as exc:
            emit_json({"error": exc.code})
            return 1
        emit_json({"operation_id": args.operation_id, "approved": approve})
        return 0
    finally:
        runtime.close()


async def cmd_approvals(args, settings) -> int:
    runtime = open_or_fail(settings)
    try:
        require_owner(runtime)
        emit_json(runtime.control.pending_approvals())
        return 0
    finally:
        runtime.close()


async def cmd_memory(args, settings) -> int:
    runtime = open_or_fail(settings)
    try:
        owner = require_owner(runtime)
        actor = owner.actor()
        if args.action == "remember":
            record = runtime.memory.remember(args.value, actor, source="cli")
            emit_json(record.model_dump(mode="json"))
        elif args.action == "search":
            emit_json([r.model_dump(mode="json") for r in runtime.memory.search(args.value, actor)])
        elif args.action == "forget":
            try:
                receipt = await runtime.purge.forget(args.value, actor.id)
            except (KeyError, ValueError):
                emit_json({"error": "not_found"})
                return 1
            emit_json(receipt.model_dump(mode="json"))
            return 0 if receipt.state == "complete" else 3
        elif args.action == "pending":
            emit_json([r.model_dump(mode="json") for r in runtime.memory.pending_purges(actor)])
        return 0
    finally:
        runtime.close()


async def cmd_session_clear(args, settings) -> int:
    runtime = open_or_fail(settings)
    try:
        owner = require_owner(runtime)
        runtime.sessions.clear_session(owner.session_id, owner.actor_id)
        emit_json({"cleared": owner.session_id})
        return 0
    finally:
        runtime.close()


async def cmd_tools(args, settings) -> int:
    runtime = open_or_fail(settings)
    try:
        emit_json(runtime.registry.catalog())
        return 0
    finally:
        runtime.close()


async def cmd_goals(args, settings) -> int:
    runtime = open_or_fail(settings)
    try:
        owner = require_owner(runtime)
        goals = runtime.goals
        if args.action == "add":
            check = None
            if args.check_file:
                check = {"kind": "file_contains", "path": args.check_file, "text": args.check_text}
            session = runtime.control.create_session(owner.actor_id)
            emit_json(
                goals.create(
                    owner.actor_id,
                    session,
                    args.value,
                    args.criteria,
                    allowed_tools=tuple(
                        args.tools
                        or (c for c in owner_capabilities(settings) if c != "process.sudo")
                    ),
                    budget_turns=args.budget,
                    review_interval_s=args.interval,
                    check=check,
                )
            )
        elif args.action == "list":
            emit_json(goals.for_actor(owner.actor_id))
        else:
            status = {"pause": "paused", "resume": "active", "abandon": "abandoned"}[args.action]
            try:
                emit_json(goals.set_status(args.value, owner.actor_id, status, "owner_control"))
            except KeyError:
                emit_json({"error": "goal_not_found"})
                return 1
        return 0
    finally:
        runtime.close()


async def cmd_flag(args, settings) -> int:
    runtime = open_or_fail(settings)
    try:
        owner = require_owner(runtime)
        setter = (
            runtime.attention.set_quiet
            if args.command == "quiet"
            else runtime.attention.set_stopped
        )
        setter(owner.actor_id, args.value == "on")
        emit_json(runtime.attention.state(owner.actor_id))
        return 0
    finally:
        runtime.close()


async def cmd_autonomy(args, settings) -> int:
    from b12.autonomy import Scheduler, SchedulerLocked

    runtime = open_or_fail(settings)
    try:
        require_owner(runtime)
        await runtime.purge.resume()
        try:
            scheduler = Scheduler(runtime)
        except SchedulerLocked:
            emit_json({"error": "scheduler_locked"})
            return 1
        try:
            if args.reflect:
                emit_json(await scheduler.reflect_idle())
            else:
                emit_json(await scheduler.tick())
            return 0
        finally:
            scheduler.close()
    finally:
        runtime.close()


async def cmd_backup(args, settings) -> int:
    from b12.service import Operations

    operations = Operations(settings.state_dir)
    if args.action == "list":
        emit_json(operations.inventory())
        return 0
    if args.action == "create":
        emit_json(operations.create_snapshot())
        return 0
    if args.action == "verify":
        report = operations.verify(args.snapshot_id)
        emit_json(report)
        return 0 if report["ok"] else 1
    if args.action == "delete":
        operations.delete_snapshot(args.snapshot_id)
        emit_json({"deleted": args.snapshot_id})
        return 0
    try:
        emit_json(await operations.restore(args.snapshot_id, settings))
    except RuntimeError as exc:
        emit_json({"error": str(exc)})
        return 1
    return 0


async def cmd_status(args, settings) -> int:
    from b12.telemetry import status

    runtime = open_or_fail(settings)
    try:
        require_owner(runtime)
        emit_json(status(runtime))
        return 0
    finally:
        runtime.close()


async def cmd_mcp(args, settings) -> int:
    from b12.tools.mcp import load_catalog

    path = settings.state_dir / "mcp.json"
    entries = load_catalog(settings.state_dir)
    argv = args.server_argv
    if args.action == "add":
        if not argv or not args.capability:
            emit_json({"error": "command_and_capability_required"})
            return 1
        entries = [e for e in entries if e["name"] != args.name]
        entries.append(
            {
                "name": args.name,
                "command": argv,
                "capability": args.capability,
                "risk": "typed",
                "read_only": args.read_only,
                **({"timeout_s": args.timeout_s} if args.timeout_s else {}),
            }
        )
        settings.state_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
        fd = os.open(path, os.O_CREAT | os.O_TRUNC | os.O_WRONLY, 0o600)
        with os.fdopen(fd, "w") as handle:
            json.dump(entries, handle, indent=2)
    elif args.action == "remove":
        entries = [e for e in entries if e["name"] != args.name]
        fd = os.open(path, os.O_CREAT | os.O_TRUNC | os.O_WRONLY, 0o600)
        with os.fdopen(fd, "w") as handle:
            json.dump(entries, handle, indent=2)
    elif args.action == "test":
        from b12.tools.mcp import McpServer

        entry = next((e for e in entries if e["name"] == args.name), None)
        if entry is None:
            emit_json({"error": "not_found"})
            return 1
        server = McpServer(entry["name"], entry["command"], cwd=entry.get("cwd"))
        try:
            await server.start(timeout_s=60)
            tools = await server.list_tools()
        finally:
            await server.aclose()
        emit_json({"name": args.name, "tools": [t.get("name") for t in tools]})
        return 0
    emit_json(entries)
    return 0


async def cmd_serve(args, settings) -> int:
    import ipaddress

    import uvicorn

    from b12.api import create_app

    if not ipaddress.ip_address(args.host).is_loopback:
        emit_json({"error": "loopback_only"})
        return 1
    app = create_app(settings, port=args.port, autonomy=not args.no_autonomy)
    server = uvicorn.Server(
        uvicorn.Config(
            app,
            host=args.host,
            port=args.port,
            log_level="warning",
            access_log=False,
            timeout_graceful_shutdown=5,  # then open streams are cancelled -> turns cancel
        )
    )
    print(
        json.dumps(
            {
                "url": f"http://{args.host}:{args.port}",
                "token_file": str(settings.state_dir / "api" / "owner.token"),
            }
        ),
        file=sys.stderr,
    )
    await server.serve()
    return 0


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(prog="b12", description="Локальний компаньйон B-12")
    root.add_argument("--config", help="TOML settings file (B12_* env overrides it)")
    sub = root.add_subparsers(dest="command", required=True)
    sub.add_parser("doctor", help="стан моделі, профілю й сховищ").add_argument(
        "--json", action="store_true"
    )
    init = sub.add_parser("init", help="створити owner і сесію CLI")
    init.add_argument("--no-consent", action="store_true", help="без збереження пам’яті")
    chat = sub.add_parser("chat", help="розмова; -m для одного turn")
    chat.add_argument("-m", "--message")
    chat.add_argument("--json", action="store_true")
    chat.add_argument("--timeout", type=float, default=300.0)
    resume = sub.add_parser("resume", help="продовжити turn після approval")
    resume.add_argument("turn_id")
    resume.add_argument("--json", action="store_true")
    for name in ("approve", "deny"):
        sub.add_parser(name).add_argument("operation_id")
    sub.add_parser("approvals", help="черга approval")
    memory = sub.add_parser("memory", help="пам’ять власника")
    memory.add_argument("action", choices=("remember", "search", "forget", "pending"))
    memory.add_argument("value", nargs="?", default="")
    session = sub.add_parser("session", help="робоча історія CLI")
    session.add_argument("action", choices=("clear",))
    sub.add_parser("tools", help="каталог інструментів")
    serve = sub.add_parser("serve", help="локальний API (лише loopback)")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8712)
    serve.add_argument("--no-autonomy", action="store_true", help="без фонового scheduler")
    goals = sub.add_parser("goals", help="фонові цілі власника")
    goals.add_argument("action", choices=("add", "list", "pause", "resume", "abandon"))
    goals.add_argument("value", nargs="?", default="")
    goals.add_argument("--criteria", default="Короткий звіт про результат")
    goals.add_argument("--budget", type=int, default=5)
    goals.add_argument("--interval", type=float, default=3600)
    goals.add_argument("--tools", nargs="*")
    goals.add_argument("--check-file")
    goals.add_argument("--check-text", default="")
    for name in ("quiet", "stop"):
        sub.add_parser(
            name, help="тихий режим" if name == "quiet" else "зупинка фону"
        ).add_argument("value", choices=("on", "off"))
    mcp = sub.add_parser("mcp", help="довірений каталог MCP-серверів власника")
    mcp.add_argument("action", choices=("list", "add", "remove", "test"))
    mcp.add_argument("name", nargs="?", default="")
    mcp.add_argument("--capability")
    mcp.add_argument("--read-only", action="store_true")
    mcp.add_argument("--timeout-s", type=float, help="per-tool timeout (slow model loads)")
    backup = sub.add_parser("backup", help="керовані знімки стану")
    backup.add_argument("action", choices=("create", "list", "verify", "restore", "delete"))
    backup.add_argument("snapshot_id", nargs="?")
    sub.add_parser("status", help="метрики й ресурси")
    autonomy = sub.add_parser("autonomy", help="один прохід scheduler")
    autonomy.add_argument("--reflect", action="store_true", help="лише idle рефлексія")
    return root


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    # `b12 mcp add NAME --capability C -- server argv...`: everything after -- is the argv.
    server_argv = argv[argv.index("--") + 1 :] if "--" in argv else []
    argv = argv[: argv.index("--")] if "--" in argv else argv
    args = parser().parse_args(argv)
    args.server_argv = server_argv
    try:
        settings = load_settings(args.config)
    except (ValueError, OSError, tomllib.TOMLDecodeError) as exc:
        emit_json({"error": "invalid_settings", "detail": type(exc).__name__})
        return 1
    handlers = {
        "doctor": cmd_doctor,
        "init": cmd_init,
        "chat": cmd_chat,
        "resume": cmd_resume,
        "approve": lambda a, s: cmd_decide(a, s, True),
        "deny": lambda a, s: cmd_decide(a, s, False),
        "approvals": cmd_approvals,
        "memory": cmd_memory,
        "session": cmd_session_clear,
        "tools": cmd_tools,
        "serve": cmd_serve,
        "goals": cmd_goals,
        "quiet": cmd_flag,
        "stop": cmd_flag,
        "autonomy": cmd_autonomy,
        "backup": cmd_backup,
        "mcp": cmd_mcp,
        "status": cmd_status,
    }
    try:
        return asyncio.run(handlers[args.command](args, settings))
    except SystemExit as exc:
        return int(exc.code or 0)


if __name__ == "__main__":
    sys.exit(main())
