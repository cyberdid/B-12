"""Голосовий конвеєр B-12: PTT/utterance → VAD/endpoint → ASR → Agent → streaming TTS."""

import asyncio
import time
from dataclasses import dataclass
from typing import Literal

import numpy as np

from b12.audio.asr import TranscriptResult, WhisperAsr
from b12.audio.capture import MicController, PttCapture
from b12.audio.endpoint import EndpointDecision, EndpointDetector
from b12.audio.tts import PiperTts, SynthesizedAudio, generate_earcon_pcm, split_sentences
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
    """Повний голосовий цикл із роздільним вимірюванням endpoint, ASR, LLM TTFT та TTS."""

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
    ) -> VoiceTurnResult:
        """Обробити записану репліку користувача (16 кГц float32) від VAD до потокового TTS."""
        self.mic.require_unmuted()
        t_start = time.perf_counter()

        earcon_ms: float | None = None
        if play_earcon:
            _, earcon_ms = generate_earcon_pcm()

        ep = self.endpoint.detect_utterance(audio_16k)
        target_audio = ep.speech_audio if len(ep.speech_audio) > 0 else audio_16k

        t_asr_start = time.perf_counter()
        transcript = await asyncio.to_thread(self.asr.transcribe, target_audio, language=language)
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
        sentence_buffer = ""
        sentence_queue: asyncio.Queue[str | None] = asyncio.Queue(
            maxsize=self.tts.max_queue_phrases
        )
        tts_chunks: list[SynthesizedAudio] = []

        async def tts_worker() -> None:
            nonlocal first_audio_at
            while True:
                if cancel is not None and cancel.is_set():
                    break
                sentence = await sentence_queue.get()
                if sentence is None:
                    break
                chunk = await asyncio.to_thread(self.tts.synthesize, sentence)
                if first_audio_at is None and chunk.pcm_int16:
                    first_audio_at = time.perf_counter()
                if chunk.pcm_int16:
                    tts_chunks.append(chunk)

        worker_task = asyncio.create_task(tts_worker())

        async def on_event(event) -> None:
            nonlocal first_token_at, sentence_buffer
            if event.type == "text_delta":
                if first_token_at is None:
                    first_token_at = time.perf_counter()
                sentence_buffer += event.data.get("text", "")
                parts = split_sentences(sentence_buffer)
                if len(parts) > 1:
                    for complete in parts[:-1]:
                        await sentence_queue.put(complete)
                    sentence_buffer = parts[-1]
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
            tail = sentence_buffer.strip() or (turn_res.content.strip() if not tts_chunks else "")
            if tail and (cancel is None or not cancel.is_set()):
                for s in split_sentences(tail):
                    await sentence_queue.put(s)
        finally:
            await sentence_queue.put(None)
            await worker_task

        now = time.perf_counter()
        t_first_tok = first_token_at or now
        t_first_aud = first_audio_at or now
        asr_to_ft_ms = max(0.0, (t_first_tok - t_llm_start) * 1000.0)
        ft_to_audio_ms = max(0.0, (t_first_aud - t_first_tok) * 1000.0)
        ep_to_audio_ms = endpoint_to_asr_ms + asr_to_ft_ms + ft_to_audio_ms
        phys_to_audio_ms = ep.physical_eou_to_endpoint_ms + ep_to_audio_ms

        metrics = VoiceTurnMetrics(
            physical_eou_to_endpoint_ms=round(ep.physical_eou_to_endpoint_ms, 2),
            endpoint_to_asr_ms=round(endpoint_to_asr_ms, 2),
            asr_to_first_token_ms=round(asr_to_ft_ms, 2),
            first_token_to_first_meaningful_audio_ms=round(ft_to_audio_ms, 2),
            endpoint_to_first_meaningful_audio_ms=round(ep_to_audio_ms, 2),
            physical_eou_to_first_meaningful_audio_ms=round(phys_to_audio_ms, 2),
            earcon_ms=earcon_ms,
            total_turn_ms=round((now - t_start) * 1000.0, 2),
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
