"""Live full-duplex loop (A-14): continuous frames, one ASR per utterance, barge-in."""

import asyncio

import numpy as np
import pytest

from b12.audio.asr import TranscriptResult
from b12.audio.live import FRAME_SAMPLES, LiveMic, LiveSession, Segmenter
from b12.audio.tts import SynthesizedAudio
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


# --- segmenter: pure, deterministic ---------------------------------------------------------


def test_segmenter_emits_one_utterance_after_the_speaker_stops():
    segmenter = Segmenter(end_silence_s=0.3, min_speech_s=0.2, preroll_s=0.0)
    emitted = []
    for frame in _frames(_voice_signal(0.8)):
        out = segmenter.push(frame, vad_probability=0.9, echo=False)
        emitted.append(out)
    for frame in _silence(0.5):
        emitted.append(segmenter.push(frame, vad_probability=0.0, echo=False))
    utterances = [u for u in emitted if u is not None]
    assert len(utterances) == 1
    assert len(utterances[0].audio) >= 0.8 * 16000 * 0.9


def test_segmenter_drops_bursts_shorter_than_the_minimum_and_ignores_echo():
    segmenter = Segmenter(end_silence_s=0.3, min_speech_s=0.3, preroll_s=0.0)
    results = []
    for frame in _frames(_voice_signal(0.1)):
        results.append(segmenter.push(frame, vad_probability=0.9, echo=False))
    for frame in _silence(0.5):
        results.append(segmenter.push(frame, vad_probability=0.0, echo=False))
    for frame in _frames(_voice_signal(0.8)):
        results.append(segmenter.push(frame, vad_probability=0.9, echo=True))
    for frame in _silence(0.5):
        results.append(segmenter.push(frame, vad_probability=0.0, echo=True))
    assert [r for r in results if r is not None] == []


# --- live loop: real duplex path, fake mic, fake model, fake ASR and TTS --------------------


class ScriptedMic(LiveMic):
    """Frames from a script; each item is a list of frames. The loop reads them in order."""

    def __init__(self, mic, script):
        super().__init__(mic)
        self._script = script

    async def frames(self, stop):
        for block in self._script:
            for frame in block:
                if stop.is_set():
                    return
                yield frame
                await asyncio.sleep(FRAME_SAMPLES / 16000)  # real time: 32 ms per frame


class EnergyVad:
    """Stands in for Silero in loop tests: the synthetic tones here are not speech, and Silero's
    recurrent state on them is not what these tests check. Real speech is covered physically."""

    def __init__(self):
        self.threshold = 0.5
        self.allow_rms_fallback = False

    def frame_probability(self, frame) -> float:
        return 0.9 if float(np.sqrt(np.mean(np.square(frame)))) > 0.05 else 0.0

    def clone(self):
        return self

    def reset(self) -> None:
        return None


@pytest.fixture
def live_runtime(profile_settings, tmp_path):
    from b12.audio.duplex import DuplexSession

    class SlowModel:
        def __init__(self):
            self.calls = 0

        async def chat(self, admitted, *, on_delta=None, cancel=None, deadline=None):
            self.calls += 1
            out = ""
            clauses = (
                "Добре, зараз відповім. ",
                "Ось моя відповідь на твоє питання. ",
                "Погода сьогодні хмарна. ",
                "Вночі очікується дощ. ",
                "Вітер слабкий. ",
                "Це все, що я знаю. ",
            )
            for clause in clauses:
                if cancel is not None and cancel.is_set():
                    break
                out += clause
                if on_delta:
                    await on_delta(clause)
                await asyncio.sleep(0.9)  # slow enough that the user talks while B-12 generates
            return ModelReply(
                content=out.strip(),
                tool_calls=(),
                metrics={"prompt_tokens": 16, "output_tokens": 16, "total_ms": 100.0},
                finish_reason="stop",
            )

    settings = profile_settings.model_copy(
        update={"state_dir": tmp_path / "state", "num_ctx": 32768, "output_tokens": 512}
    )
    model = SlowModel()
    runtime = open_runtime(settings, model=model)
    owner = runtime.control.create_actor(owner=True, consent=True)
    session_id = runtime.control.create_session(owner.id)
    runtime.control.set_meta("owner_actor", owner.id)
    duplex = DuplexSession(runtime, session_id=session_id, actor_id=owner.id)
    duplex.player.simulated_max_duration_s = 0.4
    asr_inputs = []

    def fake_transcribe(audio_16k, *, language="auto"):
        duplex.pipeline.asr.transcribe_count += 1
        asr_inputs.append(len(audio_16k))
        return TranscriptResult(
            text="Розкажи коротко про погоду",
            language="uk",
            language_probability=0.99,
            duration_s=len(audio_16k) / 16000.0,
            asr_latency_ms=5.0,
            provenance_id="prov",
        )

    def fast_synth(text, *, lang="auto"):
        pcm = (np.sin(np.linspace(0, 50, 1600)) * 8000).astype(np.int16).tobytes()
        return SynthesizedAudio(
            text=text, language="uk", sample_rate=16000, pcm_int16=pcm, ttfa_ms=3.0, duration_s=0.1
        )

    duplex.pipeline.asr.transcribe = fake_transcribe
    duplex.pipeline.tts.synthesize = fast_synth
    duplex._stream_vad = EnergyVad()
    yield runtime, duplex, model, asr_inputs
    runtime.close()


async def test_one_utterance_is_recognized_once_and_answered_while_the_mic_keeps_running(
    live_runtime,
):
    runtime, duplex, model, asr_inputs = live_runtime
    stop = asyncio.Event()
    mic = ScriptedMic(
        runtime.control and _mic(runtime),
        script=[_frames(_voice_signal(0.9)), _silence(1.0), _silence(1.0)],
    )
    session = LiveSession(duplex, mic)
    stats = await asyncio.wait_for(session.run(stop), 60)
    assert stats["utterances"] == 1
    assert stats["asr_calls"] == 1, "a repeated recognition of the same utterance is a defect"
    assert len(asr_inputs) == 1
    assert model.calls == 1


async def test_user_speech_while_b12_talks_interrupts_and_is_recognized_once(live_runtime):
    runtime, duplex, model, asr_inputs = live_runtime
    stop = asyncio.Event()
    mic = ScriptedMic(
        _mic(runtime),
        script=[
            _frames(_voice_signal(0.8)),
            _silence(0.8),  # B-12 answers now
            _silence(0.3),
            _frames(_voice_signal(0.8, f0=190.0)),  # the user interrupts
            _silence(1.0),
        ],
    )
    events = []
    session = LiveSession(duplex, mic, on_event=events.append)
    stats = await asyncio.wait_for(session.run(stop), 60)
    turns = [e["state"] for e in events if e["event"] == "turn"]
    assert "cancelled" in turns, "the interrupted answer must end cancelled, not keep speaking"
    assert stats["utterances"] == 2
    assert stats["asr_calls"] == 2, "each utterance is recognized once, the interruption included"
    assert stats["barge_ins"] >= 1


def _mic(runtime):
    from b12.audio.capture import MicController

    return MicController(runtime.control)
