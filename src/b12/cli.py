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
    timeout = max(args.timeout, 1800.0) if args.persist else args.timeout
    if args.message is not None:
        grant, task = owner.grant(timeout)
        console = Console(quiet=args.json)
        result = await run_with_interrupt(
            runtime.agent.turn,
            owner.session_id,
            grant,
            args.message,
            task_id=task,
            on_event=console,
            timeout_s=timeout,
            persist=args.persist,
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
        grant, task = owner.grant(timeout)
        print("B-12> ", end="", flush=True)
        result = await run_with_interrupt(
            runtime.agent.turn,
            owner.session_id,
            grant,
            line.strip(),
            task_id=task,
            on_event=console,
            timeout_s=timeout,
            persist=args.persist,
        )
        result = await interactive_approvals(runtime, result, console, timeout)
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


async def cmd_knowledge(args, settings) -> int:
    runtime = open_or_fail(settings)
    try:
        owner = require_owner(runtime)
        actor = owner.actor()
        if args.action == "index":
            emit_json(runtime.knowledge.index_document(Path(args.value), actor))
        elif args.action == "remove":
            emit_json(runtime.knowledge.remove_document(Path(args.value), actor))
        else:
            emit_json(runtime.knowledge.search(args.value, actor))
        if args.action != "search":
            await runtime.purge.sync_knowledge(actor)  # dependent memories become stale now
        return 0
    finally:
        runtime.close()


async def cmd_memory(args, settings) -> int:
    runtime = open_or_fail(settings)
    try:
        owner = require_owner(runtime)
        actor = owner.actor()
        if args.action == "remember":
            record = runtime.memory.remember(
                args.value, actor, source="cli", documents=tuple(args.document or ())
            )
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


async def cmd_voice(args, settings) -> int:
    from b12.audio.asr import WhisperAsr
    from b12.audio.capture import MicController, PttCapture, inventory_devices
    from b12.audio.pipeline import VoicePipeline
    from b12.audio.tts import AudioPlayer, PiperTts

    runtime = open_or_fail(settings)
    try:
        owner = require_owner(runtime)
        mic = MicController(runtime.control)
        tts = PiperTts()
        if args.action == "status":
            from b12.audio.aec import PulseAudioWebRtcAec
            from b12.audio.endpoint import SileroVad

            emit_json(
                {
                    "muted": mic.muted,
                    "consent": owner.actor().consent,
                    "uk_tts_ready": tts.uk_model_path.is_file(),
                    "en_tts_ready": tts.en_model_path.is_file(),
                    "vad_backend": SileroVad().backend,
                    "webrtc_aec_supported": PulseAudioWebRtcAec.is_supported(),
                    "devices": inventory_devices(),
                }
            )
            return 0
        if args.action in ("mute", "unmute"):
            emit_json({"muted": mic.set_muted(args.action == "mute")})
            return 0
        if args.action == "say":
            if not args.value.strip():
                emit_json({"error": "text_required"})
                return 1
            audio = await asyncio.to_thread(tts.synthesize, args.value, lang=args.lang)
            if args.out:
                Path(args.out).write_bytes(audio.to_wav_bytes())
            if args.play:
                player = AudioPlayer(use_hardware=True)
                await player.play(audio)
            emit_json(
                {
                    "language": audio.language,
                    "sample_rate": audio.sample_rate,
                    "duration_s": audio.duration_s,
                    "ttfa_ms": audio.ttfa_ms,
                    "output_file": args.out,
                }
            )
            return 0
        if args.action == "live":
            from b12.audio.duplex import DuplexSession
            from b12.audio.live import LiveMic, LiveSession

            duplex = DuplexSession(
                runtime,
                session_id=owner.session_id,
                actor_id=owner.actor_id,
                use_hardware_audio=True,
            )
            stop = asyncio.Event()
            loop = asyncio.get_running_loop()
            for sig in (signal.SIGINT, signal.SIGTERM):
                loop.add_signal_handler(sig, stop.set)
            session = LiveSession(
                duplex,
                LiveMic(mic),
                on_event=lambda event: print(json.dumps(event, ensure_ascii=False), flush=True),
            )
            try:
                stats = await session.run(stop)
            except PermissionError:
                emit_json({"error": "microphone_muted"})
                return 1
            finally:
                duplex.close()
                for sig in (signal.SIGINT, signal.SIGTERM):
                    loop.remove_signal_handler(sig)
            emit_json(stats)
            return 0
        if args.action == "listen":
            try:
                if args.file:
                    raw = Path(args.file).read_bytes()
                    audio_16k = WhisperAsr.to_float32_16k(raw)
                else:
                    audio_16k = await PttCapture(mic).record_hardware(duration_s=args.duration)
            except PermissionError:
                emit_json({"error": "microphone_muted"})
                return 1
            if args.chat:
                pipe = VoicePipeline(runtime, tts=tts)
                live_player = AudioPlayer(use_hardware=True) if args.play else None
                res = await pipe.process_utterance(
                    session_id=owner.session_id,
                    actor_id=owner.actor_id,
                    audio_16k=audio_16k,
                    language=args.lang,
                    player=live_player,
                )
                emit_json(
                    {
                        "state": res.state,
                        "transcript": res.transcript.text,
                        "language": res.transcript.language,
                        "reply": res.reply_text,
                        "metrics": {
                            "physical_eou_to_endpoint_ms": res.metrics.physical_eou_to_endpoint_ms,
                            "endpoint_to_asr_ms": res.metrics.endpoint_to_asr_ms,
                            "asr_to_first_token_ms": res.metrics.asr_to_first_token_ms,
                            "first_token_to_first_meaningful_audio_ms": (
                                res.metrics.first_token_to_first_meaningful_audio_ms
                            ),
                            "endpoint_to_first_meaningful_audio_ms": (
                                res.metrics.endpoint_to_first_meaningful_audio_ms
                            ),
                            "physical_eou_to_first_meaningful_audio_ms": (
                                res.metrics.physical_eou_to_first_meaningful_audio_ms
                            ),
                            "total_turn_ms": res.metrics.total_turn_ms,
                        },
                    }
                )
                return 0
            asr = WhisperAsr()
            tr = await asyncio.to_thread(asr.transcribe, audio_16k, language=args.lang)
            emit_json(
                {
                    "text": tr.text,
                    "language": tr.language,
                    "language_probability": tr.language_probability,
                    "duration_s": tr.duration_s,
                    "asr_latency_ms": tr.asr_latency_ms,
                    "provenance_id": tr.provenance_id,
                }
            )
            return 0
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


async def cmd_tui(args, settings) -> int:
    """Start the terminal UI on the owner's running API (the token file is the owner's)."""
    from b12.tui.app import B12App
    from b12.tui.client import ApiClient

    token_file = settings.state_dir / "api" / "owner.token"
    if not token_file.exists():
        emit_json({"error": "owner_token_missing", "hint": "start `b12 serve` once"})
        return 1
    import httpx

    try:
        httpx.get(f"{args.url}/api/health", timeout=3).raise_for_status()
    except httpx.HTTPError:
        emit_json({"error": "server_unavailable", "url": args.url, "hint": "run `b12 serve` first"})
        return 1
    client = ApiClient(args.url, token_file.read_text().strip())
    try:
        # Already inside asyncio.run(main): the app must run on this loop (run_async).
        await B12App(
            client, persist_default=args.persist, state_dir=settings.state_dir
        ).run_async()
    finally:
        await client.close()
    return 0


async def cmd_tui_hook(args, settings) -> int:
    """Best-effort metadata only: silent success must never change a provider decision."""
    import select
    import time

    from b12.tui.activity import ActivityStore
    from b12.tui.hook import MAX_INPUT_BYTES

    try:
        # One bounded JSON object on a pipe; do not wait indefinitely for a broken hook.
        deadline = time.monotonic() + 0.5
        fd = sys.stdin.fileno()
        data = bytearray()
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0 or not select.select([fd], [], [], remaining)[0]:
                return 0
            chunk = os.read(fd, min(8192, MAX_INPUT_BYTES + 1 - len(data)))
            if not chunk:
                break
            data.extend(chunk)
            if len(data) > MAX_INPUT_BYTES:
                return 0
        payload = json.loads(data)
        if isinstance(payload, dict):
            ActivityStore(settings.state_dir).append(args.source, payload)
    except (OSError, ValueError, TypeError, RecursionError):
        pass
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
    chat.add_argument(
        "--persist", action="store_true", help="не зупинятися: до 150 кроків і авто-продовження"
    )
    resume = sub.add_parser("resume", help="продовжити turn після approval")
    resume.add_argument("turn_id")
    resume.add_argument("--json", action="store_true")
    for name in ("approve", "deny"):
        sub.add_parser(name).add_argument("operation_id")
    sub.add_parser("approvals", help="черга approval")
    memory = sub.add_parser("memory", help="пам’ять власника")
    memory.add_argument("action", choices=("remember", "search", "forget", "pending"))
    memory.add_argument("value", nargs="?", default="")
    memory.add_argument(
        "--document",
        action="append",
        default=[],
        help="evidence_id з knowledge search; спогад застаріє, якщо документ зміниться",
    )
    knowledge = sub.add_parser("knowledge", help="документи власника для пошуку й доказів")
    knowledge.add_argument("action", choices=("index", "remove", "search"))
    knowledge.add_argument("value")
    session = sub.add_parser("session", help="робоча історія CLI")
    session.add_argument("action", choices=("clear",))
    sub.add_parser("tools", help="каталог інструментів")
    tui = sub.add_parser("tui", help="термінальний інтерфейс (Textual) до локального API")
    tui.add_argument("--url", default="http://127.0.0.1:8712")
    tui.add_argument("--persist", action="store_true", help="початково ввімкнути «Не зупинятися»")
    hook = sub.add_parser("tui-hook", help="локальні metadata lifecycle hooks без provider decisions")
    hook.add_argument("--source", required=True, choices=("claude-code", "codex", "antigravity"))
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
    voice = sub.add_parser("voice", help="локальний голосовий шар (PTT, ASR, TTS)")
    voice.add_argument("action", choices=("status", "mute", "unmute", "say", "listen", "live"))
    voice.add_argument("value", nargs="?", default="")
    voice.add_argument("--lang", choices=("auto", "uk", "en"), default="auto")
    voice.add_argument("--out", help="записати синтезований WAV у файл")
    voice.add_argument("--file", help="прочитати WAV/PCM файл замість мікрофона")
    voice.add_argument("--duration", type=float, default=5.0, help="тривалість PTT запису (с)")
    voice.add_argument("--chat", action="store_true", help="виконати повний turn моделі й TTS")
    voice.add_argument("--play", action="store_true", help="відтворити аудіо через динамік")
    return root


# Commands without the runtime lock: serve takes it itself; tui uses the API;
# tui-hook writes only the independent local UI metadata spool.
SERVER_OWNED = frozenset({"serve", "tui", "tui-hook"})
EXIT_SERVER_UNAVAILABLE = 4
EXIT_REQUIRES_STOPPED_SERVER = 5


def _try_state_lock(settings):
    """The runtime lock, or None when a running B-12 (serve or restore) already holds it."""
    from b12.service import RuntimeLock

    settings.state_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    try:
        return RuntimeLock(settings.state_dir)
    except RuntimeError:
        return None


def _remote_command(args, session_id: str = "") -> tuple[str, str, dict | None, str] | None:
    """(method, path, json body, how to read the answer) for a command the API serves.

    `how` is "json" for a plain answer, "turn" for a streaming turn, or "approve"/"deny" for
    approvals. None means the API has no equivalent yet.
    """
    cmd = args.command
    if cmd == "status":
        return ("GET", "/api/status", None, "json")
    if cmd == "tools":
        return ("GET", "/api/tools", None, "json")
    if cmd == "approvals":
        return ("GET", "/api/approvals", None, "json")
    if cmd in ("approve", "deny"):
        return (
            "POST",
            f"/api/approvals/{args.operation_id}",
            {"approve": cmd == "approve"},
            "json",
        )
    if cmd == "knowledge":
        if args.action == "index":
            return ("POST", "/api/knowledge/index", {"path": args.value}, "json")
        if args.action == "remove":
            return ("POST", "/api/knowledge/remove", {"path": args.value}, "json")
        return ("GET", "/api/knowledge/search", {"q": args.value}, "json")
    if cmd == "memory":
        if args.action == "remember":
            body = {"text": args.value, "documents": list(args.document or [])}
            return ("POST", "/api/memory", body, "json")
        if args.action == "search":
            return ("GET", "/api/memory", {"q": args.value}, "json")
        if args.action == "forget":
            return ("DELETE", f"/api/memory/{args.value}", None, "json")
        return None  # `memory pending` has no API endpoint yet
    if cmd == "goals":
        if args.action == "list":
            return ("GET", "/api/goals", None, "json")
        if args.action in ("pause", "resume", "abandon"):
            status = {"pause": "paused", "resume": "active", "abandon": "abandoned"}[args.action]
            return ("POST", f"/api/goals/{args.value}/status", {"status": status}, "json")
        return None  # `goals add` maps to GoalBody with an owner-capability default; not yet
    if cmd in ("quiet", "stop"):
        key = "quiet" if cmd == "quiet" else "stopped"
        return ("POST", "/api/attention", {key: args.value == "on"}, "json")
    if cmd == "backup":
        if args.action == "create":
            return ("POST", "/api/backups", None, "json")
        if args.action == "list":
            return ("GET", "/api/backups", None, "json")
        return None  # verify, restore and delete are not on the API yet
    if cmd == "voice":
        if args.action == "status":
            return ("GET", "/api/voice/status", None, "json")
        if args.action in ("mute", "unmute"):
            return ("POST", "/api/voice/mute", {"muted": args.action == "mute"}, "json")
        return None
    if cmd == "chat" and args.message is not None:
        body = {
            "session_id": session_id,
            "text": args.message,
            "timeout_s": args.timeout,
            "persist": args.persist,
        }
        return ("POST", "/api/chat", body, "turn")
    if cmd == "resume":
        return ("POST", f"/api/turns/{args.turn_id}/resume", None, "turn")
    return None


def run_remote(args, settings) -> int:
    """Answer the command through the running server's API; never open the databases directly."""
    from b12.cli_remote import (
        RemoteClient,
        RemoteError,
        ServerUnavailable,
        api_url,
        read_owner_token,
    )

    try:
        client = RemoteClient(api_url(), read_owner_token(settings.state_dir))
    except ServerUnavailable as exc:
        emit_json({"error": "server_unavailable", "detail": str(exc)})
        return EXIT_SERVER_UNAVAILABLE
    try:
        session_id = ""
        if args.command == "chat" and args.message is not None:
            session_id = client.call("GET", "/api/cli-session")["session_id"] or ""
        plan = _remote_command(args, session_id)
        if plan is None:
            emit_json(
                {
                    "error": "requires_stopped_server",
                    "command": args.command,
                    "detail": "ця команда ще не має API; зупиніть b12 serve або дочекайтесь API",
                }
            )
            return EXIT_REQUIRES_STOPPED_SERVER
        method, path, body, how = plan
        if how == "turn":
            result = client.stream_result(method, path, json_body=body)
            if getattr(args, "json", False):
                emit_json(result)
            else:
                print(result.get("content", ""))
            return 0 if result.get("state") == "completed" else 1
        if method == "GET":
            emit_json(client.call(method, path, params=body))
        else:
            emit_json(client.call(method, path, json=body))
        return 0
    except ServerUnavailable as exc:
        emit_json({"error": "server_unavailable", "detail": str(exc)})
        return EXIT_SERVER_UNAVAILABLE
    except RemoteError as exc:
        emit_json({"error": exc.code})
        return 1
    finally:
        client.close()


def _is_tui_hook(argv: list[str]) -> bool:
    """Identify the command, without confusing config paths or chat text with it."""
    skip_config_value = False
    for value in argv:
        if skip_config_value:
            skip_config_value = False
            continue
        option = value.split("=", 1)[0]
        # Match argparse's existing long-option abbreviation support as well.
        if option.startswith("--") and "--config".startswith(option):
            skip_config_value = "=" not in value
            continue
        if value.startswith("-"):
            continue
        return value == "tui-hook"
    return False


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    # `b12 mcp add NAME --capability C -- server argv...`: everything after -- is the argv.
    server_argv = argv[argv.index("--") + 1 :] if "--" in argv else []
    argv = argv[: argv.index("--")] if "--" in argv else argv
    if _is_tui_hook(argv):
        # argparse normally prints and exits before reaching the hook handler.
        # A misconfigured telemetry hook must also remain silent and successful.
        import io
        from contextlib import redirect_stderr, redirect_stdout

        with redirect_stderr(io.StringIO()), redirect_stdout(io.StringIO()):
            try:
                args = parser().parse_args(argv)
            except SystemExit:
                return 0
    else:
        args = parser().parse_args(argv)
    args.server_argv = server_argv
    try:
        settings = load_settings(args.config)
    except (ValueError, OSError, tomllib.TOMLDecodeError) as exc:
        if args.command == "tui-hook":
            return 0
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
        "knowledge": cmd_knowledge,
        "session": cmd_session_clear,
        "tools": cmd_tools,
        "serve": cmd_serve,
        "tui": cmd_tui,
        "tui-hook": cmd_tui_hook,
        "goals": cmd_goals,
        "quiet": cmd_flag,
        "stop": cmd_flag,
        "autonomy": cmd_autonomy,
        "backup": cmd_backup,
        "mcp": cmd_mcp,
        "status": cmd_status,
        "voice": cmd_voice,
    }
    lock = None
    if args.command not in SERVER_OWNED:
        lock = _try_state_lock(settings)
        if lock is None:
            return run_remote(args, settings)
    try:
        return asyncio.run(handlers[args.command](args, settings))
    except SystemExit as exc:
        return int(exc.code or 0)
    finally:
        if lock is not None:
            lock.release()


if __name__ == "__main__":
    sys.exit(main())
