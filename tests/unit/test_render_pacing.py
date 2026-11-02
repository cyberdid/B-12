"""The render reference is fed as audio is written, not all at once (A-06)."""

import numpy as np

from b12.audio.tts import AudioPlayer, SynthesizedAudio


async def test_reference_arrives_in_blocks_over_the_playback_not_before_it():
    calls = []
    player = AudioPlayer(on_render_reference=calls.append, use_hardware=False)
    player.simulated_max_duration_s = 0.6
    pcm = (np.sin(np.linspace(0, 40, 9600)) * 8000).astype(np.int16).tobytes()  # 0.6 s at 16 kHz
    audio = SynthesizedAudio(
        text="тест", language="uk", sample_rate=16000, pcm_int16=pcm, ttfa_ms=1.0, duration_s=0.6
    )
    await player.play(audio)
    assert len(calls) >= 3, "the reference must arrive over time, in several blocks"
    assert max(len(c) for c in calls) < 9600, "no single call may carry the whole sentence"
    assert sum(len(c) for c in calls) <= 9600


async def test_stop_measured_reports_signal_and_exit_separately():
    """A-15: the time of the signal and the time of the process exit are not the physical stop."""
    import asyncio

    class FakeProc:
        def __init__(self):
            self.returncode = None
            self.terminated = False

        def terminate(self):
            self.terminated = True
            asyncio.get_running_loop().call_later(0.05, self._exit)

        def _exit(self):
            self.returncode = -15

        async def wait(self):
            while self.returncode is None:
                await asyncio.sleep(0.005)
            return self.returncode

    player = AudioPlayer(use_hardware=True)
    player._proc = FakeProc()
    result = await player.stop_measured()
    assert result["process"] == "exited"
    assert result["exit_ms"] >= result["signal_ms"] >= 0.0
    assert result["exit_ms"] >= 40.0  # the exit came after the signal, not at the same instant
