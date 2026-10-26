"""B-12 software soak: real runtime, stand-in model with downtime, kills and verification.

  python scripts/soak.py drive --out /abs/run --hours 8
The driver owns a worker subprocess, interrupts it (SIGTERM or SIGKILL) at random
intervals, restarts it, and runs an independent verification after every stop:
SQLite integrity, canary recall, forgotten markers absent from every state byte,
no orphan tool children. All effects stay inside <out>/sandbox. Duration is reported
from wall-clock checkpoints only; an interrupted run is never labelled complete.
"""

import argparse
import asyncio
import hashlib
import json
import os
import random
import signal
import sqlite3
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

SESSIONS = 4
CHILD_MARKER = "b12-soak-child"


def now():
    return datetime.now(UTC).isoformat()


def append(path: Path, record: dict):
    with path.open("a") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")


# --- synthetic model profile (byte-level tokenizer, no download) ---------------------
def ensure_profile(out: Path):
    from tokenizers import Tokenizer, models, pre_tokenizers

    assets = out / "assets"
    profile = out / "profile.json"
    if profile.exists():
        return profile, assets
    assets.mkdir(parents=True, exist_ok=True)
    alphabet = sorted(pre_tokenizers.ByteLevel.alphabet())
    tokenizer = Tokenizer(models.BPE({c: i for i, c in enumerate(alphabet)}, []))
    tokenizer.pre_tokenizer = pre_tokenizers.ByteLevel(add_prefix_space=False, use_regex=False)
    tokenizer.save(str(assets / "tokenizer.json"))
    (assets / "tokenizer_config.json").write_text('{"bos_token":"","eos_token":""}')
    (assets / "chat_template.jinja").write_text(
        "{% for m in messages %}{{m.role}}:{{m.content}}"
        "{{m.tool_calls | default([]) | tojson}};{% endfor %}{{tools | tojson}}assistant:"
    )
    spec = {
        "renderer": "hf-jinja-v1",
        "revision": "soak-v1",
        "model": "soak-model",
        "server_version": "soak-1",
        "manifest_digest": "b" * 64,
        "native_template_sha256": hashlib.sha256(b"{{ .Prompt }}").hexdigest(),
        "files": {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in assets.iterdir()},
        "safety_tokens": 8,
        "inline_reasoning": [],
    }
    profile.write_text(json.dumps(spec))
    return profile, assets


# --- stand-in Ollama with programmable downtime ---------------------------------------
class StandIn:
    def __init__(self, settings):
        from b12.model_profile import ModelProfile

        self.profile = ModelProfile(settings)
        self.down_until = 0.0
        self.requests = 0

    def reply(self, body):
        messages = body["messages"]
        last = messages[-1]
        if last["role"] == "tool":
            return {"content": "Готово: " + last["content"][:80]}
        text = last["content"]
        command, _, rest = text.partition(" ")
        if command == "WRITE":
            path, _, payload = rest.partition(" ")
            return {"calls": [("file_write", {"path": path, "text": payload, "overwrite": True})]}
        if command == "READ":
            return {"calls": [("file_read", {"path": rest})]}
        if command == "REMEMBER":
            return {"calls": [("memory_store", {"text": rest})]}
        if command == "SEARCH":
            return {"calls": [("memory_search", {"query": rest})]}
        if command == "SHELL":
            return {
                "calls": [
                    (
                        "shell_exec",
                        {
                            "executable": sys.executable,
                            "argv": ["-c", f"import time;time.sleep(0.2);print('{CHILD_MARKER}')"],
                            "cwd": rest,
                            "declared_effects": ["short child process"],
                        },
                    )
                ]
            }
        return {"content": "Відповідь: " + text[:200]}

    async def handle(self, reader, writer):
        try:
            header = await reader.readuntil(b"\r\n\r\n")
            path = header.split(b" ")[1].decode()
            length = next(
                (
                    int(line.split(b":")[1])
                    for line in header.split(b"\r\n")
                    if line.lower().startswith(b"content-length:")
                ),
                0,
            )
            body = json.loads(await reader.readexactly(length)) if length else {}

            def respond(status, payload):
                data = json.dumps(payload).encode()
                writer.write(
                    f"HTTP/1.1 {status} X\r\nContent-Length: {len(data)}\r\n"
                    "Connection: close\r\n\r\n".encode()
                    + data
                )

            if time.monotonic() < self.down_until:
                respond(503, {"error": "injected downtime"})
            elif path.endswith("/api/version"):
                respond(200, {"version": "soak-1"})
            elif path.endswith("/api/tags"):
                respond(200, {"models": [{"name": "soak-model", "digest": "b" * 64}]})
            elif path.endswith("/api/show"):
                respond(200, {"template": "{{ .Prompt }}"})
            elif path.endswith("/api/ps"):
                respond(200, {"models": []})
            elif path.endswith("/api/generate"):
                respond(200, {"done_reason": "unload"})
            elif path.endswith("/api/chat"):
                self.requests += 1
                step = self.reply(body)
                writer.write(b"HTTP/1.1 200 OK\r\nConnection: close\r\n\r\n")
                message = {"role": "assistant", "content": step.get("content", "")}
                if step.get("calls"):
                    message["tool_calls"] = [
                        {"function": {"name": n, "arguments": a}} for n, a in step["calls"]
                    ]
                writer.write(json.dumps({"message": message, "done": False}).encode() + b"\n")
                count = self.profile.count(body["messages"], body.get("tools", []))
                final = {
                    "message": {"role": "assistant", "content": ""},
                    "done": True,
                    "done_reason": "stop",
                    "prompt_eval_count": count,
                    "eval_count": 3,
                }
                writer.write(json.dumps(final).encode() + b"\n")
            await writer.drain()
        except (ConnectionError, asyncio.IncompleteReadError):
            pass
        finally:
            writer.close()


# --- worker -----------------------------------------------------------------------
def settings_for(out: Path, url: str):
    from b12.config import Settings

    profile, assets = ensure_profile(out)
    return Settings(
        state_dir=out / "state",
        model="soak-model",
        model_profile=profile,
        tokenizer_dir=assets,
        ollama_url=url,
        num_ctx=65536,
        output_tokens=512,
        model_timeout_s=30,
        quiet_start="00:00",
        quiet_end="00:00",
    )


def owner_identity(runtime, out: Path):
    control = runtime.control
    actor_id = control.get_meta("owner_actor")
    if actor_id is None:
        actor_id = control.create_actor(owner=True, consent=True).id
        control.set_meta("owner_actor", actor_id)
        for index in range(SESSIONS):
            control.set_meta(f"soak_session_{index}", control.create_session(actor_id))
    sessions = [control.get_meta(f"soak_session_{i}") for i in range(SESSIONS)]
    return control.resolve_actor(actor_id), sessions


def canaries(runtime, actor, out: Path) -> dict:
    path = out / "canaries.json"
    if path.exists():
        return json.loads(path.read_text())
    data = {
        "live": [
            runtime.memory.remember(f"Канарка {i}: стабільний факт КАНАРКА{i}ЖИВА", actor).id
            for i in range(5)
        ],
        "forgotten": [],
    }
    path.write_text(json.dumps(data))
    return data


async def worker(out: Path):
    from b12.auth import HOST_CAPABILITIES
    from b12.runtime import open_runtime

    standin = None
    server = None
    # Model server first, then runtime against it.
    probe = settings_for(out, "http://127.0.0.1:9")
    standin = StandIn(probe)
    server = await asyncio.start_server(standin.handle, "127.0.0.1", 0)
    url = f"http://127.0.0.1:{server.sockets[0].getsockname()[1]}"
    settings = settings_for(out, url)
    runtime = open_runtime(settings)
    await runtime.purge.resume()
    actor, sessions = owner_identity(runtime, out)
    marks = canaries(runtime, actor, out)
    sandbox = out / "sandbox"
    sandbox.mkdir(exist_ok=True)
    stats = {"turns": 0, "by_state": {}, "errors": {}, "latency": [], "forgets": 0}
    metrics = out / "metrics.jsonl"
    append(out / "events.jsonl", {"at": now(), "event": "worker_started", "pid": os.getpid()})

    async def session_loop(index, session):
        rng = random.Random(index * 7919 + int(time.time()))
        big = sandbox / f"big-{index}.txt"
        big.write_text("рядок довгого виводу\n" * 4000)
        while True:
            choice = rng.random()
            target = sandbox / f"s{index}-{rng.randrange(20)}.txt"
            if choice < 0.25:
                text = f"WRITE {target} вміст {rng.randrange(10**6)}"
            elif choice < 0.4:
                text = f"READ {big}"
            elif choice < 0.55:
                text = f"REMEMBER спостереження сесії {index} номер {rng.randrange(10**6)}"
            elif choice < 0.7:
                text = f"SEARCH спостереження {rng.randrange(10)}"
            elif choice < 0.78:
                text = f"SHELL {sandbox}"
            else:
                text = f"Привіт, як справи? {rng.randrange(1000)}"
            task = runtime.control.create_task(session)
            grant = runtime.control.issue_grant(
                actor.id,
                session,
                HOST_CAPABILITIES["full"],
                task_id=task,
                ttl_s=600,
                full_execution=True,
            )
            started = time.monotonic()
            result = await runtime.agent.turn(session, grant, text, task_id=task, timeout_s=60)
            stats["turns"] += 1
            stats["by_state"][result.state] = stats["by_state"].get(result.state, 0) + 1
            if result.error_code:
                stats["errors"][result.error_code] = stats["errors"].get(result.error_code, 0) + 1
            stats["latency"].append((time.monotonic() - started) * 1000)
            await asyncio.sleep(rng.uniform(0.2, 1.5))

    async def growth_loop():
        index = 0
        while True:
            for _ in range(50):
                runtime.memory.remember(f"фонове зростання запис {index} тема {index % 97}", actor)
                index += 1
            await asyncio.sleep(60)

    async def forget_loop():
        rng = random.Random()
        while True:
            await asyncio.sleep(90)
            pool = [r.id for r in runtime.memory.search("зростання", actor, limit=50)]
            if pool:
                await runtime.purge.forget(rng.choice(pool), actor.id)
                stats["forgets"] += 1
            if len(marks["forgotten"]) < 200 and rng.random() < 0.34:
                marker = f"ЗАБУТО{len(marks['forgotten'])}ЩЬЯ"
                record = runtime.memory.remember(f"тимчасовий секрет {marker}", actor)
                runtime.memory.search("тимчасовий секрет", actor)
                receipt = await runtime.purge.forget(record.id, actor.id)
                marks["forgotten"].append(
                    {"id": record.id, "marker": marker, "state": receipt.state}
                )
                (out / "canaries.json").write_text(json.dumps(marks))

    async def snapshot_loop():
        while True:
            await asyncio.sleep(1800)
            runtime.operations.create_snapshot(kind="soak")
            for old in runtime.operations.inventory()[:-2]:
                runtime.operations.delete_snapshot(old["id"])

    async def downtime_loop():
        while True:
            await asyncio.sleep(1200)
            standin.down_until = time.monotonic() + 60
            append(out / "events.jsonl", {"at": now(), "event": "model_downtime", "seconds": 60})

    async def metrics_loop():
        while True:
            await asyncio.sleep(60)
            latency = sorted(stats["latency"][-2000:])
            fds = len(os.listdir("/proc/self/fd"))
            rss = int(
                next(
                    line.split()[1]
                    for line in Path("/proc/self/status").read_text().splitlines()
                    if line.startswith("VmRSS:")
                )
            )
            append(
                metrics,
                {
                    "at": now(),
                    "pid": os.getpid(),
                    "turns": stats["turns"],
                    "by_state": stats["by_state"],
                    "errors": stats["errors"],
                    "forgets": stats["forgets"],
                    "p50_ms": latency[len(latency) // 2] if latency else None,
                    "p95_ms": latency[int(len(latency) * 0.95)] if latency else None,
                    "rss_kb": rss,
                    "fds": fds,
                    "active_turns": len(runtime.agent.active),
                    "model_requests": standin.requests,
                    "state_bytes": sum(
                        p.stat().st_size for p in settings.state_dir.rglob("*") if p.is_file()
                    ),
                },
            )
            stats["latency"] = stats["latency"][-2000:]

    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    loop.add_signal_handler(signal.SIGTERM, stop.set)
    tasks = [asyncio.create_task(session_loop(i, s)) for i, s in enumerate(sessions)]
    tasks += [
        asyncio.create_task(f())
        for f in (growth_loop, forget_loop, snapshot_loop, downtime_loop, metrics_loop)
    ]
    await stop.wait()
    for turn_id in list(runtime.agent.active):
        runtime.agent.active[turn_id].cancel.set()
    for task in tasks:
        task.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)
    runtime.close()
    server.close()
    append(out / "events.jsonl", {"at": now(), "event": "worker_stopped_gracefully"})


# --- independent verification -----------------------------------------------------
def verify(out: Path) -> dict:
    from b12.runtime import open_runtime

    report = {"at": now(), "integrity": {}, "problems": []}
    state = out / "state"
    for path in state.rglob("*.sqlite3"):
        connection = sqlite3.connect(path)
        try:
            result = connection.execute("PRAGMA integrity_check").fetchone()[0]
        finally:
            connection.close()
        if result != "ok":
            report["problems"].append(f"integrity:{path.relative_to(out)}")
    orphans = subprocess.run(["pgrep", "-f", CHILD_MARKER], capture_output=True, text=True)
    if orphans.stdout.strip():
        report["problems"].append(f"orphans:{orphans.stdout.split()}")
    runtime = open_runtime(settings_for(out, "http://127.0.0.1:9"))
    try:
        actor_id = runtime.control.get_meta("owner_actor")
        if actor_id:
            actor = runtime.control.resolve_actor(actor_id)
            marks = json.loads((out / "canaries.json").read_text())
            missing = [m for m in marks["live"] if not runtime.memory.is_live(m, actor)]
            if missing:
                report["problems"].append(f"canary_lost:{missing}")
            started_purges = runtime.memory.pending_purges(actor)
            report["pending_purges"] = [r.pending_stores for r in started_purges]
            report["memories_live_sample"] = len(
                runtime.memory.search("зростання", actor, limit=1000)
            )
            report["forgotten_checked"] = len(marks["forgotten"])
    finally:
        runtime.close()
    blob_markers = (
        [m["marker"].encode() for m in json.loads((out / "canaries.json").read_text())["forgotten"]]
        if (out / "canaries.json").exists()
        else []
    )
    for path in state.rglob("*"):
        if path.is_file():
            data = path.read_bytes()
            leaked = [m.decode() for m in blob_markers if m in data]
            if leaked:
                report["problems"].append(f"forgotten_payload:{path.relative_to(out)}:{leaked[:3]}")
    report["ok"] = not report["problems"]
    return report


def drive(out: Path, hours: float, seed: int):
    out.mkdir(parents=True, exist_ok=True)
    rng = random.Random(seed)
    begin = time.monotonic()
    deadline = begin + hours * 3600
    events = out / "events.jsonl"
    append(events, {"at": now(), "event": "soak_started", "hours": hours, "seed": seed})
    cycles = 0
    while time.monotonic() < deadline:
        log = (out / "worker.log").open("a")
        process = subprocess.Popen(
            [sys.executable, __file__, "worker", "--out", str(out)], stdout=log, stderr=log
        )
        run_for = min(rng.uniform(900, 2700), max(5, deadline - time.monotonic()))
        try:
            process.wait(timeout=run_for)
            append(events, {"at": now(), "event": "worker_exited", "code": process.returncode})
        except subprocess.TimeoutExpired:
            mode = "SIGKILL" if cycles % 2 else "SIGTERM"
            process.send_signal(signal.SIGKILL if mode == "SIGKILL" else signal.SIGTERM)
            try:
                process.wait(timeout=60)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
                mode += "+forced"
            append(events, {"at": now(), "event": "worker_stopped", "mode": mode})
        log.close()
        time.sleep(2)
        report = verify(out)
        append(out / "verify.jsonl", report)
        cycles += 1
    elapsed = time.monotonic() - begin
    append(
        events,
        {"at": now(), "event": "soak_finished", "elapsed_h": elapsed / 3600, "cycles": cycles},
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("drive", "worker", "verify"))
    parser.add_argument("--out", required=True)
    parser.add_argument("--hours", type=float, default=8.0)
    parser.add_argument("--seed", type=int, default=12)
    args = parser.parse_args()
    out = Path(args.out).absolute()
    if args.mode == "drive":
        drive(out, args.hours, args.seed)
    elif args.mode == "worker":
        asyncio.run(worker(out))
    else:
        print(json.dumps(verify(out), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
