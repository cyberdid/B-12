---
type: source
updated: 2026-10-26
status: referenced_not_read
sources: [wiki/sources/archive-index-public.md]
tags: [archive-index, embeddinggemma, retrieval, benchmark, owner-research]
---
# Стаття власника про archive-index

**Перевірений факт (розташування):** окрема наукова робота власника про archive-index — lexical, dense і hybrid search, EmbeddingGemma 2, морфологія, квантування, ANN, GGUF і масштабування. Репозиторій `~/Projects/llm/archive-index`, гілка `paper`, коміт `4fd5084` (26.10.2026): `paper/manuscript/article-en.pdf` (SHA-256 `8924f9721d9756288f7806c19629f03e6d38561a7a2516d621924c59e9dd92a5`) і `paper/manuscript/article-uk.pdf` (SHA-256 `8f1e015245ee8c816b65eab3dadd577b02f7a63dcae4c1918d4e7c25ef96b39b`), таблиці — у `paper/manuscript/generated/`. Копію в `raw/` не робили: це окрема робота власника з власним версіонуванням.

**Межа:** у цій сесії статтю не читали. Її висновки про якість пошуку, квантування й масштабування — першоджерело власника; B-12 на них посилається і їх не переміряє.

**Що B-12 вимірює сам** (лише інтеграцію, деталі — у [agent loop](../topics/agent-loop.md)): EmbeddingGemma 2 через міст до встановленого archive-index — холодне завантаження ~16 с, +1.6 GB VRAM поруч із Bolt (~5.0 GB разом), теплий query 55–150 мс, поріг recall 0.7 за двома синтетичними прикладами. Окремо: MCP-пошук в архіві з реальним Bolt; перший виклик ~72 с через холодне завантаження моделі в процесі archive-index.

Пов’язано: [archive-index-public](archive-index-public.md), [archive-index для B-12](../topics/archive-retrieval.md).
