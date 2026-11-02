"""Full-duplex сесія B-12: однопрохідний AEC/ASR, потоковий TTS, scoped barge-in та SpeakerID."""

import asyncio
import contextlib
import time
from dataclasses import dataclass, field

import numpy as np

from b12.audio.aec import AcousticEchoCanceller, AecStats, PulseAudioWebRtcAec
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
    cleaned_audio: np.ndarray = field(default_factory=lambda: np.zeros(0, dtype=np.float32))


class DuplexSession:
    """Керування full-duplex потоком із миттєвим scoped barge-in та захистом від self-trigger."""

    def __init__(
        self,
        runtime,
        *,
        session_id: str,
        actor_id: str,
        pipeline: VoicePipeline | None = None,
        use_hardware_audio: bool = False,
        use_system_webrtc_aec: bool = False,
        barge_in_vad_threshold: float = 0.5,
    ):
        self.runtime = runtime
        self.session_id = session_id
        self.actor_id = actor_id
        self.pipeline = pipeline or VoicePipeline(runtime)
        self.aec = AcousticEchoCanceller(sample_rate=16000)
        self.system_aec = PulseAudioWebRtcAec() if use_system_webrtc_aec else None
        self._stream_vad = self.pipeline.endpoint.vad.clone()
        self.speaker_store = SpeakerStore(runtime.settings.state_dir / "voice" / "speakers.sqlite3")
        self.speaker_verifier = SpeakerVerifier(self.speaker_store, runtime.control)
        self.player = AudioPlayer(
            on_render_reference=self.aec.feed_render_reference,
            use_hardware=use_hardware_audio,
        )
        self.barge_in_vad_threshold = barge_in_vad_threshold
        self._active_cancel: asyncio.Event | None = None
        self._active_turn_id: str | None = None
        self._tts_queue: asyncio.Queue[SynthesizedAudio | None] = asyncio.Queue(
            maxsize=self.pipeline.tts.max_queue_phrases
        )

    @property
    def tts_queue_size(self) -> int:
        return self._tts_queue.qsize()

    def reset_vad(self) -> None:
        self._stream_vad.reset()

    def close(self) -> None:
        self.player.stop()
        if self.system_aec is not None:
            self.system_aec.stop()
        self.speaker_store.close()

    def _flush_tts_queue(self) -> None:
        while not self._tts_queue.empty():
            with contextlib.suppress(asyncio.QueueEmpty):
                self._tts_queue.get_nowait()

    def _cancel_scoped_voice_turns(self) -> None:
        """Скасувати лише активний хід поточної голосової сесії, не чіпаючи інші сесії (V-005)."""
        target_ids: set[str] = set()
        if self._active_turn_id:
            target_ids.add(self._active_turn_id)
        for tid, handle in list(self.runtime.agent.active.items()):
            sid = getattr(handle, "session_id", None)
            if sid is None:
                ident = self.runtime.control.turn_identity(tid)
                sid = ident["session_id"] if ident else None
            if sid == self.session_id:
                target_ids.add(tid)
        for tid in target_ids:
            self.runtime.control.cancel_turn(tid)
            handle = self.runtime.agent.active.get(tid)
            if handle is not None:
                handle.cancel.set()

    async def speak_response(
        self,
        text: str,
        *,
        autonomous: bool = False,
    ) -> list[SynthesizedAudio]:
        """Паралельно синтезувати та відтворювати відповідь через bounded queue (V-001, V-004)."""
        if autonomous:
            att = self.runtime.attention.state(self.actor_id)
            if att.get("quiet") or att.get("stopped"):
                return []

        sentences = split_sentences(text)
        if not sentences:
            return []

        cancel = asyncio.Event()
        self._active_cancel = cancel
        self._flush_tts_queue()
        played: list[SynthesizedAudio] = []

        async def _producer() -> None:
            try:
                for s in sentences:
                    if cancel.is_set():
                        break
                    chunk = await asyncio.to_thread(self.pipeline.tts.synthesize, s)
                    if cancel.is_set():
                        break
                    # Чекаємо місце в bounded queue або виходимо при cancel
                    while not cancel.is_set():
                        try:
                            await asyncio.wait_for(self._tts_queue.put(chunk), timeout=0.05)
                            break
                        except TimeoutError:
                            continue
            finally:
                if cancel.is_set():
                    self._flush_tts_queue()
                with contextlib.suppress(asyncio.QueueFull):
                    self._tts_queue.put_nowait(None)

        async def _consumer() -> None:
            while not cancel.is_set():
                try:
                    item = await asyncio.wait_for(self._tts_queue.get(), timeout=0.05)
                except TimeoutError:
                    if prod_task.done() and self._tts_queue.empty():
                        break
                    continue
                if item is None:
                    break
                self.aec.record_tts_utterance(item.text)
                completed = await self.player.play(item, cancel=cancel)
                if completed:
                    played.append(item)
                if cancel.is_set():
                    break

        prod_task = asyncio.create_task(_producer())
        cons_task = asyncio.create_task(_consumer())
        try:
            await asyncio.gather(prod_task, cons_task)
        finally:
            if not prod_task.done():
                prod_task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await prod_task
            if not cons_task.done():
                cons_task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await cons_task
            if self._active_cancel is cancel:
                self._active_cancel = None
        return played

    async def feed_capture_frame(
        self,
        mic_16k: np.ndarray,
        *,
        background_media_active: bool = False,
    ) -> BargeInResult:
        """Обробити фрейм мікрофона через mute guard → 1× AEC → stateful VAD → scoped barge-in."""
        self.pipeline.mic.require_unmuted()
        cleaned, aec_stats = self.aec.process_capture(
            mic_16k,
            background_media_active=background_media_active,
        )
        cleaned_ro = cleaned.copy()
        cleaned_ro.setflags(write=False)

        # Використовуємо сесійний stateful VAD без скидання між фреймами (V-006)
        self._stream_vad.allow_rms_fallback = self.pipeline.endpoint.vad.allow_rms_fallback
        self._stream_vad.threshold = self.pipeline.endpoint.vad.threshold
        probs = []
        for i in range(0, max(1, len(cleaned) - 512 + 1), 512):
            probs.append(self._stream_vad.frame_probability(cleaned[i : i + 512]))
        max_prob = max(probs) if probs else 0.0

        is_speaking = (
            max_prob >= self.barge_in_vad_threshold
            and not aec_stats.is_echo_dominant
            and not aec_stats.is_media_contaminated
        )

        barge_triggered = False
        stop_ms: float | None = None
        if is_speaking and (
            self.player.is_playing
            or self._active_cancel is not None
            or not self._tts_queue.empty()
            or self._active_turn_id is not None
        ):
            t0 = time.perf_counter()
            if self._active_cancel is not None:
                self._active_cancel.set()
            self._cancel_scoped_voice_turns()
            self.player.stop()
            self._flush_tts_queue()
            self.aec.clear_reference()
            stop_ms = round((time.perf_counter() - t0) * 1000.0, 3)
            barge_triggered = True

        spk_match = self.speaker_verifier.verify(cleaned_ro) if len(cleaned_ro) >= 1600 else None
        return BargeInResult(
            barge_in_triggered=barge_triggered,
            time_to_stop_ms=stop_ms,
            vad_probability=round(max_prob, 4),
            aec_stats=aec_stats,
            speaker_match=spk_match,
            cleaned_audio=cleaned_ro,
        )

    async def handle_duplex_utterance(
        self,
        mic_16k: np.ndarray,
        *,
        background_media_active: bool = False,
        live_playback: bool = True,
    ) -> VoiceTurnResult | None:
        """Повний дуплексний хід: 1× AEC → barge-in → 1× ASR → live VoicePipeline."""
        barge = await self.feed_capture_frame(
            mic_16k,
            background_media_active=background_media_active,
        )
        self._stream_vad.reset()
        if barge.aec_stats.is_echo_dominant or barge.aec_stats.is_media_contaminated:
            return None

        # Використовуємо вже очищений буфер із feed_capture_frame без повторного виклику AEC (V-002)
        cleaned = barge.cleaned_audio
        ep = self.pipeline.endpoint.detect_utterance(cleaned)
        target_audio = ep.speech_audio if len(ep.speech_audio) > 0 else cleaned

        # Виконуємо ASR рівно один раз і передаємо готовий транскрипт у конвеєр (V-003)
        transcript = await asyncio.to_thread(self.pipeline.asr.transcribe, target_audio)
        if not transcript.text.strip() or self.aec.is_tts_echo_text(transcript.text):
            return None

        cancel = asyncio.Event()
        self._active_cancel = cancel

        def _set_turn_id(tid: str) -> None:
            self._active_turn_id = tid

        try:
            res = await self.pipeline.process_utterance(
                session_id=self.session_id,
                actor_id=self.actor_id,
                audio_16k=cleaned,
                cancel=cancel,
                precomputed_transcript=transcript,
                precomputed_endpoint=ep,
                player=self.player if live_playback else None,
                on_tts_chunk=lambda ch: self.aec.record_tts_utterance(ch.text),
                on_turn_started=_set_turn_id,
            )
            return res
        finally:
            if self._active_cancel is cancel:
                self._active_cancel = None
            self._active_turn_id = None
