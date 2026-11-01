---
type: topic
updated: 2026-11-01
status: compiled
sources: [raw/B-12_Master_Project_2026-10-24.md, evals/voice/licenses.json, evals/voice/report.json, evals/voice/duplex/report.json]
tags: [voice, ukrainian, latency, duplex, aec, speaker]
---
# Голосовий шар (Tasks 16–17, R15)

**Вимоги з brief §7 та spec §12:** локальний UA/EN/code-switching діалог, PTT і full-duplex, barge-in, відсікання власного TTS (AEC render reference) і фонового медіа, окремий контроль `mute` та `consent`, volatile сирий мікрофон за замовчуванням, а також реєстрація голосу виключно через контрольний шлях (схожість голосу ніколи не є авторизацією).

## Реалізована архітектура (`src/b12/audio/`)

Каскад реалізовано у модулях [capture.py](../../src/b12/audio/capture.py) → [aec.py](../../src/b12/audio/aec.py) → [endpoint.py](../../src/b12/audio/endpoint.py) → [asr.py](../../src/b12/audio/asr.py) → [pipeline.py](../../src/b12/audio/pipeline.py) (`Runtime.agent.turn`) → [tts.py](../../src/b12/audio/tts.py) → [duplex.py](../../src/b12/audio/duplex.py) та [speaker.py](../../src/b12/audio/speaker.py):

| Компонент | Реалізація в B-12 | Ліцензія та перевірені артефакти |
|---|---|---|
| Захоплення (PTT / stream) | `MicController` + `PttCapture` (`pw-record` / `arecord` 16 кГц s16 → volatile `float32`); `mic_muted` у `ControlStore` окремо від `actor.consent` | Власний код (`Apache-2.0`); сирі `.wav`/`.pcm` за замовчуванням не пишуться на диск |
| VAD та Endpoint | `SileroVad` (`silero_vad.onnx`, ONNX Runtime CPU, 64-семпловий контекст для 512-семплових вікон 32 мс) + `EndpointDetector` | `snakers4/silero-vad` (`MIT`); розділяє `physical_eou_sample` і `decision_sample` |
| ASR | `WhisperAsr` (`Systran/faster-whisper-small`, CTranslate2 `int8`, однопрохідний `encode` із обмеженням авто-мови до `{uk, en}`) | `faster-whisper` / OpenAI Whisper (`MIT`); підтримка UA, EN та code-switching |
| TTS | `PiperTts` (`uk_UA-ukrainian_tts-medium.onnx`, `uk_UA-mykyta-high.onnx`, `en_US-lessac-medium.onnx`), нормалізація чисел/акронімів UA, обмежена черга фраз (`max_queue_phrases`) | Engine `piper-tts` (`MIT`), голоси `CC0-1.0` / `Apache-2.0` / Blizzard Lessac ([licenses.json](../../evals/voice/licenses.json)) |
| AEC та анти-self-trigger | `AcousticEchoCanceller` (NLMS + кореляційне пригнічення за точним 16 кГц `render_reference` плеєра + текстовий фільтр самовідлуння) | ERLE `148,6–156,3 дБ` на синтетичному reference ([duplex/report.json](../../evals/voice/duplex/report.json)) |
| Speaker verification | `SpeakerStore` (`SQLite` із `secure_delete = ON`) + `SpeakerVerifier` (спектрально-гармонічний voiceprint + захист від exact-replay та spoof) | Enrollment лише через контрольний шлях власника; інструменти моделі не мають доступу до реєстрації |
| Інтерфейси | CLI `b12 voice {status,mute,unmute,say,listen}`, HTTP `/api/voice/{status,mute,tts,asr,speaker/*}`, Web UI (`🎙 Голос`, `Mute мікр.`, `Озвучувати`) | Покрито інтеграційними тестами `tests/integration/test_voice.py` та `tests/integration/test_duplex.py` |

## Виміряні метрики на локальному хості (31.10.2026)

Джерела: [evals/voice/report.json](../../evals/voice/report.json) та [evals/voice/duplex/report.json](../../evals/voice/duplex/report.json) на `Ubuntu 24.04.5, i9-14900HX, CPUExecutionProvider (int8)` (**перевірений факт**):

- **Cold start (CPU):** TTS `1717,03 мс`, ASR `2746,10 мс`.
- **Warm TTS TTFA (Time-To-First-Audio):** P50 `258,57 мс` (діапазон `166–422 мс` для типових фраз 2,7–4,8 с), P95 `1595,77 мс`.
- **Endpoint latency (`physical_eou_to_endpoint_ms`):** P50 `320,0 мс` (10 фреймів тиші по 32 мс після завершення мовлення). Earcon обліковується окремо (`earcon_ms`) і не зараховується як змістовне аудіо.
- **Warm ASR latency (`faster-whisper-small` CPU int8):** P50 `2359,13 мс`, P95 `2478,74 мс`. Середній WER на синтезованому корпусі: EN `4,17 %` (`0,0417`), UA `39,24 %` (`0,3924`, фонетичні розбіжності синтезованого TTS без помилок визначення мови).
- **Barge-in та переривання:** зупинка плеєра й очищення черги TTS при перебиванні займає P50 `0,029 мс`, P95 `0,039 мс`, P99 `0,040 мс` (`interruption_time_to_stop_ms: 0,008 мс`).
- **Speaker verification та anti-replay:** FRR `0,0` (10/10), FAR `0,0` (10/10), exact bit-for-bit replay атака блокується (`exact_replay_blocked: true`).

## Відкриті межі достовірності

- Реалізовано повний програмний стек M2/M3 (Tasks 16–17), інтеграційні тести та локальні бенчмарки.
- **Потребує перевірки у фізичній кімнаті власника:** 8-годинний акустичний full-duplex soak із реальним динаміком, мікрофоном, фоновим телевізором/шумом та одночасним GPU-навантаженням (`limits.physical_8h_acoustic_soak = open`).
