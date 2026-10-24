---
type: topic
updated: 2026-10-24
status: candidates
sources: [raw/B-12_Master_Project_2026-10-24.md, wiki/sources/external-checks.md]
tags: [models, benchmark]
---
# Моделі та план порівняння

За brief §8 основний новий кандидат — Nemotron 3.5 Bolt E4B Q4; comparators — Gemma 4 E4B/E2B, Qwen 3.5 4B і lightweight Gemma 3 1B. Bolt встановлено як тестовий Ollama alias та [вперше виміряно](../project/bolt-first-test.md); остаточний вибір і інтеграція в когнітивне ядро B-12 ще не зроблені. [Аудит системи](../project/model-test-readiness.md) також виявив наявні поза проєктом Gemma E2B/E4B для можливого порівняння.

[Незалежна перевірка](../sources/external-checks.md) підтвердила опубліковані NVIDIA 5 785 мс TTFT для Bolt на Nano 8GB при 3K нових токенів без кешу. **Інженерний висновок:** цей режим не вкладається у голосову ціль 1,5 с, навіть до ASR/TTS. Це не доводить неможливість іншої конфігурації: менший prompt, кеш, reasoning settings і інший host потребують власних замірів.

Bolt не створює [автобіографічну пам’ять](memory.md) чи [ініціативу](autonomy.md) сам по собі. Великий контекст не замінює retrieval; потрібні короткий prompt і вимірювання prefill. Зір викликається на значущих подіях, без обов’язкової VLM на кожен кадр.

## Пропозиція першого A/B експерименту

Однаковий версійований набір UA/EN/code-switch сценаріїв: grounding, recall, незгода з аргументом, tool schemas, тиша/ініціатива, спростування помилкового спогаду. Однакові limits і prompt-політика; відмінності model chat template й reasoning явно записати. Не підміняти порівняння якості порівнянням різних бюджетів.

Зберігати JSONL сирих результатів і manifest: host, runtime commit, модель/hash, quantization, input/output tokens, warm/cold/cache, seed/temperature, context size, wall time, TTFT, token rate, memory та judge/rubric. Розділяти deterministic tests tools/permissions і суб’єктивні оцінки характеру/мови. Для перцентилів записати кількість повторів.

Спочатку короткі текстові сценарії, потім 50–100 ходів, далі голос і [спільне навантаження Jetson](hardware.md). Результат може обрати різні моделі для швидкого діалогу й повільної рефлексії. Це варіант для перевірки, не новий прийнятий ADR. [Наступні дії](../project/roadmap.md).

## Уточнення після огляду локальної системи

RTX 4060 Laptop 8GB / Ollama 0.33.3 успішно запустили офіційний text-only Q4_K_M без drafter: warm decode ~62–64 tok/s, uncached first-content medians ~0,17–0,56 с для ~440–1700 нових токенів; cold first-content ~29,82 с. Точні умови, недоліки поведінки та overflow case наведені у [власному експерименті](../project/bolt-first-test.md). Це не результат Nano та не voice SLO.

Registry `nemotron-3.5-bolt:latest` веде на більший 74B-A9B пакет, а `:e4b` додає projector і drafter. [Точні manifests](../project/model-test-readiness.md) запобігають підміні конфігурації. Наявні Gemma QAT Q4_0 не мають тотожної Bolt Q4_K_M квантизації; це потрібно врахувати при порівнянні. Мовчазне context truncation здатне видалити instructions, тому token admission control має передувати довгим діалогам.
