"""Інтеграційні тести full-duplex, NLMS AEC, live streaming та scoped barge-in (V-001..V-011)."""

import asyncio
import time

import numpy as np
import pytest

from b12.contracts import ModelReply
from b12.runtime import open_runtime


def _voice_signal(duration_s: float = 0.8, sr: int = 16000, f0: float = 165.0) -> np.ndarray:
    t = np.linspace(0.0, duration_s, int(sr * duration_s), endpoint=False)
    envelope = np.clip(np.sin(np.pi * t / duration_s) * 1.4, 0.2, 1.0)
    wave = (
        0.45 * np.sin(2 * np.pi * f0 * t)
        + 0.25 * np.sin(2 * np.pi * (f0 * 2) * t + 0.3)
        + 0.15 * np.sin(2 * np.pi * (f0 * 3) * t + 0.7)
        + 0.08 * np.sin(2 * np.pi * (f0 * 4) * t + 1.1)
    )
    return (wave * envelope).astype(np.float32)


def test_aec_nlms_render_reference_delay_alignment_and_short_reply_guard():
    """V-008, V-011: багатотаповий NLMS AEC з вирівнюванням затримки та захист відповідей."""
    from b12.audio.aec import AcousticEchoCanceller

    aec = AcousticEchoCanceller(sample_rate=16000, filter_length=128)
    tts_ref = _voice_signal(0.6, f0=190.0)
    # Симулюємо акустичне відлуння із затримкою 24 семпли (1.5 мс) та загасанням
    delayed_echo = np.concatenate([np.zeros(24, dtype=np.float32), 0.65 * tts_ref[:-24]])
    aec.feed_render_reference(tts_ref)

    cleaned, stats = aec.process_capture(delayed_echo)
    assert stats.echo_return_loss_enhancement_db > 6.0
    assert stats.delay_samples >= 0
    assert stats.is_echo_dominant is True
    assert float(np.sqrt(np.mean(cleaned**2))) < float(np.sqrt(np.mean(delayed_echo**2))) * 0.4

    # V-011: Текстовий anti-self-trigger блокує точне повторення фрази B-12,
    # але НЕ відхиляє короткі відповіді користувача («Так», «Зараз», «Ні»)
    aec.record_tts_utterance("Ти хочеш запустити перевірку системи зараз чи пізніше?")
    assert aec.is_tts_echo_text("Ти хочеш запустити перевірку системи зараз чи пізніше") is True
    assert aec.is_tts_echo_text("Зараз") is False
    assert aec.is_tts_echo_text("Так, зараз") is False
    assert aec.is_tts_echo_text("Яка зараз година у Києві?") is False


def test_speaker_enrollment_control_boundary_and_physiological_purge(profile_settings, tmp_path):
    """Реєстрація голосу неможлива через інструменти моделі; видалення стирає біометрію."""
    from b12.audio.speaker import SpeakerStore, SpeakerVerifier

    settings = profile_settings.model_copy(
        update={"state_dir": tmp_path / "state", "num_ctx": 32768, "output_tokens": 512}
    )
    runtime = open_runtime(settings)
    try:
        tool_names = {t["name"] for t in runtime.registry.catalog()}
        assert not any("enroll" in name or "speaker" in name for name in tool_names)

        owner = runtime.control.create_actor(owner=True, consent=True)
        guest = runtime.control.create_actor(owner=False, consent=False)
        runtime.control.set_meta("owner_actor", owner.id)

        store = SpeakerStore(settings.state_dir / "voice" / "speakers.sqlite3")
        runtime.purge.speakers = store
        verifier = SpeakerVerifier(store, runtime.control)

        owner_sample_1 = _voice_signal(1.0, f0=135.0)
        owner_sample_2 = _voice_signal(1.0, f0=137.0)
        stranger_sample = _voice_signal(1.0, f0=265.0)

        with pytest.raises(PermissionError):
            verifier.enroll(actor_id=guest.id, caller_actor_id=guest.id, audio_16k=owner_sample_1)

        profile = verifier.enroll(
            actor_id=owner.id, caller_actor_id=owner.id, audio_16k=owner_sample_1
        )
        assert profile["actor_id"] == owner.id

        match_owner = verifier.verify(owner_sample_2)
        assert match_owner.matched is True
        assert match_owner.actor_id == owner.id
        assert match_owner.score >= match_owner.threshold
        assert match_owner.is_spoof_or_replay is False

        match_stranger = verifier.verify(stranger_sample)
        assert match_stranger.matched is False

        replay_attempt = verifier.verify(owner_sample_1)
        assert replay_attempt.is_spoof_or_replay is True
        assert replay_attempt.matched is False

        # Координоване видалення через PurgeCoordinator.forget_voice_profile
        assert runtime.purge.forget_voice_profile(owner.id) is True
        assert verifier.verify(owner_sample_2).matched is False
        store.close()
    finally:
        runtime.close()


@pytest.mark.asyncio
async def test_speak_response_over_8_sentences_no_deadlock_and_live_playback(
    profile_settings, tmp_path
):
    """V-001, V-004: speak_response() на 12 реченнях не зависає і грає першу фразу наживо."""
    from b12.audio.duplex import DuplexSession
    from b12.audio.tts import SynthesizedAudio

    settings = profile_settings.model_copy(
        update={"state_dir": tmp_path / "state", "num_ctx": 32768, "output_tokens": 512}
    )
    runtime = open_runtime(settings)
    try:
        owner = runtime.control.create_actor(owner=True, consent=True)
        session_id = runtime.control.create_session(owner.id)
        runtime.control.set_meta("owner_actor", owner.id)

        duplex = DuplexSession(runtime, session_id=session_id, actor_id=owner.id)
        duplex.player.simulated_max_duration_s = 0.02

        synth_timestamps: list[float] = []
        play_timestamps: list[float] = []

        def fast_mock_synth(text: str, *, lang: str = "auto") -> SynthesizedAudio:
            time.sleep(0.01)
            synth_timestamps.append(time.perf_counter())
            pcm = (np.sin(np.linspace(0, 50, 1600)) * 8000).astype(np.int16).tobytes()
            return SynthesizedAudio(
                text=text,
                language="uk",
                sample_rate=16000,
                pcm_int16=pcm,
                ttfa_ms=5.0,
                duration_s=0.1,
            )

        duplex.pipeline.tts.synthesize = fast_mock_synth  # type: ignore[method-assign]
        duplex.player.on_playback_start = lambda: play_timestamps.append(time.perf_counter())

        long_text = " ".join(f"Речення номер {i} для перевірки черги." for i in range(1, 13))
        played = await asyncio.wait_for(duplex.speak_response(long_text), timeout=5.0)

        assert len(played) == 12
        assert len(synth_timestamps) == 12
        assert len(play_timestamps) == 12
        # Перше речення почало грати ДО того, як синтезувалося 12-те речення!
        assert play_timestamps[0] < synth_timestamps[-1]
        duplex.close()
    finally:
        runtime.close()


@pytest.mark.asyncio
async def test_single_pass_aec_and_single_pass_asr_in_handle_duplex_utterance(
    profile_settings, tmp_path
):
    """V-002, V-003, V-004: handle_duplex_utterance викликає AEC та ASR рівно 1 раз."""
    from b12.audio.asr import TranscriptResult
    from b12.audio.duplex import DuplexSession
    from b12.audio.tts import SynthesizedAudio

    llm_done_at = 0.0

    class MultiClauseModel:
        async def chat(self, admitted, *, on_delta=None, cancel=None, deadline=None):
            nonlocal llm_done_at
            clauses = [
                "Привіт Олександре, я уважно слухаю тебе. ",
                "Зараз перевіряю стан усіх підсистем. ",
                "Усі локальні сервіси працюють відмінно.",
            ]
            out = ""
            for c in clauses:
                out += c
                if on_delta:
                    await on_delta(c)
                await asyncio.sleep(0.04)
            llm_done_at = time.perf_counter()
            return ModelReply(
                content=out.strip(),
                tool_calls=(),
                metrics={"prompt_tokens": 24, "output_tokens": 24, "total_ms": 120.0},
                finish_reason="stop",
            )

    settings = profile_settings.model_copy(
        update={"state_dir": tmp_path / "state", "num_ctx": 32768, "output_tokens": 512}
    )
    runtime = open_runtime(settings, model=MultiClauseModel())
    try:
        owner = runtime.control.create_actor(owner=True, consent=True)
        session_id = runtime.control.create_session(owner.id)
        runtime.control.set_meta("owner_actor", owner.id)

        duplex = DuplexSession(runtime, session_id=session_id, actor_id=owner.id)
        duplex.player.simulated_max_duration_s = 0.02

        def fast_synth(text: str, *, lang: str = "auto") -> SynthesizedAudio:
            pcm = (np.sin(np.linspace(0, 50, 1600)) * 8000).astype(np.int16).tobytes()
            return SynthesizedAudio(
                text=text,
                language="uk",
                sample_rate=16000,
                pcm_int16=pcm,
                ttfa_ms=4.0,
                duration_s=0.1,
            )

        asr_inputs: list[np.ndarray] = []

        def fake_transcribe(audio_16k: np.ndarray, *, language: str = "auto") -> TranscriptResult:
            duplex.pipeline.asr.transcribe_count += 1
            asr_inputs.append(audio_16k)
            return TranscriptResult(
                text="Перевір будь ласка стан підсистем",
                language="uk",
                language_probability=0.99,
                duration_s=len(audio_16k) / 16000.0,
                asr_latency_ms=12.5,
                provenance_id="prov-1",
            )

        duplex.pipeline.tts.synthesize = fast_synth  # type: ignore[method-assign]
        duplex.pipeline.asr.transcribe = fake_transcribe  # type: ignore[method-assign]

        user_audio = _voice_signal(0.6, f0=150.0)
        res = await duplex.handle_duplex_utterance(user_audio, live_playback=True)

        assert res is not None
        # V-002: AEC викликано рівно 1 раз
        assert duplex.aec.call_count == 1
        # V-003: ASR викликано рівно 1 раз
        assert duplex.pipeline.asr.transcribe_count == 1
        assert len(asr_inputs) == 1
        # V-004: Перша фраза була передана в плеєр ДО завершення генерації LLM
        assert res.metrics.playback_started_before_llm_completed is True
        assert res.metrics.first_pcm_submitted_ms is not None
        duplex.close()
    finally:
        runtime.close()


@pytest.mark.asyncio
async def test_duplex_barge_in_stops_playback_and_is_scoped_to_voice_session(
    profile_settings, tmp_path
):
    """V-005: barge-in зупиняє звук і скасовує лише хід своєї голосової сесії."""
    from b12.agent import _Active
    from b12.audio.duplex import DuplexSession

    settings = profile_settings.model_copy(
        update={"state_dir": tmp_path / "state", "num_ctx": 32768, "output_tokens": 512}
    )
    runtime = open_runtime(settings)
    try:
        owner = runtime.control.create_actor(owner=True, consent=True)
        voice_session = runtime.control.create_session(owner.id)
        runtime.control.create_session(owner.id)
        runtime.control.set_meta("owner_actor", owner.id)

        duplex = DuplexSession(runtime, session_id=voice_session, actor_id=owner.id)
        # Симулюємо паралельний активний хід у web_session та активний хід у voice_session
        web_cancel = asyncio.Event()
        voice_cancel = asyncio.Event()
        runtime.agent.active["turn-web-1"] = _Active(owner.id, web_cancel)
        runtime.agent.active["turn-voice-1"] = _Active(owner.id, voice_cancel)
        duplex._active_turn_id = "turn-voice-1"

        turn_task = asyncio.create_task(
            duplex.speak_response("Перше речення для озвучення. Друге речення. Третє речення.")
        )
        await asyncio.sleep(0.05)

        # Реальне синтезоване українське мовлення для перебивання (ONNX Silero VAD)
        barge_wav = duplex.pipeline.tts.synthesize("Стоп, зачекай будь ласка!")
        user_barge = barge_wav.to_float32_16k() * 1.4
        barge_result = await duplex.feed_capture_frame(user_barge)

        assert barge_result.barge_in_triggered is True
        assert barge_result.time_to_stop_ms is not None
        assert barge_result.time_to_stop_ms < 200.0
        assert duplex.player.is_playing is False
        assert duplex.tts_queue_size == 0
        # V-005: Голосовий хід скасовано, а паралельний web-хід НЕ скасовано!
        assert voice_cancel.is_set() is True
        assert web_cancel.is_set() is False

        await turn_task
        duplex.close()
    finally:
        runtime.close()
