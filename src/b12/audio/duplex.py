"""Full-duplex сесія B-12: AEC render reference, barge-in, quiet-mode та speaker verification."""

import asyncio
import contextlib
import time
from dataclasses import dataclass

import numpy as np

from b12.audio.aec import AcousticEchoCanceller, AecStats
from b12.audio.pipeline import VoicePipeline, VoiceTurnResult
from b12.audio.speaker import SpeakerMatch, SpeakerStore, SpeakerVerifier
from b12.audio.tts import AudioPlayer, SynthesizedAudio, split_sentences


@dataclass(frozen=True)
class BargeInResult:
    barge_in_triggered: bool
    time_to_stop_ms: float | None
    vad_probability: float
    aec_stats: AecStats
    speaker_match: SpeakerMatch | None = None


class DuplexSession:
    """Керування full-duplex аудіопотоком із миттєвим barge-in та захистом від self-trigger."""

    def __init__(
        self,
        runtime,
        *,
        session_id: str,
        actor_id: str,
        pipeline: VoicePipeline | None = None,
        use_hardware_audio: bool = False,
        barge_in_vad_threshold: float = 0.5,
    ):
        self.runtime = runtime
        self.session_id = session_id
        self.actor_id = actor_id
        self.pipeline = pipeline or VoicePipeline(runtime)
        self.aec = AcousticEchoCanceller(sample_rate=16000)
        self.speaker_store = SpeakerStore(runtime.settings.state_dir / "voice" / "speakers.sqlite3")
        self.speaker_verifier = SpeakerVerifier(self.speaker_store, runtime.control)
        self.player = AudioPlayer(
            on_render_reference=self.aec.feed_render_reference,
            use_hardware=use_hardware_audio,
        )
        self.barge_in_vad_threshold = barge_in_vad_threshold
        self._active_cancel: asyncio.Event | None = None
        self._tts_queue: asyncio.Queue[SynthesizedAudio | None] = asyncio.Queue(
            maxsize=self.pipeline.tts.max_queue_phrases
        )

    @property
    def tts_queue_size(self) -> int:
        return self._tts_queue.qsize()

    def close(self) -> None:
        self.player.stop()
        self.speaker_store.close()

    def _flush_tts_queue(self) -> None:
        while not self._tts_queue.empty():
            with contextlib.suppress(asyncio.QueueEmpty):
                self._tts_queue.get_nowait()

    async def speak_response(
        self,
        text: str,
        *,
        autonomous: bool = False,
    ) -> list[SynthesizedAudio]:
        """Озвучити відповідь по реченнях із render reference для AEC та barge-in."""
        if autonomous:
            att = self.runtime.attention.state(self.actor_id)
            if att.get("quiet") or att.get("stopped"):
                return []

        cancel = asyncio.Event()
        self._active_cancel = cancel
        self._flush_tts_queue()
        played: list[SynthesizedAudio] = []

        sentences = split_sentences(text)
        for s in sentences:
            if cancel.is_set():
                break
            chunk = await asyncio.to_thread(self.pipeline.tts.synthesize, s)
            if cancel.is_set():
                break
            await self._tts_queue.put(chunk)

        with contextlib.suppress(asyncio.QueueFull):
            self._tts_queue.put_nowait(None)

        try:
            while not cancel.is_set():
                if self._tts_queue.empty():
                    break
                item = await self._tts_queue.get()
                if item is None:
                    break
                self.aec.record_tts_utterance(item.text)
                completed = await self.player.play(item, cancel=cancel)
                if completed:
                    played.append(item)
                if cancel.is_set():
                    break
        finally:
            if self._active_cancel is cancel:
                self._active_cancel = None
        return played

    async def feed_capture_frame(
        self,
        mic_16k: np.ndarray,
        *,
        background_media_active: bool = False,
    ) -> BargeInResult:
        """Обробити вхідний фрейм мікрофона через mute guard → AEC → VAD → barge-in."""
        self.pipeline.mic.require_unmuted()
        cleaned, aec_stats = self.aec.process_capture(
            mic_16k,
            background_media_active=background_media_active,
        )

        # Evaluate VAD across 512-sample subframes of cleaned signal
        self.pipeline.endpoint.vad.reset()
        probs = []
        for i in range(0, max(1, len(cleaned) - 512 + 1), 512):
            probs.append(self.pipeline.endpoint.vad.frame_probability(cleaned[i : i + 512]))
        max_prob = max(probs) if probs else 0.0

        is_speaking = (
            max_prob >= self.barge_in_vad_threshold
            and not aec_stats.is_echo_dominant
            and not aec_stats.is_media_contaminated
        )

        barge_triggered = False
        stop_ms: float | None = None
        if is_speaking and (
            self.player.is_playing or self._active_cancel is not None or not self._tts_queue.empty()
        ):
            t0 = time.perf_counter()
            if self._active_cancel is not None:
                self._active_cancel.set()
            for turn_id in list(self.runtime.agent.active):
                self.runtime.control.cancel_turn(turn_id)
                self.runtime.agent.active[turn_id].cancel.set()
            self.player.stop()
            self._flush_tts_queue()
            self.aec.clear_reference()
            stop_ms = round((time.perf_counter() - t0) * 1000.0, 3)
            barge_triggered = True

        spk_match = self.speaker_verifier.verify(cleaned) if len(cleaned) >= 1600 else None
        return BargeInResult(
            barge_in_triggered=barge_triggered,
            time_to_stop_ms=stop_ms,
            vad_probability=round(max_prob, 4),
            aec_stats=aec_stats,
            speaker_match=spk_match,
        )

    async def handle_duplex_utterance(
        self,
        mic_16k: np.ndarray,
        *,
        background_media_active: bool = False,
    ) -> VoiceTurnResult | None:
        """Повний дуплексний хід: AEC → barge-in → anti-self-trigger → VoicePipeline."""
        barge = await self.feed_capture_frame(
            mic_16k,
            background_media_active=background_media_active,
        )
        if barge.aec_stats.is_echo_dominant or barge.aec_stats.is_media_contaminated:
            return None

        cleaned, _ = self.aec.process_capture(
            mic_16k, background_media_active=background_media_active
        )
        transcript = await asyncio.to_thread(self.pipeline.asr.transcribe, cleaned)
        if not transcript.text.strip() or self.aec.is_tts_echo_text(transcript.text):
            return None

        cancel = asyncio.Event()
        self._active_cancel = cancel
        try:
            res = await self.pipeline.process_utterance(
                session_id=self.session_id,
                actor_id=self.actor_id,
                audio_16k=cleaned,
                cancel=cancel,
            )
            for chunk in res.tts_chunks:
                self.aec.record_tts_utterance(chunk.text)
            return res
        finally:
            if self._active_cancel is cancel:
                self._active_cancel = None
