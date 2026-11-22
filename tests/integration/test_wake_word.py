"""Tests for local wake word gating and RAM-only ring buffer (H6 step 1)."""

from __future__ import annotations

import asyncio
import builtins
import os
from pathlib import Path

import numpy as np
import pytest

from b12.audio.asr import TranscriptResult
from b12.audio.capture import MicController
from b12.audio.duplex import DuplexSession
from b12.audio.live import FRAME_SAMPLES, LiveMic, LiveSession, Segmenter
from b12.audio.tts import SynthesizedAudio
from b12.audio.wake import WakeDetector
from b12.contracts import ModelReply
from b12.runtime import open_runtime
from tests.integration.test_duplex import _voice_signal


def _frames(signal: np.ndarray) -> list[np.ndarray]:
    usable = len(signal) - len(signal) % FRAME_SAMPLES
    return [signal[i : i + FRAME_SAMPLES] for i in range(0, usable, FRAME_SAMPLES)]


def _silence(seconds: float) -> list[np.ndarray]:
    return [
        np.zeros(FRAME_SAMPLES, dtype=np.float32)
        for _ in range(round(seconds * 16000 / FRAME_SAMPLES))
    ]


class _FastScriptedMic(LiveMic):
    """Yields scripted blocks without wall-clock sleep; calls optional hooks between blocks."""

    def __init__(self, mic: MicController, script):
        super().__init__(mic)
        self._script = script

    async def frames(self, stop):
        for item in self._script:
            if callable(item):
                item()
                continue
            for frame in item:
                if stop.is_set():
                    return
                yield frame
                await asyncio.sleep(0)


class _EnergyVad:
    def __init__(self):
        self.threshold = 0.5
        self.allow_rms_fallback = False

    def frame_probability(self, frame) -> float:
        return 0.9 if float(np.sqrt(np.mean(np.square(frame)))) > 0.05 else 0.0

    def clone(self):
        return self

    def reset(self) -> None:
        return None


class _FakeClock:
    def __init__(self, start: float = 100.0):
        self.now_s = start

    def __call__(self) -> float:
        return self.now_s

    def advance(self, delta_s: float) -> None:
        self.now_s += delta_s


class _FakeWakeDetector:
    """Deterministic frame-level detector driven by explicit frame indices."""

    def __init__(self, trigger_on_frames: set[int]):
        self._trigger_on = set(trigger_on_frames)
        self.calls = 0

    def feed(self, frame: np.ndarray) -> bool:
        self.calls += 1
        return self.calls in self._trigger_on


@pytest.fixture
def wake_runtime(profile_settings, tmp_path):
    class QuickModel:
        def __init__(self):
            self.calls = 0

        async def chat(self, admitted, *, on_delta=None, cancel=None, deadline=None):
            self.calls += 1
            return ModelReply(
                content="Гаразд, слухаю.",
                tool_calls=(),
                metrics={"prompt_tokens": 12, "output_tokens": 6, "total_ms": 10.0},
                finish_reason="stop",
            )

    settings = profile_settings.model_copy(
        update={
            "state_dir": tmp_path / "state",
            "num_ctx": 32768,
            "output_tokens": 512,
            "wake_word": True,
        }
    )
    model = QuickModel()
    runtime = open_runtime(settings, model=model)
    owner = runtime.control.create_actor(owner=True, consent=True)
    session_id = runtime.control.create_session(owner.id)
    runtime.control.set_meta("owner_actor", owner.id)
    duplex = DuplexSession(runtime, session_id=session_id, actor_id=owner.id)
    duplex.player.simulated_max_duration_s = 0.01

    def fake_transcribe(audio_16k: np.ndarray, *, language: str = "auto") -> TranscriptResult:
        duplex.pipeline.asr.transcribe_count += 1
        return TranscriptResult(
            text="Яка зараз година?",
            language="uk",
            language_probability=0.99,
            duration_s=len(audio_16k) / 16000.0,
            asr_latency_ms=2.0,
            provenance_id="prov-wake",
        )

    def fake_synth(text: str, *, lang: str = "auto") -> SynthesizedAudio:
        pcm = np.zeros(800, dtype=np.int16).tobytes()
        return SynthesizedAudio(
            text=text, language="uk", sample_rate=16000, pcm_int16=pcm, ttfa_ms=1.0, duration_s=0.05
        )

    duplex.pipeline.asr.transcribe = fake_transcribe  # type: ignore[method-assign]
    duplex.pipeline.tts.synthesize = fake_synth  # type: ignore[method-assign]
    duplex._stream_vad = _EnergyVad()
    try:
        yield runtime, duplex, model, tmp_path
    finally:
        duplex.close()
        runtime.close()


async def test_utterances_before_wake_are_ignored(wake_runtime):
    runtime, duplex, model, _ = wake_runtime
    mic_ctrl = MicController(runtime.control)

    first_speech = _frames(_voice_signal(0.6))
    first_silence = _silence(0.5)
    wake_trigger_frame_idx = len(first_speech) + len(first_silence) + 1
    second_speech = _frames(_voice_signal(0.6, f0=190.0))
    second_silence = _silence(0.5)

    mic = _FastScriptedMic(
        mic_ctrl,
        script=[first_speech, first_silence, second_speech, second_silence],
    )
    detector = _FakeWakeDetector({wake_trigger_frame_idx})
    events: list[dict] = []
    segmenter = Segmenter(end_silence_s=0.3, min_speech_s=0.2, preroll_s=0.0)
    session = LiveSession(
        duplex,
        mic,
        segmenter=segmenter,
        on_event=events.append,
        mode="wake",
        wake_detector=detector,
    )
    stats = await asyncio.wait_for(session.run(asyncio.Event()), 10)

    event_names = [e["event"] for e in events]
    assert "wake_ignored" in event_names
    assert "wake" in event_names
    assert event_names.index("wake_ignored") < event_names.index("wake")
    assert stats["utterances"] == 1
    assert stats["asr_calls"] == 1
    assert model.calls == 1


async def test_window_closes_after_8_seconds(wake_runtime):
    runtime, duplex, model, _ = wake_runtime
    mic_ctrl = MicController(runtime.control)
    clock = _FakeClock(start=100.0)

    wake_burst = _silence(0.05)  # 2 frames; frame 1 triggers wake at t=100.0
    first_speech = _frames(_voice_signal(0.6))
    first_silence = _silence(0.5)
    second_speech = _frames(_voice_signal(0.6, f0=190.0))
    second_silence = _silence(0.5)

    mic = _FastScriptedMic(
        mic_ctrl,
        script=[
            wake_burst,
            lambda: clock.advance(1.0),  # t=101.0 (inside 8 s window)
            first_speech,
            first_silence,
            lambda: clock.advance(7.5),  # t=108.5 (past 8.0 s window)
            second_speech,
            second_silence,
        ],
    )
    detector = _FakeWakeDetector({1})
    events: list[dict] = []
    segmenter = Segmenter(end_silence_s=0.3, min_speech_s=0.2, preroll_s=0.0)
    session = LiveSession(
        duplex,
        mic,
        segmenter=segmenter,
        on_event=events.append,
        mode="wake",
        wake_detector=detector,
        wake_window_s=8.0,
        clock=clock,
    )
    stats = await asyncio.wait_for(session.run(asyncio.Event()), 10)

    assert stats["utterances"] == 1
    assert stats["asr_calls"] == 1
    assert model.calls == 1
    assert [e["event"] for e in events].count("wake") == 1
    assert [e["event"] for e in events].count("wake_ignored") == 1


def test_ring_buffer_never_persists(tmp_path, monkeypatch):
    clock = _FakeClock(start=0.0)
    detector = WakeDetector(
        threshold=0.5,
        refractory_s=2.0,
        ring_buffer_s=1.5,
        scorer=lambda _frame: 0.0,
        clock=clock,
    )

    write_attempts: list[str] = []
    orig_open = builtins.open
    orig_os_open = os.open

    def guarded_open(file, mode="r", *args, **kwargs):
        if any(flag in mode for flag in ("w", "a", "x", "+")):
            write_attempts.append(f"open:{file}:{mode}")
        return orig_open(file, mode, *args, **kwargs)

    def guarded_os_open(path, flags, *args, **kwargs):
        if flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_APPEND):
            write_attempts.append(f"os.open:{path}:{flags}")
        return orig_os_open(path, flags, *args, **kwargs)

    monkeypatch.setattr(builtins, "open", guarded_open)
    monkeypatch.setattr(os, "open", guarded_os_open)
    monkeypatch.setattr(
        Path,
        "write_bytes",
        lambda self, data: write_attempts.append(f"write_bytes:{self}"),
    )
    monkeypatch.setattr(
        Path,
        "write_text",
        lambda self, data, **kwargs: write_attempts.append(f"write_text:{self}"),
    )

    before_files = set(tmp_path.rglob("*"))
    # Feed 3.2 seconds (100 frames of 512 samples at 16 kHz) — exceeds 1.5 s ring capacity.
    for idx in range(100):
        frame = np.full(FRAME_SAMPLES, float(idx + 1) * 1e-4, dtype=np.float32)
        assert detector.feed(frame) is False
        clock.advance(FRAME_SAMPLES / 16000.0)

    buffered = detector.ring_buffer_audio()
    assert write_attempts == []
    assert set(tmp_path.rglob("*")) == before_files
    assert 1.45 <= detector.ring_buffer_seconds <= 1.55
    assert len(buffered) == detector.ring_buffer_frames * FRAME_SAMPLES
    # Oldest frames rolled out: earliest retained sample matches frame 53 (100 - 47).
    expected_first = float((100 - detector.ring_buffer_frames) + 1) * 1e-4
    assert np.isclose(buffered[0], expected_first, atol=1e-6)


def test_refractory_period_suppresses_triggers_within_2_seconds():
    clock = _FakeClock(start=10.0)
    detector = WakeDetector(
        threshold=0.5,
        refractory_s=2.0,
        ring_buffer_s=1.5,
        scorer=lambda _frame: 0.95,
        clock=clock,
    )
    frame = np.zeros(FRAME_SAMPLES, dtype=np.float32)

    assert detector.feed(frame) is True
    clock.advance(0.5)
    assert detector.feed(frame) is False
    clock.advance(1.4)  # elapsed = 1.9 s < 2.0 s
    assert detector.feed(frame) is False
    clock.advance(0.15)  # elapsed = 2.05 s >= 2.0 s
    assert detector.feed(frame) is True


def test_default_detector_without_model_never_triggers_and_flag_enables_wake_mode(wake_runtime):
    runtime, duplex, _, _ = wake_runtime
    mic = _FastScriptedMic(MicController(runtime.control), script=[])
    detector = WakeDetector()
    assert detector.feed(np.zeros(FRAME_SAMPLES, dtype=np.float32)) is False
    session = LiveSession(duplex, mic)
    assert session.mode == "wake"
