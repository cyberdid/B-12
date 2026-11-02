"""Виявлення мовленнєвої активності (Silero VAD ONNX) та детектор завершення репліки (endpoint)."""

from collections import deque
from dataclasses import dataclass
from pathlib import Path

import numpy as np

FRAME_SAMPLES_16K = 512  # 32 мс при 16 кГц
CONTEXT_SAMPLES_16K = 64


def _default_vad_model_path() -> Path | None:
    candidates: list[Path] = [
        Path.home() / ".local" / "share" / "b12" / "voices" / "silero_vad.onnx",
        Path.home()
        / ".cache"
        / "torch"
        / "hub"
        / "snakers4_silero-vad_master"
        / "src"
        / "silero_vad"
        / "data"
        / "silero_vad.onnx",
    ]
    try:
        from faster_whisper.utils import get_assets_path

        fw_vad = Path(get_assets_path()) / "silero_vad_v6.onnx"
        candidates.append(fw_vad)
    except Exception:
        pass

    for path in candidates:
        if path.is_file():
            return path
    return None


class SileroVad:
    """Stateful-обгортка Silero VAD (ONNX Runtime CPU) з 64-семпловим контекстом (16 кГц)."""

    def __init__(
        self,
        model_path: Path | str | None = None,
        *,
        threshold: float = 0.45,
        rms_silence_floor: float = 0.002,
        allow_rms_fallback: bool = False,
        require_onnx: bool = False,
    ):
        self.threshold = threshold
        self.rms_silence_floor = rms_silence_floor
        self.allow_rms_fallback = allow_rms_fallback
        resolved = Path(model_path) if model_path else _default_vad_model_path()
        self.model_path = resolved
        self._session = None
        self._input_names: set[str] = set()
        if resolved is not None and resolved.is_file():
            import onnxruntime as ort

            opts = ort.SessionOptions()
            opts.inter_op_num_threads = 1
            opts.intra_op_num_threads = 1
            opts.enable_cpu_mem_arena = False
            opts.log_severity_level = 4
            self._session = ort.InferenceSession(
                str(resolved),
                providers=["CPUExecutionProvider"],
                sess_options=opts,
            )
            self._input_names = {inp.name for inp in self._session.get_inputs()}
        elif require_onnx:
            raise RuntimeError("Silero VAD ONNX model is required but was not found")
        self.reset()

    @property
    def backend(self) -> str:
        return "onnx" if self._session is not None else "rms_fallback"

    def clone(self) -> "SileroVad":
        """Створити незалежний екземпляр VAD з власним внутрішнім LSTM-станом."""
        cloned = object.__new__(SileroVad)
        cloned.threshold = self.threshold
        cloned.rms_silence_floor = self.rms_silence_floor
        cloned.allow_rms_fallback = self.allow_rms_fallback
        cloned.model_path = self.model_path
        cloned._session = self._session
        cloned._input_names = self._input_names
        cloned.reset()
        return cloned

    def reset(self) -> None:
        self._state = np.zeros((2, 1, 128), dtype=np.float32)
        self._h = np.zeros((1, 1, 128), dtype=np.float32)
        self._c = np.zeros((1, 1, 128), dtype=np.float32)
        self._context = np.zeros((1, CONTEXT_SAMPLES_16K), dtype=np.float32)
        self._sr = np.array(16000, dtype=np.int64)

    def frame_probability(self, frame_512: np.ndarray) -> float:
        """Оцінити ймовірність мовлення (0..1) для одного фрейму 512 семплів (16 кГц)."""
        arr = np.asarray(frame_512, dtype=np.float32).reshape(-1)
        if len(arr) < FRAME_SAMPLES_16K:
            arr = np.pad(arr, (0, FRAME_SAMPLES_16K - len(arr)))
        elif len(arr) > FRAME_SAMPLES_16K:
            arr = arr[:FRAME_SAMPLES_16K]

        rms = float(np.sqrt(np.mean(arr * arr)))
        if rms < self.rms_silence_floor:
            # Оновлюємо контекст без виклику ONNX на мертвій тиші (патерн NVIDIA vad_loop)
            self._context = arr[None, -CONTEXT_SAMPLES_16K:]
            return 0.0

        if self._session is None:
            if not self.allow_rms_fallback:
                return 0.0
            return min(1.0, rms * 8.0)

        inp = np.concatenate([self._context, arr[None, :]], axis=1)
        if "h" in self._input_names and "c" in self._input_names:
            out, self._h, self._c = self._session.run(
                ["speech_probs", "hn", "cn"],
                {"input": inp, "h": self._h, "c": self._c},
            )
            prob = float(np.asarray(out).reshape(-1)[0])
        else:
            out, self._state = self._session.run(
                None,
                {"input": inp, "state": self._state, "sr": self._sr},
            )
            prob = float(out[0, 0])

        self._context = inp[:, -CONTEXT_SAMPLES_16K:]
        if self.allow_rms_fallback and prob < self.threshold and rms >= 0.08:
            return max(prob, min(0.95, rms * 5.0))
        return prob


@dataclass(frozen=True)
class EndpointDecision:
    ended: bool
    speech_audio: np.ndarray
    speech_duration_ms: float
    physical_eou_sample: int
    decision_sample: int
    physical_eou_to_endpoint_ms: float
    max_vad_prob: float


class EndpointDetector:
    """Потоковий та пакетний детектор кінця репліки зі збереженням стану між 32-мс чанками."""

    def __init__(
        self,
        vad: SileroVad | None = None,
        *,
        sample_rate: int = 16000,
        min_speech_ms: float = 128.0,
        silence_threshold_ms: float = 320.0,
        lookback_ms: float = 128.0,
    ):
        self.vad = vad or SileroVad()
        self._batch_vad = self.vad.clone()
        self.sample_rate = sample_rate
        self.min_speech_frames = max(1, int(round(min_speech_ms / 32.0)))
        self.silence_frames_needed = max(1, int(round(silence_threshold_ms / 32.0)))
        self.lookback_frames = max(1, int(round(lookback_ms / 32.0)))
        self.reset_stream()

    def reset_stream(self) -> None:
        """Скинути лише потоковий стан VAD/endpoint (на межі репліки або сесії)."""
        self.vad.reset()
        self._lookback: deque[np.ndarray] = deque(maxlen=self.lookback_frames)
        self._speech_chunks: list[np.ndarray] = []
        self._is_speaking = False
        self._speech_frames = 0
        self._silence_frames = 0
        self._stream_samples_seen = 0
        self._first_speech_sample: int | None = None
        self._last_speech_end_sample = 0
        self._max_stream_prob = 0.0

    def feed_stream_chunk(self, chunk_16k: np.ndarray) -> tuple[float, EndpointDecision | None]:
        """Обробити черговий чанк потоку без втрати LSTM-стану між викликами.

        Повертає (max_vad_prob_in_chunk, EndpointDecision | None).
        Коли репліка завершилась паузою, повертає сформований EndpointDecision і скидає стан.
        """
        samples = np.asarray(chunk_16k, dtype=np.float32).reshape(-1)
        if len(samples) == 0:
            return 0.0, None

        probs: list[float] = []
        decision: EndpointDecision | None = None
        total_frames = (len(samples) + FRAME_SAMPLES_16K - 1) // FRAME_SAMPLES_16K

        for idx in range(total_frames):
            start = idx * FRAME_SAMPLES_16K
            end = min(len(samples), start + FRAME_SAMPLES_16K)
            frame = samples[start:end]
            if len(frame) < FRAME_SAMPLES_16K:
                frame = np.pad(frame, (0, FRAME_SAMPLES_16K - len(frame)))
            prob = self.vad.frame_probability(frame)
            probs.append(prob)
            if prob > self._max_stream_prob:
                self._max_stream_prob = prob

            frame_start_sample = self._stream_samples_seen
            self._stream_samples_seen += len(frame)
            frame_end_sample = self._stream_samples_seen

            if prob >= self.vad.threshold:
                self._silence_frames = 0
                if not self._is_speaking:
                    self._is_speaking = True
                    self._first_speech_sample = frame_start_sample
                    self._speech_chunks = list(self._lookback)
                self._speech_frames += 1
                self._speech_chunks.append(frame)
                self._last_speech_end_sample = frame_end_sample
            else:
                if self._is_speaking:
                    self._speech_chunks.append(frame)
                    self._silence_frames += 1
                    if (
                        self._speech_frames >= self.min_speech_frames
                        and self._silence_frames >= self.silence_frames_needed
                    ):
                        speech_audio = (
                            np.concatenate(self._speech_chunks)
                            if self._speech_chunks
                            else np.zeros(0, dtype=np.float32)
                        )
                        first_s = (
                            self._first_speech_sample
                            if self._first_speech_sample is not None
                            else 0
                        )
                        speech_dur_ms = (
                            max(0, self._last_speech_end_sample - first_s)
                            * 1000.0
                            / self.sample_rate
                        )
                        eou_to_ep_ms = (
                            max(0, frame_end_sample - self._last_speech_end_sample)
                            * 1000.0
                            / self.sample_rate
                        )
                        decision = EndpointDecision(
                            ended=True,
                            speech_audio=speech_audio,
                            speech_duration_ms=round(speech_dur_ms, 2),
                            physical_eou_sample=self._last_speech_end_sample,
                            decision_sample=frame_end_sample,
                            physical_eou_to_endpoint_ms=round(eou_to_ep_ms, 2),
                            max_vad_prob=round(self._max_stream_prob, 4),
                        )
                        self.reset_stream()
                        break
                else:
                    self._lookback.append(frame)

        return (max(probs) if probs else 0.0), decision

    def detect_utterance(self, audio_16k: np.ndarray) -> EndpointDecision:
        """Пакетний аналіз записаного буфера 16 кГц (використовує ізольований стан _batch_vad)."""
        samples = np.asarray(audio_16k, dtype=np.float32).reshape(-1)
        if len(samples) == 0:
            return EndpointDecision(
                ended=False,
                speech_audio=samples,
                speech_duration_ms=0.0,
                physical_eou_sample=0,
                decision_sample=0,
                physical_eou_to_endpoint_ms=0.0,
                max_vad_prob=0.0,
            )

        self._batch_vad.allow_rms_fallback = self.vad.allow_rms_fallback
        self._batch_vad.threshold = self.vad.threshold
        self._batch_vad.reset()
        speech_frames = 0
        trailing_silence = 0
        first_speech_idx: int | None = None
        last_speech_end = 0
        decision_sample = len(samples)
        ended_by_silence = False
        max_prob = 0.0

        total_frames = (len(samples) + FRAME_SAMPLES_16K - 1) // FRAME_SAMPLES_16K
        for idx in range(total_frames):
            start = idx * FRAME_SAMPLES_16K
            end = min(len(samples), start + FRAME_SAMPLES_16K)
            frame = samples[start:end]
            prob = self._batch_vad.frame_probability(frame)
            if prob > max_prob:
                max_prob = prob

            if prob >= self._batch_vad.threshold:
                if first_speech_idx is None:
                    first_speech_idx = start
                speech_frames += 1
                trailing_silence = 0
                last_speech_end = end
            elif speech_frames >= self.min_speech_frames:
                trailing_silence += 1
                if trailing_silence >= self.silence_frames_needed:
                    decision_sample = end
                    ended_by_silence = True
                    break

        if first_speech_idx is None:
            return EndpointDecision(
                ended=False,
                speech_audio=samples,
                speech_duration_ms=0.0,
                physical_eou_sample=len(samples),
                decision_sample=len(samples),
                physical_eou_to_endpoint_ms=0.0,
                max_vad_prob=round(max_prob, 4),
            )

        pre_roll = max(0, first_speech_idx - FRAME_SAMPLES_16K * 2)
        post_roll = min(len(samples), last_speech_end + FRAME_SAMPLES_16K * 3)
        speech_slice = samples[pre_roll:post_roll]
        eou_to_endpoint_ms = max(
            0.0, (decision_sample - last_speech_end) * 1000.0 / self.sample_rate
        )

        return EndpointDecision(
            ended=ended_by_silence or speech_frames >= self.min_speech_frames,
            speech_audio=speech_slice,
            speech_duration_ms=(last_speech_end - first_speech_idx) * 1000.0 / self.sample_rate,
            physical_eou_sample=last_speech_end,
            decision_sample=decision_sample,
            physical_eou_to_endpoint_ms=round(eou_to_endpoint_ms, 2),
            max_vad_prob=round(max_prob, 4),
        )
