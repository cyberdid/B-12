"""Локальне розпізнавання мовлення (faster-whisper) для UA, EN та code-switching."""

import io
import re
import time
import uuid
import wave
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import numpy as np

_CODE_SWITCH_CANONICAL = (
    (re.compile(r"\bлокал[у]?\s+runtime\b", re.IGNORECASE), "local runtime"),
    (re.compile(r"\bлокал[\s\-]*ранта[йєії]м\b", re.IGNORECASE), "local runtime"),
    (re.compile(r"\bлокал[\s\-]*вранта[\s\-]*ім\b", re.IGNORECASE), "local runtime"),
    (re.compile(r"\bвіде[ії]\s*карти\b", re.IGNORECASE), "відеокарти"),
    (re.compile(r"\bпам['’ʼ]яти\b"), "пам'яті"),
    (re.compile(r"\bпраціє\b"), "працює"),
)


def _canonicalize_code_switching(text: str) -> str:
    out = text
    for pattern, repl in _CODE_SWITCH_CANONICAL:
        out = pattern.sub(repl, out)
    return out


def _resolve_whisper_model(model_id: str) -> str:
    path = Path(model_id).expanduser()
    if path.exists():
        return str(path)
    slug = model_id.replace("/", "--")
    hub_dir = Path.home() / ".cache" / "huggingface" / "hub" / f"models--{slug}" / "snapshots"
    if hub_dir.is_dir():
        snapshots = sorted(p for p in hub_dir.iterdir() if p.is_dir())
        if snapshots:
            return str(snapshots[-1])
    return model_id


@dataclass(frozen=True)
class TranscriptResult:
    text: str
    language: str
    language_probability: float
    duration_s: float
    asr_latency_ms: float
    provenance_id: str
    segments: tuple[str, ...] = ()


class WhisperAsr:
    """Адаптер faster-whisper із однопрохідним кодуванням, warmup та UA/EN code-switching."""

    _SHARED_MODELS: dict[tuple[str, str, str], object] = {}

    def __init__(
        self,
        model_id: str = "Systran/faster-whisper-small",
        *,
        device: str = "cpu",
        compute_type: str = "int8",
        cpu_threads: int = 8,
    ):
        self.model_id = model_id
        self.resolved_path = _resolve_whisper_model(model_id)
        self.device = device
        self.compute_type = compute_type
        self.cpu_threads = cpu_threads
        self._model = None
        self.transcribe_count: int = 0

    @property
    def model(self):
        if self._model is None:
            key = (self.resolved_path, self.device, self.compute_type)
            if key not in self._SHARED_MODELS:
                from faster_whisper import WhisperModel

                try:
                    self._SHARED_MODELS[key] = WhisperModel(
                        self.resolved_path,
                        device=self.device,
                        compute_type=self.compute_type,
                        cpu_threads=self.cpu_threads,
                        local_files_only=Path(self.resolved_path).exists(),
                    )
                except Exception:
                    # Fallback на CPU int8 (як у NVIDIA stt.py), якщо CUDA-бібліотеки недоступні
                    self.device = "cpu"
                    self.compute_type = "int8"
                    fallback_key = (self.resolved_path, "cpu", "int8")
                    if fallback_key not in self._SHARED_MODELS:
                        self._SHARED_MODELS[fallback_key] = WhisperModel(
                            self.resolved_path,
                            device="cpu",
                            compute_type="int8",
                            cpu_threads=self.cpu_threads,
                            local_files_only=Path(self.resolved_path).exists(),
                        )
                    self._model = self._SHARED_MODELS[fallback_key]
                    return self._model
            self._model = self._SHARED_MODELS[key]
        return self._model

    def warmup(self) -> float:
        """Прогріти модель на короткому буфері в пам'яті без запису файлів на диск."""
        t0 = time.perf_counter()
        dummy = np.zeros(8000, dtype=np.float32)
        prev = self.transcribe_count
        self.transcribe(dummy, language="uk")
        self.transcribe_count = prev
        return round((time.perf_counter() - t0) * 1000.0, 2)

    @staticmethod
    def to_float32_16k(pcm_or_wav: bytes | np.ndarray, sample_rate: int = 16000) -> np.ndarray:
        """Перетворити PCM int16 / WAV байти або масив до 16 кГц mono float32."""
        if isinstance(pcm_or_wav, bytes | bytearray | memoryview):
            raw = bytes(pcm_or_wav)
            if raw[:4] == b"RIFF" and raw[8:12] == b"WAVE":
                with wave.open(io.BytesIO(raw), "rb") as wf:
                    sample_rate = wf.getframerate()
                    channels = wf.getnchannels()
                    width = wf.getsampwidth()
                    frames = wf.readframes(wf.getnframes())
                if width == 2:
                    arr = np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0
                elif width == 4:
                    arr = np.frombuffer(frames, dtype=np.int32).astype(np.float32) / 2147483648.0
                else:
                    arr = (np.frombuffer(frames, dtype=np.uint8).astype(np.float32) - 128.0) / 128.0
                if channels > 1:
                    arr = arr.reshape(-1, channels).mean(axis=1)
            else:
                even = len(raw) - (len(raw) % 2)
                arr = (
                    np.frombuffer(memoryview(raw)[:even], dtype=np.int16).astype(np.float32)
                    / 32768.0
                )
        else:
            arr = np.asarray(pcm_or_wav)
            if arr.dtype == np.int16:
                arr = arr.astype(np.float32) / 32768.0
            else:
                arr = arr.astype(np.float32, copy=False).reshape(-1)

        if len(arr) == 0 or sample_rate == 16000:
            return arr.astype(np.float32, copy=False)
        target_len = max(1, int(round(len(arr) * 16000.0 / sample_rate)))
        resampled = np.interp(
            np.linspace(0.0, len(arr) - 1, target_len),
            np.arange(len(arr)),
            arr,
        )
        return resampled.astype(np.float32)

    def transcribe(
        self,
        audio_16k: np.ndarray,
        *,
        language: Literal["uk", "en", "auto"] | None = "auto",
    ) -> TranscriptResult:
        """Розпізнати буфер 16 кГц float32 з одноразовим запуском енкодера."""
        from faster_whisper.audio import pad_or_trim
        from faster_whisper.tokenizer import Tokenizer
        from faster_whisper.transcribe import TranscriptionOptions, get_suppressed_tokens

        self.transcribe_count += 1
        samples = np.asarray(audio_16k, dtype=np.float32).reshape(-1)
        duration_s = len(samples) / 16000.0
        if len(samples) < 800:  # < 50 мс
            return TranscriptResult(
                text="",
                language="uk",
                language_probability=0.0,
                duration_s=duration_s,
                asr_latency_ms=0.0,
                provenance_id=str(uuid.uuid4()),
            )

        t0 = time.perf_counter()
        m = self.model
        features = m.feature_extractor(samples)
        segment = pad_or_trim(features, m.feature_extractor.nb_max_frames)
        encoder_output = m.encode(segment)

        if language in ("uk", "en"):
            chosen_lang = language
            lang_prob = 1.0
        else:
            results = m.model.detect_language(encoder_output)[0]
            probs = {tok.strip("<|>"): float(p) for tok, p in results}
            uk_p = probs.get("uk", 0.0)
            en_p = probs.get("en", 0.0)
            if en_p > uk_p * 1.5 and en_p > 0.25:
                chosen_lang = "en"
                lang_prob = en_p
            else:
                chosen_lang = "uk"
                lang_prob = max(uk_p, 1.0 - en_p)

        tokenizer = Tokenizer(
            m.hf_tokenizer,
            m.model.is_multilingual,
            task="transcribe",
            language=chosen_lang,
        )
        options = TranscriptionOptions(
            beam_size=1,
            best_of=1,
            patience=1.0,
            length_penalty=1.0,
            repetition_penalty=1.0,
            no_repeat_ngram_size=0,
            log_prob_threshold=-1.0,
            no_speech_threshold=0.6,
            compression_ratio_threshold=2.4,
            condition_on_previous_text=False,
            prompt_reset_on_temperature=0.5,
            temperatures=[0.0],
            initial_prompt=(
                "Українська мова. Привіт, Олександре! Перевір, будь ласка, стан локальної пам'яті, "
                "температуру процесора та відеокарти. Система працює стабільно, B-12, local runtime"
                if chosen_lang == "uk"
                else "Hello friend, B-12 local voice pipeline, system status."
            ),
            prefix=None,
            suppress_blank=True,
            suppress_tokens=get_suppressed_tokens(tokenizer, [-1]),
            without_timestamps=True,
            max_initial_timestamp=1.0,
            word_timestamps=False,
            prepend_punctuations="\"'“¿([{-",
            append_punctuations="\"'.。,，!！?？:：”)]}、",
            multilingual=False,
            max_new_tokens=None,
            clip_timestamps="0",
            hallucination_silence_threshold=None,
            hotwords="Олександре, будь ласка, пам'яті, працює, local runtime, B-12"
            if chosen_lang == "uk"
            else "B-12, pipeline, status",
        )
        seg_iter = m.generate_segments(
            features,
            tokenizer,
            options,
            False,
            encoder_output=encoder_output,
        )
        seg_texts = tuple(
            _canonicalize_code_switching(s.text.strip())
            for s in seg_iter
            if s.text and s.text.strip()
        )
        latency_ms = (time.perf_counter() - t0) * 1000.0
        return TranscriptResult(
            text=" ".join(seg_texts).strip(),
            language=chosen_lang,
            language_probability=round(lang_prob, 4),
            duration_s=round(duration_s, 3),
            asr_latency_ms=round(latency_ms, 2),
            provenance_id=str(uuid.uuid4()),
            segments=seg_texts,
        )

    def transcribe_pcm(
        self,
        pcm_or_wav: bytes | np.ndarray,
        *,
        sample_rate: int = 16000,
        language: Literal["uk", "en", "auto"] | None = "auto",
    ) -> TranscriptResult:
        audio_16k = self.to_float32_16k(pcm_or_wav, sample_rate=sample_rate)
        return self.transcribe(audio_16k, language=language)
