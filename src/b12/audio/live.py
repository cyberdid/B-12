"""Live full-duplex loop: the microphone is read continuously, while B-12 speaks or thinks.

The loop never alternates between "listening" and "speaking". Every 32 ms frame goes through the
duplex session (AEC, then barge-in). A segmenter turns the stream into utterances. Each
utterance is recognized exactly once and starts one agent turn, which runs as a task so the
microphone keeps flowing. Speech that starts while B-12 is talking interrupts the current turn
and its speech through the duplex barge-in path.
"""

from __future__ import annotations

import asyncio
import contextlib
import shutil
import time
from collections import deque
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass

import numpy as np

from b12.audio.capture import MicController

FRAME_SAMPLES = 512  # 32 ms at 16 kHz, the frame size the VAD and AEC are tuned for
SAMPLE_RATE = 16000


@dataclass(frozen=True)
class Utterance:
    audio: np.ndarray
    started_at: float
    ended_at: float


class LiveMic:
    """Continuous 16 kHz mono frames from pw-record or arecord (no fixed duration).

    The source stops as soon as the microphone is muted, so mute keeps its meaning.
    """

    def __init__(self, mic: MicController, *, sample_rate: int = SAMPLE_RATE, command=None):
        self.mic = mic
        self.sample_rate = sample_rate
        self._command = command

    def _capture_command(self) -> list[str]:
        if self._command is not None:
            return list(self._command)
        pw_record = shutil.which("pw-record")
        arecord = shutil.which("arecord")
        if pw_record:
            return [
                pw_record,
                "--format",
                "s16",
                "--rate",
                str(self.sample_rate),
                "--channels",
                "1",
                "-",
            ]
        if arecord:
            return [
                arecord,
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
        raise RuntimeError("no_capture_tool")

    async def frames(self, stop: asyncio.Event) -> AsyncIterator[np.ndarray]:
        self.mic.require_unmuted()
        process = await asyncio.create_subprocess_exec(
            *self._capture_command(),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        try:
            assert process.stdout is not None
            while not stop.is_set():
                raw = await process.stdout.readexactly(FRAME_SAMPLES * 2)
                self.mic.require_unmuted()
                yield np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
        finally:
            if process.returncode is None:
                process.terminate()
                with contextlib.suppress(Exception):
                    await process.wait()


class Segmenter:
    """Turns a frame stream into utterances from VAD probability and echo flags.

    A speech start includes a short pre-roll so the first phoneme is not cut. An utterance ends
    after `end_silence_s` of non-speech, or at `max_s`. Bursts shorter than `min_speech_s` are
    noise and are dropped.
    """

    def __init__(
        self,
        *,
        threshold: float = 0.5,
        frame_s: float = FRAME_SAMPLES / SAMPLE_RATE,
        end_silence_s: float = 0.6,
        min_speech_s: float = 0.3,
        preroll_s: float = 0.2,
        max_s: float = 20.0,
    ):
        self.threshold = threshold
        self.frame_s = frame_s
        self.end_silence_frames = max(1, round(end_silence_s / frame_s))
        self.min_speech_frames = max(1, round(min_speech_s / frame_s))
        self.max_frames = max(1, round(max_s / frame_s))
        self._preroll: deque[np.ndarray] = deque(maxlen=max(1, round(preroll_s / frame_s)))
        self._frames: list[np.ndarray] = []
        self._speech_frames = 0
        self._silence_frames = 0
        self._active = False
        self._started_at = 0.0

    @property
    def in_speech(self) -> bool:
        return self._active

    def push(
        self,
        frame: np.ndarray,
        *,
        vad_probability: float,
        echo: bool,
        now: float | None = None,
    ) -> Utterance | None:
        now = time.monotonic() if now is None else now
        speech = vad_probability >= self.threshold and not echo
        if not self._active:
            self._preroll.append(frame)
            if speech:
                self._active = True
                self._started_at = now
                self._frames = list(self._preroll)
                self._speech_frames = 1
                self._silence_frames = 0
            return None
        self._frames.append(frame)
        if speech:
            self._speech_frames += 1
            self._silence_frames = 0
        else:
            self._silence_frames += 1
        ended = (
            self._silence_frames >= self.end_silence_frames or len(self._frames) >= self.max_frames
        )
        if not ended:
            return None
        frames, speech_frames, started = self._frames, self._speech_frames, self._started_at
        self._reset()
        if speech_frames < self.min_speech_frames:
            return None
        return Utterance(
            audio=np.concatenate(frames).astype(np.float32),
            started_at=started,
            ended_at=now,
        )

    def _reset(self) -> None:
        self._frames = []
        self._speech_frames = 0
        self._silence_frames = 0
        self._active = False
        self._preroll.clear()


class LiveSession:
    """Runs the live loop until `stop` is set. Each utterance is answered by one turn task."""

    def __init__(
        self,
        duplex,
        mic: LiveMic,
        *,
        segmenter: Segmenter | None = None,
        on_event: Callable[[dict], None] | None = None,
    ):
        self.duplex = duplex
        self.mic = mic
        self.segmenter = segmenter or Segmenter(threshold=duplex.barge_in_vad_threshold)
        self.on_event = on_event or (lambda event: None)
        self.utterances = 0
        self.asr_calls = 0
        self.barge_ins = 0
        self._turn: asyncio.Task | None = None

    def _emit(self, event: str, **data) -> None:
        self.on_event({"event": event, **data})

    async def run(self, stop: asyncio.Event) -> dict:
        async for frame in self.mic.frames(stop):
            barge = await self.duplex.feed_capture_frame(frame)
            if barge.barge_in_triggered:
                self.barge_ins += 1
                self._emit("barge_in", stop_ms=barge.time_to_stop_ms)
            utterance = self.segmenter.push(
                barge.cleaned_audio,
                vad_probability=barge.vad_probability,
                echo=barge.aec_stats.is_echo_dominant or barge.aec_stats.is_media_contaminated,
            )
            if utterance is not None:
                self.utterances += 1
                self._emit("utterance", seconds=round(len(utterance.audio) / SAMPLE_RATE, 3))
                await self._cancel_turn()
                self._turn = asyncio.create_task(self._answer(utterance.audio))
            if stop.is_set():
                break
        if stop.is_set():
            await self._cancel_turn()  # the user stopped the loop: in-flight work is dropped
        else:
            await self._finish_turn()  # the input ended on its own: the last answer completes
        return self.stats()

    async def _finish_turn(self, timeout_s: float = 120.0) -> None:
        if self._turn is not None:
            with contextlib.suppress(asyncio.TimeoutError, Exception):
                await asyncio.wait_for(asyncio.shield(self._turn), timeout_s)
        self._turn = None

    async def _cancel_turn(self) -> None:
        if self._turn is not None and not self._turn.done():
            self._turn.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await self._turn
        self._turn = None

    async def _answer(self, audio: np.ndarray) -> None:
        # One recognition per utterance; the pipeline receives the transcript, never the audio.
        transcript = await asyncio.to_thread(self.duplex.pipeline.asr.transcribe, audio)
        self.asr_calls += 1
        self._emit("transcript", text=transcript.text, language=transcript.language)
        result = await self.duplex.process_cleaned_utterance(audio, transcript)
        if result is not None:
            self._emit("turn", state=getattr(result, "state", None))

    def stats(self) -> dict:
        return {
            "utterances": self.utterances,
            "asr_calls": self.asr_calls,
            "barge_ins": self.barge_ins,
        }
