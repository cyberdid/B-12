---
type: topic
updated: 2026-11-02
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
| VAD та Endpoint | `SileroVad` (`silero_vad.onnx` / `silero_vad_v6.onnx`, ONNX Runtime CPU, 64-семпловий контекст для 512-семплових вікон 32 мс, `rms_silence_floor = 0.002`, без штучного RMS-бустингу в продакшені) + потоковий `EndpointDetector.feed_stream_chunk()` із кільцевим `lookback`-буфером | `snakers4/silero-vad` (`MIT`); розділяє `physical_eou_sample` і `decision_sample`, зберігає LSTM-стан між фреймами |
| ASR | `WhisperAsr` (`Systran/faster-whisper-small`, CTranslate2 `int8`, `warmup()` у пам'яті, авто-фолбек на CPU при помилці CUDA, доменні `initial_prompt` + `hotwords`, канонізація code-switching, одноразовий виклик на хід у `DuplexSession`) | `faster-whisper` / OpenAI Whisper (`MIT`); нульовий WER (`0.0`) на синтетичному корпусі UA/EN/code-switching |
| TTS та стрімінг | `PiperTts` (дефолтний український голос `uk_UA-mykyta-high.onnx` на espeak-фонемах із фолбеком на `uk_UA-ukrainian_tts-medium.onnx`, англійський `en_US-lessac-medium.onnx`), адаптивне дроблення на клаузи `extract_stream_clauses()` (від 3+ слів на розділових знаках), 3-ступеневий паралельний пайплайн у `VoicePipeline` та конкурентні `asyncio.Task` продюсера/консюмера у `DuplexSession.speak_response()` | Engine `piper-tts` (`MIT`), голоси `Apache-2.0` / `CC0-1.0` / Blizzard Lessac ([licenses.json](../../evals/voice/licenses.json)); відтворення фрази №1 стартує до завершення генерації LLM |
| AEC та анти-self-trigger | `AcousticEchoCanceller` (128-таповий FIR NLMS-фільтр із FFT-вирівнюванням причинної затримки, детектор double-talk за вирівняним reference, одноразовий прохід на фрейм у `BargeInResult.cleaned_audio`, збереження 1–2-слівних відповідей у `is_tts_echo_text`) + системний `PulseAudioWebRtcAec` (`pactl module-echo-cancel aec_method=webrtc`) | ERLE `30,41 дБ` (мін. `28,45 дБ`) на багатопроменевому RIR з шумом ([duplex/report.json](../../evals/voice/duplex/report.json)) |
| Плеєр і хуки руху | `AudioPlayer` із почанковим неблокуючим записом у PipeWire/ALSA, миттєвим `stop()` та хуками `on_playback_start` / `on_playback_end` для синхронізації жестів | Відсутність блокування потoку на довгих PCM-буферах |
| Speaker verification | `SpeakerStore` (`SQLite` із `secure_delete = ON`) + `SpeakerVerifier` (16 DCT-II MFCC-подібних кепстральних коефіцієнтів + log-mel + F0 гармонічний профіль + захист від exact-replay) + інтеграція в `PurgeCoordinator.forget_voice_profile()` | Enrollment лише через контрольний шлях власника; інструменти моделі не мають доступу до реєстрації |
| Інтерфейси | CLI `b12 voice {status,mute,unmute,say,listen}`, HTTP `/api/voice/{status,mute,tts,asr,speaker/*}`, Web UI (`🎙 Голос`, `Mute мікр.`, `Озвучувати`), ізольоване скасування лише активного голосового ходу при barge-in | Покрито 12 інтеграційними тестами у `tests/integration/test_voice.py` (7) та `tests/integration/test_duplex.py` (5) |

## Виміряні метрики на локальному хості (02.11.2026)

Джерела: [evals/voice/report.json](../../evals/voice/report.json) та [evals/voice/duplex/report.json](../../evals/voice/duplex/report.json) на `Ubuntu 24.04.5, i9-14900HX, CPUExecutionProvider (int8)` (**перевірений факт**, програмний roundtrip та RIR-симуляція):

- **Точність TTS → ASR roundtrip (`faster-whisper-small` CPU int8 + `uk_UA-mykyta-high` / `en_US-lessac-medium`):** середній WER по всіх 8 кейсах (UA, EN, code-switching) становить **UA `0,0 %` (`0.0`)** та **EN `0,0 %` (`0.0`)** (після переходу на espeak-фонемізатор `uk_UA-mykyta-high` та збереження природної української пунктуації й регістру).
- **Warm TTS TTFA (Time-To-First-Audio):** EN `153,91–206,63 мс`, UA (`mykyta-high`, 22,05 кГц) `1575,61–2158,40 мс` (загальна медіана по корпусу P50 `1634,61 мс`, P95 `2441,51 мс`). Завдяки `extract_stream_clauses()` перша клауза з 3+ слів вирушає на синтез і програвання ще під час генерації решти відповіді LLM (`playback_started_before_llm_completed = True`).
- **Endpoint latency (`physical_eou_to_endpoint_ms`):** P50 `320,0 мс` (10 фреймів тиші по 32 мс після завершення мовлення). Earcon обліковується окремо (`earcon_ms`) і не зараховується як змістовне аудіо.
- **Warm ASR latency (`faster-whisper-small` CPU int8):** P50 `2173,58 мс`, P95 `2347,91 мс`.
- **AEC на симульованому багатопроменевому RIR із гаусовим шумом:** середній ERLE `30,41 дБ` (мінімум `28,45 дБ` по 5 прогонах).
- **Barge-in та переривання (реальне мовлення поверх TTS через чистий ONNX Silero VAD без RMS-оверрайду):** внутрішній програмний час зупинки плеєра, скасування голосового ходу й очищення черги становить P50 `0,025 мс`, P95 `0,036 мс`, P99 `0,042 мс`. Паралельні ходи в інших сесіях (Web/TUI/CLI) не скасовуються.
- **Speaker verification та anti-replay (діагностичний акустичний верифікатор):** FRR `0,0` (10/10), FAR `0,0` (10/10), exact bit-for-bit replay атака блокується (`exact_replay_blocked: true`).

## Відкриті межі достовірності

- Реалізовано повний програмний стек M2/M3 (Tasks 16–17), усунено всі функціональні зауваження рев'ю `V-001`..`V-011`, додано інженерні патерни з `reachy-mini-jetson-assistant`, виконано інтеграційні тести та локальні бенчмарки.
- **Потребує перевірки у фізичній кімнаті власника:** 8-годинний акустичний full-duplex soak із реальним динаміком, мікрофоном, фоновим телевізором/шумом та одночасним GPU-навантаженням (`limits.physical_8h_acoustic_soak = open`).
