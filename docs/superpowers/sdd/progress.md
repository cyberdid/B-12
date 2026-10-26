# SDD ledger — plan: docs/superpowers/plans/2026-10-24-b12-full-system.md

Spec: docs/superpowers/specs/2026-10-24-b12-system-design.md
Worktree: /home/cyberdid/Projects/B-12/.worktrees/runtime
Branch: feat/b12-runtime
Baseline: 78daaef
Owner authorization: full implementation/tests/host tools, 24.10.2026. Goal active; R01–R17 retained.

## Pre-flight shared interfaces/files

| Tasks | Check |
|---|---|
| 1 / 2–19 | Actor/MemoryRecord/ToolCall/ToolResult/ModelReply/Settings are public contracts; exact names fixed |
| 2 / 3,6,7,9,11,13,15,19 | MemoryStore canonical methods, no-consent before persistence, purge across projections |
| 3 / 6,7,12,15 | KnowledgeIndex exact scope, update/delete freshness, no implicit production archive access |
| 4 / 7,9,11,14,16 | OllamaModel/ContextBuilder async, bounded/cancellable; 4096 deployment gate |
| 5 / 6,7,9,12 | ToolRegistry consumes trusted control grant, never model approval fields |
| 6 / 7,14 | Real host side effects and ToolResult, sandbox eval |
| 7 / 8,9,11,16 | Agent/sessions shared by CLI/API/scheduler/audio |
| 8 / 13,20 | Installed CLI operations/deployment contract |
| 9 / 10,13,16 | Authenticated API/control before UI/voice host tools |
| 10 / 11,13,16 | UI consumes actual goal/approval/audio state |
| 11 / 13,15,19 | Persistent goals, quiet/cooldown, evidence-backed reflection |
| 12 / 14,15 | MCP policy/cancel + semantic joint resources |
| 13 / 15,19,20 | Service/backup/recovery inventory |
| 14 / 15,20 | Versioned corpus, settings and visible failures |
| 16 / 17,18 | Capture/render/cancel shared by duplex/robot media |
| 18 / 20 | Physical acceptance separate from protocol mocks |
| 19 / 20 | Actual 1/7/30-day evidence |

## Task self-consistency

| Task | Check |
|---|---|
| 1 | Files/interfaces/tests align with spec matrix; completion unproven pending actual evidence |
| 2 | Files/interfaces/tests align with spec matrix; completion unproven pending actual evidence |
| 3 | Files/interfaces/tests align with spec matrix; completion unproven pending actual evidence |
| 4 | Files/interfaces/tests align with spec matrix; completion unproven pending actual evidence |
| 5 | Files/interfaces/tests align with spec matrix; completion unproven pending actual evidence |
| 6 | Files/interfaces/tests align with spec matrix; completion unproven pending actual evidence |
| 7 | Files/interfaces/tests align with spec matrix; completion unproven pending actual evidence |
| 8 | Files/interfaces/tests align with spec matrix; completion unproven pending actual evidence |
| 9 | Files/interfaces/tests align with spec matrix; completion unproven pending actual evidence |
| 10 | Files/interfaces/tests align with spec matrix; completion unproven pending actual evidence |
| 11 | Files/interfaces/tests align with spec matrix; completion unproven pending actual evidence |
| 12 | Files/interfaces/tests align with spec matrix; completion unproven pending actual evidence |
| 13 | Files/interfaces/tests align with spec matrix; completion unproven pending actual evidence |
| 14 | Files/interfaces/tests align with spec matrix; completion unproven pending actual evidence |
| 15 | Files/interfaces/tests align with spec matrix; completion unproven pending actual evidence |
| 16 | Files/interfaces/tests align with spec matrix; completion unproven pending actual evidence |
| 17 | Files/interfaces/tests align with spec matrix; completion unproven pending actual evidence |
| 18 | Files/interfaces/tests align with spec matrix; completion unproven pending actual evidence |
| 19 | Files/interfaces/tests align with spec matrix; completion unproven pending actual evidence |
| 20 | Files/interfaces/tests align with spec matrix; completion unproven pending actual evidence |

## Rulings

- Ruling: start/execution/worktree authorized by owner's full implementation request; no repeated workflow-choice prompt. Cost if wrong: reversible local work only.
- Ruling: Task 1 context 4096 candidate config, not verified deployment fit; Task 4 tests first. Cost if wrong: adjust default.
- Ruling: Task 2 canonical lexical FTS independent of Task 3; shared pinned lexical processing later; knowledge uses archive Store/search. Avoid dependency cycle.
- Ruling: persistent application IDs UUID; model call IDs opaque validated strings. Preserve native protocol.
- Ruling: Ollama defaults loopback; explicit owner-configured HTTP(S) endpoints allowed, malformed/credential URLs rejected. Enables later host split.
- Ruling: baseline had no commit; 78daaef preserves historical evidence including one pre-existing whitespace line in checksum-covered benchmark runner. Do not rewrite old artifacts for style.
- Ruling: skill scripts are not executable here; invoke via bash and pass explicit output paths instead of changing installed skill permissions.

## Execution

Task 1: in_progress
BASE: 78daaef
Implementer: pending dispatch
Report: task-1-report.md
Next: task review, fix findings, Task 2.

- Ruling: early architecture review requires schema_version=1, UTC/UUID validation, turn/task provenance and ToolResult side_effects/outcome_unknown. Task 1 brief updated while implementation is in progress; actor trust stays in authenticated control, not DTO construction.

## Architecture review rulings (accepted for implementation)

Report: architecture-review.md. Six P1 and two P2 are contract gaps, not completed-code defects. Spec §15 and plan binding amendments address all; actual enforcement remains gated by corresponding tests.
- P1-1: local delete bool distinct from global PurgeReceipt/outbox/hooks; Task2 primitives, Task7/9 coordinator, Task13 backup.
- P1-2: server-resolved actor/session/control revision, no Actor/grant request body; Task5/7/9.
- P1-3: explicit arbitrary-code execution grants/approvals, no fake argv sandbox; full host capability retained.
- P1-4: exact approval binding, persistent tool lifecycle, unknown side effects/no blind replay.
- P1-5: immutable admitted request, exact tokenizer or validated whole-template bound, no silent tool-group truncation.
- P1-6: per-actor derived DB and UUID/revision EvidenceRef; source updates invalidate old references.
- P2-7: shared typed handler/cancel/event/application-factory interfaces before consumers.
- P2-8: durable original goal intent/checkpoint/budget and evidence completion; quiet speech not pause.

Runtime preflight evidence: artifacts/runtime-preflight-2026-10-24; real ctx4096/8192 each returned ГОТОВО for 2109-token prompt, size_vram ~3.32GB. /api/tokenize and /api/encode both 404. Official BF16 tokenizer files downloaded pinned/hash-verified under Downloads/B-12-runtime/tokenizer for Task4 research. No production adapter exists yet.


Task 1: complete
BASE 78daaef; implementation 4cf5e79; fix 4c455b5.
Spec PASS / Quality PASS in task-1-rereview.md. Coordinator fresh run: 94 passed.
No GPU/model or production state touched by foundation tests. Source/plan refinements staged separately.

Task 2: ready
Additional purge primitives/DTO/deletion revision and expected-revision late-write guard added to exact task brief. This prepares global coordination without falsely claiming full R05 in the storage primitive.

## Resume 2026-10-25

Task 2: in_progress. User resumed after explicit pause. Current HEAD remains b16917b; Task2 code/tests are uncommitted. Previous agent handle is missing from authoritative live inventory; replacement implementer /root/task2_finish finishes existing work, not a duplicate implementation. BASE remains b16917b. Previous turn was a requested pause; this turn resumes concrete work.

Task 2: review_pending (BASE b16917b; HEAD d18441c). Implementer completion report task-2-report.md: 23 focused /117 full tests; historical RED explicitly distinguished from current verified runs. Coordinator fresh pytest: 117 passed in 0.40s; ruff clean. Reviewer /root/task2_review uses task-2-review.diff and will report task-2-review.md. Task3/4 briefs prepared; neither dispatched before Task2 gate.

Task 2: complete (commits b16917b..d18441c, review clean). Spec PASS/Quality Approved in task-2-review.md; no findings. Cross-task verification limits (trusted Actor origin, external hooks, backup deletion) explicitly assigned to Tasks5/7/9/13, not a completed R05 claim.

Task 3: ready. Brief task-3-brief.md includes spec15.3 EvidenceRef/per-actor Store and explicit re-ingest/invalidation interface requirements. Ruling: Task3 exposes document evidence resolution/invalidation; shared canonical/document/tool resolver is wired in Task7 before reflections, when those consumers exist. Cost if wrong: adapter integration rework, not silent acceptance of unvalidated evidence.

Task 3: in_progress (BASE 3c138bb). Implementer /root/task3_retrieval; report task-3-report.md. Documentation checkpoint 3c138bb records verified Tasks1–2 without declaring global purge or an agent ready.

- Ruling: KnowledgeIndex(path) is a dedicated private directory with private scope registry and UUID-named actor DBs. Adapter receipt carries invalidated_evidence_ids plus cleanup state; source tombstone uses keyed identity without retained path/text. Explicit re-ingest control represented by allow_reingest, verified by downstream control adapter. Reason: resolve global upstream path UNIQUE safely and prevent silent source resurrection. Cost if wrong: compatible adapter/storage migration before user deployment.

Task4 read-only preflight: artifacts/model-profile-preflight-2026-10-25 frozen profile/template hashes. Server0.33.3, alias manifest unchanged 7eaa0c..5ad09; generic 13-byte native template not sufficient identity alone. Alias remains ctx2048; Task4 must explicitly override admitted ctx4096. No generation executed or global settings changed. Fresh docs selected sections tracked in wiki/sources/runtime-api-docs.md.

Task 3: review_pending (BASE3c138bb; HEADe33b926). Implementer task-3-report.md:15 focused/132 full passed, Ruff clean, wheel attribution/source hashes verified. Coordinator fresh pytest132 passed1.30s. Review /root/task3_review -> task-3-review.md. Two self-review receipt recovery regressions fixed via RED/GREEN before commit. API includes resolve_evidence, operation_receipts and resume_cleanup; downstream Task7 must consume persisted invalidations, not only current return values.

Task 3: complete (commits 3c138bb..e33b926, review clean). task-3-review.md SpecPASS/QualityApproved; no findings. Shared resolver/control revisions/dependent purge hooks explicitly remain Tasks5/7/9/13 and cannot be inferred complete from local store receipt.

Task 4: in_progress (BASE88459da). Implementer /root/task4_model, report task-4-report.md. Brief carries immutable snapshot, real NDJSON faults/cancel, profile identity/calibration and sanitized real-model evidence requirements. Documentation checkpoint88459da records reviewed Tasks1–3 and selected official API docs. Task5/7 briefs are preparation, not dispatched implementation.

Task4 milestone reported: 10 context +48 config tests green after RED; deeply frozen AdmittedRequest and configurable hash-verified tokenizer/template profile. Transport API under implementation: chat(request, *, on_delta: Callable[[str],None|Awaitable[None]], cancel:asyncio.Event|None, deadline:monotonic float|None). Not yet final verification or completion; real-model/fault/cancel gates remain.

Task4 later milestone reported:41 focused context/transport green, output-token guard before callbacks, 8MiB response/1MiB frame limits. Real run1 12/12 cases (4x3):counts51/968/183/3228 exactly matched native Ollama and independent expected replies; schemas and two tool rounds included. Run2 tighter boundary/native generated tool call underway; no executable tool effect claimed. Finished run1 preserved separately. Task4 still in progress pending final tests/report/review.

Task4 final-code milestone reported:179 passed1 skipped ordinary suite;47 new context/transport tests;run2 15/15, near-boundary3928+16margin+128reserve=4072 and first/last codes retained; native tool generation3/3. Await implementation commit, post-commit marked calibration, report and review. Ruling: transport close is not provider KV erasure; Task7 must inventory provider context and evidence reset or keep purge pending. Cost if wrong: reset coordination rework/extra reload latency; prevents false global privacy completion.

Task4 review_pending (BASE88459da; implementation4e3cc06; docsb673212). Reviewer /root/task4_review with task-4-review.diff/report. Coordinator fresh ordinary suite179passed1skipped2.13s; independent recorded run3 check:17 artifact hashes and14 listed runtime/test/dependency file hashes verified, plus6 vendor upstream hash entries separately verified. All15 recorded replies independently checked for exact native prompt counts, admission bound, boundary text and native call args. Runtime metadataHEAD4e3cc06 with empty dirty diff. Profile reload adds visible warm latency; voice SLO not established. Cross-task cache/control/purge and broader model corpus remain pending requirements.

Task4 review interrupted by reviewer usage cap; replacement reviewer /root/task4_reviewer_rerun completed artifact task-4-review.md. Spec ❌/quality Needs fixes: (1) forged snapshot with injected unbudgeted `images` passed public validate; (2) sync callback blocked event loop and returned success 0.371s after 0.1s deadline; (3) unhashable JSON done_reason leaked TypeError. Exact lines/probes and full severity are in review artifact. Fix round1 dispatched to same implementer /root/task4_model against BASE b673212.

- Ruling: on_delta becomes cooperative async-only and rejects sync callbacks before transport. Reason: Python cannot preempt arbitrary sync callback code and still guarantee bounded cancel/deadline; async-only contract enables bounded cooperative cancellation and avoids untracked callback threads. Cost if wrong: synchronous UI consumers need a small async adapter; no production consumers existed yet.

Task4 fix round1 implementation: commit46b374c; findings addressed in code/test claims; 76 focused passed, full suite coordinator208 passed1 skipped, Ruff clean. Fix report append awaited while postcommit run4 executes. Re-review /root/task4_rereview -> task-4-rereview.md on fix range b673212..46b374c. Run4 separate immutable real calibration still running, not yet verified.

Task 4: complete (fix commits b673212..46b374c; docs HEAD 623d4f0). Initial reviewer found 3 Important; replacement reviewer confirmed all addressed in scoped re-review with no open findings and no new Critical/Important. Run4 post-commit exact fix revision independently verified: 17 artifact hashes,14 runtime/test/dependency code hashes,15 replies; alias/output and admission arithmetic valid. Coordinator fresh full suite208passed1skipped; ruff clean. Initial task review's previous verdict is superseded by clean fix re-review. No Task7/global provider-cache erase claim.

Task4 rereview report task-4-rereview.md: all 3 findings addressed; no new breakage. Task4 currently complete; no remaining review findings.

Task 5: in_progress, brief task-5-brief.md; BASE 623d4f0. Task 6 and 7 briefs were prepared with purge/backup/cache constraints. Must re-check Task4 current async-only callback and error contracts when dispatching agent/session consumers.

Task5 design checkpoint: ControlStore uses generated actor/session/grant/turn IDs and resolves consent, revision, expiry and capabilities server-side. Frozen ExecutionContext includes private server turn credential; `.execute(call, context, cancel)` is replacing old caller actor/grant dict sketch. Approval binds exact actor/session/turn/call/canonical args digest/revision, consumed atomically with start. EffectGuard rechecks before side effect. Initial focused 30 SQLite/temp-file tests pass; 1 new status assertion (`approval_denied` vs actual `replay_blocked`) is under correction. Crash/expiry/deadline/cancel coverage being extended before full suite.

Task 5: review_pending (BASE623d4f0; HEAD0ecc6cd). Implementer Task5 report:49focused,257full/1skip,Ruff clean. Coordinator freshly reran full:257 passed/1 skipped in4.76s; Ruff clean. Review diff `.superpowers/sdd/2026-10-24-b12-full-system/task-5-review.diff`; dispatch reviewer next. ControlStore/registry/report artifacts use `ExecutionContext`, no Actor/grant dict authorization. All tests temp DB/files; no production user/model/archive touched.

Task 5: complete after fix round. Initial review on 623d4f0..0ecc6cd found Important I1 (handler outcome contract omitted ToolResult effects/truncation/unknown evidence) and Minor M1 (expired approval operations remained active). Fix commit `bc07196` adds strict bounded HandlerOutcome/SideEffect, registry-owned identity/effects/outcome lifecycle, cleanup-only unknown evidence, and transactional approval-expiry terminal audit/digest erasure. Implementer: 66 focused passed, full 274 passed/1 skipped; coordinator fresh exact-HEAD run 274 passed/1 skipped, Ruff and diff check clean. Independent scoped rereview `task-5-rereview.md`: Spec PASS, Quality Approved, I1/M1 addressed, no new Critical/Important. Wiki tool-control topic/status/index/roadmap/log updated and linted: 27 pages, 230 local links, source paths/frontmatter/index coverage clean, master brief SHA unchanged. Next: Task 6 ready; full-host handler brief amended with HandlerOutcome constraints, use real temp files/process groups/local HTTP only, and retain Task7 purge hooks for backups/memory.

Task 6: in_progress (BASE d0e5fe0; brief `task-6-brief.md`, including binding HandlerOutcome amendment from Task5 fix review). Fresh implementer dispatched by coordinator. Scope: actual host tool handlers and boundary tests on temp/local fixtures; no unrelated user-file/process/network effects. Must deliver RED/GREEN, full suite, Ruff, report/commit, then independent scoped review. Task7 purge coordinator remains the only route for global memory forget; no fake success.

Task 6: review_pending (BASE d0e5fe0; HEAD 012f248). Commit adds all 13 host tools, private overwrite/staging backup inventory+purge hooks, raw bounded HTTP, process-group cancel, exact actor/revision memory ports. Implementer: 30 focused passed; full suite 304 passed/1 skipped; Ruff/diffcheck clean. Coordinator fresh exact-HEAD suite 304 passed/1 skipped in 8.51s; Ruff and diffcheck clean; tracked tree clean. Review package `task-6-review.diff`; independent reviewer checks exact files against Task6 brief/spec and Task5 outcome contract. No Task7 dispatch until review/fix gate.

Task 6 review found fix round required on exact implementation HEAD `012f248`: Important I1 resolver returning None bypassed deletion revision (confirmed real temp-store resurrection); Important I2 missing fsync ordering for backup/staging directories vs persisted inventory/purge ack; Minor M1 depth-capped file_search could return `truncated=false`. I1 fix committed `f0f8ea2` with RED7/GREEN37 and coordinator fresh full 311 passed/1 skipped, Ruff clean. Task6 implementer is now fixing I2/M1 in a second scoped fix round; Task7 remains gated. Initial review artifact pending write.

## Resume 2026-10-26 (Claude Code)

Codex coordinator зупинився на usage limit у Task 6 fix round 2 із незакоміченим GREEN деревом. Coordinator (Claude Code) перевірив diff проти review I2/M1, повний suite 318 passed/1 skipped, Ruff/diffcheck clean; commit `7d7809e`. Scoped rereview `task-6-rereview.md` виконав той самий coordinator (не окремий агент): I1/I2/M1 ADDRESSED, нових Critical/Important немає, 2 observations передані до Task7/13.

Task 6: complete (BASE d0e5fe0; implementation 012f248; fixes f0f8ea2, 7d7809e).
Task 7: ready (brief task-7-brief.md; переглянути проти фактичних Task4–6 API перед стартом).

Task 7: complete (BASE a14ac43; commits d885d49, 9b4f31a, 2d6ee36, 740629a). Report task-7-report.md. Deterministic: 350 passed / 2 skipped, Ruff clean; 10 mutation probes each caught. Real Bolt run1 negative preserved (context_mismatch from anyOf schema; gate defect fixed), run2/run3 0 protocol failures, write/read/system/memory-recall 3/3, shell_ls behavior misses recorded. Review: coordinator self-review only (no separate agent) — recorded as limit.
Task 8: in_progress (CLI).
Task 8: complete (BASE bddd571; commit 964709b). Report task-8-report.md. 361 passed / 2 skipped; live installed CLI with real Bolt verified. Review: coordinator self-review + 4 mutations.
Task 9: next (API/auth).
Task 9: complete (BASE 4d7b7c0; commit 9632cdc). Report task-9-report.md. 382 passed / 2 skipped; 8 API security mutations caught; live uvicorn + real Bolt verified. Review: coordinator self-review.
Task 10: next (Web UI).
Task 10: complete (BASE 9ce4c9d; commit 6610f85). Report task-10-report.md. Headless Chrome CDP acceptance run2 20/20 with real Bolt; 385 passed / 2 skipped.
Task 11: next (goals/attention/reflection).
Task 11: complete (BASE 5045992; commits 71fba28, 3b47f39, 6032a15). Report task-11-report.md. 404 passed / 2 skipped; 10 mutations caught; real Bolt goal 3/3 achieved by trusted check, reflection 3/3 recorded.
Task 13: next (service/backup/restore), then Task 15 soak start.

## Pause 2026-10-26 ~15:35 UTC (owner: "закінчуй поки це", publish to GitHub as B-12)
Tasks 11, 12, 13 complete (13: real service install left to owner). Task 14 ctx4096 done, ctx8192 partial (resumable). Task 15 soak 1h19m only + open RSS growth. Tasks 16–17 deferred by owner. Task 18 protocol only. Task 19 driver only. Task 20 pending. Details: task-12-15-18-19-report.md. Full suite at 8b60bd7: 450 passed / 3 skipped.
Resume order: (1) RSS leak probe+fix, (2) re-run eval ctx4096 on HEAD + finish ctx8192, (3) full 8 h soak, (4) wiki for tasks 12–19, (5) Task 20 audit; voice when owner decides.
