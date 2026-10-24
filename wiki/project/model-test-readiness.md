---
type: readiness
updated: 2026-10-24
status: superseded_by_smoke_test
sources: [raw/system-audit-2026-10-24.json, wiki/sources/system-audit-2026-10-24.md]
tags: [nvidia, bolt, tools, local-host]
---
# Готовність до першого тесту NVIDIA Bolt

**Оновлення:** цей аудит описує стан до запуску. Надалі download, перевірку SHA-256, імпорт і перший тест виконано; поточні результати — [Перший тест Bolt](bolt-first-test.md). Формулювання «ще не завантажено/не виконано» нижче стосуються моменту первинного аудиту 20:08 Europe/Kyiv, а не поточного стану.

**Перевірений факт:** на поточному ноутбуці є GPU, робочий CUDA driver і запущений Ollama з CUDA backend. Цього достатньо для підготовки пробного GGUF-запуску без встановлення нового стеку. **Потребує перевірки:** фактичне завантаження Bolt, розбір його chat template, full GPU offload, latency і мовна якість. Inference у межах аудиту не запускався.

## Система

| Ресурс | Виявлено |
|---|---|
| ОС | Ubuntu 24.04.5 LTS, x86_64, kernel 7.0.0-38-generic |
| CPU | Intel Core i9-14900HX, 24 ядра / 32 потоки |
| RAM | 31 GiB доступної системі фізичної RAM; на початку огляду ~14 GiB available |
| GPU | NVIDIA GeForce RTX 4060 Laptop GPU, 8 188 MiB total; у snapshot близько 7,6 GiB free |
| Driver / CUDA | NVIDIA 610.57.04; CUDA Driver API 13.3, compute capability 8.9, `cuInit`/device queries успішні |
| CUDA Toolkit | 13.3, `nvcc` 13.3.73 у `/usr/local/cuda/bin`; у PATH не знайдений |
| Диск проєкту | Близько 10,4 GiB вільно на системному розділі |
| Диск моделей | Близько 192,9 GiB вільно на filesystem, де Downloads, обидва Ollama stores і HF cache |

Вільні RAM/VRAM — моментний стан, не гарантований бюджет тесту. Незвичну power telemetry GPU не використовували для висновків про споживання. Дискретна VRAM цього ноутбука відрізняється від unified RAM Jetson: результати не можна переносити без повторного тесту.

## Tools

| Інструмент | Статус і практичне значення |
|---|---|
| Ollama server | 0.33.3, API `127.0.0.1:11434` відповідає; `api/ps` порожній під час огляду |
| Ollama system CLI | `/usr/local/bin/ollama`, 0.33.3; збігається із server |
| Ollama у PATH | `/home/cyberdid/.local/bin/ollama`, 0.33.1; дає warning про різницю версій. Для тесту використовувати system CLI; глобальний PATH не змінювався |
| Ollama CUDA backend | `cuda_v12/libggml-cuda.so` і `cuda_v13/libggml-cuda.so` наявні |
| Hugging Face CLI | `hf` / `huggingface-cli`, huggingface-hub 1.29.0 |
| Python / uv | Python 3.12.3; uv 0.12.1 |
| llama.cpp standalone | `llama-cli`, `llama-server`, `llama-bench` не знайдені у PATH та перевірених типових місцях; бібліотеки всередині Ollama наявні |
| Docker | 29.8.1, daemon доступний; GPU execution не перевірений, `nvidia` runtime не зареєстрований у `docker info`; container toolkit package не знайдений |
| PyTorch / Transformers / vLLM | Не знайдені у системному Python; окремі venv не інвентаризувалися. Для Ollama вони не потрібні |

Активний server показує Gemma 12B і дві Qwen 27B, **Bolt у ньому немає**. Окремий user store містить Gemma E2B/E4B QAT Q4_0 та embeddinggemma з усіма очікуваними blobs; server їх не показує. Це потенційні comparators після перевірки походження й метаданих, не вже інтегровані моделі B-12. Копіювання або перемикання stores не виконувалося.

## Точний кандидат

[Офіційна NVIDIA model card](https://huggingface.co/nvidia/NVIDIA-Nemotron-3.5-Bolt-E4B-4GB) задає Q4_K_M text model. Через HF API перевірено:

- Repo: `nvidia/NVIDIA-Nemotron-3.5-Bolt-E4B-4GB`.
- Revision: `1db54d5b12533ff1bcaa8e42cf4c667988a1f1be`.
- Файл: `Nemotron-3.5-Bolt-E4B-Q4_K_M.gguf`.
- Розмір: 6 180 446 208 байтів, приблизно 6,18 GB / 5,76 GiB.
- Очікуваний SHA-256: `c8af2b8aea10a690a1d9491db744a9446660173cb38fc489612b556615a69612`.

Цього blob немає у двох перевірених Ollama stores. Файл не завантажений і hash локальної копії ще не перевірений. Розмір GGUF не є сумарною VRAM: потрібен запас на KV-cache і runtime.

**Пастка тега:** [Ollama library](https://ollama.com/library/nemotron-3.5-bolt) і registry зараз розрізняють `:e4b` та `:latest`. Registry `latest` містить близько 24,75 GB шарів більшої 74B-A9B моделі. `:e4b` містить потрібний 6,18 GB model blob, але також projector ~0,99 GB і drafter ~0,74 GB, загалом ~7,91 GB. Це не тотожний чистому text-only baseline пакет. Які шари runtime завантажує у VRAM, залежить від режиму й ще не перевірено.

## Рекомендований перший тест — ще не виконано

Використати наявний Ollama і **офіційний text-only NVIDIA GGUF без drafter**, з контекстом 2048, коротким output limit і одним запитом одночасно. Це пропозиція, а не доведений fit у 8 GB. Ваги розміщувати на filesystem моделей; не заповнювати системний розділ копіями.

Для відтворюваного завантаження підготовлено точну команду:

```bash
hf download nvidia/NVIDIA-Nemotron-3.5-Bolt-E4B-4GB \
  Nemotron-3.5-Bolt-E4B-Q4_K_M.gguf \
  --revision 1db54d5b12533ff1bcaa8e42cf4c667988a1f1be \
  --local-dir /home/cyberdid/Downloads/B-12-models/bolt-e4b-q4
```

Ця команда записана як наступний крок, не виконана аудитом. Після SHA-256 verification імпортувати локальний GGUF під окремим ім’ям B-12 у наявний runtime, перевірити chat template, reasoning/conversational controls і фактичне GPU розміщення. Почати з української відповіді, точного extraction/JSON і контрольованого tool-call сценарію без реальних зовнішніх дій.

Потім вимірювати cold load окремо від warm TTFT, decode tok/s і total time. До P50/P95 потрібні повтори й зафіксований корпус. Зберігати runtime version, model digest, settings, token counts, raw streaming timestamps та GPU/RAM snapshot. Модельна відповідь не є першим meaningful audio; голосовий SLO цим тестом не перевіряється. [Загальна методика](../topics/models.md).
