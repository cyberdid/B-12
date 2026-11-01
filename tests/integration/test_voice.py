"""Інтеграційні тести голосового шару (Task 16 — Desktop Voice / PTT)."""

import asyncio

import numpy as np
import pytest

from b12.runtime import open_runtime


def _sine_speech(duration_s: float = 0.6, sr: int = 16000, freq: float = 220.0) -> np.ndarray:
    t = np.linspace(0.0, duration_s, int(sr * duration_s), endpoint=False)
    signal = 0.35 * np.sin(2 * np.pi * freq * t) + 0.15 * np.sin(2 * np.pi * (freq * 2) * t)
    return signal.astype(np.float32)


@pytest.mark.asyncio
async def test_ptt_mute_blocks_capture_and_no_durable_raw_audio(profile_settings, tmp_path):
    """RED: mute блокує захоплення, а сирий звук за замовчуванням не записується на диск."""
    from b12.audio.capture import MicController, PttCapture

    settings = profile_settings.model_copy(
        update={"state_dir": tmp_path / "state", "num_ctx": 32768, "output_tokens": 512}
    )
    runtime = open_runtime(settings)
    try:
        actor = runtime.control.create_actor(owner=True, consent=True)
        runtime.control.set_meta("owner_actor", actor.id)
        mic = MicController(runtime.control)

        assert mic.muted is False
        mic.set_muted(True)
        assert mic.muted is True
        # Mute is independent from memory consent
        assert runtime.control.resolve_actor(actor.id).consent is True

        capture = PttCapture(mic)
        with pytest.raises(PermissionError, match="microphone_muted"):
            await capture.record_from_source([_sine_speech(0.2)])

        mic.set_muted(False)
        pcm = await capture.record_from_source([_sine_speech(0.2), _sine_speech(0.2)])
        assert isinstance(pcm, np.ndarray)
        assert pcm.dtype == np.float32
        assert len(pcm) == int(16000 * 0.4)

        # Verify no raw .wav or .pcm files were written anywhere in state_dir
        raw_files = list((tmp_path / "state").rglob("*.wav")) + list(
            (tmp_path / "state").rglob("*.pcm")
        )
        assert raw_files == []
    finally:
        runtime.close()


@pytest.mark.asyncio
async def test_ptt_streaming_cancellation_stops_capture_immediately(profile_settings, tmp_path):
    """RED: скасування під час PTT негайно перериває потік захоплення."""
    from b12.audio.capture import MicController, PttCapture

    settings = profile_settings.model_copy(
        update={"state_dir": tmp_path / "state", "num_ctx": 32768, "output_tokens": 512}
    )
    runtime = open_runtime(settings)
    try:
        mic = MicController(runtime.control)
        capture = PttCapture(mic)
        cancel = asyncio.Event()

        async def slow_chunks():
            for i in range(20):
                if i == 2:
                    cancel.set()
                await asyncio.sleep(0.01)
                yield _sine_speech(0.05)

        pcm = await capture.record_from_source(slow_chunks(), cancel=cancel)
        # Should stop right after cancel is set (<= 3 chunks of 0.05s = 2400 samples)
        assert 0 < len(pcm) <= int(16000 * 0.2)
    finally:
        runtime.close()


@pytest.mark.asyncio
async def test_tts_bounded_phrase_queue_and_cancellation():
    """RED: черга фраз TTS обмежена (bounded), а скасування очищує чергу й зупиняє відтворення."""
    from b12.audio.tts import PiperTts, split_sentences

    sentences = split_sentences(
        "Привіт, Олександре! Система Б-12 готова до роботи. Перевіряємо третє речення."
    )
    assert sentences == [
        "Привіт, Олександре!",
        "Система Б-12 готова до роботи.",
        "Перевіряємо третє речення.",
    ]

    tts = PiperTts(max_queue_phrases=2)
    assert tts.max_queue_phrases == 2

    cancel = asyncio.Event()
    produced = []

    async for chunk in tts.stream_sentences(
        ["Перше речення для тесту.", "Друге речення для тесту.", "Третє речення."],
        cancel=cancel,
        on_first_chunk=lambda: cancel.set(),
    ):
        produced.append(chunk)

    assert len(produced) == 1
    assert produced[0].audio_int16_bytes
    assert produced[0].sample_rate > 0


@pytest.mark.asyncio
async def test_real_ua_en_codeswitch_tts_and_asr_roundtrip():
    """GREEN: реальний синтез Piper (UA/EN) і розпізнавання faster-whisper (UA/EN/code-switch)."""
    from b12.audio.asr import WhisperAsr
    from b12.audio.tts import PiperTts

    tts = PiperTts()
    asr = WhisperAsr()

    # 1. Ukrainian synthesis + ASR
    ua_synth = tts.synthesize("Привіт, Олександре! Система бі дванадцять працює стабільно.")
    assert ua_synth.sample_rate == 22050
    assert ua_synth.ttfa_ms > 0
    assert len(ua_synth.pcm_int16) > 10000

    ua_res = asr.transcribe_pcm(ua_synth.pcm_int16, sample_rate=ua_synth.sample_rate, language="uk")
    assert ua_res.language == "uk"
    assert "привіт" in ua_res.text.lower()
    assert "стабільно" in ua_res.text.lower()

    # 2. English synthesis + ASR
    en_synth = tts.synthesize(
        "Hello friend! The local voice pipeline is working properly.", lang="en"
    )
    assert en_synth.sample_rate == 22050
    en_res = asr.transcribe_pcm(en_synth.pcm_int16, sample_rate=en_synth.sample_rate, language="en")
    assert en_res.language == "en"
    assert "local" in en_res.text.lower() or "voice" in en_res.text.lower()

    # 3. Code-switch (UA + EN clauses)
    cs_synth = tts.synthesize("Система працює в режимі local runtime. Check status now.")
    cs_res = asr.transcribe_pcm(cs_synth.pcm_int16, sample_rate=cs_synth.sample_rate)
    assert len(cs_res.text.strip()) > 10


@pytest.mark.asyncio
async def test_voice_pipeline_metrics_and_transcript_provenance(profile_settings, tmp_path):
    """RED: метрики фізичного завершення та endpoint окремі від earcon; provenance у сесії."""
    from b12.audio.pipeline import VoicePipeline
    from b12.contracts import ModelReply

    class FakeModel:
        async def chat(self, admitted, *, on_delta=None, cancel=None, deadline=None):
            text = "Я почув тебе, Олександре. Голосовий конвеєр активний."
            if on_delta:
                for token in ("Я почув тебе, ", "Олександре. ", "Голосовий конвеєр активний."):
                    await on_delta(token)
            return ModelReply(
                content=text,
                tool_calls=(),
                metrics={"prompt_tokens": 30, "output_tokens": 12, "total_ms": 25.0},
                finish_reason="stop",
            )

    settings = profile_settings.model_copy(
        update={"state_dir": tmp_path / "state", "num_ctx": 32768, "output_tokens": 512}
    )
    runtime = open_runtime(settings, model=FakeModel())
    try:
        owner = runtime.control.create_actor(owner=True, consent=True)
        session_id = runtime.control.create_session(owner.id)
        runtime.control.set_meta("owner_actor", owner.id)
        runtime.control.set_meta("cli_session", session_id)

        pipeline = VoicePipeline(runtime)
        # Synthesize user prompt audio in Ukrainian, plus 0.4s trailing silence
        prompt_wav = pipeline.tts.synthesize("Привіт, запам'ятай що мій улюблений колір синій.")
        speech_16k = pipeline.asr.to_float32_16k(prompt_wav.pcm_int16, prompt_wav.sample_rate)
        silence_16k = np.zeros(int(16000 * 0.45), dtype=np.float32)
        full_utterance = np.concatenate([speech_16k, silence_16k])

        result = await pipeline.process_utterance(
            session_id=session_id,
            actor_id=owner.id,
            audio_16k=full_utterance,
            play_earcon=True,
        )

        assert result.transcript.text
        assert "привіт" in result.transcript.text.lower()
        assert result.reply_text == "Я почув тебе, Олександре. Голосовий конвеєр активний."
        assert len(result.tts_chunks) >= 1
        assert result.metrics.earcon_ms is not None
        assert result.metrics.physical_eou_to_endpoint_ms >= 0
        assert result.metrics.endpoint_to_first_meaningful_audio_ms > 0
        assert (
            result.metrics.physical_eou_to_first_meaningful_audio_ms
            >= result.metrics.endpoint_to_first_meaningful_audio_ms
        )
        # Verify transcript provenance in session history
        history = runtime.agent.history_messages(session_id, owner)
        assert any(m["role"] == "user" and "привіт" in m["content"].lower() for m in history)
    finally:
        runtime.close()


@pytest.mark.asyncio
async def test_voice_api_routes_status_mute_tts_asr_and_speaker(api):
    """Інтеграційний тест HTTP маршрутів /api/voice/* (status, mute, tts, asr, speaker)."""
    import base64

    _, client, token, _, _ = api
    headers = {"Authorization": f"Bearer {token}"}

    status_res = await client.get("/api/voice/status", headers=headers)
    assert status_res.status_code == 200
    data = status_res.json()
    assert data["muted"] is False
    assert data["uk_tts_ready"] is True

    # Synthesize via /api/voice/tts
    tts_res = await client.post(
        "/api/voice/tts",
        json={"text": "Привіт, перевірка голосового інтерфейсу.", "lang": "uk"},
        headers=headers,
    )
    assert tts_res.status_code == 200
    assert tts_res.headers["content-type"] == "audio/wav"
    assert float(tts_res.headers["x-ttfa-ms"]) > 0
    wav_bytes = tts_res.content
    assert wav_bytes[:4] == b"RIFF"

    # Mute blocks /api/voice/asr
    mute_res = await client.post("/api/voice/mute", json={"muted": True}, headers=headers)
    assert mute_res.status_code == 200 and mute_res.json()["muted"] is True

    asr_blocked = await client.post(
        "/api/voice/asr",
        json={"audio_b64": base64.b64encode(wav_bytes).decode(), "language": "uk"},
        headers=headers,
    )
    assert asr_blocked.status_code == 403

    # Unmute and run /api/voice/asr
    await client.post("/api/voice/mute", json={"muted": False}, headers=headers)
    asr_ok = await client.post(
        "/api/voice/asr",
        json={"audio_b64": base64.b64encode(wav_bytes).decode(), "language": "uk"},
        headers=headers,
    )
    assert asr_ok.status_code == 200
    asr_json = asr_ok.json()
    assert "привіт" in asr_json["text"].lower()
    assert asr_json["language"] == "uk"

    # Speaker enroll & delete via control channel
    enroll_res = await client.post(
        "/api/voice/speaker/enroll",
        json={"audio_b64": base64.b64encode(wav_bytes).decode()},
        headers=headers,
    )
    assert enroll_res.status_code == 200
    actor_id = enroll_res.json()["actor_id"]

    del_res = await client.delete(f"/api/voice/speaker/{actor_id}", headers=headers)
    assert del_res.status_code == 200 and del_res.json()["deleted"] is True
