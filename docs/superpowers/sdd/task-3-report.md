# Task 3 — derived knowledge retrieval

Дата: 2026-10-25. Base: `3c138bbe3c020e893cae5015bbf3a2856c1bd2c2`.
Робоча гілка: `feat/b12-runtime`. Реалізація та self-review виконані одним implementer без subagents.

## Реалізоване

- `src/b12/retrieval.py`: public `KnowledgeIndex`, явний ingest одного файла, lexical search, actor-bound document evidence resolver, update/remove та recovery APIs.
- `src/b12/retrieval_storage.py`: focused support для private namespace mapping, upstream transaction adapter, lifecycle filtering перед candidate limits і durable physical cleanup. Винесення відділяє SQLite lifecycle від public retrieval API.
- `src/b12/contracts.py`: strict versioned `EvidenceRef` з UUID `id`, `source_id`, `revision`, exact `owner_id`, enum `kind`, nonblank `locator`, strict `active`. Unknown fields і неправильний schema version відхиляються.
- `src/b12/_vendor/archive_index/`: exact upstream `__init__.py`, `lexical.py`, `store.py`, `search.py`, `LICENSE`, `NOTICE`. `SOURCE.json` фіксує repository, pinned commit, provenance і SHA-256 кожного з шести upstream файлів.
- `pyproject.toml`: вузький Ruff exclusion лише для `src/b12/_vendor/archive_index`; adapter/tests/contracts залишаються під Ruff.
- `tests/integration/test_retrieval.py`: 15 тестів з реальними тимчасовими SQLite/FTS і synthetic source files.

Прочитано AGENTS.md, wiki index/status/recent log, task-3-brief цілком, spec §15.2/15.3, binding plan amendments, релевантні contracts, MemoryStore boundaries і wiki/topics/archive-retrieval.md. Весь архів не читався.

## Namespace, provenance та атомарність

`KnowledgeIndex(path)` приймає **виділену managed directory**, а не archive database. Private `scopes.sqlite3` зберігає exact actor ID → generated UUID; окремі `scope-<UUID>.sqlite3` створюються для кожного actor. Raw actor ID ніколи не стає filesystem path. Додаткова identity всередині Store перевіряє exact owner binding. Role `owner` не змінює namespace і не обходить consent.

Directory має mode 0700, metadata/DB та SQLite sidecars — 0600. Нові відсутні батьківські теки створюються private; permissions на вже наявних батьківських теках не змінюються. Сам `path` явно є managed root. Symlink root/database відхиляються. Це локальна application boundary, а не захист від адміністратора або іншого процесу з тими самими OS правами.

Source ID, evidence ID і revision — generated application UUID, незалежні від SQLite rowid. IDs і revision незмінного активного документа переживають повторний ingest і restart. Зміна тексту створює нові evidence IDs/revision; source ID лишається сталим. Старі evidence rows позбавляються chunk reference і locator, стають inactive; resolver їх не повертає. Після remove/re-ingest жодний старий evidence ID не оживає.

Upstream `replace_document` робить власний `commit()`. Local `DeferredCommit` відкладає цей commit лише всередині явної `BEGIN IMMEDIATE` транзакції adapter. Тому upstream document/FTS, source/evidence metadata та operation outbox commit/rollback разом. Real failure injection після upstream mutator перевіряє відкат навіть його internal commit. Невдалий ingest до transaction commit зберігає попередню коректну revision; cleanup failure після commit приховує affected revision.

Candidate authorization походить з окремого exact actor Store; lifecycle `active`, current revision і pending/failed cleanup додатково фільтруються SQL **до** candidate limit/top-k. Upstream project prefix filters не використовуються. Search має єдиний SQLite read snapshot для hits і evidence metadata.

## Public API

- `KnowledgeIndex(path: Path)`: dedicated private managed directory; same-thread SQLite connections.
- `index_document(path: Path, actor: Actor, *, allow_reingest: bool = False) -> dict`: consent перевіряється до source resolve/stat/read та actor-specific persistence. Читає тільки явно переданий UTF-8 файл. Незмінний active ingest повертає оригінальний operation receipt без нових IDs. Для forgotten source потрібний literal control boolean `allow_reingest=True`.
- `search(query: str, actor: Actor, limit: int = 5) -> list[dict]`: кожен hit містить `evidence_id`, `source_id`, `revision`, `source` (absolute source path), `locator`, `text`, `score`. Empty/unknown query повертає `[]`; zero limit — `[]`; invalid negative/non-integer limit відхиляється. `score` є rank score, не confidence факту.
- `resolve_evidence(evidence_id: str, actor: Actor) -> EvidenceRef | None`: перевіряє exact actor, consent, current active source/evidence revision, наявність chunk і відсутність incomplete local cleanup. Malformed/foreign/stale/deleted/hidden ID повертає `None`; відсутня згода дає `PermissionError`.
- `remove_document(path: Path, actor: Actor) -> dict`: явне видалення тільки з actor-owned derived Store; original source file не видаляється. Повторний remove повертає той самий persisted operation ID та invalidation list.
- `resume_cleanup(actor: Actor) -> list[dict]`: retry pending/failed local operations; працює як перший виклик після restart і повертає receipts саме retry. Звичайне перше відкриття actor Store також відновлює cleanup до видачі affected даних.
- `operation_receipts(actor: Actor) -> list[dict]`: persisted receipts усіх actor-owned операцій у sequence order, включно з local complete. API дозволяє пізнішому coordinator відновити invalidation delivery після crash незалежно від того, який файл/виклик відкрив Store. Deduplication — за `operation_id`. Читання receipts при першому відкритті може поновити local cleanup; `complete` ніколи не означає acknowledgement зовнішніх stores.
- `close()`: закриває actor Stores і registry; повторний close безпечний.

Receipts мають `operation_id` UUID, `state` (`pending|complete|failed`), `invalidated_evidence_ids` (стала ordered list UUID) і `error_code` (`None|cleanup_busy|cleanup_failed`). Повторний незмінний ingest після update повертає **той самий** receipt з початковими invalidated IDs: coordinator має дедуплікувати операцію, а не втрачати незавершені hooks. Initial ingest без попередніх доказів має порожній invalidation list.

Як у canonical MemoryStore, explicit own-data remove/cleanup і payload-free receipt recovery дозволені після consent revocation; нове читання source/text, search, evidence resolve та ingest заборонені. Actor є trusted DTO; server-owned control revision/expiry resolver підключається пізніше.

## Видалення і recovery

Delete транзакційно фіксує payload-free operation та tombstone, прибирає document/chunks/FTS і інвалідовує evidence. Tombstone містить keyed HMAC від normalized absolute path, source UUID і revision; не зберігає path, user text або безключовий payload hash. Per-actor випадковий HMAC secret живе в тому самому private DB. Призначення ключа — control lookup forgotten path; це не audit, не encryption та не обіцянка cryptographic erasure.

Physical cleanup використовує secure_delete, FTS rebuild, VACUUM і WAL checkpoint(TRUNCATE). Поки cleanup pending/failed, affected source evidence не видається. Busy WAL snapshot дає durable `pending/cleanup_busy`; SQLite cleanup failure дає `failed/cleanup_failed`. Повторний виклик/restart retry зберігає operation ID та старі invalidated IDs. `complete` фіксується лише після успішних local physical cleanup/checkpoint. Тест перевіряє відсутність synthetic forgotten bytes у managed files і видаленого path у managed files, залишаючи external original незмінним.

Global dependent projections, canonical memory, sessions, goals, backups, active-turn cancellation і спільний memory/document/tool evidence resolver **не підключені** цим task. Для них повертаються invalidated IDs та recovery receipts; інтеграція — Task7/пізніші purge hooks. Canonical `MemoryStore` не змінено.

## TDD і перевірки

Команди нижче виконані у `.worktrees/runtime` з `UV_CACHE_DIR=/home/cyberdid/Downloads/B-12-runtime/uv-cache` і наявним `.venv`; без sync/model download.

Перший RED:

```text
uv run --no-sync pytest tests/integration/test_retrieval.py -q
FFFFFFFFF [100%]
9 failed in 0.10s
```

Очікувані assertion failures: відсутні KnowledgeIndex, EvidenceRef і pinned vendor. Перший GREEN:

```text
......... [100%]
9 passed in 0.88s
```

Self-review RED для recovery semantics:

```text
.........FF.. [100%]
2 failed, 11 passed in 0.84s
```

Відтворено втрату invalidation list після pending update/restart та втрату receipt при першому `resume_cleanup` після restart. Після виправлення:

```text
............. [100%]
13 passed in 0.88s
```

Окремий RED для durable receipt discovery після реального SQLite VACUUM failure:

```text
.............F. [100%]
1 failed, 14 passed in 0.91s
```

Очікувана відсутність `operation_receipts`; після API і refactor:

```text
............... [100%]
15 passed in 0.94s
All checks passed!
```

Фінальний full suite, виконаний один раз після завершення коду:

```text
uv run --no-sync pytest -q
........................................................................ [ 54%]
............................................................             [100%]
132 passed in 1.32s

uv run --no-sync ruff check src tests
All checks passed!

git diff --check
(exit 0, no output)
```

15 focused tests охоплюють: exact prefix-neighbor isolation; same absolute path у двох actors; role change; consent-before-source-read без owner bypass; morphology та кілька українських apostrophes; missing/empty/syntax-like queries; відсутність implicit unrelated-file scan; ID/revision stability і restart; old evidence denial; update/delete freshness; explicit re-ingest; forgotten bytes/paths cleanup; durable busy WAL; opaque traversal-like actor ID/private permissions; strict DTO; exact upstream hashes; pending update receipt recovery; first-call resume; upstream transaction rollback; erasure після consent revoke; реальний failed cleanup і recovery discovery; незалежні index instances без stale cache.

## Distribution і attribution

```text
uv build --wheel --offline --out-dir /tmp/b12-task3-wheel-20261025
Building wheel...
Successfully built /tmp/b12-task3-wheel-20261025/b12_runtime-0.1.0-py3-none-any.whl
```

ZIP inspection перевірила наявність adapter/contracts та 4 exact upstream modules + LICENSE + NOTICE + SOURCE.json; кожний upstream member звірено з source tree і SHA-256 manifest. Wheel SHA-256: `dfae9ad138c94c3b4961cc0308d8b874f750423cf1f80c59c4c06201808d9bb0`.

Upstream pin: `https://github.com/cyberdid/archive-index-public`, commit `7ad80dcdc7e327b7dd1b352ab5e6dc38a00d784a`. Копії взято тільки з reviewed `raw/archive-index-public-7ad80dcdc7e3`, upstream bytes/formatting/notices не змінено. No Torch, embedder чи model download; lexical chunks мають zero-length float32 vectors. Cache створюється на кожний search; lexical mode не завантажує vectors.

## Межі та self-review

- UTF-8 source ingest зараз зберігає один document chunk з locator `line 1`, без PDF/Office parser або token selection. Hit text — повний chunk; bounded context/admission належить Task4.
- Same-thread connections; між незалежними instances SQLite serializes mutations. Це не async/thread-pool API і не performance benchmark. FTS rebuild/VACUUM під час мутації мають вартість пропорційно local actor DB.
- Source path permission поза actor/consent перевіряє майбутній trusted control/tool layer; цей storage adapter не є filesystem sandbox.
- Local receipt state не доводить global R05. Receipt outbox не містить source paths, текстів чи arguments; external coordinator delivery/ack не підмінено local complete.
- Self-review перевірив consent/scope перед candidate limits, exact upstream attribution, атомарність internal commit, persisted revisions, pending/failed visibility, ідемпотентність, physical cleanup та restart receipts. Виявлені дві recovery помилки виправлено RED/GREEN; невирішених Task3 blockers немає.
- Production DB, user files, raw originals, canonical memory та моделі не змінювались. Coordinator-owned wiki/source зміни залишені поза task commit.
