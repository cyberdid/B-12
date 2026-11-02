"""Оцінювання голосового конвеєра B-12 (Task 16): UA/EN/code-switch WER, TTFA, endpoint."""

import asyncio
import hashlib
import json
import re
import time
from datetime import UTC, datetime
from pathlib import Path

import numpy as np

from b12.audio.asr import WhisperAsr
from b12.audio.endpoint import EndpointDetector
from b12.audio.tts import AudioPlayer, PiperTts

CORPUS = [
    {"id": "ua-01", "lang": "uk", "text": "Привіт, Олександре, система працює стабільно."},
    {"id": "ua-02", "lang": "uk", "text": "Перевір, будь ласка, стан локальної пам'яті."},
    {"id": "ua-03", "lang": "uk", "text": "Запам'ятай, що мій улюблений колір синій."},
    {"id": "ua-04", "lang": "uk", "text": "Яка зараз температура процесора та відеокарти?"},
    {"id": "en-01", "lang": "en", "text": "Hello friend, the local voice pipeline is ready."},
    {"id": "en-02", "lang": "en", "text": "Please check the system status and active processes."},
    {"id": "en-03", "lang": "en", "text": "Remember that the backup schedule runs every night."},
    {"id": "cs-01", "lang": "uk", "text": "Запусти перевірку local runtime та покажи статус."},
]

_WORD_RE = re.compile(r"[0-9a-zа-яіїєґ']+")


def _words(text: str) -> list[str]:
    return _WORD_RE.findall(text.lower().replace("’", "'").replace("ʼ", "'"))


def word_error_rate(ref: str, hyp: str) -> float:
    r = _words(ref)
    h = _words(hyp)
    if not r:
        return 0.0 if not h else 1.0
    dp = list(range(len(h) + 1))
    for i, rw in enumerate(r, 1):
        prev = dp[0]
        dp[0] = i
        for j, hw in enumerate(h, 1):
            temp = dp[j]
            cost = 0 if rw == hw else 1
            dp[j] = min(dp[j] + 1, dp[j - 1] + 1, prev + cost)
            prev = temp
    return round(dp[-1] / len(r), 4)


def sha256_file(path: Path) -> str | None:
    if not path.is_file():
        return None
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


async def main() -> None:
    out_dir = Path(__file__).resolve().parent
    voices_dir = Path.home() / ".local" / "share" / "b12" / "voices"

    licenses = {
        "generated_at_utc": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "components": [
            {
                "role": "TTS (Ukrainian multi-speaker)",
                "model": "uk_UA-ukrainian_tts-medium.onnx",
                "engine": "piper-tts 1.8.0 (MIT)",
                "dataset_url": "https://github.com/OHF-Voice/voice-datasets",
                "license": "CC0-1.0",
                "sample_rate": 22050,
                "sha256": sha256_file(voices_dir / "uk_UA-ukrainian_tts-medium.onnx"),
            },
            {
                "role": "TTS (Ukrainian high espeak)",
                "model": "uk_UA-mykyta-high.onnx",
                "engine": "piper-tts 1.8.0 (MIT)",
                "dataset_url": "https://github.com/egorsmkv/ukrainian-tts-datasets",
                "license": "Apache-2.0",
                "sample_rate": 22050,
                "sha256": sha256_file(voices_dir / "uk_UA-mykyta-high.onnx"),
            },
            {
                "role": "TTS (English Lessac)",
                "model": "en_US-lessac-medium.onnx",
                "engine": "piper-tts 1.8.0 (MIT)",
                "dataset_url": "https://www.cstr.ed.ac.uk/projects/blizzard/2013/lessac_blizzard2013/",
                "license": "Blizzard 2013 Lessac Research/Permissive",
                "sample_rate": 22050,
                "sha256": sha256_file(voices_dir / "en_US-lessac-medium.onnx"),
            },
            {
                "role": "VAD / Endpoint",
                "model": "silero_vad.onnx",
                "engine": "onnxruntime 1.31.1 (MIT)",
                "source_url": "https://github.com/snakers4/silero-vad",
                "license": "MIT",
                "sample_rate": 16000,
                "sha256": sha256_file(voices_dir / "silero_vad.onnx"),
            },
            {
                "role": "ASR (UA/EN/code-switch)",
                "model": "Systran/faster-whisper-small",
                "engine": "faster-whisper 1.2.1 / CTranslate2 4.8.4 (MIT)",
                "license": "MIT",
                "sample_rate": 16000,
            },
        ],
    }
    (out_dir / "licenses.json").write_text(
        json.dumps(licenses, ensure_ascii=False, indent=2) + "\n"
    )

    tts = PiperTts()
    asr = WhisperAsr()
    endpoint = EndpointDetector()

    # Measure cold start (both UK and EN models)
    t0 = time.perf_counter()
    cold_audio = tts.synthesize(CORPUS[0]["text"], lang="uk")
    _ = tts.synthesize(CORPUS[4]["text"], lang="en")
    cold_tts_ms = round((time.perf_counter() - t0) * 1000.0, 2)
    t0 = time.perf_counter()
    _ = asr.transcribe_pcm(cold_audio.pcm_int16, sample_rate=cold_audio.sample_rate, language="uk")
    cold_asr_ms = round((time.perf_counter() - t0) * 1000.0, 2)

    cases_report = []
    ttfa_list = []
    asr_ms_list = []
    ep_ms_list = []
    wer_by_lang: dict[str, list[float]] = {"uk": [], "en": []}

    for item in CORPUS:
        synth = tts.synthesize(item["text"], lang=item["lang"])
        ttfa_list.append(synth.ttfa_ms)
        speech_16k = asr.to_float32_16k(synth.pcm_int16, sample_rate=synth.sample_rate)
        padded_16k = np.concatenate([speech_16k, np.zeros(int(16000 * 0.4), dtype=np.float32)])

        ep = endpoint.detect_utterance(padded_16k)
        ep_ms_list.append(ep.physical_eou_to_endpoint_ms)

        tr = asr.transcribe(ep.speech_audio, language=item["lang"])
        asr_ms_list.append(tr.asr_latency_ms)
        wer = word_error_rate(item["text"], tr.text)
        wer_by_lang[item["lang"]].append(wer)

        cases_report.append(
            {
                "id": item["id"],
                "lang": item["lang"],
                "reference": item["text"],
                "hypothesis": tr.text,
                "wer": wer,
                "tts_ttfa_ms": synth.ttfa_ms,
                "asr_latency_ms": tr.asr_latency_ms,
                "physical_eou_to_endpoint_ms": ep.physical_eou_to_endpoint_ms,
                "audio_duration_s": synth.duration_s,
            }
        )

    # Measure player interruption time-to-stop
    player = AudioPlayer(use_hardware=False)
    play_task = asyncio.create_task(player.play(cold_audio))
    await asyncio.sleep(0.02)
    stop_ms = player.stop()
    await play_task

    report = {
        "generated_at_utc": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "host": "Ubuntu 24.04.5, i9-14900HX, CPUExecutionProvider (int8)",
        "measurement_scope": "tts_to_asr_synthetic_roundtrip_smoke_test",
        "cold_start": {"tts_ms": cold_tts_ms, "asr_ms": cold_asr_ms},
        "summary": {
            "cases": len(cases_report),
            "uk_mean_wer": round(float(np.mean(wer_by_lang["uk"])), 4),
            "en_mean_wer": round(float(np.mean(wer_by_lang["en"])), 4),
            "tts_ttfa_p50_ms": round(float(np.percentile(ttfa_list, 50)), 2),
            "tts_ttfa_p95_ms": round(float(np.percentile(ttfa_list, 95)), 2),
            "asr_p50_ms": round(float(np.percentile(asr_ms_list, 50)), 2),
            "asr_p95_ms": round(float(np.percentile(asr_ms_list, 95)), 2),
            "physical_eou_to_endpoint_p50_ms": round(float(np.percentile(ep_ms_list, 50)), 2),
            "interruption_time_to_stop_ms": stop_ms,
        },
        "cases": cases_report,
    }
    (out_dir / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(report["summary"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
