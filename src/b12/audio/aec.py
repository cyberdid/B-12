"""Придушення акустичного відлуння (NLMS FIR + системний WebRTC AEC) та анти-self-trigger."""

import re
import shutil
import subprocess
from collections import deque
from dataclasses import dataclass

import numpy as np

_WORD_RE = re.compile(r"[0-9A-Za-zА-Яа-яІіЇїЄєҐґ']+")

AEC_SOURCE_NAME = "b12_aec_source"
AEC_SINK_NAME = "b12_aec_sink"


def _tokens_list(text: str) -> list[str]:
    return [w.lower() for w in _WORD_RE.findall(text.replace("’", "'").replace("ʼ", "'"))]


@dataclass(frozen=True)
class AecStats:
    input_rms: float
    output_rms: float
    reference_rms: float
    correlation: float
    echo_return_loss_enhancement_db: float
    is_echo_dominant: bool
    is_media_contaminated: bool
    delay_samples: int = 0
    double_talk_detected: bool = False


class PulseAudioWebRtcAec:
    """Системний WebRTC AEC маршрут через PulseAudio/PipeWire module-echo-cancel."""

    def __init__(
        self,
        *,
        source_master: str | None = None,
        source_name: str = AEC_SOURCE_NAME,
        sink_name: str = AEC_SINK_NAME,
    ):
        self.source_master = source_master
        self.source_name = source_name
        self.sink_name = sink_name
        self.sink_master: str | None = None
        self.module_id: int | None = None
        self.last_error: str | None = None

    @property
    def active(self) -> bool:
        return self.module_id is not None

    @staticmethod
    def is_supported() -> bool:
        return shutil.which("pactl") is not None

    def _managed_module_ids(self) -> list[int]:
        if not self.is_supported():
            return []
        try:
            res = subprocess.run(
                ["pactl", "list", "short", "modules"],
                capture_output=True,
                text=True,
                timeout=3,
                check=False,
            )
        except Exception:
            return []
        ids: list[int] = []
        for line in res.stdout.splitlines():
            parts = line.split("\t", 2)
            if len(parts) < 3 or parts[1] != "module-echo-cancel":
                continue
            args = parts[2]
            if f"source_name={self.source_name}" in args or f"sink_name={self.sink_name}" in args:
                try:
                    ids.append(int(parts[0]))
                except ValueError:
                    pass
        return ids

    def cleanup_stale(self) -> None:
        for mid in self._managed_module_ids():
            try:
                subprocess.run(
                    ["pactl", "unload-module", str(mid)],
                    capture_output=True,
                    text=True,
                    timeout=3,
                    check=False,
                )
            except Exception:
                pass

    def start(self, sink_master: str | None = None, source_master: str | None = None) -> bool:
        if not self.is_supported():
            self.last_error = "pactl not found"
            return False
        self.stop()
        self.cleanup_stale()
        self.last_error = None
        src = source_master or self.source_master
        args = [
            "pactl",
            "load-module",
            "module-echo-cancel",
            "aec_method=webrtc",
            f"source_name={self.source_name}",
            f"sink_name={self.sink_name}",
            "source_properties=device.description=B12_AEC_Microphone",
            "sink_properties=device.description=B12_AEC_Speaker",
        ]
        if src:
            args.append(f"source_master={src}")
        if sink_master:
            args.append(f"sink_master={sink_master}")
        try:
            res = subprocess.run(args, capture_output=True, text=True, timeout=5, check=False)
            if res.returncode != 0:
                self.last_error = res.stderr.strip() or "Could not load module-echo-cancel"
                return False
            self.module_id = int(res.stdout.strip())
            self.sink_master = sink_master
            if src:
                self.source_master = src
            return True
        except Exception as exc:
            self.last_error = str(exc)
            self.module_id = None
            return False

    def stop(self) -> None:
        mid = self.module_id
        self.module_id = None
        self.sink_master = None
        if mid is None or not self.is_supported():
            return
        try:
            subprocess.run(
                ["pactl", "unload-module", str(mid)],
                capture_output=True,
                text=True,
                timeout=3,
                check=False,
            )
        except Exception:
            pass


class AcousticEchoCanceller:
    """Адаптивний багатотаповий FIR NLMS ехокомпенсатор із DTD та анти-self-trigger."""

    def __init__(
        self,
        *,
        sample_rate: int = 16000,
        filter_length: int = 128,
        step_size: float = 0.35,
        max_ref_seconds: float = 12.0,
        max_delay_ms: float = 40.0,
    ):
        self.sample_rate = sample_rate
        self.filter_length = max(8, int(filter_length))
        self.step_size = float(step_size)
        self.max_ref_samples = int(sample_rate * max_ref_seconds)
        self.max_delay_samples = max(0, int(sample_rate * max_delay_ms / 1000.0))
        self._ref_buffer = np.zeros(0, dtype=np.float32)
        self._weights = np.zeros(self.filter_length, dtype=np.float32)
        # Ініціалізуємо головний тап одиницею для швидкого старту на нульовій затримці
        self._weights[0] = 0.5
        self._recent_tts: deque[str] = deque(maxlen=16)
        self.call_count: int = 0

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

    def reset_filter(self) -> None:
        self._weights.fill(0.0)
        self._weights[0] = 0.5
        self.clear_reference()

    def _align_reference(self, mic: np.ndarray) -> tuple[np.ndarray, np.ndarray, int]:
        """Витягти вікно ref і вирівняти його за causal-затримкою через FFT крос-кореляцію."""
        n = len(mic)
        avail = len(self._ref_buffer)
        if avail >= n:
            raw_ref = self._ref_buffer[:n]
            self._ref_buffer = self._ref_buffer[n:]
        else:
            raw_ref = np.pad(self._ref_buffer, (0, n - avail))
            self._ref_buffer = np.zeros(0, dtype=np.float32)

        max_lag = min(self.max_delay_samples, n // 2)
        if max_lag <= 0 or float(np.dot(raw_ref, raw_ref)) <= 1e-8:
            return raw_ref, raw_ref, 0

        fft_size = 1 << (2 * n - 1).bit_length()
        mic_f = np.fft.rfft(mic, n=fft_size)
        ref_f = np.fft.rfft(raw_ref, n=fft_size)
        # Позитивний лаг d означає mic[t] ~ ref[t - d]
        xcorr = np.fft.irfft(mic_f * np.conj(ref_f), n=fft_size)[: max_lag + 1]
        best_lag = int(np.argmax(np.abs(xcorr)))
        if best_lag > 0:
            aligned = np.concatenate(
                [np.zeros(best_lag, dtype=np.float32), raw_ref[: n - best_lag]]
            )
        else:
            aligned = raw_ref
        return raw_ref, aligned, best_lag

    def _nlms_block_filter(
        self, mic: np.ndarray, raw_ref: np.ndarray, aligned_ref: np.ndarray
    ) -> tuple[np.ndarray, float, bool]:
        """Багатотаповий FIR NLMS-фільтр із детектором double-talk за вирівняною кореляцією."""
        L = self.filter_length
        n = len(mic)
        align_corr = float(
            abs(np.dot(mic, aligned_ref))
            / (np.linalg.norm(mic) * np.linalg.norm(aligned_ref) + 1e-8)
        )
        in_rms = float(np.sqrt(np.mean(mic * mic)) + 1e-9)
        ref_rms = float(np.sqrt(np.mean(raw_ref * raw_ref)) + 1e-9)
        double_talk = in_rms > ref_rms * 0.65 and align_corr < 0.72

        if n < L:
            ref_e = float(np.dot(aligned_ref, aligned_ref)) + 1e-8
            gain = float(np.dot(mic, aligned_ref) / ref_e)
            y_est = gain * aligned_ref
            return mic - y_est, align_corr, double_talk

        padded_ref = np.pad(raw_ref, (L - 1, 0))
        shape = (n, L)
        strides = (padded_ref.strides[0], padded_ref.strides[0])
        X = np.lib.stride_tricks.as_strided(padded_ref, shape=shape, strides=strides)[:, ::-1]

        if not double_talk:
            step_stride = max(1, n // 64)
            X_sub = X[::step_stride]
            m_sub = mic[::step_stride]
            # Регуляризований NLMS / RLS крок для багатотапової імпульсної характеристики RIR
            gram = (X_sub.T @ X_sub) / max(1, len(X_sub)) + np.eye(L, dtype=np.float32) * 1e-4
            rhs = (X_sub.T @ m_sub) / max(1, len(X_sub))
            target_w = np.linalg.solve(gram, rhs).astype(np.float32)
            self._weights = (1.0 - self.step_size) * self._weights + self.step_size * target_w

        y_fir = X @ self._weights
        fir_corr = float(
            abs(np.dot(mic, y_fir)) / (np.linalg.norm(mic) * np.linalg.norm(y_fir) + 1e-8)
        )
        best_corr = max(align_corr, fir_corr)
        double_talk = in_rms > ref_rms * 0.65 and best_corr < 0.72

        e_fir = mic - y_fir
        align_energy = float(np.dot(aligned_ref, aligned_ref))
        if align_energy > 1e-8 and not double_talk:
            res_gain = float(np.dot(e_fir, aligned_ref) / (align_energy + 1e-8))
            residual = e_fir - res_gain * aligned_ref
        else:
            residual = e_fir
        return residual, best_corr, double_talk

    def process_capture(
        self,
        mic_16k: np.ndarray,
        *,
        background_media_active: bool = False,
    ) -> tuple[np.ndarray, AecStats]:
        """Пригнітити відлуння динаміка та оцінити ERLE, double-talk і домінування відлуння."""
        self.call_count += 1
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
                delay_samples=0,
                double_talk_detected=False,
            )

        raw_ref, aligned_ref, delay_samples = self._align_reference(mic)
        ref_rms = float(np.sqrt(np.mean(raw_ref * raw_ref)) + 1e-9)
        ref_energy = float(np.dot(raw_ref, raw_ref))

        if ref_energy > 1e-8:
            residual, corr, double_talk = self._nlms_block_filter(mic, raw_ref, aligned_ref)
            if corr > 0.75 and not double_talk:
                suppression = max(0.05, 1.0 - corr * 0.92)
                cleaned = residual * suppression
            else:
                cleaned = residual
        else:
            corr = 0.0
            double_talk = False
            cleaned = mic.copy()

        out_rms = float(np.sqrt(np.mean(cleaned * cleaned)) + 1e-9)
        erle_db = float(20.0 * np.log10(max(1.0, in_rms / out_rms)))
        is_echo_dominant = corr > 0.75 and out_rms < in_rms * 0.45 and not double_talk
        return cleaned.astype(np.float32), AecStats(
            input_rms=round(in_rms, 6),
            output_rms=round(out_rms, 6),
            reference_rms=round(ref_rms, 6),
            correlation=round(corr, 4),
            echo_return_loss_enhancement_db=round(erle_db, 2),
            is_echo_dominant=is_echo_dominant,
            is_media_contaminated=background_media_active and out_rms < 0.05,
            delay_samples=delay_samples,
            double_talk_detected=double_talk,
        )

    def record_tts_utterance(self, text: str) -> None:
        if text and text.strip():
            self._recent_tts.append(text.strip())

    def is_tts_echo_text(self, transcript: str, *, threshold: float = 0.75) -> bool:
        """Перевірити, чи не є розпізнаний текст самовідтворенням щойно озвученого TTS.

        Короткі природні відповіді (1-2 слова: «так», «ні», «зараз», «стоп») на довшу
        репліку B-12 ніколи не блокуються як відлуння (виправлення V-011).
        """
        cand_list = _tokens_list(transcript)
        if not cand_list:
            return False
        cand_set = set(cand_list)
        cand_joined = " ".join(cand_list)

        for prev in self._recent_tts:
            ref_list = _tokens_list(prev)
            if not ref_list:
                continue
            ref_set = set(ref_list)
            ref_joined = " ".join(ref_list)

            # Якщо і репліка TTS, і транскрипт тотожні — це відлуння
            if cand_joined == ref_joined:
                return True

            # Коротка відповідь користувача (1-2 слова) на фразу з >= 3 слів — це НЕ відлуння
            if len(cand_list) <= 2 and len(ref_list) >= 3:
                continue

            # Порівнюємо перетин відносно більшого з (довжини кандидата, 3) та частки референсу
            denom = max(len(cand_set), min(len(ref_set), 4))
            overlap = len(cand_set & ref_set) / max(1, denom)
            ref_coverage = len(cand_set & ref_set) / max(1, len(ref_set))
            if overlap >= threshold and ref_coverage >= 0.5:
                return True
        return False
