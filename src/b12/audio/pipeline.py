"""Голосовий конвеєр B-12: PTT/utterance → VAD/endpoint → ASR → Agent → live TTS/Playback."""

import asyncio
import contextlib
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal

import numpy as np

from b12.audio.asr import TranscriptResult, WhisperAsr
from b12.audio.capture import MicController, PttCapture
from b12.audio.endpoint import EndpointDecision, EndpointDetector
from b12.audio.tts import (
    AudioPlayer,
    PiperTts,
    SynthesizedAudio,
    extract_stream_clauses,
    generate_earcon_pcm,
    split_sentences,
)
from b12.auth import GUEST_CAPABILITIES, owner_capabilities


@dataclass(frozen=True)
class VoiceTurnMetrics:
    physical_eou_to_endpoint_ms: float
    endpoint_to_asr_ms: float
    asr_to_first_token_ms: float
    first_token_to_first_meaningful_audio_ms: float
    endpoint_to_first_meaningful_audio_ms: float
    physical_eou_to_first_meaningful_audio_ms: float
    earcon_ms: float | None = None
    total_turn_ms: float = 0.0
    first_pcm_submitted_ms: float | None = None
    playback_started_before_llm_completed: bool = False


@dataclass(frozen=True)
class VoiceTurnResult:
    turn_id: str | None
    session_id: str
    state: str
    transcript: TranscriptResult
    endpoint: EndpointDecision
    reply_text: str
    tts_chunks: tuple[SynthesizedAudio, ...]
    metrics: VoiceTurnMetrics


class VoicePipeline:
    """Повний голосовий цикл із триступеневим потоковим LLM → TTS → Playback конвеєром."""

    def __init__(
        self,
        runtime,
        *,
        asr: WhisperAsr | None = None,
        tts: PiperTts | None = None,
        endpoint: EndpointDetector | None = None,
    ):
        self.runtime = runtime
        self.mic = MicController(runtime.control)
        self.capture = PttCapture(self.mic)
        self.endpoint = endpoint or EndpointDetector()
        self.asr = asr or WhisperAsr()
        self.tts = tts or PiperTts()

    async def process_utterance(
        self,
        *,
        session_id: str,
        actor_id: str,
        audio_16k: np.ndarray,
        language: Literal["uk", "en", "auto"] = "auto",
        play_earcon: bool = False,
        timeout_s: float = 300.0,
        persist: bool = False,
        cancel: asyncio.Event | None = None,
        precomputed_transcript: TranscriptResult | None = None,
        precomputed_endpoint: EndpointDecision | None = None,
        player: AudioPlayer | None = None,
        on_tts_chunk: Callable[[SynthesizedAudio], None] | None = None,
        on_turn_started: Callable[[str], None] | None = None,
    ) -> VoiceTurnResult:
        """Обробити записану репліку користувача (16 кГц) від VAD до потокового TTS і live playback.

        Якщо передано precomputed_transcript (наприклад, із DuplexSession після gate-перевірки),
        повторне розпізнавання ASR не виконується (виправлення V-003).
        Якщо передано player, синтезовані фрази починають відтворюватися наживо ще під час
        генерації тексту моделлю (виправлення V-004).
        """
        self.mic.require_unmuted()
        t_start = time.perf_counter()

        earcon_ms: float | None = None
        if play_earcon:
            _, earcon_ms = generate_earcon_pcm()

        ep = precomputed_endpoint or self.endpoint.detect_utterance(audio_16k)
        target_audio = ep.speech_audio if len(ep.speech_audio) > 0 else audio_16k

        if precomputed_transcript is not None:
            transcript = precomputed_transcript
            endpoint_to_asr_ms = transcript.asr_latency_ms
        else:
            t_asr_start = time.perf_counter()
            transcript = await asyncio.to_thread(
                self.asr.transcribe, target_audio, language=language
            )
            endpoint_to_asr_ms = (time.perf_counter() - t_asr_start) * 1000.0

        if not transcript.text.strip():
            metrics = VoiceTurnMetrics(
                physical_eou_to_endpoint_ms=ep.physical_eou_to_endpoint_ms,
                endpoint_to_asr_ms=round(endpoint_to_asr_ms, 2),
                asr_to_first_token_ms=0.0,
                first_token_to_first_meaningful_audio_ms=0.0,
                endpoint_to_first_meaningful_audio_ms=round(endpoint_to_asr_ms, 2),
                physical_eou_to_first_meaningful_audio_ms=round(
                    ep.physical_eou_to_endpoint_ms + endpoint_to_asr_ms, 2
                ),
                earcon_ms=earcon_ms,
                total_turn_ms=round((time.perf_counter() - t_start) * 1000.0, 2),
            )
            return VoiceTurnResult(
                turn_id=None,
                session_id=session_id,
                state="empty_transcript",
                transcript=transcript,
                endpoint=ep,
                reply_text="",
                tts_chunks=(),
                metrics=metrics,
            )

        actor = self.runtime.control.resolve_actor(actor_id)
        caps = (
            owner_capabilities(self.runtime.settings) if actor.owner else tuple(GUEST_CAPABILITIES)
        )
        task_id = self.runtime.control.create_task(session_id)
        grant = self.runtime.control.issue_grant(
            actor.id,
            session_id,
            caps or ("time.read",),
            task_id=task_id,
            ttl_s=timeout_s + 3600,
            full_execution=actor.owner and self.runtime.settings.host_access == "full",
        )

        t_llm_start = time.perf_counter()
        first_token_at: float | None = None
        first_audio_at: float | None = None
        first_pcm_submitted_at: float | None = None
        llm_completed_at: float | None = None
        sentence_buffer = ""
        first_clause_queued = False

        sentence_queue: asyncio.Queue[str | None] = asyncio.Queue(
            maxsize=self.tts.max_queue_phrases
        )
        pcm_queue: asyncio.Queue[SynthesizedAudio | None] = asyncio.Queue(
            maxsize=self.tts.max_queue_phrases
        )
        tts_chunks: list[SynthesizedAudio] = []

        async def tts_synth_worker() -> None:
            nonlocal first_audio_at
            try:
                while True:
                    if cancel is not None and cancel.is_set():
                        break
                    sentence = await sentence_queue.get()
                    if sentence is None:
                        break
                    chunk = await asyncio.to_thread(self.tts.synthesize, sentence)
                    if cancel is not None and cancel.is_set():
                        break
                    if first_audio_at is None and chunk.pcm_int16:
                        first_audio_at = time.perf_counter()
                    if chunk.pcm_int16:
                        tts_chunks.append(chunk)
                        if on_tts_chunk is not None:
                            on_tts_chunk(chunk)
                        if player is not None:
                            await pcm_queue.put(chunk)
            finally:
                if player is not None:
                    with contextlib.suppress(asyncio.QueueFull):
                        pcm_queue.put_nowait(None)

        async def playback_worker() -> None:
            nonlocal first_pcm_submitted_at
            if player is None:
                return
            while True:
                if cancel is not None and cancel.is_set():
                    player.stop()
                    break
                item = await pcm_queue.get()
                if item is None:
                    break
                if first_pcm_submitted_at is None:
                    first_pcm_submitted_at = time.perf_counter()
                await player.play(item, cancel=cancel)
                if cancel is not None and cancel.is_set():
                    break

        synth_task = asyncio.create_task(tts_synth_worker())
        play_task = asyncio.create_task(playback_worker()) if player is not None else None

        async def on_event(event) -> None:
            nonlocal first_token_at, sentence_buffer, first_clause_queued
            if event.type == "turn_started":
                tid = event.data.get("turn_id")
                if tid and on_turn_started is not None:
                    on_turn_started(str(tid))
            elif event.type == "text_delta":
                if first_token_at is None:
                    first_token_at = time.perf_counter()
                sentence_buffer += event.data.get("text", "")
                ready, rem = extract_stream_clauses(
                    sentence_buffer,
                    is_first=not first_clause_queued,
                )
                if ready:
                    for clause in ready:
                        if cancel is not None and cancel.is_set():
                            break
                        await sentence_queue.put(clause)
                        first_clause_queued = True
                    sentence_buffer = rem
            elif event.type == "tool_started":
                sentence_buffer = ""

        try:
            turn_res = await self.runtime.agent.turn(
                session_id,
                grant,
                transcript.text,
                task_id=task_id,
                on_event=on_event,
                cancel=cancel,
                timeout_s=timeout_s,
                persist=persist,
            )
            llm_completed_at = time.perf_counter()
            if on_turn_started is not None and turn_res.turn_id:
                on_turn_started(str(turn_res.turn_id))
            tail = sentence_buffer.strip() or (
                turn_res.content.strip() if not first_clause_queued and not tts_chunks else ""
            )
            if tail and (cancel is None or not cancel.is_set()):
                for s in split_sentences(tail):
                    if cancel is not None and cancel.is_set():
                        break
                    await sentence_queue.put(s)
        finally:
            if cancel is not None and cancel.is_set():
                while not sentence_queue.empty():
                    with contextlib.suppress(asyncio.QueueEmpty):
                        sentence_queue.get_nowait()
            await sentence_queue.put(None)
            await synth_task
            if play_task is not None:
                if cancel is not None and cancel.is_set():
                    while not pcm_queue.empty():
                        with contextlib.suppress(asyncio.QueueEmpty):
                            pcm_queue.get_nowait()
                    with contextlib.suppress(asyncio.QueueFull):
                        pcm_queue.put_nowait(None)
                await play_task

        now = time.perf_counter()
        t_first_tok = first_token_at or now
        t_first_aud = first_audio_at or now
        asr_to_ft_ms = max(0.0, (t_first_tok - t_llm_start) * 1000.0)
        ft_to_audio_ms = max(0.0, (t_first_aud - t_first_tok) * 1000.0)
        ep_to_audio_ms = endpoint_to_asr_ms + asr_to_ft_ms + ft_to_audio_ms
        phys_to_audio_ms = ep.physical_eou_to_endpoint_ms + ep_to_audio_ms
        first_pcm_sub_ms = (
            round(max(0.0, (first_pcm_submitted_at - t_llm_start) * 1000.0), 2)
            if first_pcm_submitted_at is not None
            else None
        )
        started_before_done = bool(
            first_pcm_submitted_at is not None
            and llm_completed_at is not None
            and first_pcm_submitted_at <= llm_completed_at
        )

        metrics = VoiceTurnMetrics(
            physical_eou_to_endpoint_ms=round(ep.physical_eou_to_endpoint_ms, 2),
            endpoint_to_asr_ms=round(endpoint_to_asr_ms, 2),
            asr_to_first_token_ms=round(asr_to_ft_ms, 2),
            first_token_to_first_meaningful_audio_ms=round(ft_to_audio_ms, 2),
            endpoint_to_first_meaningful_audio_ms=round(ep_to_audio_ms, 2),
            physical_eou_to_first_meaningful_audio_ms=round(phys_to_audio_ms, 2),
            earcon_ms=earcon_ms,
            total_turn_ms=round((now - t_start) * 1000.0, 2),
            first_pcm_submitted_ms=first_pcm_sub_ms,
            playback_started_before_llm_completed=started_before_done,
        )
        return VoiceTurnResult(
            turn_id=turn_res.turn_id,
            session_id=session_id,
            state=turn_res.state,
            transcript=transcript,
            endpoint=ep,
            reply_text=turn_res.content,
            tts_chunks=tuple(tts_chunks),
            metrics=metrics,
        )
