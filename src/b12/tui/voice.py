"""Explicit, bounded TUI audio processes; audio exists only in memory.

The caller checks the server's mute state before recording. Construction performs
no device access, and these helpers never change mute or memory consent.
"""

import asyncio
import io
import shutil
import wave
from dataclasses import dataclass

SAMPLE_RATE = 16_000
MAX_RECORD_SECONDS = 12.0
MAX_PCM_BYTES = int(SAMPLE_RATE * 2 * MAX_RECORD_SECONDS)
MAX_WAV_BYTES = 32 * 1024 * 1024
MAX_PLAY_SECONDS = 300.0


class VoiceError(RuntimeError):
    """A stable code suitable for display, without subprocess/device details."""

    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


async def _terminate(process: asyncio.subprocess.Process) -> None:
    """Stop only this child PID, escalating to kill after a short grace period."""
    if process.returncode is not None:
        await process.wait()
        return
    try:
        process.terminate()
    except ProcessLookupError:
        pass
    except OSError:
        raise VoiceError("audio_stop_failed") from None
    try:
        await asyncio.wait_for(process.wait(), timeout=0.35)
    except TimeoutError:
        try:
            process.kill()
        except ProcessLookupError:
            pass
        except OSError:
            raise VoiceError("audio_stop_failed") from None
        try:
            await asyncio.wait_for(process.wait(), timeout=0.65)
        except TimeoutError:
            raise VoiceError("audio_stop_timeout") from None


class PttRecorder:
    """Capture 16 kHz mono s16 PCM after start(), for at most twelve seconds.

    start() returns once the child is created. stop() ends capture and consumes its
    result, including after the automatic deadline. cancel() stops and discards it.
    A finished recording remains bounded in memory until stop() or cancel().
    """

    def __init__(self):
        self._lock = asyncio.Lock()
        self._task: asyncio.Task[bytes] | None = None
        self._stop = asyncio.Event()

    @property
    def recording(self) -> bool:
        return self._task is not None and not self._task.done()

    @property
    def has_recording(self) -> bool:
        """Whether there is a live capture or a completed result to consume."""
        return self._task is not None

    async def start(self) -> None:
        async with self._lock:
            if self._task is not None:
                raise VoiceError("audio_capture_busy")
            if command := shutil.which("pw-record"):
                argv = [
                    command,
                    "--format",
                    "s16",
                    "--rate",
                    str(SAMPLE_RATE),
                    "--channels",
                    "1",
                    "-",
                ]
            elif command := shutil.which("arecord"):
                argv = [
                    command,
                    "-q",
                    "-N",
                    "-f",
                    "S16_LE",
                    "-r",
                    str(SAMPLE_RATE),
                    "-c",
                    "1",
                    "-t",
                    "raw",
                    "-d",
                    "12",
                    "-",
                ]
            else:
                raise VoiceError("audio_capture_unavailable")
            try:
                process = await asyncio.create_subprocess_exec(
                    *argv,
                    stdin=asyncio.subprocess.DEVNULL,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.DEVNULL,
                    limit=8192,
                )
            except OSError:
                raise VoiceError("audio_capture_failed") from None
            self._stop = asyncio.Event()
            deadline = asyncio.get_running_loop().time() + MAX_RECORD_SECONDS
            self._task = asyncio.create_task(self._capture(process, self._stop, deadline))

    async def _capture(
        self, process: asyncio.subprocess.Process, stop: asyncio.Event, deadline: float
    ) -> bytes:
        raw = bytearray()
        try:
            assert process.stdout is not None
            while len(raw) < MAX_PCM_BYTES and not stop.is_set():
                remaining = deadline - asyncio.get_running_loop().time()
                if remaining <= 0:
                    break
                try:
                    chunk = await asyncio.wait_for(
                        process.stdout.read(min(4096, MAX_PCM_BYTES - len(raw))),
                        timeout=min(0.1, remaining),
                    )
                except TimeoutError:
                    continue
                if not chunk:
                    try:
                        returncode = await asyncio.wait_for(process.wait(), timeout=0.2)
                    except TimeoutError:
                        raise VoiceError("audio_capture_failed") from None
                    if returncode:
                        raise VoiceError("audio_capture_failed")
                    break
                raw.extend(chunk)
            even = len(raw) - len(raw) % 2
            if not even:
                raise VoiceError("audio_capture_empty")
            return bytes(raw[:even])
        except OSError:
            raise VoiceError("audio_capture_failed") from None
        finally:
            raw.clear()
            await _terminate(process)

    async def stop(self) -> bytes:
        async with self._lock:
            task = self._task
            if task is None:
                return b""
            self._stop.set()
            try:
                return await task
            finally:
                self._task = None

    async def cancel(self) -> None:
        """Stop capture and discard its PCM, including a completed pending result."""
        try:
            await self.stop()
        except VoiceError as exc:
            if exc.code not in ("audio_capture_empty", "audio_capture_failed"):
                raise


@dataclass
class _Playback:
    process: asyncio.subprocess.Process
    stopped: bool = False


class VoicePlayer:
    """Play an in-memory PCM WAV; stop() interrupts only the owned child process."""

    def __init__(self):
        self._lock = asyncio.Lock()
        self._playback: _Playback | None = None
        self._generation = 0

    @property
    def playing(self) -> bool:
        state = self._playback
        return state is not None and not state.stopped and state.process.returncode is None

    @staticmethod
    def _decode(wav_bytes: bytes) -> tuple[bytes, int, int, float]:
        if not isinstance(wav_bytes, bytes) or not 44 <= len(wav_bytes) <= MAX_WAV_BYTES:
            raise VoiceError("invalid_wav_audio")
        try:
            with wave.open(io.BytesIO(wav_bytes), "rb") as source:
                channels, rate = source.getnchannels(), source.getframerate()
                frames, width = source.getnframes(), source.getsampwidth()
                duration = frames / rate if rate else 0
                if (
                    source.getcomptype() != "NONE"
                    or width != 2
                    or channels not in (1, 2)
                    or not 8000 <= rate <= 48000
                    or not 0 < duration <= MAX_PLAY_SECONDS
                    or frames * channels * width > MAX_WAV_BYTES
                ):
                    raise VoiceError("invalid_wav_audio")
                pcm = source.readframes(frames)
                if len(pcm) != frames * channels * width:
                    raise VoiceError("invalid_wav_audio")
                return pcm, rate, channels, duration
        except (wave.Error, EOFError, OSError, ValueError):
            raise VoiceError("invalid_wav_audio") from None

    async def play(self, wav_bytes: bytes) -> None:
        async with self._lock:
            self._generation += 1
            generation = self._generation
        pcm, rate, channels, duration = await asyncio.to_thread(self._decode, wav_bytes)
        async with self._lock:
            if generation != self._generation:
                return
            if self._playback is not None:
                self._playback.stopped = True
                await _terminate(self._playback.process)
                self._playback = None
            if command := shutil.which("pw-play"):
                # With '-' PipeWire consumes raw PCM, not a WAV container.
                argv = [
                    command,
                    "--format",
                    "s16",
                    "--rate",
                    str(rate),
                    "--channels",
                    str(channels),
                    "-",
                ]
            elif command := shutil.which("aplay"):
                argv = [
                    command,
                    "-q",
                    "-N",
                    "-t",
                    "raw",
                    "-f",
                    "S16_LE",
                    "-r",
                    str(rate),
                    "-c",
                    str(channels),
                    "-",
                ]
            else:
                raise VoiceError("audio_playback_unavailable")
            try:
                process = await asyncio.create_subprocess_exec(
                    *argv,
                    stdin=asyncio.subprocess.PIPE,
                    stdout=asyncio.subprocess.DEVNULL,
                    stderr=asyncio.subprocess.DEVNULL,
                )
            except OSError:
                raise VoiceError("audio_playback_failed") from None
            state = _Playback(process)
            self._playback = state
        try:
            async with asyncio.timeout(duration + 5.0):
                assert process.stdin is not None
                for offset in range(0, len(pcm), 4096):
                    if state.stopped:
                        return
                    process.stdin.write(memoryview(pcm)[offset : offset + 4096])
                    await process.stdin.drain()
                process.stdin.close()
                await process.stdin.wait_closed()
                returncode = await process.wait()
                if returncode and not state.stopped:
                    raise VoiceError("audio_playback_failed")
        except TimeoutError:
            raise VoiceError("audio_playback_timeout") from None
        except OSError:
            if not state.stopped:
                raise VoiceError("audio_playback_failed") from None
        finally:
            try:
                await _terminate(process)
            finally:
                async with self._lock:
                    if self._playback is state:
                        self._playback = None

    async def stop(self) -> None:
        async with self._lock:
            # Invalidate a pending WAV decode as well as active playback.
            self._generation += 1
            if self._playback is not None:
                state = self._playback
                state.stopped = True
                try:
                    await _terminate(state.process)
                finally:
                    if self._playback is state:
                        self._playback = None
