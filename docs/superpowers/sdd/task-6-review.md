# Task 6 — independent scoped review

BASE: `d0e5fe0f4fef36423db08cc663e68c752c44e5b4`.
HEAD: `012f2481d3b7261aba2b3311d5999f3c0de92aa9`.
Усі посилання на рядки нижче належать цьому HEAD. Подальший fix у shared worktree не входить до цього verdict. Source/index/HEAD не змінювалися; записано лише цей workflow artifact.

## Spec Compliance

- **❌ Issues found.** Обов’язкова original-turn deletion revision може бути мовчки відсутня через `None` return trusted resolver, що вимикає захист MemoryStore; I1. Managed backup/staging hooks не мають directory durability barrier перед `ready`/install та перед acknowledgment видалення; I2. Це in-scope handoff до Task7, а не вимога реалізувати весь Task7/13 зараз.
- **✅ Решта перевіреного scope присутня.** Factory реєструє всі 13 названих tools; strict schemas і capabilities застосовуються через Task5 registry. `shell_exec` має Risk.ARBITRARY та exact reviewable arguments, `memory_forget` — Risk.DESTRUCTIVE й injected coordinator. Missing dependency повертає unavailable без fake local global-success. File/HTTP/process results bounded і мають typed effects; actor/source/turn/operation provenance збережений у private managed copies. Реальні temp/local tests охоплюють argv, process groups, HTTP cancellation, permissions, xattrs/ACL та audit redaction.

## Strengths

- Control identity/approval лишилися у reviewed registry; model arguments не можуть підмінити grant/actor/result IDs. Exact shell approval реально передує temp-file effect, а replay не виконує його вдруге (`tests/security/test_host_boundaries.py:38`).
- File overwrite використовує pinned parent dirfd, відхиляє leaf symlink/nonregular targets, готує новий inode та зберігає mode/owner/access xattrs/POSIX ACL до install (`src/b12/tools/filesystem.py:488`, `:528`; real tests `tests/integration/test_host_tools.py:16`, `:315`, `:343`). Failed cleanup залишається у private inventory, а cancel regressions перевіряють також FD count та backup evidence (`tests/integration/test_host_tools.py:211`, `tests/security/test_host_boundaries.py:122`).
- Process stdout/stderr drain-яться одночасно з bounded prefixes; argv не інтерпретується shell. Timeout/Event cleanup TERM→KILL перевіряється на реальних child і grandchild з ігноруванням SIGTERM; uncertain outcome зберігає доступний stdout і provenance (`src/b12/tools/process.py:104`, `:136`; `tests/integration/test_host_tools.py:111`). Escape через setsid чесно не названо sandbox guarantee.
- HTTP fetch не успадковує proxy/auth environment, не слідує redirect та читає raw wire bytes; server-forced gzip не роздувається до output bound (`src/b12/tools/network.py:56`, `:72`; `tests/integration/test_host_tools.py:289`).
- Audit не отримує path/argv/stdout/secret payload; memory/purge post-effect exceptions залишають possible-effect metadata (`tests/security/test_host_boundaries.py:57`, `tests/integration/test_host_tools.py:325`, `:368`).

## Issues

### Critical

- Не виявлено в перевіреному Task6 scope.

### Important

**I1 — `None` від memory revision resolver вимикає stale-turn guard.**

- **Де:** `src/b12/tools/memory.py:97`, `:101`, `:110`; upstream optional guard `src/b12/memory.py:172`, `:189`.
- **Що:** handler перевіряє лише наявність callable, але не його результат. `memory_revision(context)` може повернути `None`; цей return передається в `expected_deletion_revision`, де `MemoryStore.remember` спеціально трактує `None` як відсутність перевірки. Після purge старий turn тоді знову записує дані. Type alias `Callable[..., int]` не виконує runtime validation.
- **Чому:** Task6 binding handoff вимагає original-turn revision та truthful unavailable за її відсутності. Це fail-open integration boundary, навіть коли сам port є trusted application code; помилка lookup/missing snapshot не повинна дозволяти resurrection.
- **Доказ:** окремий reviewer probe витягнув `src/` exact HEAD через `git archive` в temp directory, створив real ControlStore/MemoryStore/BackupStore і turn до deletion. Revision стала `0 → 1`. Resolver із captured integer `0` дав `failed/permission_denied`, даних немає; resolver `lambda context: None` дав `completed`, synthetic memory реально збереглася. Поточні tests перевіряють `memory_revision=None` та stale integer, але не missing return value (`tests/security/test_host_boundaries.py:74`, `:88`).
- **Виправлення:** перед remember вимагати literal nonnegative int snapshot (`bool` також відхилити); `None`/invalid/missing snapshot має давати unavailable без storage call. Додати real-store regression для `None` result після deletion та невалідних resolver values.

**I2 — Backup ready/purge complete випереджають durable зміни каталогів.**

- **Де:** `src/b12/tools/filesystem.py:230`, `:234`, `:288`, `:293`, `:304`, `:307`, `:312`; cancellation staging cleanup `:456`, `:465`.
- **Що:** capture fsync-ить bytes copy FD, але не `objects/` directory перед durable `ready` та наступним overwrite target. Purge unlink-ить copy/staging і видаляє tracking row/повертає `complete` без fsync відповідного directory. Cancel cleanup так само може забути staging row до durable unlink. SQLite `synchronous=FULL` забезпечує DB transaction, але не зовнішні filesystem directory entries.
- **Чому:** при power loss/crash consistency backup entry може не пережити вже durable overwrite; або після acknowledged purge може повернутися payload entry, tracking row якого вже видалено. Така orphan copy не потрапить до наступного inventory/purge. Task6 явно створює managed copies і hook для Task7; final global acknowledgment залежатиме від цього local receipt. Task13 general service backup не усуває цей gap у primitives.
- **Доказ:** code path не має directory sync для `objects/` чи purge parents. Reviewer trace на exact HEAD з real temp overwrite/purge зафіксував `write_status=completed`, `capture_directory_fsyncs=[target parent]`; після `purge_state=complete` — `purge_directory_fsyncs=[]`. Actual power-cut/data-loss simulation не виконувалася; finding стосується відсутнього durability ordering/barrier, не заявляє вже спостереженої втрати даних на цьому FS.
- **Виправлення:** fsync backup directory перед marking ready/дозволом destructive install. Після unlink copy/staging fsync pinned відповідний parent до видалення durable tracking/complete; при sync failure зберігати deleting/pending metadata й чесний receipt. Покрити ordering та directory-fsync failure injection, включно зі staging cancellation cleanup.

### Minor

**M1 — Depth-pruned `file_search` не показує неповне охоплення.**

- **Де:** `src/b12/tools/filesystem.py:409`, `:438`.
- **Що:** directory на depth 8 пропускається без `truncated=True`; completed empty result виглядає як повний пошук, хоча subtree не переглянуто.
- **Доказ:** exact-HEAD temp tree з needle у directory depth 9 дав `status=completed`, `matches=[]`, `truncated=false`. Entry-count/output truncation позначається, depth bound — ні.
- **Виправлення:** позначати skipped subtree як truncated (або явний bounded-search coverage field); додати depth-bound case.

## Explicit limits / downstream scope

- Task7 ще має реалізувати original revision lookup, реальний cross-store PurgeCoordinator, managed-copy inventory delivery та active-turn invalidation; Task9 — authenticated application/API control. Наявні trusted ports/ControlStore object не є готовою network authentication.
- Knowledge receipt preview не acknowledge-ить durable ledger; Task7 має читати original operation receipts. Underlying retrieval/history allocations та same-thread BackupStore inventory не оголошені bounded service resource policy.
- Arbitrary OS execution може detach/setsid; process-group cleanup не доводить зупинку всіх escaped daemons. Blocking/uncooperative OS/Python I/O не має hard-preemption guarantee. Ці обмеження явно задокументовані й не позначені як нові findings.

## Evidence та assessment

- Прочитано exact review package file list/hunks і всі дев’ять changed source/test files у bounded ranges; line references звірено з pinned `git show 012f248:<path>`. Relevant named outside-diff checks: MemoryStore optional deletion revision, reviewed EffectGuard/registry/HandlerOutcome та spec8/15.1/15.2/15.4.
- Implementer: 30 focused passed; full304 passed/1 skipped8.22s, Ruff/diffcheck clean. Coordinator окремо повідомив exact HEAD full304 passed/1 skipped8.51s і clean Ruff/diffcheck. Це не власний reviewer suite run.
- Reviewer виконав лише дві targeted temp-only probes на archived exact HEAD: revision None bypass; directory-fsync trace + depth-pruning result. Source checkout, Git state, production data/model/archive не змінювалися.

**Spec Compliance: ❌ Issues found. Task quality: Needs fixes.** I1/I2 слід закрити перед Task7, потім виконати окремий scoped fix rereview. M1 — невеликий correctness repair для truthful bounded search.
