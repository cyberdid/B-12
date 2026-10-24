---
type: topic
updated: 2026-10-24
status: proposed
sources: [raw/B-12_Master_Project_2026-10-24.md, wiki/sources/external-checks.md]
tags: [reachy, jetson, deployment]
---
# Reachy Mini, Jetson і розміщення

**Зі слів brief §9–11:** бажаний корпус — Reachy Mini Wireless, простіший SDK baseline — Lite; особистий Orin Nano Super 8GB ще планувався. Купівля й доступність обладнання не підтверджені. Робочі Jetson користувача не є пристроями B-12.

| Варіант | Можлива перевага | Питання до рішення |
|---|---|---|
| Lite + host | Прямий локальний доступ до media | Живлення, host requirements, фізичний UX |
| Wireless + host | Більша свобода розташування | Duplex media, reconnect, AEC reference, clock sync |
| Nano 8GB самостійно | Один edge host | Реальні RAM і latency всього стеку |
| Nano + ноутбук | Розділення LLM і perception | Затримка LAN, authoritative memory, режим без ноутбука |
| NX 16GB пізніше | Потенційно більший запас | Потреба має випливати із profiling, а не припущення |

У [зовнішній перевірці](../sources/external-checks.md) підтверджено Lite target NVIDIA assistant. Опис NVIDIA спільного Reachy/Bolt/Cosmos demo не встановлює спосіб residency моделей або поведінку повного аудіостеку. Сумувати файловий розмір GGUF, standalone peak і відсоток RAM іншого demo як один бюджет некоректно.

**План перевірки на власному пристрої:** Bolt-only → Cosmos-only → послідовна спільна конфігурація → concurrent → ASR/TTS/VAD/media. Контексти 512/1024/2048/4096; повторити warm/cold; фіксувати system unified memory, process RSS/PSS, GPU allocator за доступності, swap, tegrastats, power mode, температури, OOM і dropouts. RSS не дорівнює повній зайнятості unified memory. Swap не зараховується як доказ real-time придатності.

Wireless transport спочатку перевіряти без LLM. При втраті host/Wi-Fi потрібні визначені safe motor state, mute/stop, стан пам’яті та reconnect без повторного виконання старих команд. Рішення про authoritative memory host і автономний degraded mode ще відкрите.

Ціни та строки продавців у master brief — історичні відомості без повторної перевірки. Ця сторінка не є рекомендацією придбати конкретний пристрій. [Питання Q3–Q7](../project/open-questions.md) та [M4–M5](../project/roadmap.md) визначають потрібні докази.
