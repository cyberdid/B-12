"""Real argv execution with bounded drains and same-process-group cleanup.

Full execution is arbitrary OS code, not isolation. A program can deliberately
escape its group; this is not a sandbox or a guarantee against detached daemons.
"""

import asyncio
import ctypes
import os
import platform
import shlex
import shutil
import signal
from pathlib import Path
from types import SimpleNamespace

from pydantic import Field, field_validator

from b12.tools._common import AbsolutePath, Args, EmptyArgs, clip, failure
from b12.tools.outcomes import HandlerOutcome, SideEffect
from b12.tools.policy import Risk

_LIBC = ctypes.CDLL(None, use_errno=True)
_PR_SET_PDEATHSIG = 1


def _die_with_parent():
    """Runs in the forked child: SIGKILL it if the B-12 process dies abruptly.

    Covers the direct child only; detached grandchildren remain an OS-level limit.
    """
    _LIBC.prctl(_PR_SET_PDEATHSIG, signal.SIGKILL)


class ProcessListArgs(Args):
    limit: int = Field(default=50, ge=1, le=200)
    pid: int = Field(default=0, ge=0, description="0 lists all processes")


class CommandArgs(Args):
    command: str = Field(
        min_length=1,
        max_length=4096,
        description=(
            "One terminal line, exactly as typed in a shell: pipes, redirects, globs and "
            "&& are allowed, e.g. grep -n 'def ' file.py | head -40"
        ),
    )
    cwd: AbsolutePath = Field(description="Absolute working directory, e.g. /home/cyberdid")
    declared_effects: list[str] = Field(
        min_length=1,
        max_length=16,
        description="What the command does, in words: e.g. read-only search, writes a report file",
    )
    max_output_bytes: int = Field(default=4096, ge=1, le=4096)


class ExecArgs(Args):
    executable: AbsolutePath = Field(
        description="Full path to the program, for example /usr/bin/wc"
    )
    argv: list[str] = Field(
        max_length=128,
        description=(
            "Only the arguments, without the program name: for wc -l FILE use ['-l', 'FILE']"
        ),
    )
    cwd: AbsolutePath = Field(description="Absolute working directory")
    declared_effects: list[str] = Field(
        min_length=1, max_length=16, description="Expected effects, e.g. read-only listing"
    )
    max_output_bytes: int = Field(default=4096, ge=1, le=4096)

    @field_validator("argv", "declared_effects")
    @classmethod
    def _bounded(cls, values):
        if any("\x00" in value or len(value.encode()) > 8192 for value in values):
            raise ValueError("invalid argv/effects")
        if sum(len(value.encode()) for value in values) > 65536:
            raise ValueError("argv/effects limit")
        return values


def _stat(pid):
    fields = Path(f"/proc/{pid}/stat").read_text().rpartition(") ")[2].split()
    return fields[0], int(fields[1]), int(fields[2])


def _live_group(group):
    for entry in os.scandir("/proc"):
        if entry.name.isdigit():
            try:
                state, _, pgid = _stat(entry.name)
                if pgid == group and state not in ("Z", "X"):
                    return True
            except (OSError, ValueError, IndexError):
                continue
    return False


async def system_info(args, guard):
    guard.check()
    return HandlerOutcome(
        content={
            "os": platform.system(),
            "release": platform.release(),
            "machine": platform.machine(),
            "cpu_count": os.cpu_count(),
            "uid": os.geteuid(),
            "memory_bytes": os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES"),
        }
    )


async def process_list(args, guard):
    rows, truncated = [], False
    guard.check()
    with os.scandir("/proc") as iterator:
        names = (
            (str(args.pid),)
            if args.pid
            else (entry.name for entry in iterator if entry.name.isdigit())
        )
        for pid in names:
            guard.check()
            try:
                state, ppid, _ = _stat(pid)
                name, cut = clip(Path("/proc", pid, "comm").read_text().strip(), 64)
            except (OSError, ValueError, IndexError):
                continue
            if len(rows) == args.limit:
                truncated = True
                break
            truncated |= cut
            rows.append({"pid": int(pid), "ppid": ppid, "state": state, "name": name})
            await asyncio.sleep(0)
    return HandlerOutcome(content={"processes": rows}, truncated=truncated)


async def _terminate(proc, drains):
    """Cleanup only: TERM→KILL, bounded waits, close local pipe transports."""
    for sig in (signal.SIGTERM, signal.SIGKILL):
        try:
            os.killpg(proc.pid, sig)
        except ProcessLookupError:
            pass
        except PermissionError:
            break
        try:
            await asyncio.wait_for(
                asyncio.shield(proc.wait()), 0.15 if sig == signal.SIGTERM else 0.5
            )
        except TimeoutError:
            pass
        if not _live_group(proc.pid):
            break
        await asyncio.sleep(0.02)
    try:
        await asyncio.wait_for(asyncio.gather(*drains), 0.3)
    except (TimeoutError, asyncio.CancelledError):
        for task in drains:
            task.cancel()
        await asyncio.gather(*drains, return_exceptions=True)
    confirmed = proc.returncode is not None and not _live_group(proc.pid)
    # CPython subprocess has no public close for StreamReader pipe transports.
    # Close local resources even if arbitrary code detached with inherited pipes.
    proc._transport.close()
    return confirmed


SHELLS = {"sh", "bash", "zsh", "dash"}


def normalize_argv(executable: str, argv: list[str]) -> list[str]:
    """Models repeat the program name in argv or pass a command line to a shell.

    `argv` is only the arguments: a leading copy of the program name is dropped, and a
    shell given plain words gets them as one `-c` command line.
    """
    name = os.path.basename(executable)
    if argv and argv[0] == name:
        argv = argv[1:]
    if name in SHELLS and argv and argv[0] != "-c":
        argv = ["-c", " ".join(shlex.quote(word) for word in argv)]
    return argv


async def shell_exec(args, guard):
    proc = None
    spawn = None
    drains = []
    outputs = [bytearray(), bytearray()]
    cut = [False, False]
    argv = normalize_argv(args.executable, args.argv)

    async def drain(stream, index):
        while chunk := await stream.read(8192):
            remaining = args.max_output_bytes - len(outputs[index])
            outputs[index].extend(chunk[:remaining])
            cut[index] |= len(chunk) > remaining

    def outcome(status="completed", code=None, cleanup=True):
        return HandlerOutcome(
            status=status,
            error_code=code,
            content={
                "pid": proc.pid,
                "exit_code": proc.returncode,
                "command_succeeded": proc.returncode == 0 if status == "completed" else False,
                "stdout": outputs[0].decode("utf-8", "replace"),
                "stderr": outputs[1].decode("utf-8", "replace"),
                "cleanup_confirmed": cleanup,
            },
            truncated=any(cut),
            side_effects=(
                SideEffect(
                    kind="process_execution",
                    state="completed" if status == "completed" else "possible",
                ),
            ),
        )

    try:
        guard.check()
        spawn = asyncio.create_task(
            asyncio.create_subprocess_exec(
                args.executable,
                *argv,
                cwd=args.cwd,
                stdin=asyncio.subprocess.DEVNULL,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                start_new_session=True,
                preexec_fn=_die_with_parent,
                env={"PATH": os.defpath, "LANG": "C.UTF-8"},
            )
        )
        # Preserve ownership of a child even if cancellation races with PID issuance.
        proc = await asyncio.shield(spawn)
        drains = [
            asyncio.create_task(drain(proc.stdout, 0)),
            asyncio.create_task(drain(proc.stderr, 1)),
        ]
        await proc.wait()
        await asyncio.gather(*drains)
        guard.check()
        cleanup = await _terminate(proc, drains) if _live_group(proc.pid) else True
        if not cleanup:
            return outcome("unknown", "cleanup_failed", False)
        proc._transport.close()
        return outcome()
    except asyncio.CancelledError:
        if proc is None and spawn is not None:
            try:
                proc = await spawn
            except OSError:
                raise
        if proc is None:
            raise
        if not drains:
            drains = [
                asyncio.create_task(drain(proc.stdout, 0)),
                asyncio.create_task(drain(proc.stderr, 1)),
            ]
        cleanup = await _terminate(proc, drains)
        return outcome("unknown", "cancelled" if cleanup else "cleanup_failed", cleanup)
    except OSError as exc:
        if proc is None:
            return failure(exc)
        cleanup = await _terminate(proc, drains)
        return outcome("unknown", "process_failed" if cleanup else "cleanup_failed", cleanup)
    except BaseException:
        if proc is not None:
            await _terminate(proc, drains)
        raise


def make_sudo_exec(sudo_path: str | None):
    """sudo_exec: run one exact command through non-interactive sudo (never a password)."""

    async def sudo_exec(args, guard):
        binary = sudo_path or shutil.which("sudo")
        if not binary:
            return failure("not_found")
        derived = ExecArgs(
            executable=binary,
            argv=["-n", "--", args.executable, *args.argv],
            cwd=args.cwd,
            declared_effects=args.declared_effects,
            max_output_bytes=args.max_output_bytes,
        )
        return await shell_exec(derived, guard)

    return sudo_exec


def register_sudo(registry, sudo_path: str | None = None):
    registry.register(
        "sudo_exec",
        "Run one exact absolute command as root via sudo -n; every call needs owner approval",
        ExecArgs,
        make_sudo_exec(sudo_path),
        "process.sudo",
        risk=Risk.DESTRUCTIVE,
    )


async def run_command(args, guard):
    """A full terminal line through /bin/bash -c, with the same bounds and cleanup as shell_exec."""
    as_exec = SimpleNamespace(
        executable="/bin/bash",
        argv=["-c", args.command],
        cwd=args.cwd,
        declared_effects=args.declared_effects,
        max_output_bytes=args.max_output_bytes,
    )
    return await shell_exec(as_exec, guard)


def register(registry):
    registry.register(
        "system_info",
        "Read actual host OS and resource information",
        EmptyArgs,
        system_info,
        "system.read",
    )
    registry.register(
        "process_list",
        "List bounded process identities without argv/environment",
        ProcessListArgs,
        process_list,
        "process.read",
    )
    registry.register(
        "shell_exec",
        "Run a program: executable is its full path (e.g. /usr/bin/wc); argv lists only "
        "its arguments, without the program name (wc -l FILE is executable=/usr/bin/wc, "
        "argv=['-l', 'FILE'])",
        ExecArgs,
        shell_exec,
        "process.execute",
        risk=Risk.ARBITRARY,
    )
    registry.register(
        "run_command",
        "Run one terminal line as a shell would (pipes, redirects, globs allowed); "
        "returns stdout, stderr and the exit code, bounded to 4 KB",
        CommandArgs,
        run_command,
        "process.execute",
        risk=Risk.ARBITRARY,
    )
