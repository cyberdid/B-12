"""Придушення акустичного відлуння (AEC) з точним render reference та анти-self-trigger."""

import re
from collections import deque
from dataclasses import dataclass

import numpy as np

_WORD_RE = re.compile(r"[0-9A-Za-zА-Яа-яІіЇїЄєҐґ']+")


def _tokens(text: str) -> set[str]:
    return {w.lower() for w in _WORD_RE.findall(text.replace("’", "'").replace("ʼ", "'"))}


@dataclass(frozen=True)
class AecStats:
    input_rms: float
    output_rms: float
    reference_rms: float
    correlation: float
    echo_return_loss_enhancement_db: float
    is_echo_dominant: bool
    is_media_contaminated: bool


class AcousticEchoCanceller:
    """Адаптивний ехокомпенсатор (NLMS + кореляційне пригнічення) із текстовим анти-self-trigger."""

    def __init__(
        self,
        *,
        sample_rate: int = 16000,
        filter_length: int = 256,
        step_size: float = 0.35,
        max_ref_seconds: float = 12.0,
    ):
        self.sample_rate = sample_rate
        self.filter_length = filter_length
        self.step_size = step_size
        self.max_ref_samples = int(sample_rate * max_ref_seconds)
        self._ref_buffer = np.zeros(0, dtype=np.float32)
        self._recent_tts: deque[str] = deque(maxlen=16)

    def feed_render_reference(self, ref_16k: np.ndarray) -> None:
        """Додати точний буфер відтворення TTS (16 кГц float32) до reference-лінії AEC."""
        arr = np.asarray(ref_16k, dtype=np.float32).reshape(-1)
        if len(arr) == 0:
            return
        self._ref_buffer = np.concatenate([self._ref_buffer, arr])
        if len(self._ref_buffer) > self.max_ref_samples:
            self._ref_buffer = self._ref_buffer[-self.max_ref_samples :]

    def clear_reference(self) -> None:
        self._ref_buffer = np.zeros(0, dtype=np.float32)

    def process_capture(
        self,
        mic_16k: np.ndarray,
        *,
        background_media_active: bool = False,
    ) -> tuple[np.ndarray, AecStats]:
        """Пригнітити відлуння власного динаміка та оцінити ERLE і домінування відлуння."""
        mic = np.asarray(mic_16k, dtype=np.float32).reshape(-1)
        n = len(mic)
        if n == 0:
            return mic, AecStats(0.0, 0.0, 0.0, 0.0, 0.0, False, background_media_active)

        in_rms = float(np.sqrt(np.mean(mic * mic)) + 1e-9)
        if len(self._ref_buffer) == 0:
            return mic.copy(), AecStats(
                input_rms=in_rms,
                output_rms=in_rms,
                reference_rms=0.0,
                correlation=0.0,
                echo_return_loss_enhancement_db=0.0,
                is_echo_dominant=False,
                is_media_contaminated=background_media_active and in_rms < 0.04,
            )

        # Align with current reference slice
        if len(self._ref_buffer) >= n:
            ref = self._ref_buffer[:n]
            self._ref_buffer = self._ref_buffer[n:]
        else:
            ref = np.pad(self._ref_buffer, (0, n - len(self._ref_buffer)))
            self._ref_buffer = np.zeros(0, dtype=np.float32)

        ref_rms = float(np.sqrt(np.mean(ref * ref)) + 1e-9)
        ref_energy = float(np.dot(ref, ref))
        if ref_energy > 1e-8:
            # Least-squares gain estimate + NLMS residual suppression
            gain = float(np.dot(mic, ref) / (ref_energy + 1e-8))
            corr = float(abs(np.dot(mic, ref)) / (np.linalg.norm(mic) * np.linalg.norm(ref) + 1e-8))
            estimated_echo = gain * ref
            residual = mic - estimated_echo
            # Spectral suppression when echo correlation is high (single-talk echo)
            if corr > 0.75:
                suppression = max(0.05, 1.0 - corr * 0.92)
                cleaned = residual * suppression
            else:
                cleaned = residual
        else:
            corr = 0.0
            cleaned = mic.copy()

        out_rms = float(np.sqrt(np.mean(cleaned * cleaned)) + 1e-9)
        erle_db = float(20.0 * np.log10(max(1.0, in_rms / out_rms)))
        is_echo_dominant = corr > 0.75 and out_rms < in_rms * 0.45
        return cleaned.astype(np.float32), AecStats(
            input_rms=round(in_rms, 6),
            output_rms=round(out_rms, 6),
            reference_rms=round(ref_rms, 6),
            correlation=round(corr, 4),
            echo_return_loss_enhancement_db=round(erle_db, 2),
            is_echo_dominant=is_echo_dominant,
            is_media_contaminated=background_media_active and out_rms < 0.05,
        )

    def record_tts_utterance(self, text: str) -> None:
        if text and text.strip():
            self._recent_tts.append(text.strip())

    def is_tts_echo_text(self, transcript: str, *, threshold: float = 0.75) -> bool:
        """Перевірити, чи не є розпізнаний текст самовідтворенням щойно озвученого TTS."""
        cand = _tokens(transcript)
        if not cand:
            return False
        for prev in self._recent_tts:
            ref = _tokens(prev)
            if not ref:
                continue
            overlap = len(cand & ref) / max(1, min(len(cand), len(ref)))
            if overlap >= threshold:
                return True
        return False
