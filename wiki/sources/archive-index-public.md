---
type: source
updated: 2026-10-24
status: reviewed_selected_source
sources: [raw/archive-index-public-7ad80dcdc7e3/SOURCE.json, raw/archive-index-public-7ad80dcdc7e3/REVIEW.json, raw/archive-index-public-7ad80dcdc7e3/SHA256.json]
tags: [archive, retrieval, source-review]
---
# archive-index-public

Надано власником: [cyberdid/archive-index-public](https://github.com/cyberdid/archive-index-public). За GitHub API зафіксовано commit `7ad80dcdc7e327b7dd1b352ab5e6dc38a00d784a`, дата commit 23.10.2026. Переглянуто README, packaging/license metadata та вибрані модулі пошуку, SQLite store, embeddings, CLI, MCP, chunking і redaction.

**Це окремий retrieval engine.** Він не є підтвердженням, що знайдено історичний memory kernel B-12. Старий kernel, його consent policy та latency logs досі не встановлені.

## Локальні докази

- [SOURCE.json](../../raw/archive-index-public-7ad80dcdc7e3/SOURCE.json) фіксує 16 вибраних файлів, upstream Git blob IDs і розміри. Копії байтово збігаються; [SHA256.json](../../raw/archive-index-public-7ad80dcdc7e3/SHA256.json) дає контрольні суми. Це вибірковий знімок для review, не повна installable копія repo.
- [REVIEW.json](../../raw/archive-index-public-7ad80dcdc7e3/REVIEW.json): 17 upstream core tests пройшли в наявному venv з імпортом саме snapshot package, без pytest cache/plugin autoload. Тестувалися chunking, леми, redaction, query expressions і окремі store/search helpers; повний suite не запускався.
- Окрема synthetic перевірка на тимчасовій SQLite: новий документ доступний lexical search одразу; semantic VectorCache бачить його після явного refresh. Відтворений cache-freshness нюанс збережено в REVIEW.
- `archive` і `archive-tui` установлені в `/home/cyberdid/.local/share/embeddinggemma2/venv`; package `archive-index` 0.1.0 editable з `/home/cyberdid/Projects/llm/archive-index`. Перевірені локальні source blob IDs відрізняються від публічного snapshot. Поведінку інстальованої версії не можна автоматично прирівнювати до цього review.

Production archive DB не відкривалась; приватні документи/сесії не шукались і не переносились. Embedding model не завантажувалась у GPU. Код, інсталяція, таймери й production services не змінювалися.

## Підтверджені можливості й межі

[store.py](../../raw/archive-index-public-7ad80dcdc7e3/src/archive_index/store.py) містить SQLite documents/chunks/FTS5, source paths, locators, hashes і timestamps. [search.py](../../raw/archive-index-public-7ad80dcdc7e3/src/archive_index/search.py) об’єднує lexical/semantic результати з project/collection filters. [mcp_server.py](../../raw/archive-index-public-7ad80dcdc7e3/src/archive_index/mcp_server.py) відкриває `archive_search` і `archive_stats`.

Store оновлює й видаляє chunks; це mutable derived index. У переглянутій schema немає контрактів consent/owner/guest або canonical event ledger. Project filter має prefix semantics, а не роль контролю доступу. Redaction приховує відомі форми секретів, але не надає згоди на збереження даних.

За [LICENSING.md](../../raw/archive-index-public-7ad80dcdc7e3/LICENSING.md) software має Apache-2.0, paper/experimental records — окремий CC BY 4.0 scope. LICENSE і NOTICE збережені. Ваги, dependencies й чужі дані мають власні умови; повний юридичний аудит не проводився.

План використання без автоматичного перенесення приватного архіву — [retrieval для B-12](../topics/archive-retrieval.md).
