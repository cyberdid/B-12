---
type: source
updated: 2026-10-24
status: measured
sources: [benchmarks/bolt-e4b-smoke-2026-10-24/report.json, benchmarks/bolt-e4b-smoke-2026-10-24/gguf-import-verification.json, raw/system-audit-2026-10-24.json]
tags: [evidence, bolt, local-experiment]
---
# Докази першого локального запуску Bolt

За прямим дорученням власника виконано download → SHA-256 verification → окремий Ollama import → inference. [Звіт](../project/bolt-first-test.md) містить висновки; [каталог експерименту](../../benchmarks/bolt-e4b-smoke-2026-10-24/README.md) — команди й структуру артефактів.

## Походження

- [NVIDIA model card](https://huggingface.co/nvidia/NVIDIA-Nemotron-3.5-Bolt-E4B-4GB), pinned revision `1db54d5b12533ff1bcaa8e42cf4c667988a1f1be`; очікуваний upstream SHA-256 уже зафіксований [аудитом](system-audit-2026-10-24.md).
- [Download receipt](../../benchmarks/bolt-e4b-smoke-2026-10-24/download-receipt.json): розмір і повний SHA-256 збіглися. Xet stalled; застосовано byte-range HTTP download. Тимчасові фрагменти прибрано після успішної перевірки.
- [Cold run](../../benchmarks/bolt-e4b-smoke-2026-10-24/run-20261024T174305.749816Z/results.jsonl): один перший запит, UTC 17:43:05–17:43:45.
- [Головний smoke run](../../benchmarks/bolt-e4b-smoke-2026-10-24/run-20261024T174417.979468Z/results.jsonl): 13 запитів, UTC 17:44:17–17:44:27.
- [Prefill 20/60/120 lines](../../benchmarks/bolt-e4b-smoke-2026-10-24/prefill-20261024T174508Z/results.jsonl): 9 запитів; останні 3 виключені з performance comparison, див. review поруч.
- [Prefill 90 lines](../../benchmarks/bolt-e4b-smoke-2026-10-24/prefill-20261024T174612Z/results.jsonl): три коректні uncached measurements.

Разом 26 запитів: 23 не належать до overflow-групи; це кількість спостережень, не число пройдених поведінкових тестів. Payload synthetic; реальні tools, speaker data та memory не використовувалися. Reasoning text не зберігався.

## Імпорт GGUF

Ollama створив container layer digest `49eca097c81e38013c4a6278ade7d8541f4a50918000ee16f73ee151ca01c8bc`, відмінний від upstream `c8af…`. [Окрема перевірка](../../benchmarks/bolt-e4b-smoke-2026-10-24/gguf-import-verification.json) підтвердила actual hash імпортованого файла, однакові 720 tensor descriptors та байтово однаковий tensor payload. Metadata values за ключами теж однакові; header bytes відрізняються. Точну причину відмінності serialization header не досліджували, еквівалентність ваг перевірена.

Дані не доводять GPU memory peak, long-term stability, широкий UA quality або переносимість на Jetson. Обмеження й ручні оцінки наведено у [зведенні JSON](../../benchmarks/bolt-e4b-smoke-2026-10-24/report.json).

[Маніфест контрольних сум](../../benchmarks/bolt-e4b-smoke-2026-10-24/artifacts.sha256.json) покриває 49 файлів експерименту. Збережені результати не переписувати повторними прогонами: runners створюють нові каталоги, а нові висновки фіксуються окремо.
