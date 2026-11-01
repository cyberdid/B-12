"""Інтеграційні тести full-duplex, AEC, barge-in та speaker identity (Task 17)."""

import asyncio

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


def test_aec_render_reference_cancels_tts_echo_and_prevents_self_trigger():
    """RED: точний TTS render reference пригнічує власне відлуння й блокує self-trigger."""
    from b12.audio.aec import AcousticEchoCanceller

    aec = AcousticEchoCanceller(sample_rate=16000, filter_length=256)
    tts_ref = _voice_signal(0.6, f0=190.0)
    # Simulate speaker-to-mic acoustic echo (attenuated + slight delay)
    echo_mic = 0.65 * tts_ref
    aec.feed_render_reference(tts_ref)

    cleaned, stats = aec.process_capture(echo_mic)
    assert stats.echo_return_loss_enhancement_db > 6.0
    assert stats.is_echo_dominant is True
    assert float(np.sqrt(np.mean(cleaned**2))) < float(np.sqrt(np.mean(echo_mic**2))) * 0.4

    # Text-level self-trigger guard
    aec.record_tts_utterance("Система Б-12 працює у штатному режимі.")
    assert aec.is_tts_echo_text("Система Б-12 працює у штатному режимі") is True
    assert aec.is_tts_echo_text("Яка зараз година у Києві?") is False


def test_speaker_enrollment_control_boundary_and_physiological_purge(profile_settings, tmp_path):
    """RED: реєстрація голосу неможлива через інструменти моделі; видалення стирає біометрію."""
    from b12.audio.speaker import SpeakerStore, SpeakerVerifier

    settings = profile_settings.model_copy(
        update={"state_dir": tmp_path / "state", "num_ctx": 32768, "output_tokens": 512}
    )
    runtime = open_runtime(settings)
    try:
        # 1. Model tool catalog must never expose speaker enrollment or voiceprint modification
        tool_names = {t["name"] for t in runtime.registry.catalog()}
        assert not any("enroll" in name or "speaker" in name for name in tool_names)

        owner = runtime.control.create_actor(owner=True, consent=True)
        guest = runtime.control.create_actor(owner=False, consent=False)
        runtime.control.set_meta("owner_actor", owner.id)

        store = SpeakerStore(settings.state_dir / "voice" / "speakers.sqlite3")
        verifier = SpeakerVerifier(store, runtime.control)

        owner_sample_1 = _voice_signal(1.0, f0=135.0)
        owner_sample_2 = _voice_signal(1.0, f0=137.0)
        stranger_sample = _voice_signal(1.0, f0=265.0)

        # Guest without consent or owner privilege cannot enroll owner
        with pytest.raises(PermissionError):
            verifier.enroll(actor_id=guest.id, caller_actor_id=guest.id, audio_16k=owner_sample_1)

        # Owner enrolls via control channel
        profile = verifier.enroll(
            actor_id=owner.id, caller_actor_id=owner.id, audio_16k=owner_sample_1
        )
        assert profile["actor_id"] == owner.id

        # Verify owner match vs stranger rejection
        match_owner = verifier.verify(owner_sample_2)
        assert match_owner.matched is True
        assert match_owner.actor_id == owner.id
        assert match_owner.score >= match_owner.threshold
        assert match_owner.is_spoof_or_replay is False

        match_stranger = verifier.verify(stranger_sample)
        assert match_stranger.matched is False

        # Exact bit-for-bit replay of enrollment audio is flagged as replay attack!
        replay_attempt = verifier.verify(owner_sample_1)
        assert replay_attempt.is_spoof_or_replay is True
        assert replay_attempt.matched is False

        # Physiological data deletion wipes embedding from SQLite store
        assert store.delete_actor(owner.id) is True
        assert verifier.verify(owner_sample_2).matched is False
        store.close()
    finally:
        runtime.close()


@pytest.mark.asyncio
async def test_duplex_barge_in_stops_playback_and_flushes_queue(profile_settings, tmp_path):
    """RED: barge-in під час активного відтворення негайно зупиняє звук і очищує чергу TTS."""
    from b12.audio.duplex import DuplexSession

    class SlowStreamingModel:
        async def chat(self, admitted, *, on_delta=None, cancel=None, deadline=None):
            sentences = [
                "Перша довга фраза для перевірки дуплексного режиму. ",
                "Друга довга фраза яка має бути перервана користувачем. ",
                "Третя фраза яка ніколи не повинна відтворитися.",
            ]
            out = ""
            for s in sentences:
                if cancel and cancel.is_set():
                    break
                out += s
                if on_delta:
                    await on_delta(s)
                await asyncio.sleep(0.05)
            return ModelReply(
                content=out,
                tool_calls=(),
                metrics={"prompt_tokens": 20, "output_tokens": 20, "total_ms": 50.0},
                finish_reason="stop",
            )

    settings = profile_settings.model_copy(
        update={"state_dir": tmp_path / "state", "num_ctx": 32768, "output_tokens": 512}
    )
    runtime = open_runtime(settings, model=SlowStreamingModel())
    try:
        owner = runtime.control.create_actor(owner=True, consent=True)
        session_id = runtime.control.create_session(owner.id)
        runtime.control.set_meta("owner_actor", owner.id)

        duplex = DuplexSession(runtime, session_id=session_id, actor_id=owner.id)
        # Start a background speaking turn
        turn_task = asyncio.create_task(
            duplex.speak_response("Перше речення для озвучення. Друге речення. Третє речення.")
        )
        await asyncio.sleep(0.05)

        # User barges in with strong near-field speech not matching render reference
        user_barge = _voice_signal(0.4, f0=145.0) * 1.5
        barge_result = await duplex.feed_capture_frame(user_barge)
        assert barge_result.barge_in_triggered is True
        assert barge_result.time_to_stop_ms is not None
        assert barge_result.time_to_stop_ms < 200.0
        assert duplex.player.is_playing is False
        assert duplex.tts_queue_size == 0

        await turn_task
    finally:
        runtime.close()
