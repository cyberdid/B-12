"""Потоковий синтез мовлення (Piper TTS UA/EN), розбиття на клаузи, обмежена черга та плеєр."""

import asyncio
import contextlib
import io
import re
import shutil
import time
import wave
from collections.abc import AsyncIterator, Callable, Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import numpy as np

_SENTENCE_SPLIT = re.compile(r"(?<=[.!?;])\s+|\n+")
_CLAUSE_SPLIT = re.compile(r"(?<=[.!?;,:—])\s+|\n+")

_UK_ONES = (
    "нуль",
    "один",
    "два",
    "три",
    "чотири",
    "п'ять",
    "шість",
    "сім",
    "вісім",
    "дев'ять",
    "десять",
    "одинадцять",
    "дванадцять",
    "тринадцять",
    "чотирнадцять",
    "п'ятнадцять",
    "шістнадцять",
    "сімнадцять",
    "вісімнадцять",
    "дев'ятнадцять",
)
_UK_TENS = (
    "",
    "",
    "двадцять",
    "тридцять",
    "сорок",
    "п'ятдесят",
    "шістдесят",
    "сімдесят",
    "вісімдесят",
    "дев'яносто",
)
_UK_HUNDREDS = (
    "",
    "сто",
    "двісті",
    "триста",
    "чотириста",
    "п'ятсот",
    "шістсот",
    "сімсот",
    "вісімсот",
    "дев'ятсот",
)

_TECH_TERMS_UK = {
    "b-12": "бі дванадцять",
    "б-12": "бі дванадцять",
    "b12": "бі дванадцять",
    "cpu": "сі пі ю",
    "gpu": "джі пі ю",
    "ram": "рам",
    "vram": "ві рам",
    "api": "ей пі ай",
    "cli": "сі ел ай",
    "tui": "ті ю ай",
    "sql": "ес к'ю ел",
    "sqlite": "ес к'ю лайт",
    "json": "джейсон",
    "http": "ейч ті ті пі",
    "usb": "ю ес бі",
    "wifi": "вай фай",
    "wi-fi": "вай фай",
    "ok": "окей",
    "local": "локал",
    "runtime": "рантайм",
    "status": "статус",
    "check": "чек",
    "now": "нау",
}

_LATIN_TO_UK = str.maketrans(
    {
        "a": "а",
        "b": "б",
        "c": "к",
        "d": "д",
        "e": "е",
        "f": "ф",
        "g": "г",
        "h": "х",
        "i": "і",
        "j": "дж",
        "k": "к",
        "l": "л",
        "m": "м",
        "n": "н",
        "o": "о",
        "p": "п",
        "q": "к",
        "r": "р",
        "s": "с",
        "t": "т",
        "u": "у",
        "v": "в",
        "w": "в",
        "x": "кс",
        "y": "й",
        "z": "з",
    }
)

_ALLOWED_UK_CHARS = set(" !$,'-.:;?^_абвгдежзийклмнопрстуфхцчшщьюяєіїґ—")


def _int_to_uk(n: int) -> str:
    if n < 0:
        return "мінус " + _int_to_uk(-n)
    if n < 20:
        return _UK_ONES[n]
    if n < 100:
        t, r = divmod(n, 10)
        return _UK_TENS[t] + (" " + _UK_ONES[r] if r else "")
    if n < 1000:
        h, r = divmod(n, 100)
        return _UK_HUNDREDS[h] + (" " + _int_to_uk(r) if r else "")
    if n < 1_000_000:
        th, r = divmod(n, 1000)
        if th % 10 == 1 and th % 100 != 11:
            th_word = (_int_to_uk(th - 1) + " одна тисяча").strip() if th > 1 else "одна тисяча"
        elif th % 10 in (2, 3, 4) and th % 100 not in (12, 13, 14):
            prefix = _int_to_uk(th - (th % 10))
            last = "дві" if th % 10 == 2 else _UK_ONES[th % 10]
            th_word = f"{prefix} {last} тисячі".strip()
        else:
            th_word = f"{_int_to_uk(th)} тисяч"
        return th_word + (" " + _int_to_uk(r) if r else "")
    return " ".join(_UK_ONES[int(d)] for d in str(n))


def _normalize_uk_text(text: str, *, strict_char_map: bool = False) -> str:
    s = text.replace("’", "'").replace("ʼ", "'").replace("`", "'")
    for term, repl in _TECH_TERMS_UK.items():
        s = re.sub(rf"\b{re.escape(term)}\b", repl, s, flags=re.IGNORECASE)
    s = re.sub(r"\d+", lambda m: _int_to_uk(int(m.group(0))), s)
    if strict_char_map:
        s = s.lower().translate(_LATIN_TO_UK)
        cleaned = "".join(ch if ch in _ALLOWED_UK_CHARS else " " for ch in s)
        return re.sub(r"\s+", " ", cleaned).strip()
    s = re.sub(r"[A-Za-z]+", lambda m: m.group(0).lower().translate(_LATIN_TO_UK), s)
    return re.sub(r"\s+", " ", s).strip()


def split_sentences(text: str) -> list[str]:
    """Розбити текст на окремі речення для потокового TTS."""
    parts = [p.strip() for p in _SENTENCE_SPLIT.split(text.strip()) if p and p.strip()]
    return parts if parts else ([text.strip()] if text.strip() else [])


def extract_stream_clauses(
    buffer: str,
    *,
    is_first: bool = False,
    first_chunk_words: int = 3,
    max_chunk_words: int = 12,
) -> tuple[list[str], str]:
    """Виділити готові речення або природні клаузи з буфера LLM (патерн NVIDIA stream_and_speak).

    Ніколи не розриває слова посередині: віддає повні речення одразу, або клаузи на розділових
    знаках (кома, двокрапка, тире), якщо накопичено достатньо слів для першого чанка.
    """
    if not buffer:
        return [], ""

    parts = _SENTENCE_SPLIT.split(buffer)
    if len(parts) > 1:
        ready = [p.strip() for p in parts[:-1] if p and p.strip()]
        return ready, parts[-1]

    # Якщо повного речення ще немає, але є клауза на комі/тире/двокрапці і достатньо слів
    clause_parts = _CLAUSE_SPLIT.split(buffer)
    if len(clause_parts) > 1:
        limit = first_chunk_words if is_first else max_chunk_words
        head = " ".join(p.strip() for p in clause_parts[:-1] if p and p.strip())
        if len(head.split()) >= limit:
            return [head], clause_parts[-1]

    return [], buffer


def _detect_sentence_lang(text: str) -> Literal["uk", "en"]:
    cyr = sum(1 for c in text if "\u0400" <= c <= "\u04ff")
    lat = sum(1 for c in text if "a" <= c.lower() <= "z")
    if lat > cyr and cyr == 0:
        return "en"
    return "uk"


@dataclass(frozen=True)
class SynthesizedAudio:
    text: str
    language: str
    sample_rate: int
    pcm_int16: bytes
    ttfa_ms: float
    duration_s: float

    @property
    def audio_int16_bytes(self) -> bytes:
        return self.pcm_int16

    def to_wav_bytes(self) -> bytes:
        buf = io.BytesIO()
        with wave.open(buf, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(self.sample_rate)
            wf.writeframes(self.pcm_int16)
        return buf.getvalue()

    def to_float32_16k(self) -> np.ndarray:
        if not self.pcm_int16:
            return np.zeros(0, dtype=np.float32)
        arr = np.frombuffer(self.pcm_int16, dtype=np.int16).astype(np.float32) / 32768.0
        if self.sample_rate == 16000:
            return arr
        target_len = max(1, int(round(len(arr) * 16000.0 / self.sample_rate)))
        return np.interp(
            np.linspace(0.0, len(arr) - 1, target_len),
            np.arange(len(arr)),
            arr,
        ).astype(np.float32)


def generate_earcon_pcm(sample_rate: int = 22050, duration_ms: float = 45.0) -> tuple[bytes, float]:
    """Згенерувати звуковий маркер (earcon); обліковується окремо від змістовного аудіо."""
    t0 = time.perf_counter()
    n = max(1, int(sample_rate * duration_ms / 1000.0))
    t = np.linspace(0.0, duration_ms / 1000.0, n, endpoint=False)
    env = np.sin(np.pi * np.arange(n) / n)
    wave_f = 0.15 * np.sin(2 * np.pi * 660.0 * t) * env
    pcm = (wave_f * 32767.0).astype(np.int16).tobytes()
    return pcm, round((time.perf_counter() - t0) * 1000.0, 3)


class PiperTts:
    """Адаптер Piper TTS з підтримкою української та англійської мов і обмеженою чергою фраз."""

    _SHARED_VOICES: dict[str, object] = {}

    def __init__(
        self,
        voices_dir: Path | str | None = None,
        *,
        uk_model: str = "uk_UA-mykyta-high.onnx",
        en_model: str = "en_US-lessac-medium.onnx",
        uk_speaker_id: int | None = None,
        max_queue_phrases: int = 8,
    ):
        if max_queue_phrases < 1:
            raise ValueError("max_queue_phrases must be >= 1")
        self.voices_dir = (
            Path(voices_dir) if voices_dir else Path.home() / ".local" / "share" / "b12" / "voices"
        )
        candidate_uk = self.voices_dir / uk_model
        if not candidate_uk.is_file():
            fallback_uk = self.voices_dir / "uk_UA-ukrainian_tts-medium.onnx"
            if fallback_uk.is_file():
                candidate_uk = fallback_uk
        self.uk_model_path = candidate_uk
        self.en_model_path = self.voices_dir / en_model
        self.uk_speaker_id = uk_speaker_id
        self.max_queue_phrases = max_queue_phrases

    def _load_voice(self, path: Path):
        key = str(path)
        if key not in self._SHARED_VOICES:
            from piper import PiperVoice

            self._SHARED_VOICES[key] = PiperVoice.load(key)
        return self._SHARED_VOICES[key]

    def synthesize(
        self,
        text: str,
        *,
        lang: Literal["auto", "uk", "en"] = "auto",
    ) -> SynthesizedAudio:
        """Синтезувати текст (з підтримкою code-switching між реченнями) та виміряти TTFA."""
        from piper import SynthesisConfig

        sentences = split_sentences(text)
        if not sentences:
            return SynthesizedAudio(
                text="",
                language="uk" if lang == "auto" else lang,
                sample_rate=22050,
                pcm_int16=b"",
                ttfa_ms=0.0,
                duration_s=0.0,
            )

        t0 = time.perf_counter()
        first_chunk_ms: float | None = None
        pcm_parts: list[bytes] = []
        sample_rate = 22050
        primary_lang = _detect_sentence_lang(sentences[0]) if lang == "auto" else lang

        for sentence in sentences:
            s_lang = _detect_sentence_lang(sentence) if lang == "auto" else lang
            if s_lang == "en" and self.en_model_path.is_file():
                voice = self._load_voice(self.en_model_path)
                norm = sentence.strip()
                cfg = None
            else:
                voice = self._load_voice(self.uk_model_path)
                is_char_model = "ukrainian_tts" in self.uk_model_path.name
                norm = _normalize_uk_text(sentence, strict_char_map=is_char_model)
                spk = (
                    self.uk_speaker_id
                    if self.uk_speaker_id is not None
                    else (1 if is_char_model else None)
                )
                cfg = SynthesisConfig(speaker_id=spk) if spk is not None else None

            if not norm:
                continue
            for chunk in voice.synthesize(norm, cfg):
                if first_chunk_ms is None:
                    first_chunk_ms = (time.perf_counter() - t0) * 1000.0
                sample_rate = chunk.sample_rate
                pcm_parts.append(chunk.audio_int16_bytes)

        pcm = b"".join(pcm_parts)
        ttfa = first_chunk_ms if first_chunk_ms is not None else (time.perf_counter() - t0) * 1000.0
        duration = (len(pcm) / 2.0) / sample_rate if sample_rate else 0.0
        return SynthesizedAudio(
            text=text,
            language=primary_lang,
            sample_rate=sample_rate,
            pcm_int16=pcm,
            ttfa_ms=round(ttfa, 2),
            duration_s=round(duration, 3),
        )

    async def stream_sentences(
        self,
        sentences: Iterable[str] | AsyncIterator[str],
        *,
        cancel: asyncio.Event | None = None,
        on_first_chunk: Callable[[], None] | None = None,
    ) -> AsyncIterator[SynthesizedAudio]:
        """Синтезувати потік речень через обмежену чергу (bounded queue) зі скасуванням."""
        queue: asyncio.Queue[SynthesizedAudio | None] = asyncio.Queue(
            maxsize=self.max_queue_phrases
        )

        async def producer() -> None:
            try:
                if isinstance(sentences, AsyncIterator):
                    async for s in sentences:
                        if cancel is not None and cancel.is_set():
                            break
                        if not s.strip():
                            continue
                        audio = await asyncio.to_thread(self.synthesize, s)
                        if cancel is not None and cancel.is_set():
                            break
                        await queue.put(audio)
                else:
                    for s in sentences:
                        if cancel is not None and cancel.is_set():
                            break
                        if not s.strip():
                            continue
                        audio = await asyncio.to_thread(self.synthesize, s)
                        if cancel is not None and cancel.is_set():
                            break
                        await queue.put(audio)
            finally:
                with contextlib.suppress(asyncio.QueueFull):
                    queue.put_nowait(None)

        prod_task = asyncio.create_task(producer())
        first_seen = False
        try:
            while True:
                if cancel is not None and cancel.is_set():
                    break
                item = await queue.get()
                if item is None:
                    break
                if not first_seen:
                    first_seen = True
                    if on_first_chunk is not None:
                        on_first_chunk()
                yield item
                if cancel is not None and cancel.is_set():
                    break
        finally:
            prod_task.cancel()
            while not queue.empty():
                with contextlib.suppress(asyncio.QueueEmpty):
                    queue.get_nowait()
            with contextlib.suppress(asyncio.CancelledError):
                await prod_task


class AudioPlayer:
    """Відтворення аудіо з передачею render reference для AEC, хуками руху та миттєвою зупинкою."""

    def __init__(
        self,
        *,
        on_render_reference: Callable[[np.ndarray], None] | None = None,
        on_playback_start: Callable[[], None] | None = None,
        on_playback_end: Callable[[], None] | None = None,
        use_hardware: bool = False,
        simulated_max_duration_s: float = 0.25,
    ):
        self.on_render_reference = on_render_reference
        self.on_playback_start = on_playback_start
        self.on_playback_end = on_playback_end
        self.use_hardware = use_hardware
        self.simulated_max_duration_s = simulated_max_duration_s
        self.is_playing = False
        self.last_playback_started_ns: int = 0
        self.last_playback_ended_ns: int = 0
        self._proc: asyncio.subprocess.Process | None = None
        self._stop_event = asyncio.Event()

    async def play(
        self,
        audio: SynthesizedAudio,
        *,
        cancel: asyncio.Event | None = None,
    ) -> bool:
        """Відтворити синтезовану фразу й передати точний render reference."""
        if not audio.pcm_int16:
            return False
        if cancel is not None and cancel.is_set():
            return False

        self._stop_event.clear()
        self.is_playing = True
        self.last_playback_started_ns = time.monotonic_ns()
        if self.on_playback_start is not None:
            with contextlib.suppress(Exception):
                self.on_playback_start()
        if self.on_render_reference is not None:
            self.on_render_reference(audio.to_float32_16k())

        try:
            if self.use_hardware:
                pw_play = shutil.which("pw-play")
                aplay = shutil.which("aplay")
                if pw_play:
                    cmd = [
                        pw_play,
                        "--format",
                        "s16",
                        "--rate",
                        str(audio.sample_rate),
                        "--channels",
                        "1",
                        "-",
                    ]
                elif aplay:
                    cmd = [
                        aplay,
                        "-q",
                        "-f",
                        "S16_LE",
                        "-r",
                        str(audio.sample_rate),
                        "-c",
                        "1",
                        "-t",
                        "raw",
                        "-",
                    ]
                else:
                    cmd = []
                if cmd:
                    self._proc = await asyncio.create_subprocess_exec(
                        *cmd,
                        stdin=asyncio.subprocess.PIPE,
                        stdout=asyncio.subprocess.DEVNULL,
                        stderr=asyncio.subprocess.DEVNULL,
                    )
                    assert self._proc.stdin is not None
                    # Пишемо блоками з перевіркою cancel проти блокування drain() (V-010)
                    chunk_bytes = max(2048, audio.sample_rate * 2 // 10)  # ~100 мс
                    raw = audio.pcm_int16
                    for offset in range(0, len(raw), chunk_bytes):
                        if self._stop_event.is_set() or (cancel is not None and cancel.is_set()):
                            self._proc.terminate()
                            return False
                        self._proc.stdin.write(raw[offset : offset + chunk_bytes])
                        with contextlib.suppress(
                            asyncio.TimeoutError, BrokenPipeError, ConnectionResetError
                        ):
                            await asyncio.wait_for(self._proc.stdin.drain(), timeout=0.5)
                    with contextlib.suppress(Exception):
                        self._proc.stdin.close()
                    while self._proc.returncode is None:
                        if self._stop_event.is_set() or (cancel is not None and cancel.is_set()):
                            self._proc.terminate()
                            break
                        await asyncio.sleep(0.01)
                    return not (
                        self._stop_event.is_set() or (cancel is not None and cancel.is_set())
                    )

            step_s = 0.02
            remaining = min(audio.duration_s, self.simulated_max_duration_s)
            while remaining > 0:
                if self._stop_event.is_set() or (cancel is not None and cancel.is_set()):
                    return False
                await asyncio.sleep(min(step_s, remaining))
                remaining -= step_s
            return True
        finally:
            self.is_playing = False
            self.last_playback_ended_ns = time.monotonic_ns()
            self._proc = None
            if self.on_playback_end is not None:
                with contextlib.suppress(Exception):
                    self.on_playback_end()

    def stop(self) -> float:
        """Негайно перервати відтворення й повернути час зупинки (time-to-stop) у мілісекундах."""
        t0 = time.perf_counter()
        self._stop_event.set()
        if self._proc is not None and self._proc.returncode is None:
            with contextlib.suppress(ProcessLookupError):
                self._proc.terminate()
        self.is_playing = False
        return round((time.perf_counter() - t0) * 1000.0, 3)
