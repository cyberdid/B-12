# Task 6 — actual host tools

Дата: 2026-10-26. Implementer status: DONE; незалежний review pending.
BASE: `d0e5fe0f4fef36423db08cc663e68c752c44e5b4`.
Worktree `/home/cyberdid/Projects/B-12/.worktrees/runtime`, branch `feat/b12-runtime`.
Один implementer, без subagents. Нових dependencies немає. Task7 не реалізовувався.

## Scope та API

Прочитано AGENTS/index/status/recent log, Task6 exact brief + HandlerOutcome amendment,
Task5 report/rereview, spec8/15.1/15.2/15.4, public MemoryStore/KnowledgeIndex/control APIs.
TDD та verification-before-completion застосовані до actual temp/local fixtures.

Нові modules: `tools/{_common,filesystem,process,network,memory}.py` та factory в tools/__init__.
Нові tests: integration/test_host_tools.py, security/test_host_boundaries.py;
conftest додає shared real control/store fixture. Старі runtime/control/model/contracts/store
implementation files не змінено. Wiki update залишається coordinator checkpoint.

`register_host_tools(registry, *, backups, memory=None, knowledge=None, purge=None,
memory_revision=None)` реєструє всі 13 tool schemas. Caller володіє stores та close lifecycle.
Усі handlers повертають Task5 HandlerOutcome через registry, не model-owned IDs/approvals.

| Tools | Capability | Contract |
|---|---|---|
| system_info | system.read | actual OS/release/CPU/RAM/UID |
| process_list | process.read | bounded /proc identity, optional exact pid; без argv/env |
| file_list/read/search | filesystem.read | bounded regular-file bytes, base64 binary, literal search |
| file_write | filesystem.write | reversible typed atomic write + private overwrite backup |
| shell_exec | process.execute | Risk.ARBITRARY, exact executable/argv/cwd/declared_effects |
| http_fetch | network.http | raw-wire bounded GET, explicit status/encoding |
| memory_search/store | memory.read/write | exact resolved actor, evidence and tool operation source |
| memory_forget | memory.forget | Risk.DESTRUCTIVE, injected global coordinator only |
| knowledge_search | knowledge.read | UUID revision evidence + bounded invalidation preview |
| current_time | time.read | current ISO UTC |

EffectGuard перевіряється перед OS effects/persistence та після yielding preparation.
No Actor/request/model grant proof. Registry retains approval, outcome and no-replay identity.
A known nonzero subprocess exit is completed with `exit_code` and `command_succeeded=false`;
failed would falsely certify no effects. Timeout/Event returns forced unknown with bounded
stdout/stderr and process side effect. No shell parsing or argv sandbox/blacklist claim.

## Filesystem і managed copies

Full-host paths follow actual Linux permissions; no pretend restricted root. Writes pin
parent dirfd, refuse leaf symlink/nonregular target, prepare a same-dir temp inode, fsync,
then replace atomically (new-file install uses no-replace hard-link). Existing mode/uid/gid,
accessible xattrs and POSIX ACL are copied before install; failures do not silently install
changed permissions. Before/after target identity/mtime/ctime/size detects concurrent changes.
Final race against an independent external writer cannot be made compare-and-swap by rename;
this is not a multi-process filesystem transaction or a claim to roll back other writers.

BackupStore is private 0700 root/objects, 0600 DB/copy files, O_NOFOLLOW DB/artifacts,
secure_delete and synchronous FULL. Source paths and restore metadata (mode/uid/gid/xattrs)
are private, not audit. Stable source identity uses per-store keyed identity; tombstones
contain opaque actor/source/turn IDs. Inventory exposes opaque provenance/state only.

`inventory(actor_id)`, `purge(actor_id, *, artifact_ids=(),source_ids=(),turn_ids=())` are trusted
Task7 hooks. Purge returns local complete/pending with pending IDs and leaves unmanaged
installed source files intact. Staging copies are tracked before OS write; cancellation
closes source/temp/parent FDs, removes uninstalled temps, and retains failed cleanup as
managed deleting inventory. Source/turn tombstones block late copies, including parent
symlink aliases. `open_copy`/`copy_metadata` are trusted future restore primitives.
Physical unlink is not SSD/snapshot erasure; global R05 still requires Task7/13 integration.

## Process і HTTP

Real create_subprocess_exec, new session/process group, stdin DEVNULL, minimal PATH/LANG
environment. Both streams drain continuously while retaining bounded prefixes. Cancellation
racing PID issuance is shielded until the owned child can be cleaned up. Cleanup TERM→KILL,
bounded waits/drain, local pipe transport close; unknown result retains available evidence.
`cleanup_confirmed` is original process-group termination, not all arbitrary escaped daemons.
Arbitrary code can deliberately setsid/detach and perform any OS-permitted effects. There is
no narrower OS sandbox here. Blocking Python/OS I/O and spawn do not have hard preemption.

HTTP uses trust_env=False, no credentials/custom auth/body, no followed redirects, bounded
aiter_raw with Accept-Encoding identity. Even forced server gzip is retained as wire bytes,
never automatically decompressed. Cancellation closes actual socket and reports possible
request side effect. HTTP response status is explicit; completed fetch does not imply 2xx.

## Memory і future wiring

`MemoryRevision = Callable[[ExecutionContext],int]` must resolve ORIGINAL turn revision;
it is not a model arg. Missing revision returns coordinator_unavailable; remember uses
expected_deletion_revision and source `tool:<operation UUID>`. Permission/validation errors
before storage are known failures; unexpected post-commit exceptions report possible memory
effect without exposing exception strings.

`GlobalPurge.purge(memory_id, context, guard) -> await PurgeReceipt` is an injected trusted
application port. Missing port never calls MemoryStore.forget. Pending/failed receipt and
post-effect exceptions remain unknown with memory_forget provenance. Actual Task7 coordinator
still owns transitive stores/revision invalidation/active turns and complete acknowledgement.
A test partial port performs real canonical deletion but pending sessions; it is explicitly
not a full application coordinator or fake successful response.

Knowledge search forwards current scoped UUID/revision evidence; invalidation preview does
not acknowledge/drop durable ledger work. Task7 reads original KnowledgeIndex.operation_receipts.
Existing retrieval may load full stored chunks/receipt history internally; tool serialization
is bounded, but this does not claim bounded underlying index history allocations or semantic search.

## Limits

64KiB UTF-8 input write; 64MiB overwrite backup; <=64 xattrs/64KiB total metadata.
Read/raw HTTP <=8192 bytes; process <=4096 bytes per stream. Directory <=50 entries;
literal search <=1000 scanned entries/depth8, bounded snippets. Memory/knowledge output uses
bounded previews. HandlerOutcome remains final64KiB cap. BackupStore same-thread SQLite API;
application must authorize trusted restore/purge hooks and register them in global purge.
No model/Agent/API/auth/UI/service/production archive/GPU integration claimed.

## Actual RED/GREEN evidence

Commands use `UV_CACHE_DIR=/home/cyberdid/Downloads/B-12-runtime/uv-cache uv run --no-sync`.

1. Initial test-first host suite: setup assertion first produced14 errors; moved missing-module
assertion into actual test execution. Correct RED:14 failed0.07s, `host tools are missing`.
No production handlers existed before that RED. After modules/registration:13 passed1failed;
fixed wrong KnowledgeIndex receipt-key assumption and explicit process-list pid-filter contract
(its separate invalid-arguments RED). First GREEN14 passed1.97s.
2. Temp/capture cancellation regressions:2 failed1passed, missing post-capture artifact IDs
and omitted failed-staging inventory. Fixed persisted staging hooks, cleanup and operation
artifact provenance; focused suite23 passed2.71s. Actual FDs and temp files checked.
3. Raw gzip/user-xattr/post-commit memory exception regressions:3 failed (missing wire encoding,
lost user xattr, absent memory side effect). Fixed raw iterator, metadata preserve/backup and
possible-effect mapping;26 passed2.84s. POSIX ACL actual filesystem fixture passed; deliberate
mutation removing xattr install made ACL test fail as expected; restored code passed.
4. Purge post-local-effect exception regression:1 failed1passed, absent memory_forget metadata.
Fixed unknown possible provenance. Source/turn tombstone and ACL restore-metadata boundaries
included. Final focused after formatting:30 passed3.16s.
5. Full ordinary suite once after stable production/format:
`uv run --no-sync pytest -q` → **304 passed,1 skipped in8.22s**.
`uv run --no-sync ruff check src tests` → **All checks passed**.
`git diff --check` → exit0. No source/test changes after final full run.

All actual write/process/network effects used temp files, harmless controlled child/grandchild
processes and localhost HTTP only. Permission and POSIX ACL tests ran (not skipped) on this host.
Only intended system_info/process_list read host metadata; no env/argv secrets read into results.
Control audit assertions exclude raw path/args/stdout/synthetic secret. No production user files,
archive/model/GPU/raw/finished calibration artifacts changed. Self-review complete; independent
coordinator/full-suite/review remains a separate gate.

Implementation commit: `012f2481d3b7261aba2b3311d5999f3c0de92aa9` —
`feat(tools): implement real host effects with managed backup and cancellation`.
Review package: `task-6-review.diff`, exact d0e5fe0..012f248, one commit/9 files.
Tracked worktree clean after commit. Task6 implementation DONE, independent review pending.

# Fix round 1 — originating revision resolver validation

FIX_BASE: `012f2481d3b7261aba2b3311d5999f3c0de92aa9`.
Finding: a configured trusted resolver returning None passed
MemoryStore.remember(expected_deletion_revision=None), whose deliberate primitive-level
meaning is “no expected revision supplied”. That disabled the stale-turn comparison.
Root cause is the Task6 integration boundary, not MemoryStore's public optional primitive.

Added validation BEFORE remember: exact int and >=0 only; bool/None/negative/float/string
are invalid. Ordinary resolver exceptions are sanitized as coordinator_unavailable before
persistence. Missing port remains unavailable. No current-revision fallback, model argument,
MemoryStore contract change or unrelated refactor added. Normal cancellation still propagates
as control, not an ordinary dependency failure. Fixture accepts a trusted callable to test
actual registry/MemoryStore integration rather than mocking storage success.

Observed RED: `pytest -q tests/security/test_host_boundaries.py -k origin_revision --tb=short`
→ **7 failed,14 deselected in0.74s**. Actual real forget advanced canonical deletion revision;
None then produced completed stale resurrection. Bool/negative/float/string returned the
wrong unsupported code; resolver exception produced unknown. Each regression now requires
failed/coordinator_unavailable, no side_effects/outcome_unknown, no resurrection and unchanged
canonical audit. Exception text is absent from control audit.

Focused GREEN after formatting: `pytest -q tests/integration/test_host_tools.py
 tests/security/test_host_boundaries.py` → **37 passed in3.77s**.
Full ordinary suite once after stable fix: `uv run --no-sync pytest -q` →
**311 passed,1 skipped in8.91s**. `ruff check src tests` → All checks passed;
`git diff --check` → exit0. Same UV_CACHE_DIR/no-sync commands as initial report.
No source/tests changed after full run. Fix is scoped to memory tool boundary + behavioral
tests/test fixture; no production data/model/archive/raw changes. Independent rereview pending.

Fix commit: `f0f8ea203286ccc229db3042a4ec858eb6922857` —
`fix(tools): reject unavailable originating memory revision`.
Scoped fix review package: `task-6-fix-review.diff`, exact012f248..f0f8ea2,3 files.
Tracked worktree clean after commit. Ready for coordinator verification/rereview.

# Fix round 2 — directory durability ordering and depth truncation

FIX_BASE: `f0f8ea203286ccc229db3042a4ec858eb6922857`. Codex implementer зупинився через usage limit після GREEN (44 focused); coordinator (Claude Code) перевірив незакомічене дерево й закомітив без змін коду.
RED (зі звіту Codex): 7 failures — missing fsync barrier, false `complete` on sync failure, lost staging inventory, parent-swap race, false `truncated` at depth 9.
Coordinator fresh full suite на дереві до commit: **318 passed, 1 skipped in 9.37s**; Ruff clean; diff check clean.
Fix commit: `7d7809e` — `fix(tools): order managed copy durability and report depth-capped search`. Package `task-6-fix2-review.diff`.
