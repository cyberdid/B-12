"""Захоплення мікрофона (PTT / stream), окремий контроль mute та інвентаризація аудіопристроїв.

Інваріанти:
- Стан mute (`mic_muted`) зберігається в ControlStore окремо від згоди на пам’ять (`actor.consent`).
- Коли мікрофон вимкнено (`muted=True`), будь-яка спроба захоплення негайно кидає PermissionError.
- Сирий мікрофонний потік за замовчуванням існує виключно в оперативній пам’яті (volatile).
"""

import asyncio
import contextlib
import shutil
import subprocess
from collections.abc import AsyncIterable, Iterable
from typing import Any

import numpy as np


def inventory_devices() -> dict[str, Any]:
    """Перевірити наявні локальні інструменти й аудіопристрої PipeWire / ALSA."""
    tools = {
        name: shutil.which(name) for name in ("pw-record", "pw-play", "wpctl", "arecord", "aplay")
    }
    capture_hw = ""
    playback_hw = ""
    with contextlib.suppress(Exception):
        if tools["arecord"]:
            capture_hw = subprocess.run(
                [tools["arecord"], "-l"],
                capture_output=True,
                text=True,
                timeout=3,
                check=False,
            ).stdout.strip()
        if tools["aplay"]:
            playback_hw = subprocess.run(
                [tools["aplay"], "-l"],
                capture_output=True,
                text=True,
                timeout=3,
                check=False,
            ).stdout.strip()
    return {
        "tools": tools,
        "has_capture": bool(tools["pw-record"] or tools["arecord"]),
        "has_playback": bool(tools["pw-play"] or tools["aplay"]),
        "alsa_capture": capture_hw,
        "alsa_playback": playback_hw,
    }


class MicController:
    """Керування станом мікрофона (mute), відокремлене від згоди на збереження пам’яті."""

    META_KEY = "mic_muted"

    def __init__(self, control):
        self._control = control

    @property
    def muted(self) -> bool:
        return self._control.get_meta(self.META_KEY) == "1"

    def set_muted(self, muted: bool) -> bool:
        self._control.set_meta(self.META_KEY, "1" if muted else "0")
        return self.muted

    def require_unmuted(self) -> None:
        if self.muted:
            raise PermissionError("microphone_muted")


class PttCapture:
    """Захоплення мовлення Push-to-Talk у volatile буфер 16 кГц float32."""

    def __init__(self, mic: MicController, *, sample_rate: int = 16000):
        self.mic = mic
        self.sample_rate = sample_rate

    async def record_from_source(
        self,
        chunks: Iterable[np.ndarray | bytes] | AsyncIterable[np.ndarray | bytes],
        *,
        cancel: asyncio.Event | None = None,
    ) -> np.ndarray:
        """Зібрати чанки у volatile float32 масив; негайно зупинитися при cancel або mute."""
        self.mic.require_unmuted()
        frames: list[np.ndarray] = []

        if isinstance(chunks, AsyncIterable):
            async for chunk in chunks:
                self.mic.require_unmuted()
                frames.append(self._normalize_chunk(chunk))
                if cancel is not None and cancel.is_set():
                    break
        else:
            for chunk in chunks:
                self.mic.require_unmuted()
                frames.append(self._normalize_chunk(chunk))
                if cancel is not None and cancel.is_set():
                    break

        if not frames:
            return np.zeros(0, dtype=np.float32)
        return np.concatenate(frames).astype(np.float32, copy=False)

    async def record_hardware(
        self,
        *,
        duration_s: float = 5.0,
        cancel: asyncio.Event | None = None,
    ) -> np.ndarray:
        """Записати звук із реального мікрофона через PipeWire/ALSA у volatile пам’ять."""
        self.mic.require_unmuted()
        pw_rec = shutil.which("pw-record")
        arec = shutil.which("arecord")
        if pw_rec:
            cmd = [
                pw_rec,
                "--format",
                "s16",
                "--rate",
                str(self.sample_rate),
                "--channels",
                "1",
                "-",
            ]
        elif arec:
            cmd = [
                arec,
                "-q",
                "-f",
                "S16_LE",
                "-r",
                str(self.sample_rate),
                "-c",
                "1",
                "-t",
                "raw",
                "-",
            ]
        else:
            raise RuntimeError("no_audio_capture_tool")

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        raw = bytearray()
        max_bytes = int(self.sample_rate * 2 * duration_s)
        loop = asyncio.get_running_loop()
        deadline = loop.time() + duration_s

        try:
            assert proc.stdout is not None
            while len(raw) < max_bytes and loop.time() < deadline:
                if (cancel is not None and cancel.is_set()) or self.mic.muted:
                    break
                remaining = max(0.02, deadline - loop.time())
                try:
                    chunk = await asyncio.wait_for(
                        proc.stdout.read(2048), timeout=min(0.1, remaining)
                    )
                except TimeoutError:
                    continue
                if not chunk:
                    break
                raw.extend(chunk)
        finally:
            with contextlib.suppress(ProcessLookupError):
                proc.terminate()
            with contextlib.suppress(Exception):
                await asyncio.wait_for(proc.wait(), timeout=1.0)

        if self.mic.muted and not raw:
            raise PermissionError("microphone_muted")
        even_len = len(raw) - (len(raw) % 2)
        if even_len <= 0:
            return np.zeros(0, dtype=np.float32)
        return (
            np.frombuffer(memoryview(raw)[:even_len], dtype=np.int16).astype(np.float32) / 32768.0
        )

    @staticmethod
    def _normalize_chunk(chunk: np.ndarray | bytes) -> np.ndarray:
        if isinstance(chunk, bytes | bytearray | memoryview):
            even = len(chunk) - (len(chunk) % 2)
            return (
                np.frombuffer(memoryview(chunk)[:even], dtype=np.int16).astype(np.float32) / 32768.0
            )
        arr = np.asarray(chunk)
        if arr.dtype == np.int16:
            return arr.astype(np.float32) / 32768.0
        return arr.astype(np.float32, copy=False).reshape(-1)
