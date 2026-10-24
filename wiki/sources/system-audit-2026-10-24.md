---
type: source
updated: 2026-10-24
status: verified_selected_checks
sources: [raw/system-audit-2026-10-24.json]
tags: [host, tools, provenance]
---
# Аудит локальної системи 24.10.2026

Джерело — виконані локальні команди, CUDA Driver API, read-only API Ollama та remote model manifests. [Сирий JSON](../../raw/system-audit-2026-10-24.json) записаний 24.10.2026 о 17:08:54 UTC / 20:08:54 Europe/Kyiv.

SHA-256: `a18c51ed3033b11f5771fc375dcb32f210d136a8e81151d5ec06ce19a84827fd`.

За запитом власника перевірено готовність його поточного комп’ютера до тесту NVIDIA Bolt E4B. Зібрано CPU/GPU/RAM/storage, версії tools, системні Python packages, стан localhost Ollama, manifests двох локальних model stores, метадані NVIDIA GGUF та registry Ollama. Паролі, токени, history і ключі не читались; захищене оточення service не отримано. Встановлень, завантажень ваг, inference, рестартів сервісів або доступу до Jetson не було.

Обмеження: snapshot ресурсів змінюється; існування model blobs не доводить їхніх hash/integrity або працездатності; bounded search не виключає runtime в іншій теці чи venv; Docker GPU і повний offload Ollama ще не тестовані. NVIDIA driver API повернув успіх, compute capability 8.9.

Технічні висновки та наступний тест — [готовність до Bolt](../project/model-test-readiness.md). API-відповіді remote manifests збережені у JSON, повні вебсторінки model card/library локально не архівовано.
