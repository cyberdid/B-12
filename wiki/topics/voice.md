---
type: topic
updated: 2026-10-24
status: proposed
sources: [raw/B-12_Master_Project_2026-10-24.md]
tags: [voice, ukrainian, latency]
---
# Голосовий шар

**Вимоги з brief §7:** локальний UA/EN/code-switching діалог, full-duplex, barge-in, відсікання власного TTS і фонового медіа. Ціль першого змістовного аудіо — <1,5 с після завершення репліки користувача. Власного підтвердженого результату немає; цільовий перцентиль потрібно визначити.

Каскад: mic → AEC з точним playback reference → VAD/endpoint → streaming ASR → [пам’ять](memory.md)/LLM/tools → phrase-streaming TTS → speaker. Interrupt і скасування черги працюють незалежно від LLM. Earcon має окрему метрику й не зараховується як змістовна відповідь.

| Компонент | Кандидати зі слів brief | Що треба перевірити |
|---|---|---|
| Початок взаємодії | PTT; wake пізніше | Надійність і UX згоди |
| AEC / VAD / endpoint | WebRTC AEC3 / Silero / Smart Turn | UA endpoint errors, self-transcription, barge-in |
| ASR | faster-whisper; whisper.cpp для edge | UA/EN WER, code-switch, RTF, GPU competition |
| Speaker verification | TitaNet; ECAPA/CAM++ альтернативи | FAR/FRR на власних умовах, replay; не права доступу |
| TTS | Piper UA; інші голоси лише після перевірки | Природність, TTFA, ліцензія engine й окремого голосу |
| Оркестрація | asyncio; Pipecat/Wyoming/LiveKit альтернативи | Cancellation, backpressure, audio dropouts |

Це дослідницькі кандидати, не встановлені залежності. Kokoro без перевіреного UA-голосу не закриває українську вимогу. AEC проти власного динаміка не гарантує відсікання телевізора. VoiceID/VoiceEvolve залишається окремим проєктом.

**Метрики:** від фізичного завершення репліки та окремо від endpoint decision до першого змістовного аудіо; P50/P95/P99; ASR WER; false endpoints; time-to-stop; dropout; CPU/GPU/RAM/температура. Потрібні 8 год duplex soak з шумом, ТБ, перебиваннями й GPU load.

**Пропозиція:** визначити <1,5 с як ціль P95 для конкретного сценарію; це уточнення ще не прийняте. [Моделі](models.md) пояснюють ризик TTFT на Nano; [обладнання](hardware.md) — невідомі Wireless transport. Перед full-duplex спочатку desktop PTT (M2), потім acoustic proof (M3).

[Перший текстовий тест Bolt](../project/bolt-first-test.md) на ноутбуці дав warm first-content ~0,17–0,56 с для ~440–1700 нових токенів. ASR, endpoint, TTS й audio playback не вимірювалися; голосова ціль цим не підтверджена. Cold request дав ~29,82 с до першого тексту, тому load/recovery режим треба врахувати окремо.
