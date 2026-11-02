"""Measurements for the acoustic path. Every number here says what it measured and on what.

Synthetic scenes (a linear echo with a known delay, no room, no noise) give an upper bound for
the echo canceller, never a physical result. Physical numbers come only from runs on real audio
hardware, recorded by `b12 voice live` and the physical checklist in docs/voice-physical-test.md.
"""

from __future__ import annotations

import numpy as np


def rms(x: np.ndarray) -> float:
    x = np.asarray(x, dtype=np.float64).reshape(-1)
    return float(np.sqrt(np.mean(x * x))) if len(x) else 0.0


def erle_db(echo_only: np.ndarray, residual: np.ndarray) -> float:
    """Echo return loss enhancement: how much the canceller lowers the echo, in dB."""
    return float(20.0 * np.log10(max(1e-12, rms(echo_only)) / max(1e-12, rms(residual))))


def delay_error_samples(estimate: int, truth: int) -> int:
    return int(estimate) - int(truth)


def false_trigger_rate(flags, truth) -> float:
    """Share of non-speech frames that the detector flagged as speech."""
    flags = np.asarray(flags, dtype=bool)
    truth = np.asarray(truth, dtype=bool)
    silent = ~truth
    if not silent.any():
        return 0.0
    return float(np.mean(flags[silent]))


def summarize_ms(values) -> dict:
    """P50/P95 with the count, as every latency report in this project must show them."""
    arr = np.asarray([v for v in values if v is not None], dtype=np.float64)
    if len(arr) == 0:
        return {"n": 0, "p50": None, "p95": None, "max": None}
    return {
        "n": int(len(arr)),
        "p50": round(float(np.percentile(arr, 50)), 2),
        "p95": round(float(np.percentile(arr, 95)), 2),
        "max": round(float(arr.max()), 2),
    }
