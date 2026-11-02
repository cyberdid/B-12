"""Echo canceller quality on SYNTHETIC scenes (a linear echo, no room, no noise).

These bound the canceller from above and guard against regressions. They are not physical
measurements: physical results come only from the checklist in docs/voice-physical-test.md.
"""

import numpy as np

from b12.audio.aec import FRAME_SAMPLES_16K as FRAME
from b12.audio.aec import AcousticEchoCanceller
from b12.audio.measure import delay_error_samples, erle_db
from tests.integration.test_duplex import _voice_signal

SR = 16000


def _broadband(seconds: float, seed: int) -> np.ndarray:
    rng = np.random.default_rng(seed)
    n = int(SR * seconds)
    envelope = np.repeat(rng.uniform(0.2, 0.6, n // 800 + 2), 800)[:n]
    return (rng.standard_normal(n).astype(np.float32) * envelope * 0.3).astype(np.float32)


def _run(ref: np.ndarray, mic: np.ndarray, *, feed_ahead: int = 1600):
    """Feed the reference as playback would (block by block, ahead of capture) and process mic."""
    aec = AcousticEchoCanceller()
    fed, out, delays, dt = 0, [], [], []
    for i in range(0, len(mic) - FRAME + 1, FRAME):
        while fed < len(ref) and fed <= i + feed_ahead:
            aec.feed_render_reference(ref[fed : fed + 1600])
            fed += 1600
        cleaned, stats = aec.process_capture(mic[i : i + FRAME])
        out.append(cleaned)
        delays.append(stats.delay_samples)
        dt.append(stats.double_talk_detected)
    return np.concatenate(out), np.array(delays), np.array(dt)


def _echo(ref: np.ndarray, delay: int, gain: float = 0.6) -> np.ndarray:
    return (np.concatenate([np.zeros(delay, np.float32), gain * ref[:-delay]])).astype(np.float32)


def test_a_delay_longer_than_one_frame_is_estimated_and_cancelled():
    """A-06: 200 ms is six frames; the old canceller searched 16 ms and could not see it."""
    ref = _broadband(6.0, seed=1)
    mic = _echo(ref, 3200)
    out, delays, _ = _run(ref, mic)
    warm = len(delays) // 2
    assert set(delays[warm:].tolist()) == {3200}
    assert delay_error_samples(int(np.median(delays[warm:])), 3200) == 0
    tail = slice(int(SR * 3), None)
    assert erle_db(mic[tail], out[tail]) > 30.0


def test_a_short_delay_and_a_long_delay_are_both_found_exactly():
    ref = _broadband(6.0, seed=2)
    for delay in (0, 640, 5600):
        mic = _echo(ref, delay) if delay else (0.6 * ref).astype(np.float32)
        _, delays, _ = _run(ref, mic)
        assert set(delays[len(delays) // 2 :].tolist()) == {delay}


def test_periodic_voice_like_echo_is_still_cancelled():
    ref = _voice_signal(6.0, sr=SR, f0=150.0)
    mic = _echo(ref, 640)
    out, _, _ = _run(ref, mic)
    tail = slice(int(SR * 3), None)
    assert erle_db(mic[tail], out[tail]) > 25.0


def test_double_talk_keeps_the_users_speech():
    """While B-12 and the user talk together, the output must still carry the user's speech."""
    ref = _broadband(8.0, seed=3)
    near = _broadband(8.0, seed=4) * (2.0 / 3.0)
    near[: 3 * SR] = 0.0  # the user is silent for the first 3 s, then talks over B-12
    mic = _echo(ref, 2400) + near
    out, _, dt = _run(ref, mic)
    seg = slice(5 * SR, None)
    corr = float(np.corrcoef(out[seg], near[seg])[0, 1])
    assert corr > 0.8, f"user's speech lost under double talk: corr={corr:.3f}"
    assert dt[len(dt) // 2 :].any(), "double talk must be detected while both are active"
