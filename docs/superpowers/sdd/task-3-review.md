# Task 3 — незалежний spec і quality gate

## Spec compliance

- ✅ **Відповідає task-scoped вимогам.** Переглянуто пакет `3c138bb..e33b926`; обов’язкові файли присутні. Додатковий `retrieval_storage.py` відділяє private namespace/SQLite lifecycle від public API, не розширює product scope.
- ✅ Exact actor isolation та safe filename mapping: `src/b12/retrieval_storage.py:190`; перевірка owner binding усередині Store: `src/b12/retrieval_storage.py:94`; однаковий абсолютний source path у двох actors і зміна ролі: `tests/integration/test_retrieval.py:36`.
- ✅ Consent перевіряється до resolve/read/persistence для ingest і до retrieval; owner bypass відсутній: `src/b12/retrieval.py:43`, `src/b12/retrieval.py:93`, `src/b12/retrieval.py:166`, `src/b12/retrieval.py:212`. Explicit own-data erasure після revoke не поновлює читання: `tests/integration/test_retrieval.py:324`.
- ✅ Strict versioned EvidenceRef, UUID identity, current revision та actor-bound resolver: `src/b12/contracts.py:108`, `src/b12/retrieval.py:212`; restart/idempotence/update/delete/re-ingest перевіряються реальними SQLite tests: `tests/integration/test_retrieval.py:92`, `tests/integration/test_retrieval.py:120`.
- ✅ Lifecycle authorization стоїть перед candidate limit; prefix filters не є auth: `src/b12/retrieval_storage.py:36`, `src/b12/retrieval_storage.py:117`. Search використовує один read transaction для upstream hits та metadata: `src/b12/retrieval.py:166`.
- ✅ Exact upstream modules, LICENSE/NOTICE та manifest присутні; byte/hash comparison із pinned raw snapshot покрито `tests/integration/test_retrieval.py:231`. Narrow lint exclusion не змінює vendor bytes: `pyproject.toml:35`. Lexical chunks використовують zero-length vectors; model download/production DB не викликаються: `src/b12/retrieval.py:93`, `src/b12/retrieval.py:166`.
- ✅ Видалення original file не виконується; tombstone зберігає keyed path identity, повторний ingest вимагає явного boolean: `src/b12/retrieval.py:63`, `src/b12/retrieval.py:93`, `src/b12/retrieval.py:238`. Bytes/path erasure і busy cleanup перевіряються на synthetic managed files: `tests/integration/test_retrieval.py:120`, `tests/integration/test_retrieval.py:151`.
- ⚠️ **Міжзадачні межі не перевірено цим gate:** shared memory/document/tool resolver, server-owned control revision/expiry, dependent canonical projections, sessions/goals/backups і active-turn cancellation. Їх явно залишено coordinator у `src/b12/retrieval.py:1`, `src/b12/retrieval.py:23`, `src/b12/retrieval.py:267`; Task 7 та наступні hooks мають перевірити delivery/deduplication receipts, stale evidence перед context/reflection persistence і global purge acknowledgement. Local `complete` не є global R05.

## Сильні сторони

- **Атомарність із незміненим upstream:** `DeferredCommit` відкладає internal commit тільки всередині `BEGIN IMMEDIATE`, а rollback охоплює document/FTS, source revision, evidence та outbox (`src/b12/retrieval_storage.py:65`, `src/b12/retrieval_storage.py:77`). Тест викликає справжній upstream mutator перед injected exception й після restart перевіряє попередню revision (`tests/integration/test_retrieval.py:296`).
- **Crash-safe invalidation:** UUID operation та invalidated IDs записуються в mutation transaction; unchanged retry повертає початковий receipt; окремий discovery API повертає навіть locally completed operations (`src/b12/retrieval.py:84`, `src/b12/retrieval.py:93`, `src/b12/retrieval.py:267`). Tests охоплюють pending update, first-call resume та реальну SQLite failure (`tests/integration/test_retrieval.py:244`, `tests/integration/test_retrieval.py:274`, `tests/integration/test_retrieval.py:340`).
- **Чесна cleanup visibility:** pending/failed sources приховані, а complete встановлюється після checkpoint/rebuild/VACUUM/checkpoint для зафіксованого набору operations (`src/b12/retrieval_storage.py:36`, `src/b12/retrieval_storage.py:141`). Реальний held WAL reader дає pending, а SQLite authorizer спричиняє справжній failure VACUUM, без mocked success (`tests/integration/test_retrieval.py:151`, `tests/integration/test_retrieval.py:340`).
- **Контрольована область I/O:** fixtures створюють synthetic source files і temp SQLite, перевіряють відсутність implicit scan, exact scope, opaque actor IDs та permissions без chmod unrelated parents (`tests/integration/test_retrieval.py:30`, `tests/integration/test_retrieval.py:74`, `tests/integration/test_retrieval.py:183`).

## Findings

- **Critical:** не виявлено.
- **Important:** не виявлено.
- **Minor:** не виявлено.

## Перевірки та межі review

- Diff прочитано одним послідовним проходом у bounded ranges; changed source files окремо не перечитувались. Незмінений початок `src/b12/contracts.py:46` перевірено адресно через конкретний ризик: EvidenceRef успадковує strict/extra/schema-version semantics. Виявлено `strict=True`, `extra="forbid"`, integer-only version validator; цей ризик закрито.
- Task brief, report, spec §15.3 і binding amendments звірено з реалізацією. Початкові wiki index/status/log та тематичну archive-retrieval сторінку прочитано як required project context; broader repository crawl не виконувався.
- Suite повторно не запускався. Наявний implementer evidence: **132 passed in 1.32s**, Ruff clean, diff check clean, wheel build із notices/manifest; controller повідомив fresh **132 passed in 1.30s** без наступних code changes. Нові tests прочитано в diff; executable probe не знадобився, конкретних невирішених doubts після source review немає.
- Жодних implementation, raw, benchmark, user-data або branch mutations; записано лише цей review artifact.

## Quality verdict

**Approved.** Adapter забезпечує потрібні scope/evidence/lifecycle гарантії, не покладаючись на prefix auth чи upstream internal commit. Реальні integration tests перевіряють основні failure/recovery boundaries; global coordination обґрунтовано лишається явною наступною інтеграцією.
