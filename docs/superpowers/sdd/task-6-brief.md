### Task 6: Повний набір реальних host tools

**Files:** `src/b12/tools/{filesystem,process,network,memory}.py`, `tests/integration/test_host_tools.py`, `tests/security/test_host_boundaries.py`.

**Tools:** `system_info`, `process_list`, `file_list`, `file_read`, `file_search`, `file_write`, `shell_exec`, `http_fetch`, `memory_search`, `memory_store`, `memory_forget`, `knowledge_search`, `current_time`.

- [ ] RED: write/read file through registry in temp dir; replacement atomic; symlink/path permissions honored; bounded large/binary output; no secret values persisted to audit.
- [ ] RED: real Python child sleeps/spawns child; timeout/cancel terminates process group; argv is not interpreted by shell; stderr/exit code/output truncation returned.
- [ ] Implement host paths within actual Linux permissions, owner full-host control grant, backups for overwrites, subprocess groups and cancellable HTTP fetch. Destructive actions require explicit control approval.
- [ ] GREEN: temp filesystem + real processes + local HTTP server; no change to unrelated user files.
- [ ] Commit/review side effects and no escape via model-controlled grants.

## Binding integration constraints

Read spec15.1/15.4 and Task5 report for trusted ControlStore/ExecutionContext/handler APIs. Registry authorizes real handler capability, but handlers also check current context/deadline/cancellation immediately before filesystem/process/network effects, not only before awaiting potentially slow preparation. Server resolves actor/grants; model args never create consent/capability/approval. Same asyncio.Event/monotonic deadline propagate to real subprocess and HTTP transport.

Full host writes/argv execution are required, not read-only substitutes. Arbitrary executable/interpreter requires explicit full-execution task grant OR exact executable/argv/cwd/declared-effects approval per Task5. Argv is not a sandbox; no blacklist security claims. No real destructive/userfile operations or external messaging/publication as tests. Temp files, real harmless child/grandchild processes and local HTTP server prove effects. timeout/cancel must terminate process group, bound stdout/stderr bytes and return unknown outcome when effects may have occurred; never report timeout as clean no-effect failure after starting a writer.

Full-host tools honor OS permissions; any narrower grant path boundary must actually prevent symlink escape. Atomic replacement and private overwrite backups cannot change unrelated permissions. Backup copies created by this task are managed data: retain actor/source/turn provenance and expose purge hook/inventory for Task7; do not omit them from global forget just because general service backup/restore comes in Task13. Source files outside managed stores aren't automatically deleted by memory forget.

memory_forget public tool must route through an injected global PurgeCoordinator in Task7; expose registration/dependency interface now, and return pending/unavailable when coordinator isn't wired rather than pretending canonical bool is global success. Knowledge update/remove invalidation receipts similarly need later delivery; local complete explicitly local. Do not fake missing integration with constant successful ToolResult.

Audit/lifecycle contain machine metadata/opaque IDs only, no raw args/text/paths/stdout/env/secrets. Tool results may return actor-authorized content under consent/session retention but are bounded and carry provenance. Unknown errors shouldn't persist exception strings that embed secret paths/payload. No production archive access or raw/finished artifacts edits. Full suite once after focused RED/GREEN, report actual interfaces and remaining wiring explicitly.


## Binding handler-outcome amendment after Task5 review

Task6 handlers must return `b12.tools.outcomes.HandlerOutcome`, not a content dict or
`ToolResult`. Registry alone sets call/name IDs, duration, `outcome_unknown` and generated
operation provenance. `Handler = (validated_args, EffectGuard) -> Awaitable[HandlerOutcome]`.

- `HandlerOutcome(status='completed'|'failed'|'unknown', content={}, side_effects=(),
  truncated=False, error_code=None)` is strict/frozen/extra-forbid. Full serialized handler
  outcome is finite JSON, at most **64 KiB**; handlers must bound stdout/stderr/read buffers
  during collection too. Registry revalidates a fresh snapshot after await, including nested
  metadata and mutated/model_construct outputs. Oversize/malformed output → unknown with
  fixed `invalid_handler_outcome`, never claimed success.
- `completed`: no error code; every reported effect is confirmed completed. `failed` is an
  explicit trusted-handler certification of **no effect**, requires fixed error code and an
  empty side_effects tuple. Partial or possible effects MUST use `unknown`, with fixed error.
  `unknown` preserves bounded content/cleanup evidence and `outcome_unknown=True`; lifecycle
  is persisted as unknown and cannot be blindly replayed. Handler effect claims remain trusted
  code assertions; registry does not discover arbitrary OS effects.
- `SideEffect(kind,state,evidence_ids=(),artifact_ids=())`: kinds `file_write`,
  `process_execution`, `http_request`, `memory_write`, `memory_forget`, `knowledge_write`;
  state `completed|possible`; references are generated UUID strings. Registry adds its
  `operation_id`. Do not put paths, command output, display names or grants/actor/session IDs
  in effect metadata. Authorized paths/output may go into bounded content under session retention;
  raw content/effects are never copied into lifecycle audit. Report file writes/backups/process
  starts/network/memory effects explicitly, rather than burying these inside content fields.
- Fixed HandlerOutcome errors: `handler_failed`, `permission_denied`, `not_found`, `unsupported`,
  `process_failed`, `network_failed`, `cleanup_failed`, `deadline_exceeded`, `cancelled`,
  `coordinator_unavailable`. Arbitrary exception strings never become error codes.
- Handlers must honor guard/Event/deadline, check before each new effect and remain cooperative.
  On cancellation, either propagate CancelledError or finish bounded cleanup of ALREADY-started
  resources and return HandlerOutcome(status='unknown') with bounded stdout/cleanup evidence.
  This special cleanup return may suppress the handler task's CancelledError; it must not resume
  user actions. Registry waits for cooperative cleanup, validates the return, forces unknown with
  the original timeout/cancel code, and preserves bounded evidence only while current control still
  permits access. It never turns late completed/failed output into success. External cancellation
  of registry's own task still propagates after cleanup and persists unknown.
- There is no hard preemption for a blocking/uncooperative Python handler; child process-group
  termination and bounded cleanup must be implemented/tested in Task6. Evidence preservation is
  not permission for new effects after deadline/cancel. Do not expose typed outcome/control APIs
  to model JSON or client result IDs.

## Implemented Task6 handoff (2026-10-26)

`b12.tools.register_host_tools(registry, *, backups: BackupStore, memory=None,
knowledge=None, purge=None, memory_revision=None)` registers all 13 tools. Caller owns
and closes injected stores. `memory_revision(context)` is a trusted synchronous resolver
of the ORIGINAL turn deletion revision, never a tool/model argument. Missing memory,
revision, knowledge or global-purge dependencies return `failed/coordinator_unavailable`
without effect. `b12.tools.memory.GlobalPurge.purge(memory_id, context, guard)` is async and
returns PurgeReceipt; pending/failed coordinator receipts remain unknown, not global success.
Task7 must provide the originating revision and real cross-store purge implementation.

Capabilities: system.read, process.read, filesystem.read/write, process.execute,
network.http, memory.read/write/forget, knowledge.read, time.read. `shell_exec` uses
Risk.ARBITRARY and exact executable/argv/cwd/declared_effects; memory_forget uses
Risk.DESTRUCTIVE. Nonzero completed subprocess exit is `completed` with exit_code and
command_succeeded=false; that certifies observed tool completion, not command success.
Timeout/cancel/cleanup uncertainty remains unknown with actual bounded stdout/stderr and
process side effect. Cleanup confirmation refers only to the original process group;
arbitrary code can deliberately detach, so no OS sandbox/escaped-daemon guarantee exists.

`BackupStore(path)` tracks private overwrite backups and same-directory staging copies.
`inventory(actor_id)` exposes opaque source/turn/operation/artifact provenance and state;
`purge(actor_id, *, artifact_ids=(), source_ids=(), turn_ids=())` is an idempotent trusted
hook returning local complete/pending and explicit pending IDs. Source/turn tombstones
prevent late backup/staging resurrection. It never deletes installed unmanaged sources.
`open_copy` and `copy_metadata` are trusted restore primitives, not model tools. Actual
source paths and xattr payload live only in private managed metadata, not control audit.
Task7 must consume inventory and keep global purge pending if managed cleanup is pending.

Limits: writes 64 KiB UTF-8; overwrite backups 64 MiB; xattrs at most64 entries/64KiB total.
Leaf symlink/nonregular writes refused; parent resolution follows actual OS permissions,
then dirfd is pinned. No narrower path-root boundary is advertised. Existing owner/mode,
accessible xattrs and POSIX ACL are preserved before atomic install, otherwise install is
refused/unknown. Output limits: read/raw HTTP <=8192B, process <=4096B per stream, directory
<=50 entries, search <=1000 scanned entries/depth8 with bounded snippets. HTTP is GET-only,
no ambient proxy/auth, no implicit redirects/decompression; content_encoding identifies raw
wire representation. Knowledge invalidation preview is bounded; durable original ledger
remains the application delivery source. These are Task6 primitives; no Agent/API wiring yet.

Task6 fix-round revision port rule: `memory_revision(context)` must return an exact
nonnegative int (`type(value) is int`, bool is not accepted). Missing resolver,
None/bool/negative/non-int return or ordinary resolver exception yields
failed/coordinator_unavailable BEFORE any MemoryStore.remember call. Never substitute
current-at-handler deletion revision for the originating turn snapshot. Cancellation
remains a control signal rather than an ordinary resolver exception.
