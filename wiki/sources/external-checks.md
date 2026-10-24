---
type: evidence
updated: 2026-10-24
status: partial
sources: [wiki/sources/master-brief.md, raw/source-manifest.json]
tags: [verification, external]
---
# Незалежна перевірка зовнішніх тверджень

Дата доступу: 24.10.2026. Перевірка вибіркова; повних локальних знімків сторінок і pinned commits немає. Деталі стану перевірок зберігаються в [маніфесті](../../raw/source-manifest.json).

| Джерело | Що перевірено зараз | Межа доказу |
|---|---|---|
| [NVIDIA Research: Bolt E4B](https://research.nvidia.com/labs/nemotron/NVIDIA-Nemotron-3.5-Bolt-E4B-4GB/) | Дата 23.10.2026; опис Cosmos → Bolt → Reachy на Nano 8GB; таблиця Q4_K_M, batch 1, llama.cpp CUDA: 5 785 мс TTFT, 4,2 GB, 15,5 tok/s при 0 cached / 3K input / 50 output | Це дані авторів, а не наш прогін; опис демонстрації не дає профілю всього B-12 |
| [NVIDIA Reachy Assistant README](https://github.com/NVIDIA-AI-IOT/reachy-mini-jetson-assistant) | Ціль Lite; один 100 Hz writer рухів; memory/multilingual згадані в roadmap; software-only timings виключають фізичні етапи | Прочитано README, не проведено аудит коду й не виконано запуск |
| [Wireless issue #3](https://github.com/NVIDIA-AI-IOT/reachy-mini-jetson-assistant/issues/3) | URL відкрито; доступного тексту недостатньо для незалежної перевірки всіх коментарів | Відомості про авторів/дати/готовність адаптера залишаються зі слів brief |
| [NVIDIA Bolt model card та HF API](https://huggingface.co/nvidia/NVIDIA-Nemotron-3.5-Bolt-E4B-4GB) | Прочитано selected deployment metadata; API дав exact revision, GGUF size і SHA-256 | Ваги не завантажені, inference й повна перевірка ліцензії не проведені; [докази](system-audit-2026-10-24.md) |
| [Ollama library та registry](https://ollama.com/library/nemotron-3.5-bolt) | Перевірено відмінність latest/e4b та склад шарів remote manifests | Library package не дорівнює чистому text-only GGUF; manifests можуть змінюватись; знімки API збережені в аудиті |

Інші 111 URL з brief, зокрема Cosmos demo, інші model cards, hardware specs, каталоги голосів, ліцензії та ціни магазинів, **не перевірено незалежно в цих роботах**. Їхні історичні позначки у §19 оригіналу збережено як твердження джерела. Згадка в каталозі не означає вибір залежності.

Інженерні наслідки наведені в [аналізі](../project/analysis.md), [моделях](../topics/models.md) і [обладнанні](../topics/hardware.md).
