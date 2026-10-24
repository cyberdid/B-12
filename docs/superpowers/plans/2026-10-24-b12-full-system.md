# B-12 Full System Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Побудувати локального B-12 з постійною пам’яттю, реальними системними tools, автономністю, інтерфейсом, голосом і перевіреними апаратними адаптерами відповідно до R01–R17.

**Architecture:** Python async service з canonical SQLite memory і audit metadata, окремими derived indexes, змінним Ollama adapter, bounded tool loop та owner control plane. CLI/Web/API використовують одне application ядро; audio/motor interruption не очікують reasoning. archive-index повторно використовується під exact authorization і token-budget adapter.

**Tech Stack:** Python 3.12, SQLite/FTS5, pydantic, httpx, FastAPI/uvicorn, pytest/pytest-asyncio, pinned archive-index lexical/search components; optional audio/robot dependencies встановлюються окремо.

**Spec:** `docs/superpowers/specs/2026-10-24-b12-system-design.md` — основне джерело вимог; master brief і wiki уточнюють предметну область.

## Global Constraints

- Мова інтерфейсу й документації — українська; UA/EN/code-switch сценарії обов’язкові.
- Python public package `b12`, layout `src/b12`, tests `tests`; `requires-python >=3.12,<3.14`.
- Owner доручив повний implementation/test цикл і надав host access; не перепитувати про початок, читальні чи вже дозволені зворотні дії.
- Не підміняти host access лише read-only tools: повинні бути реальні file writes і command execution з timeout/cancel/audit та control-channel policy.
- Canonical metadata append-only; персональний payload видаляється, а source/evidence boundaries перевіряються до persistence/retrieval.
- LLM не змінює Actor, consent, grants або risk approvals.
- `raw/` і завершені benchmark artifacts незмінні; third-party LICENSE/NOTICE зберігаються.
- Tests не відкривають production archive DB і не виконують довільні дії у реальних user files; sandbox side effects реальні, не mocked success.
- No GPU/model download у deterministic unit tests; real-model eval явно маркований.
- Hidden thinking не записується до durable logs чи reports.
- Не запускати руйнівні дії, не надсилати повідомлення іншим і не публікувати нічого як побічний ефект тесту.
- Кожна task має RED → GREEN evidence, task review, exact file ownership і checkpoint commit. У progress ledger фіксуються BASE/HEAD, tests, findings і rulings.
- Загальна ціль не завершується до requirement-by-requirement перевірки R01–R17; hardware/time-dependent items залишаються видимими.

## Структура файлів

| Файли | Відповідальність |
|---|---|
| `pyproject.toml`, `uv.lock`, `config.example.toml` | Packaging, locked dependencies, перевірювана конфігурація |
| `src/b12/contracts.py`, `config.py` | Validated Actor/Memory/Tool/Model contracts, runtime limits |
| `src/b12/memory.py`, `migrations.py` | Canonical payload, audit chain, isolation, deletion/recovery |
| `src/b12/retrieval.py`, `_vendor/archive_index/` | Authorized memory/knowledge search, provenance, pinned reuse |
| `src/b12/context.py`, `model.py` | Admission, message selection, streaming Ollama, metrics/cancel |
| `src/b12/tools/{registry,policy,filesystem,process,network,memory}.py` | Typed executable tools і policy |
| `src/b12/agent.py`, `sessions.py` | Multi-round execution, working context, result association |
| `src/b12/goals.py`, `attention.py`, `reflection.py` | Persistent tasks, bounded initiative, evidence-backed growth |
| `src/b12/api.py`, `cli.py`, `web/` | Authenticated local interface й control plane |
| `src/b12/audio/`, `robotics/` | ASR/TTS/duplex/identity та single-writer hardware adapters |
| `src/b12/telemetry.py`, `service.py` | Health, cancellation, metrics, service lifecycle |
| `tests/{unit,integration,e2e,security,performance}/` | Реальні boundaries і deterministic scenarios |
| `evals/{cases,runner,scoring}.py`, `scripts/`, `deploy/` | Large evals, stress/soak, install/recovery |
| `artifacts/<run-id>/` | Parameters, responses, metrics, failure records; секрети редагуються |

Спільні зміни contracts/config потребують перевірки всіх consumers. Не створювати порожні каталоги як доказ готової функції.

## Task status

| Task | R-вимоги | Gate |
|---|---|---|
| 1 Contracts/package/config | R01–R03 | strict validation та reproducible environment |
| 2 Canonical memory | R04–R05 | restart/isolation/forget/audit tests |
| 3 Knowledge/retrieval | R04/R08 | real FTS, exact scope, freshness/purge |
| 4 Model/context | R02–R03 | real stream + conservative admission + fault tests |
| 5 Tool registry/policy | R06–R07 | validated schema, grants, denied-call no side effect |
| 6 Host tools | R06 | real filesystem/process/network sandbox effects |
| 7 Agent/session loop | R07/R09 | model→tool→result→final, cancel/limits/restart |
| 8 CLI | R11–R12 | installed executable та interactive transcript |
| 9 API/auth | R11 | owner/guest/CSRF controls, streaming/control tests |
| 10 Web UI | R11 | actual browser interaction, memory/tools/cancel |
| 11 Goals/initiative/reflection | R09–R10 | bounded real autonomous cycle |
| 12 MCP/archive/semantic | R06/R08 | real server tool bridge, joint resources |
| 13 Service/operations | R12 | user service, health/restart/backup/restore |
| 14 Large model/tool eval | R13 | 100 cases ×5, conversations, failures reported |
| 15 Stress/growth/soak | R14 | durable traces, process/resource/fault recovery |
| 16 Desktop voice | R15 | real UA/EN PTT, ASR/TTS, audio latency |
| 17 Duplex/identity | R15 | AEC/barge-in/mute/consent, 8h duplex |
| 18 Reachy/Jetson | R16 | real adapters, contract tests, physical evidence |
| 19 Long-horizon evidence | R17 | actual 1/7/30 days, forget/recovery |
| 20 Release audit | R01–R17 | final review, install/run, requirement matrix |

### Task 1: Відтворюваний package, contracts та config

**Files:** Create `pyproject.toml`, `src/b12/__init__.py`, `src/b12/contracts.py`, `src/b12/config.py`, `config.example.toml`, `tests/unit/test_contracts.py`, `tests/unit/test_config.py`. Modify `.gitignore` only for new generated state. Generate `uv.lock`.

**Interfaces produced:**

```python
class Actor(BaseModel):
    schema_version: Literal[1] = 1
    id: str  # 1..128 chars, nonempty after whitespace validation
    owner: bool = False
    consent: bool = False
    # frozen=True; strict=True; extra='forbid'

class MemoryRecord(BaseModel):
    schema_version: Literal[1] = 1
    id: str; owner_id: str; kind: str; text: str
    source: str; created_at: str; evidence_ids: tuple[str, ...] = ()

class ToolCall(BaseModel):
    schema_version: Literal[1] = 1
    id: str; name: str; arguments: dict[str, Any]
    turn_id: str | None = None; task_id: str | None = None

class ToolResult(BaseModel):
    schema_version: Literal[1] = 1
    call_id: str; name: str; status: str
    content: dict[str, Any]; duration_ms: float = 0
    error_code: str | None = None; truncated: bool = False
    side_effects: tuple[dict[str, Any], ...] = (); outcome_unknown: bool = False

class ModelReply(BaseModel):
    schema_version: Literal[1] = 1
    content: str = ''; tool_calls: tuple[ToolCall, ...] = ()
    metrics: dict[str, Any] = {}; finish_reason: str = 'stop'

class Settings(BaseModel):
    state_dir: Path; model: str = 'b12-bolt-e4b:q4km'
    ollama_url: str = 'http://127.0.0.1:11434'
    num_ctx: int = 4096; output_tokens: int = 512
    max_rounds: int = 8; max_tool_calls: int = 16
    tool_timeout_s: float = 30; host_access: str = 'full'
    # validate ranges, loopback URL shape, context reserve, state path
    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None) -> 'Settings': ...
```

MemoryRecord IDs/evidence and non-null ToolCall turn/task IDs are application UUIDs; Actor/provider call IDs are opaque. `created_at` is validated ISO8601 UTC. Actor is a DTO: routes must derive trusted actor/consent from authenticated server state.

- [ ] RED: reject Actor `id=''`, unknown fields and string booleans; reject negative rounds/output reserve >= context, malformed URLs. Confirm no cross-instance mutable defaults.
- [ ] Run `uv run pytest tests/unit/test_contracts.py tests/unit/test_config.py -q`; missing import/validation must fail before production methods exist.
- [ ] Implement strict models/range/path validation and environment parsing; no filesystem writes inside config parsing.
- [ ] GREEN: rerun targeted tests; `uv sync --extra dev --locked` succeeds; package imports without model/GPU.
- [ ] Commit `feat: establish validated B-12 runtime contracts`; review contracts against spec and next tasks.

Example observable test:

```python
def test_text_cannot_turn_into_control_consent():
    with pytest.raises(ValidationError):
        Actor(id='guest', consent='true')
```

### Task 2: Canonical persistent memory та забуття

**Files:** Create `src/b12/memory.py`, `src/b12/migrations.py`, `tests/unit/test_memory.py`, `tests/integration/test_memory_restart.py`, `tests/security/test_memory_isolation.py`.

**Consumes:** Actor/MemoryRecord from Task 1. **Produces:**

```python
MemoryStore(path: Path)
MemoryStore.remember(text: str, actor: Actor, *, kind: str = 'fact',
                     source: str = 'user', evidence_ids: tuple[str, ...] = (),
                     expected_deletion_revision: int | None = None) -> MemoryRecord
MemoryStore.search(query: str, actor: Actor, *, limit: int = 8) -> list[MemoryRecord]
MemoryStore.forget(memory_id: str, actor: Actor) -> bool
MemoryStore.audit_events(actor: Actor, *, limit: int = 100) -> list[dict]
MemoryStore.close() -> None
MemoryStore.deletion_revision(actor: Actor) -> int
MemoryStore.begin_purge(memory_id: str, actor: Actor,
                        *, stores: tuple[str, ...] = ('canonical',)) -> PurgeReceipt
MemoryStore.acknowledge_purge(operation_id: str, store: str, actor: Actor,
                              *, error_code: str | None = None) -> PurgeReceipt
MemoryStore.pending_purges(actor: Actor) -> list[PurgeReceipt]
MemoryStore.resume_purges(actor: Actor) -> list[PurgeReceipt]
```

PurgeReceipt is a new strict schema_version=1 DTO in contracts.py: operation_id UUID, target_ids tuple UUID, state pending|complete|failed, pending_stores tuple nonblank strings, error_code optional nonblank string. Storage primitive forget bool describes canonical state only, never global R05. begin_purge persists payload-free operation/closure before deleting allowed payload; canonical acknowledgement occurs only after physical cleanup/checkpoint. Busy checkpoint remains pending. Other hook acknowledgements are idempotent and actor-scoped; resume_purges retries canonical cleanup without pretending to execute external hooks. Retain IDs/deletion revision after restart. expected_deletion_revision rejects a late memory write after forget; no extra payload is stored in rejection or audit.

Tests include: denied consent leaves no payload bytes; exact owner/guest isolation; cross-scope evidence rejection; restart; transitive reflection purge; unrelated memory retained; audit has no text/source/path/arguments and is tamper-evident; SQL injection-like queries safe; pending external hooks survive restart; acknowledgement completes only after every required store; held WAL reader cannot produce a false physical complete; stale expected deletion revision denied. Existing permissions of unrelated parent directories are not changed. Future/newer schema rejected before data mutation. Use SQLite temporary files and actual independent connections/threads for concurrency, not mocked SQL.

- [ ] RED: store an allowed memory, close/reopen, retrieve exact text/source/ID; no-consent raises PermissionError before any payload persistence.
- [ ] RED: owner/guest namespaces exact; evidence from another actor rejected; forgetting cascades dependent reflections while leaving unrelated memory.
- [ ] Implement transactional payload/evidence/FTS tables, append-only payload-free audit metadata, schema version, parameterized queries, safe FTS terms, WAL/secure_delete, hash chain and restrictive state permissions.
- [ ] Implement forget transaction plus FTS/evidence cleanup and WAL checkpoint; memory lookup never uses forgotten payload. Corrupt audit chain returns explicit failure, not silently repaired history.
- [ ] GREEN: `uv run pytest tests/unit/test_memory.py tests/integration/test_memory_restart.py tests/security/test_memory_isolation.py -q`.
- [ ] Commit and review real SQL effects, durable bytes after forget and restart; no code-only assertions.

```python
def test_restart_retains_allowed_memory(tmp_path):
    actor = Actor(id='owner', owner=True, consent=True)
    path = tmp_path / 'memory.sqlite3'
    store = MemoryStore(path)
    saved = store.remember('Учора тестували мікрофон і знайшли ехо', actor, source='event-test-17')
    store.close()
    reopened = MemoryStore(path)
    hits = reopened.search('мікрофон', actor)
    assert [(m.id, m.source) for m in hits] == [(saved.id, 'event-test-17')]
```

### Task 3: Derived knowledge retrieval і pinned archive reuse

**Files:** `src/b12/retrieval.py`, `_vendor/archive_index/{__init__,lexical,store,search}.py`, `_vendor/archive_index/{LICENSE,NOTICE,SOURCE.json}`, `tests/integration/test_retrieval.py`.

**Consumes:** exact Actor scope and canonical records. **Produces:** `KnowledgeIndex(path: Path)`, `index_document(path: Path, actor: Actor)`, `search(query: str, actor: Actor, limit: int = 5) -> list[dict]`, `remove_document(path: Path, actor: Actor)`; hits include stable evidence ID/source/locator/text.

- [ ] RED: same word in B-12 and B-12-other namespaces returns only exact authorized document; update/delete reflected immediately; unrelated files not scanned implicitly.
- [ ] Copy exact pinned modules/notices from reviewed raw snapshot; use zero-length vectors for lexical-only chunks. Wrap source ingestion/lookup with exact ownership guards.
- [ ] Canonical memory may use its own transactional FTS with shared lexical functions; knowledge documents use derived archive Store/search. No blanket use of production archive DB.
- [ ] GREEN: real temp SQLite integration; test Cyrillic apostrophes/morphology and missing query, not just mocked arrays.
- [ ] Commit/review source attribution and cache invalidation.

### Task 4: Model streaming, context admission та cancellation

**Files:** `src/b12/model.py`, `context.py`, `tests/unit/test_context.py`, `tests/integration/test_ollama_transport.py`, `tests/e2e/test_real_ollama.py`.

**Produces:** `ContextBuilder(settings).build(system, messages, evidence, tools) -> list[dict]`; `OllamaModel(settings).chat(messages, tools=(), on_delta=None, cancel=None) -> ModelReply` (async); `ModelError(code, message)`.

- [ ] RED: overlong latest user input rejected; old working messages evicted before system/evidence budget violation; tool schemas count; no partial tool-result pair.
- [ ] RED: local HTTP fixture emits real JSONL success/error/malformed/missing-done/delay; adapter raises distinct errors and cancels transport. No mock of adapter parsing.
- [ ] Implement httpx async streaming, metrics and structured tools; strip reasoning before callbacks/logging; conservative UTF-8 admission until exact tokenizer validation.
- [ ] GREEN: deterministic transport tests; real marked Ollama test proves Ukrainian response at 4096 and actual prompt count within reserved budget. Benchmark 4096/8192 before changing default if memory does not fit.
- [ ] Commit/review handling of cancellation, output limits and no silent prompt truncation.

### Task 5: Tool registry, schema validation та control policy

**Files:** `src/b12/tools/{__init__,registry,policy}.py`, `tests/unit/test_registry.py`, `tests/security/test_tool_policy.py`.

**Produces:** `ToolRegistry.register(name, description, argument_model, handler, capability)`; `.schemas(actor) -> list[dict]`; async `.execute(call: ToolCall, actor: Actor, grant: dict, cancel=None) -> ToolResult`.

- [ ] RED: invalid integer/path/extra args never reaches real handler; unknown tool gives structured error; guest cannot reuse owner grant; LLM `approved=true` argument rejected.
- [ ] Implement strict argument models, owner grants from control channel, risk classes, per-call timeout, audit hooks and exact call/result IDs.
- [ ] GREEN: handler side effect file exists only for authorized valid call; denial/timeout has no claimed success.
- [ ] Commit/review grant lifecycle and bypass cases.

### Task 6: Повний набір реальних host tools

**Files:** `src/b12/tools/{filesystem,process,network,memory}.py`, `tests/integration/test_host_tools.py`, `tests/security/test_host_boundaries.py`.

**Tools:** `system_info`, `process_list`, `file_list`, `file_read`, `file_search`, `file_write`, `shell_exec`, `http_fetch`, `memory_search`, `memory_store`, `memory_forget`, `knowledge_search`, `current_time`.

- [ ] RED: write/read file through registry in temp dir; replacement atomic; symlink/path permissions honored; bounded large/binary output; no secret values persisted to audit.
- [ ] RED: real Python child sleeps/spawns child; timeout/cancel terminates process group; argv is not interpreted by shell; stderr/exit code/output truncation returned.
- [ ] Implement host paths within actual Linux permissions, owner full-host control grant, backups for overwrites, subprocess groups and cancellable HTTP fetch. Destructive actions require explicit control approval.
- [ ] GREEN: temp filesystem + real processes + local HTTP server; no change to unrelated user files.
- [ ] Commit/review side effects and no escape via model-controlled grants.

### Task 7: Інтегрований agent loop і sessions

**Files:** `src/b12/agent.py`, `sessions.py`, `tests/integration/test_agent_loop.py`, `tests/e2e/test_bolt_tools.py`.

**Produces:** `Agent(settings, model, memory, tools).turn(session_id, text, actor, on_event=None, cancel=None) -> dict`; working history persistent only with trusted consent.

- [ ] RED: local fixture model requests actual file_write/file_read; final receives real tool result, exact IDs; duplicate IDs, malformed/unknown calls, errors, multiple calls and max rounds bounded.
- [ ] Implement model→tools→results→model loop, event stream, context admission each round, per-session lock and model semaphore, tool/result provenance, safe restart.
- [ ] GREEN: actual Bolt multi-step write/read and system inspection in task sandbox; verify file content independently, not by assistant prose.
- [ ] Commit/review real model failures separately from deterministic protocol failures.

### Task 8: CLI користувача

**Files:** `src/b12/cli.py`, `tests/e2e/test_cli.py`.

- [ ] RED: subprocess `b12 doctor` produces health/model/state status; `b12 memory search/forget` survives separate processes; noninteractive turn returns machine-readable JSON.
- [ ] Implement argparse commands `doctor`, `chat`, `serve`, `memory`, `tools`, `eval`; Ctrl-C cancels current task without corrupting state.
- [ ] GREEN: installed entry point in clean environment, interactive scripted conversation, restart and explicit no-model error.
- [ ] Commit and record exact user commands.

### Task 9: Local API, auth та control channel

**Files:** `src/b12/api.py`, `auth.py`, `tests/integration/test_api.py`, `tests/security/test_api_auth.py`.

**Routes:** `/api/health`, `/api/sessions`, `/api/chat`, `/api/tasks/{id}/cancel`, `/api/memory`, `/api/tools`, `/api/control`, `/api/approvals`, `/api/goals`.

- [ ] RED: unauthenticated host action denied; guest isolation; consent/grant changed only by authenticated control; wrong browser Origin rejected; stream disconnect cancels turn.
- [ ] Implement loopback binding, 0600 owner-token bootstrap, bounded request bodies, streaming events, lifecycle startup/shutdown and owner/guest sessions.
- [ ] GREEN: real ASGI integration and separate live-server process tests with state directory in temp storage.
- [ ] Commit/review authentication before enabling host tools through API.

### Task 10: Web UI для повсякденної роботи

**Files:** `src/b12/web/{index.html,app.js,style.css}`, `tests/e2e/test_web.py`.

- [ ] Define browser acceptance: start session, stream text, view real tool result/evidence, remember/search/forget, toggle quiet/consent, approve pending action, cancel.
- [ ] Implement local static UI in Ukrainian using actual API; handle reconnect/error/pending states without fake success. Token never appears in URLs/logs.
- [ ] GREEN: browser automation against live server plus manual screenshot inspection; inspect DOM/network for actual effects.
- [ ] Commit/review empty, offline, long-output and keyboard states.

### Task 11: Goals, увага, ініціатива та self-model

**Files:** `src/b12/{goals,attention,reflection}.py`, `tests/unit/test_attention.py`, `tests/integration/test_autonomy.py`.

- [ ] RED: quiet hours/cooldown/hour cap block background speech; direct user request works; goal status survives restart; reflection requires existing allowed evidence.
- [ ] Implement persisted goals, idle scheduler, max 3 nonurgent initiatives/hour, ignored-proposal backoff, cancellable background tasks and versioned preferences with reasons.
- [ ] GREEN: fake clock only at time boundary plus real scheduler/process restart; real Bolt proposes/evaluates a bounded synthetic experiment with recorded outcome.
- [ ] Commit/review runaway-loop prevention and no unsupported claims of learning.

### Task 12: MCP bridge, archive adapter та semantic retrieval

**Files:** `src/b12/tools/mcp.py`, `semantic.py`, `tests/integration/test_mcp.py`, `tests/performance/test_joint_models.py`.

- [ ] RED: actual local MCP fixture exposes tool; discovery/schema/result/error/cancel pass through policy; tool names cannot override built-in grants.
- [ ] Implement MCP stdio client with child lifecycle, versioned catalog and bounded results; owner-only archive adapter with exact scopes and no constructor migrations on production read path.
- [ ] Benchmark embedding backend alongside Bolt; choose cache invalidation and CPU/GPU scheduling based on measured RAM/latency, retain lexical fallback.
- [ ] GREEN: end-to-end real tool via MCP and semantic fixture retrieval; real model resources measured separately.
- [ ] Commit/review source provenance and external server process cleanup.

### Task 13: Сервіс, observability, backup/restore

**Files:** `src/b12/{telemetry,service}.py`, `deploy/b12.service`, `scripts/install-user-service.sh`, `tests/e2e/test_recovery.py`.

- [ ] RED: restart restores allowed state and goals; graceful shutdown cancels children; partial transaction recovers; backup/restore preserves data; forget purges managed snapshots.
- [ ] Implement user service, root-free installation, state under configured large filesystem, health/resource/latency metrics, bounded redacted logs and backup inventory.
- [ ] GREEN: installed user service start/stop/restart, no duplicate workers, CLI/Web usable after restart, schema migration and rollback procedure verified on copies.
- [ ] Commit/review service permissions and actual deployment paths.

### Task 14: Великий корпус model/tool tests

**Files:** `evals/cases/{ua,en,tools,memory,behavior,adversarial}.jsonl`, `evals/{runner,scoring}.py`, `tests/e2e/test_eval_runner.py`.

- [ ] Define at least 100 explicit cases with independent expected values/rubrics: UA/EN, unknown facts, corrections, source grounding, quiet reasons, system tasks, injection, invalid calls, consent and cross-actor memory.
- [ ] Implement resumable runner with exact settings/digest/TTFT/token counts/call traces, deterministic checks and separate human rubric fields. Failures remain visible.
- [ ] Run 5 repeats, at least 30 multi-step real tool tasks, 50–100-turn conversations; compare cold/warm/cache and context 4096/8192. All file/process effects confined to designated test sandboxes.
- [ ] GREEN: published local report with actual case counts, failed-case list, supported conclusions and fixes linked to regression tests.
- [ ] Commit corpus/runner; artifacts stored outside Git when large/private and catalogued in wiki.

### Task 15: Stress, growth, failure injection та 8h software soak

**Files:** `scripts/soak.py`, `scripts/load_memory.py`, `tests/performance/test_growth.py`, `tests/integration/test_failure_recovery.py`.

- [ ] Define workload: 200/2k/20k/200k memories, concurrent sessions, writes/forget during retrieval, long tool output, model downtime, task interruption and abrupt process termination.
- [ ] Implement reproducible load/soak drivers and progress checkpoints. Track leaks, DB integrity, orphan processes, task latency and error recovery.
- [ ] Run 8h software soak; only a confirmed live PID/session is a verified wait. Preserve all failure windows and fix with reproducing tests.
- [ ] GREEN: no unbounded growth/silent loss/unauthorized effects, post-soak restart/forget/recall pass; incomplete duration never labelled 8h.
- [ ] Commit drivers and audit report, not synthetic elapsed-time claims.

### Task 16: Реальний desktop voice / PTT

**Files:** `src/b12/audio/{capture,asr,tts,pipeline}.py`, `tests/integration/test_voice.py`, `evals/voice/`.

- [ ] Inventory actual devices and installed models; choose licensed UA TTS and ASR based on measured quality/resources. Never import VoiceID datasets automatically.
- [ ] RED: streaming audio cancellation, no raw durable recording by default, transcript provenance, output phrase queue bound.
- [ ] Implement PTT capture, VAD, real ASR, sentence TTS playback and UI mic/consent controls; record end-of-utterance to meaningful audio separately from earcon/model timing.
- [ ] GREEN: actual UA/EN/code-switch recordings, WER/listening rubric, cold/warm first-audio results, interruption and GPU-load tests.
- [ ] Commit code/config and documented voice/model licenses.

### Task 17: Full-duplex, identity та 8h audio soak

**Files:** `src/b12/audio/{aec,endpoint,speaker,duplex}.py`, `tests/integration/test_duplex.py`, `evals/voice/duplex/`.

- [ ] RED: exact TTS render reference, barge-in stops playback/queued chunks, mute stops acquisition, guest enrollment cannot occur through model text.
- [ ] Implement AEC/endpoint, owner enrollment/verification thresholds, media-contamination policy and anti-spoof acceptance boundary.
- [ ] Run real noise/TV/distance/code-switch and 8h duplex soak with GPU activity; record FAR/FRR, false endpoints, time-to-stop and meaningful audio P50/P95/P99.
- [ ] GREEN: actual duration/evidence required; missing hardware/acoustic conditions remain explicitly open.
- [ ] Commit and review physiological data retention/deletion behavior.

### Task 18: Reachy Mini та Jetson adapters

**Files:** `src/b12/robotics/{reachy,motion,transport}.py`, `configs/jetson.toml`, `tests/integration/test_robot_protocol.py`, `evals/hardware/`.

- [ ] Implement adapter protocol with single-writer motion, speed/angle bounds, safe disconnect/reconnect; real simulator/protocol fixture tests.
- [ ] Inspect available physical equipment with owner's scope; do not commandeer work SDR/Jetson services merely because an SSH alias exists.
- [ ] Bring up real Reachy if present; Wireless media proof before LLM. On personal Jetson measure standalone/joint models, unified memory, swap/thermal/audio, and no-laptop degraded behavior.
- [ ] GREEN: physical traces and actual device identity required for hardware acceptance. Adapter tests alone prove protocol behavior only.
- [ ] Record unavailable-device dependencies while continuing desktop work.

### Task 19: Довготривала пам’ять та розвиток

**Files:** `evals/long_horizon/`, `scripts/daily_check.py`, wiki experiment pages.

- [ ] Schedule evidence-backed recall/review on real day 1/7/30, daily recovery and owner feedback on initiative/preferences.
- [ ] Verify forgotten source cannot reappear through reflection/index/session/backup and a changed opinion retains its explanation/history without deleted private payload.
- [ ] Actual 24–72h desktop operation, then 30-day record; accelerated replay is additional evidence, not a replacement.
- [ ] GREEN: dated source/event/query/results and manual feedback, failures visible.
- [ ] Commit reusable drivers; retain private runtime data outside Git.

### Task 20: Final review, release та requirement audit

**Files:** `docs/OPERATIONS.md`, `docs/ACCEPTANCE.md`, `README.md`, wiki status/index/log and deployment manifest.

- [ ] Run full deterministic suite/lint, fresh install and browser/CLI/real-model acceptance; review whole branch independently.
- [ ] Audit every R01–R17 against actual files, commands, live runtime and artifacts; mark missing/weak/contradictory evidence incomplete.
- [ ] Fix load-bearing findings with regression tests; rerun only affected plus required global gates. Preserve baseline benchmarks.
- [ ] Integrate local development branch into the user's project once verified; no remote push/publication implied.
- [ ] Goal complete only after full objective is proven; otherwise leave active with exact next task, live process handles and requirements still open.

## Execution decisions already authorized

Виконання починається в поточній сесії після запису plan/spec. Обрано subagent-driven task execution з незалежним review; необов’язковий вибір способу виконання не виноситься як повторне питання. Worktree ізолює runtime від дослідницького baseline. Власний ledger і commits є джерелом відновлення після compaction.

## Plan self-review

- Вимоги R01–R17 відображені в task matrix; voice/hardware/long horizon не вилучені заради раннього desktop результату.
- Межі contracts/memory/retrieval/tools/model/API визначені; shared-file changes проходять integration checks.
- Task 2 спершу canonical FTS, Task 3 pinned archive reuse; це не два конкуруючі авторитетні сховища.
- Task 4 context default 4096 допускається лише після реального resource/admission тесту; baseline alias 2048 не змінюється мовчки.
- Tests містять реальні side effects і зовнішні boundaries; model fakes використовуються тільки для детерміністичного protocol/fault coverage, реальний Bolt має окремі gates.

## Binding review amendments (24.10.2026)

Architecture review is captured in the execution ledger. Spec §15 overrides earlier abbreviated interfaces where needed.

- Task 2 keeps local MemoryStore.forget bool explicitly local. Also create PurgeReceipt and persisted payload-free purge outbox/tombstone primitives; busy checkpoint must not claim physical completion. Application PurgeCoordinator is wired in Tasks 7/9 and backup hook in Task 13. Audit actor IDs are internal opaque IDs, never display names; evidence resolver must reject cross-scope/revoked references.
- Task 3 uses per-actor derived archive Store files and revision-aware UUID EvidenceRef, not global path identity or mutable rowids. Registration/lookup/update/delete authorizes before top-k. Contract fixture uses two actors indexing the same absolute source path.
- Tasks 5–7 add ExecutionContext/ControlStore revision checks, exact one-shot approval binding, persistent tool lifecycle and unknown-outcome handling; no automatic replay of non-idempotent effects.
- Task 4 produces immutable AdmittedRequest; exact tokenizer or validated template-specific conservative overhead includes tool schemas. Model adapter cannot accept post-admission schema changes. Real prompt counts alone do not prove absence of truncation; boundary instructions/output are checked independently.
- Tasks 7–10 share TurnResult/event fixtures and authenticated application factory. Client DTO fields never establish owner/consent/grants. Late persistence after revoke/delete revision is rejected.
- Task 11 keeps immutable original intent/criteria, checkpoints, consumed budgets and evidence-verified completion; quiet speech and execution pause differ.
- Tasks 13/15 test purge hook failure, restart/restore with deletion replay, held WAL reader and late reflection; all managed copies must be acknowledged before global complete.
