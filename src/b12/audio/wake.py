"""Локальне виявлення wake word (Step 1): інтерфейс детектора, рефрактер 2 с, RAM ring buffer.

Перед активацією утримується лише кільцевий буфер на 1,5 с в оперативній пам'яті;
жодних записів на диск не виконується. Завантаження реальної ONNX-моделі openWakeWord
(Step 2) заблоковано до окремого схвалення власника.
"""

from __future__ import annotations

import math
import time
from collections import deque
from collections.abc import Callable

import numpy as np

DEFAULT_SAMPLE_RATE = 16000
DEFAULT_FRAME_SAMPLES = 512


class WakeDetector:
    """Frame-level wake-word detector with refractory cooldown and RAM-only ring buffer."""

    def __init__(
        self,
        *,
        threshold: float = 0.5,
        refractory_s: float = 2.0,
        ring_buffer_s: float = 1.5,
        sample_rate: int = DEFAULT_SAMPLE_RATE,
        frame_samples: int = DEFAULT_FRAME_SAMPLES,
        scorer: Callable[[np.ndarray], float] | None = None,
        clock: Callable[[], float] | None = None,
    ):
        if not math.isfinite(threshold) or not (0.0 <= threshold <= 1.0):
            raise ValueError("threshold must be between 0.0 and 1.0")
        if not math.isfinite(refractory_s) or refractory_s < 0.0:
            raise ValueError("refractory_s must be non-negative and finite")
        if not math.isfinite(ring_buffer_s) or ring_buffer_s <= 0.0:
            raise ValueError("ring_buffer_s must be positive and finite")
        if sample_rate <= 0 or frame_samples <= 0:
            raise ValueError("sample_rate and frame_samples must be positive")

        self.threshold = float(threshold)
        self.refractory_s = float(refractory_s)
        self.ring_buffer_s = float(ring_buffer_s)
        self.sample_rate = int(sample_rate)
        self.frame_samples = int(frame_samples)
        self._scorer = scorer
        self._clock = clock or time.monotonic

        max_frames = max(1, round(self.ring_buffer_s * self.sample_rate / self.frame_samples))
        self._ring: deque[np.ndarray] = deque(maxlen=max_frames)
        self._last_trigger_at: float | None = None

    @property
    def ring_buffer_frames(self) -> int:
        return len(self._ring)

    @property
    def ring_buffer_seconds(self) -> float:
        return sum(len(chunk) for chunk in self._ring) / self.sample_rate

    def ring_buffer_audio(self) -> np.ndarray:
        """Return a copy of the in-memory ring buffer; never reads or writes disk."""
        if not self._ring:
            return np.zeros(0, dtype=np.float32)
        return np.concatenate(list(self._ring)).astype(np.float32)

    def reset(self) -> None:
        self._ring.clear()
        self._last_trigger_at = None

    def score(self, frame: np.ndarray) -> float:
        """Score one audio frame in [0, 1]. Step 1 returns 0.0 when no scorer is wired."""
        if self._scorer is None:
            return 0.0
        return float(self._scorer(frame))

    def feed(self, frame: np.ndarray) -> bool:
        """Buffer frame in RAM, score it, and enforce the 2 s refractory period."""
        arr = np.asarray(frame, dtype=np.float32).reshape(-1).copy()
        arr.setflags(write=False)
        self._ring.append(arr)

        prob = self.score(arr)
        if prob < self.threshold:
            return False

        now = float(self._clock())
        if self._last_trigger_at is not None and (now - self._last_trigger_at) < self.refractory_s:
            return False
        self._last_trigger_at = now
        return True
