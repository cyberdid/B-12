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


FRAME_SAMPLES_16K = 512  # 32 ms at 16 kHz


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
    """Адаптивний FIR-ехокомпенсатор з часовою синхронізацією референсу та оцінкою затримки.

    Референс подається потоково в момент запису в програвач (FIFO). Кожен кадр захоплення
    споживає рівно стільки референсу, скільки пройшло часу, тож референс і мікрофон йдуть
    одним годинником; пропуски заповнюються нулями. Затримка між відтворенням і захопленням
    оцінюється кросс-кореляцією історії мікрофона з історією споживаного референсу до
    max_delay_ms (за замовчуванням 400 мс), тобто може перевищувати тривалість кадру.
    Коефіцієнти фільтра оновлюються з рекурсивною ковариацією між кадрами, а не з 8 рядків
    на кадр. Це власний запасний шлях: для реального відлуння в кімнаті основний шлях —
    системний echo-cancel PipeWire (див. PipeWireEchoCancel).
    """

    def __init__(
        self,
        *,
        sample_rate: int = 16000,
        filter_length: int = 256,
        step_size: float = 0.35,
        max_fifo_seconds: float = 3.0,
        max_delay_ms: float = 400.0,
        evidence_ms: float = 500.0,
    ):
        self.sample_rate = sample_rate
        self.filter_length = max(8, int(filter_length))
        self.step_size = float(step_size)
        self.max_delay_samples = max(0, int(sample_rate * max_delay_ms / 1000.0))
        self.evidence_samples = max(64, int(sample_rate * evidence_ms / 1000.0))
        self._max_fifo = int(sample_rate * max_fifo_seconds)
        self._history = self.evidence_samples + self.max_delay_samples + FRAME_SAMPLES_16K
        self._fifo = np.zeros(0, dtype=np.float32)
        self._mic_hist = np.zeros(self._history, dtype=np.float32)
        self._ref_hist = np.zeros(self._history, dtype=np.float32)
        self._weights = np.zeros(self.filter_length, dtype=np.float32)
        self._weights[0] = 0.5  # одиниця на старті: швидкий вихід на прямий шлях
        self._delay = 0
        self._delay_score = 0.0
        self._frames = 0
        self._recent_tts: deque[str] = deque(maxlen=16)
        self.call_count: int = 0

    def feed_render_reference(self, ref_16k: np.ndarray) -> None:
        """Поставити в чергу референс, який щойно записано в програвач (16 кГц float32)."""
        arr = np.asarray(ref_16k, dtype=np.float32).reshape(-1)
        if len(arr) == 0:
            return
        self._fifo = np.concatenate([self._fifo, arr])
        if len(self._fifo) > self._max_fifo:
            self._fifo = self._fifo[-self._max_fifo :]

    def clear_reference(self) -> None:
        self._fifo = np.zeros(0, dtype=np.float32)

    def reset_filter(self) -> None:
        self._weights.fill(0.0)
        self._weights[0] = 0.5
        self._delay = 0
        self._delay_score = 0.0
        self.clear_reference()

    def _consume(self, n: int) -> np.ndarray:
        """Взяти з FIFO n семплів референсу; нестача заповнюється нулями (тиша відтворення)."""
        out = np.zeros(n, dtype=np.float32)
        take = min(n, len(self._fifo))
        out[:take] = self._fifo[:take]
        self._fifo = self._fifo[take:]
        return out

    @staticmethod
    def _push(history: np.ndarray, block: np.ndarray) -> np.ndarray:
        if len(block) >= len(history):
            return block[-len(history) :].astype(np.float32)
        return np.concatenate([history[len(block) :], block]).astype(np.float32)

    def _estimate_delay(self) -> tuple[int, float] | None:
        """Затримка d (семпли): мікрофон у момент t несе референс із t - d. Повертає (d, score)."""
        window = self.evidence_samples
        span = self.max_delay_samples
        mic_w = self._mic_hist[-window:]
        ref_w = self._ref_hist[-(window + span) :]
        mic_energy = float(np.dot(mic_w, mic_w))
        if mic_energy < 1e-8 or float(np.dot(ref_w, ref_w)) < 1e-8:
            return None
        nfft = 1 << (len(ref_w) + window).bit_length()
        # r[j] = sum_k ref_w[k + j] * mic_w[k], затримка d = span - j
        corr = np.fft.irfft(np.fft.rfft(ref_w, nfft) * np.conj(np.fft.rfft(mic_w, nfft)), nfft)
        corr = corr[: span + 1]
        power = np.concatenate([[0.0], np.cumsum(ref_w.astype(np.float64) ** 2)])
        energy = power[window : window + span + 1] - power[: span + 1]
        score = corr / np.sqrt(np.maximum(energy * mic_energy, 1e-12))
        best = float(np.max(score))
        # Periodic sound repeats its peaks every pitch period, so several lags can score alike.
        # Among them keep the one nearest the current estimate; with no estimate, the best peak.
        candidates = np.nonzero(score >= 0.95 * best)[0]
        if self._delay_score > 0.0:
            lags = span - candidates
            j = int(candidates[np.argmin(np.abs(lags - self._delay))])
        else:
            j = int(np.argmax(score))
        return span - j, float(score[j])

    def _nlms_block_filter(
        self, mic: np.ndarray, raw_ref: np.ndarray, aligned_ref: np.ndarray
    ) -> tuple[np.ndarray, float, bool]:
        """FIR-фільтр з рекурсивною ковариацією та детектором double-talk."""
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
            return mic - gain * aligned_ref, align_corr, double_talk

        padded_ref = np.pad(aligned_ref, (L - 1, 0))
        X = np.lib.stride_tricks.as_strided(
            padded_ref, shape=(n, L), strides=(padded_ref.strides[0], padded_ref.strides[0])
        )[:, ::-1]

        Xc = np.ascontiguousarray(X)
        if not double_talk:
            # Блоковий NLMS: крок — кореляція помилки з референсом, нормована на потужність.
            # Кілька мс на кадр; розв'язання систем 256×256 на кожному кадрі займало ~600 мс.
            y_prev = Xc @ self._weights
            error = mic - y_prev
            # ||x||² по всіх L відводах: L × середня потужність референсу в кадрі.
            power = L * float(np.dot(aligned_ref, aligned_ref)) / max(1, n) + 1e-6
            grad = (Xc.T @ error) / n
            self._weights = self._weights + self.step_size * grad / power

        y_fir = Xc @ self._weights
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
        """Пригнітити відлуння динаміка та оцінити ERLE, double-talk і домінування від
        справжнього референсу, вирівняного за оціненою затримкою."""
        self.call_count += 1
        mic = np.asarray(mic_16k, dtype=np.float32).reshape(-1)
        n = len(mic)
        if n == 0:
            return mic, AecStats(0.0, 0.0, 0.0, 0.0, 0.0, False, background_media_active)

        in_rms = float(np.sqrt(np.mean(mic * mic)) + 1e-9)
        consumed = self._consume(n)
        self._mic_hist = self._push(self._mic_hist, mic)
        self._ref_hist = self._push(self._ref_hist, consumed)
        self._frames += 1
        if self._frames % 8 == 1:
            estimate = self._estimate_delay()
            if estimate is not None and estimate[1] >= 0.2:
                if estimate[0] != self._delay:
                    # Коефіцієнти, навчені за старим вирівнюванням, більше не чинні.
                    self._weights.fill(0.0)
                    self._weights[0] = 0.5
                self._delay, self._delay_score = estimate
        d = self._delay
        if d > 0:
            aligned = self._ref_hist[-(n + d) : -d]
        else:
            aligned = self._ref_hist[-n:]
        raw_ref = aligned
        ref_rms = float(np.sqrt(np.mean(raw_ref * raw_ref)) + 1e-9)
        ref_energy = float(np.dot(raw_ref, raw_ref))

        if ref_energy > 1e-8:
            residual, corr, double_talk = self._nlms_block_filter(mic, raw_ref, aligned)
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
            delay_samples=int(d),
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
