# B-12 / Capri Codebase Architecture & Subsystems Survey

**Author**: Explorer 2 (Codebase Architecture & Capri Subsystems Specialist)  
**Date**: 2026-11-10  
**Repository Working Directory**: `/home/cyberdid/Projects/B-12`  
**Git HEAD Commit**: `8f29661` (`8f2966144e5d6d37016cfb33b000843236e76811`) on branch `main`  
**Integrity Mode**: Development / Local Investigation  

---

## 1. Executive Summary

B-12 is a mature, production-grade local-first companion runtime implemented in Python 3.12 (`b12-runtime` v0.1.0) with custom asynchronous orchestration (`asyncio`), SQLite persistence engines, and direct OS/local model integration. Rather than a superficial LLM wrapper, B-12 implements a formal dual-system cognitive architecture (System 1 reactive loop for AEC/VAD/barge-in/motor limits; System 2 reflective loop for LLM reasoning, goal planning, and tool execution).

The companion identity ("Capri" / "Cybercat") is unified within B-12: the default character is the built-in Cybercat (animated terminal sprite atlas in Textual TUI), with Capri supported as an externally loaded skin pack (`B12_TUI_CAPRI_DIR`) adhering strictly to intellectual property boundaries documented in `wiki/sources/capri-desktop-companions-2026-11-07.md`.

Out of 656 automated tests collected in `pytest`, 650 passed, 4 were skipped (opt-in real-model benchmarks), and exactly 2 failed due to recent upstream enhancements (`note_add` expanding the tool catalog from 15 to 16, and TUI companion panel expansion altering a layout assertion). Physical robotics hardware (Reachy Mini / Jetson) and physical 8-hour acoustic room soak remain open/unverified, but simulated and local protocol layers are extensively tested.

---

## 2. Repository Layout & Module Mapping

```
/home/cyberdid/Projects/B-12/
├── src/b12/                      # Core runtime package
│   ├── contracts.py              # Pydantic DTOs: Actor, MemoryRecord, ToolCall, ToolResult, ModelReply
│   ├── config.py                 # Pydantic settings loading and path resolution
│   ├── runtime.py                # open_runtime() application factory and service wiring
│   ├── service.py                # RuntimeLock, managed snapshots, deletions ledger replay, logging
│   ├── control.py                # SQLite ControlStore: actors, sessions, grants, approvals, tokens
│   ├── memory.py                 # SQLite MemoryStore: cryptographic audit chain, FTS5 + pymorphy3, purge
│   ├── evidence.py               # EvidenceResolver for memory, document, and tool_result provenance
│   ├── semantic.py               # BridgeEmbedder and SQLite vector storage for cosine recall
│   ├── retrieval.py              # KnowledgeIndex: per-actor document indexing and hybrid search
│   ├── retrieval_storage.py      # ActorStore and ScopeRegistry for lexical storage
│   ├── context.py                # ContextBuilder: token admission and conservative headroom budgeting
│   ├── model.py                  # OllamaModel: HTTP streaming, NDJSON, cancellation, token accounting
│   ├── model_profile.py          # ModelProfile: pinned model configuration and asset verification
│   ├── model_errors.py           # Structured ModelError hierarchy
│   ├── agent.py                  # Cognitive loop: multi-round tool execution, "persist" mode, nudges
│   ├── sessions.py               # SessionStore: SQLite turns, checkpoints, evidence tags, invalidations
│   ├── purge.py                  # PurgeCoordinator: global transitive forget across 7 subsystems
│   ├── autonomy.py               # Scheduler: background goal worker with flock, deterministic criteria
│   ├── attention.py              # AttentionPolicy: quiet mode, quiet hours, cooldown, backoff
│   ├── goals.py                  # GoalStore: goal lifecycle, checkpoints, review intervals
│   ├── reflection.py             # Idle reflection daemon: memory synthesis, hypothesis generation
│   ├── maintenance.py            # Maintenance daemon: malloc_trim(0), expired approval cleanup
│   ├── migrations.py             # SQLite schema v1 -> v2 automatic migration with verified backup
│   ├── auth.py                   # API token generation and capability resolution
│   ├── api.py                    # FastAPI server: loopback REST & WebSocket endpoints
│   ├── cli.py                    # CLI entrypoint: doctor, chat, serve, memory, tools, eval
│   ├── cli_remote.py             # Remote CLI adapter delegating to running server over HTTP
│   ├── audio/                    # Local voice subsystem
│   │   ├── aec.py                # 128-tap FIR NLMS AEC with FFT alignment; PulseAudioWebRtcAec
│   │   ├── asr.py                # faster-whisper int8 speech recognition
│   │   ├── tts.py                # Piper TTS (uk_UA-mykyta-high.onnx), AudioPlayer nonblocking chunks
│   │   ├── endpoint.py           # Silero VAD ONNX with persistent LSTM state, endpoint detection
│   │   ├── duplex.py             # DuplexSession: full-duplex conversational audio with barge-in
│   │   ├── capture.py            # MicController and PttCapture
│   │   ├── speaker.py            # SpeakerStore & SpeakerVerifier: biometric voice enrollment
│   │   ├── pipeline.py           # VoicePipeline end-to-end turn execution and timing metrics
│   │   └── live.py               # LiveVoiceRunner console listener loop
│   ├── robotics/                 # Embodied AI and motion subsystem
│   │   ├── motion.py             # MotionController: single writer lease, hard angle/speed bounds
│   │   └── transport.py          # SimulatedRobot: linear joint interpolation transport simulator
│   ├── tui/                      # Cybercat & companion terminal interface
│   │   ├── app.py                # Textual application with tabs, composer, cat widget, voice toggles
│   │   ├── sprites.py            # SpriteAtlas and SkinManifest: Cybercat atlas + Capri external skin
│   │   ├── activity.py           # ActivityTracker: local coding agent hooks timeline
│   │   └── voice.py              # VoiceBar widget for audio states
│   ├── _vendor/archive_index/    # Vendored lexical tokenizer and search engine
│   └── web/                      # Embedded browser UI (index.html, app.js, markdown.js, style.css)
├── evals/                        # Evaluation framework
│   ├── build_cases.py            # Generator for 109-case benchmark corpus (v4)
│   ├── cases/                    # JSONL test suites: ua, en, tools, memory, behavior, adversarial
│   ├── runner.py                 # Multi-repeat test runner with isolated state directories
│   ├── scoring.py                # Deterministic scoring rubrics
│   ├── ollama_broker.py          # Private Unix domain socket model broker for sandbox testing
│   ├── socket_bridge.py          # Container-to-broker TCP relay
│   └── voice/                    # Voice benchmarks (WER, TTFA, AEC ERLE, barge-in)
├── tests/                        # Automated test suite (656 tests)
│   ├── unit/                     # Fast isolated unit tests (contracts, memory, attention, registry)
│   ├── integration/              # Integrated subsystem tests (agent loop, duplex, voice, robot)
│   ├── security/                 # Permission gating, host boundaries, memory isolation, network
│   ├── performance/              # History growth independence, latency stability
│   └── e2e/                      # Full CLI, server, recovery, and live Ollama tests
├── wiki/                         # Karpathy LLM Wiki knowledge base (topics, sources, project logs)
├── raw/                          # Unaltered source files (Master Brief, source manifest)
├── deploy/                       # Systemd user services (b12.service, b12-daily-check.service/timer)
├── profiles/                     # Pinned model context and tokenizer profiles (bolt-e4b.json)
└── scripts/                      # Utility scripts (daily_check.py, embed_bridge.py, soak.py)
```

---

## 3. Hardware & Runtime Environment Audit

Audit executed on 2026-11-10:

- **Host Processor**: Intel(R) Core(TM) i9-14900HX (24 physical cores: 8 P-cores + 16 E-cores, 32 threads).
- **Host Memory**: 31 GiB physical RAM (14 GiB allocated, 16 GiB available buffer/cache) + 8.0 GiB swap.
- **Host Accelerator**: NVIDIA GeForce RTX 4060 Laptop GPU (8188 MiB VRAM total, 6228 MiB free, driver 550.120).
- **Operating System**: Ubuntu 24.04.5 LTS (Linux kernel 6.8.0-48-generic x86_64).
- **Python Runtime**: Python 3.12.3 via `.venv` (symlinked to `.worktrees/runtime/.venv`), managed with `uv`.
- **Local LLM Engine**: Ollama daemon version `0.33.3` (client binary `0.33.1`).
- **Installed Ollama Models**:
  1. `b12-bolt-e4b:q4km` (ID: `7eaa0c0553b8`, 6.2 GB, Q4_K_M quantization) — Primary pinned baseline model for B-12.
  2. `qwen3.5:27b-q4_K_M` (ID: `7653528ba5cb`, 17 GB) — Large reasoning candidate.
  3. `qwen3.8:27b-q4_K_M` (ID: `25b843619e94`, 17 GB) — Large reasoning candidate.
  4. `gemma4:12b` (ID: `4eb23ef187e2`, 7.6 GB) — Medium multimodal / agent candidate.

---

## 4. Deep Analysis of Architectural Invariants

The B-12 / Capri codebase strictly enforces six architectural invariants established in the Master Project Brief and `AGENTS.md`:

### 4.1 Invariant 1: Local-First Operation
- **Evidence**: `src/b12/config.py`, `src/b12/model.py`, `src/b12/semantic.py` (`HF_HUB_OFFLINE="1"`).
- **Mechanism**: All reasoning, speech synthesis, speech recognition, embedding computation, and persistence run exclusively on loopback (`127.0.0.1` / Unix domain sockets). No telemetry or external cloud API calls are made. External network egress is confined to the explicitly granted `http_fetch` tool.

### 4.2 Invariant 2: Model Swappability
- **Evidence**: `src/b12/model.py` (`OllamaModel`), `src/b12/model_profile.py` (`ModelProfile`).
- **Mechanism**: The cognitive core interacts with language models via a generic interface with NDJSON streaming. Model-specific configurations (context window, tokenizer artifacts, chat template idiosyncrasies) are abstracted in JSON profile definitions (e.g. `profiles/bolt-e4b.json`). Changing the backend model requires updating the profile without rewriting agent logic or tool handlers.

### 4.3 Invariant 3: Non-Blocking Motion & Audio (System 1 / System 2 Decoupling)
- **Evidence**: `src/b12/audio/duplex.py` (lines 80-140), `src/b12/robotics/motion.py` (lines 48-110).
- **Mechanism**: System 1 (AEC echo cancellation, Silero VAD endpointing, barge-in interruption detection, motor hard stops) executes asynchronously on concurrent event-loop tasks independent of System 2 (LLM generation and tool execution). When a user speaks while the companion is speaking, the `DuplexSession` immediately halts audio playback in under 0.04 ms (`interruption_time_to_stop`), isolating cancellation to the active vocal turn without corrupting underlying cognitive state.

### 4.4 Invariant 4: Single Writer to Actuators
- **Evidence**: `src/b12/robotics/motion.py` (`MotionController.acquire()`, lines 57-70).
- **Mechanism**: Actuator commanding requires acquiring an exclusive UUID lease token (`self._lease`). If another subsystem attempts to issue motion commands while a writer holds the lease, the request is rejected with `MotionRejected("writer_busy")`. Motion commands specify explicit duration and targets; all values are validated against `DEFAULT_LIMITS` and `max_speed_deg_s = 90.0 deg/s`. Out-of-bounds targets trigger an immediate exception and are never silently clamped.

### 4.5 Invariant 5: Deterministic Permission and Consent Control Path
- **Evidence**: `src/b12/control.py` (`ControlStore`), `src/b12/tools/registry.py` (`ToolRegistry.execute()`), `src/b12/tools/policy.py` (`EffectGuard`).
- **Mechanism**: Permissions, actor identity, and consent are established exclusively through authenticated control channels (bootstrap token with filesystem mode 0600 or CLI invocation). The LLM's generated prose has zero authority to grant permissions, toggle consent, or invoke tools. Destructive actions (`Risk.DESTRUCTIVE`: `memory_forget`, `file_write`, `sudo_exec`) enter an `approval_pending` state, generating a SHA-256 digest of arguments that requires explicit owner approval before execution.

### 4.6 Invariant 6: Strict Memory Provenance & Verifiable Auditability
- **Evidence**: `src/b12/memory.py` (`MemoryStore`, lines 76-80, 508-522), `src/b12/evidence.py` (`EvidenceResolver`).
- **Mechanism**: Every `MemoryRecord` requires an immutable list of `sources` and `evidence_ids`. Memories linked to external documents store the exact source revision. If a referenced document changes or is removed, `mark_stale_for_documents()` executes a recursive CTE that cascades staleness to all derived memories. Furthermore, all memory operations are logged in a cryptographic hash-chained audit table (`audit`) verified on each transaction.

---

## 5. Capri / B-12 Subsystem Architecture & Implementation Assessment

### 5.1 Memory Systems
- **Autobiographical & Episodic Memory**: Implemented in `src/b12/memory.py` using SQLite (`memories` table) with PRAGMA `secure_delete=ON`, `journal_mode=WAL`, and `synchronous=FULL`. Supports typed records (`fact`, `preference`, `episode`, `procedure`, `hypothesis`, `reflection`).
- **Morphological Ukrainian Search**: `_forms()` in `src/b12/memory.py` uses `pymorphy3` with uk/ru dictionaries to generate inflections for Cyrillic search terms while preserving Ukrainian apostrophes (`'`,`’`,`ʼ`), combined with SQLite FTS5 BM25 scoring and conversational stop-word filtering.
- **Semantic Vector Storage**: `src/b12/semantic.py` provides vector indexing in a private SQLite table (`vectors`). Embeddings are calculated via `BridgeEmbedder` executing `scripts/embed_bridge.py`. Cosine similarity ranking uses NumPy. External heavy vector databases (e.g. Chroma) are intentionally omitted.
- **Knowledge Base Retrieval**: `src/b12/retrieval.py` (`KnowledgeIndex`) provides document ingestion, chunking, and lexical search across private actor directories (`ActorStore`) using vendored `archive-index` components.
- **Global Purge Protocol**: `src/b12/purge.py` (`PurgeCoordinator`) coordinates complete removal of memory IDs across seven managed stores (`canonical`, `sessions`, `goals`, `semantic`, `active_turns`, `backups`, `snapshots`, `provider_cache`, `speakers`). Transitive closure computation (`WITH RECURSIVE closure(id) AS ...`) finds all dependent derived memories. FTS indexes are rebuilt, and WAL truncation checkpoints are executed.

### 5.2 Cognitive Core / Agent Loop / Orchestration
- **Loop Orchestration**: `src/b12/agent.py` (`Agent.turn()` and `Agent.resume_turn()`). Emits structured events (`turn_started`, `text_delta`, `tool_started`, `tool_result`, `approval_pending`, `turn_completed`, `turn_failed`, `turn_cancelled`).
- **Token Admission & Headroom**: `src/b12/context.py` calculates exact token consumption across system prompt, tool definitions, recalled memories, and session history against the target context limit, preserving an output token reserve without silent truncation.
- **"Не зупинятися" (Persist Mode)**: Opt-in mode for complex file exploration. Extends budgets to 150 rounds, 300 calls, and 120 nudges. Tracks touched files and subdirectories, injecting nudges if the model stops before reviewing required directories.
- **Working Notes**: `src/b12/tools/notes.py` provides `note_add`. Findings recorded during large file reads are aggregated in a turn-scoped `[журнал знахідок]` block that survives history trimming.

### 5.3 Tool Calling & Action Execution Framework
- **Registry & Dispatch**: `src/b12/tools/registry.py` enforces strict Pydantic argument parsing and cooperative `EffectGuard` verification.
- **Registered Tools (16 total)**:
  1. `file_list`: Directory enumeration with entry caps.
  2. `file_read`: Bounded chunk reading (up to 12 chunks / ~28 KB) with UTF-8 / base64 modes.
  3. `file_search`: Recursive text search across regular files.
  4. `file_write`: Atomic file replacement with managed rollback backup.
  5. `note_add`: In-turn working notes persistence.
  6. `run_command`: Shell command execution with default cwd and declared effects.
  7. `shell_exec`: Direct executable invocation with argv and process group termination.
  8. `sudo_exec`: Explicitly authorized privileged commands via sudo.
  9. `process_list`: Host process table inspection.
  10. `http_fetch`: Network GET request with content size bounding.
  11. `memory_search`: FTS5 morphological search over memories.
  12. `memory_store`: Memory record insertion with evidence linking.
  13. `memory_forget`: Transitive deletion trigger.
  14. `knowledge_search`: Document index query.
  15. `current_time`: ISO8601 UTC timestamp generation.
  16. `mcp`: External Model Context Protocol tool invocation via JSON-RPC.

### 5.4 Safety, Permission Gating, Sandboxing & Adversarial Guards
- **Control Store**: `src/b12/control.py` manages actor authentication, sessions, and time-bounded capability grants in an internal SQLite database with permissions 0600.
- **Approval Flow**: Destructive actions cannot run on grants alone; they require a pre-execution approval record matched against an argument digest.
- **Path Guard**: `protected_paths` rejects filesystem and process operations targeting state, secrets, or system configuration roots.
- **Sandboxing Boundaries**: The production runtime executes directly as a host process under user permissions. Evaluation sandboxing using Docker was verified via `evals/ollama_broker.py` and `evals/socket_bridge.py`.

### 5.5 Audio & Voice Interaction Pipeline
- **Echo Cancellation (AEC)**: `src/b12/audio/aec.py` provides a 128-tap FIR NLMS filter with FFT cross-correlation delay estimation and double-talk detection. Achieved 30.41 dB ERLE on synthetic multipath benchmarks.
- **VAD & Endpointing**: `src/b12/audio/endpoint.py` uses ONNX Silero VAD with persistent state. P50 speech endpoint latency is 320.0 ms.
- **Speech Recognition (ASR)**: `src/b12/audio/asr.py` integrates `faster-whisper` int8 on CPU/GPU. Achieved 0.0 WER across tested Ukrainian/English benchmarks with P50 latency of 2173.58 ms.
- **Speech Synthesis (TTS)**: `src/b12/audio/tts.py` uses Piper TTS (`uk_UA-mykyta-high.onnx`). Synthesizes clauses via a 3-stage streaming pipeline to `AudioPlayer` with nonblocking chunks and motion hook callbacks. P50 TTFA is 1634.61 ms.
- **Full-Duplex Interruption**: `src/b12/audio/duplex.py` enables concurrent playback and listening. Interruption time-to-stop is 0.025–0.036 ms.
- **Speaker Verification**: `src/b12/audio/speaker.py` verifies voice embeddings. Exact-replay attacks are blocked; FAR/FRR is 0.0/0.0 on tested sets.

### 5.6 Autonomy & Initiative Loops / Background Daemons
- **Autonomous Scheduler**: `src/b12/autonomy.py` executes due background goals using non-interactive grants (`full_execution=False`). Serialized across instances via `scheduler.lock`.
- **Attention Policy**: `src/b12/attention.py` enforces quiet mode, quiet hours, cooldown intervals, and exponential backoff after ignored initiatives.
- **Idle Reflection**: `src/b12/reflection.py` reviews recent memory clusters every 6 hours to synthesize observations into hypotheses.
- **System Maintenance**: `src/b12/maintenance.py` triggers `malloc_trim(0)` every 300 seconds to prevent heap fragmentation.
- **Long-Horizon Persistence (R17)**: `scripts/daily_check.py` with systemd unit `b12-daily-check.timer`. 7-day checkpoint verified on 2026-11-04 (age 8.091 days).

### 5.7 Embodiment & Robotics Interfaces
- **Motion Controller**: `src/b12/robotics/motion.py` provides a single-writer controller commanding 6 degrees of freedom (`head_yaw`, `head_pitch`, `head_roll`, `body_yaw`, `antenna_left`, `antenna_right`). Validates hard joint bounds and angular velocity limits.
- **Simulator Transport**: `src/b12/robotics/transport.py` implements `SimulatedRobot` for integration testing.
- **Physical Actuator Status**: Physical Reachy Mini or Jetson serial/ROS2 drivers are NOT present in the repository (`NOT_AVAILABLE`).

### 5.8 Multi-Session Journey Support and Persistence
- **Session Continuity**: `src/b12/sessions.py` stores turns and messages atomically with evidence tags. Allows resumption across restarts.
- **Approval Checkpoint Survival**: Turns suspended for approval persist in SQLite and resume cleanly across process restarts.
- **Snapshot Ledger**: `src/b12/service.py` manages filesystem snapshots and replays the deletions ledger upon snapshot restoration.

---

## 6. Preliminary Capability Matrix

| Component | Subsystem | Current Status | Verified Code Location | Notes & Limitations |
|---|---|---|---|---|
| **MemoryStore (SQLite WAL)** | Memory | `TESTED` | `src/b12/memory.py:254` | Cryptographic hash audit chain, `secure_delete=ON`, foreign keys |
| **Ukrainian Morphological FTS** | Memory | `TESTED` | `src/b12/memory.py:210,620` | `pymorphy3` lemma extraction, apostrophe normalization, BM25 rank |
| **Semantic Vector Index** | Memory | `TESTED` (Synth) / `EXPERIMENTAL` (Live) | `src/b12/semantic.py:27` | SQLite vector table + NumPy cosine similarity; uses `scripts/embed_bridge.py` |
| **Chroma / Vector DB** | Memory | `NOT_AVAILABLE` | — | Architectural decision: SQLite used instead of Chroma |
| **Knowledge Retrieval (archive-index)** | Memory | `TESTED` | `src/b12/retrieval.py:23` | Scoped per actor, HMAC path tombstones, hybrid search |
| **Global Multi-Store Purge** | Memory | `TESTED` | `src/b12/purge.py:29` | Cascades through 7 stores with WAL truncate and transitive closure |
| **Agent Cognitive Loop** | Cognitive | `TESTED` | `src/b12/agent.py:449` | Multi-round tool execution, streaming events, cancellation |
| **Persist Mode ("Не зупинятися")** | Cognitive | `TESTED` | `src/b12/agent.py:81` | 150 rounds / 300 calls, unread file coverage tracking |
| **Context Admission & Budgeting** | Cognitive | `TESTED` | `src/b12/context.py:110` | Conservative token headroom budgeting without silent truncation |
| **Model Profile Management** | Cognitive | `TESTED` | `src/b12/model_profile.py:38` | Pinned profile (`bolt-e4b.json`), tokenizer metadata |
| **Cross-Model Swapping** | Cognitive | `IMPLEMENTED` / `EXPERIMENTAL` | `src/b12/model.py:45` | Pinned Bolt tested; multi-model A/B evaluation suite pending |
| **Tool Registry & Dispatch** | Tools | `TESTED` | `src/b12/tools/registry.py:76` | Strict Pydantic schemas, cooperative `EffectGuard` checks |
| **16 Host System Tools** | Tools | `TESTED` | `src/b12/tools/__init__.py:18` | Filesystem, process, network, notes, memory, time |
| **Working Notes (`note_add`)** | Tools | `TESTED` | `src/b12/tools/notes.py:21` | In-turn findings buffer surviving history truncation |
| **MCP Client Protocol** | Tools | `TESTED` | `src/b12/tools/mcp.py:120` | Subprocess stdio JSON-RPC tool integration |
| **ControlStore & Actor Gating** | Safety | `TESTED` | `src/b12/control.py:100` | SQLite actor namespace, capability grants, mode 0600 secrets |
| **Exact Approval Flow** | Safety | `TESTED` | `src/b12/control.py:73,450` | SHA-256 argument digest, suspension and resume for destructive tools |
| **Path Protection Guard** | Safety | `TESTED` | `src/b12/tools/registry.py:31` | Blocks access to state, private keys, and config roots |
| **Network Destination Allowlist** | Safety | `IMPLEMENTED` | `src/b12/tools/registry.py:85` | Configurable allowlist; currently default unrestricted |
| **Host OS Sandbox (jail/container)** | Safety | `NOT_AVAILABLE` (Runtime) / `EXPERIMENTAL` (Eval) | `evals/ollama_broker.py:25` | Production runs as host process; Docker socket broker tested |
| **Adversarial Injection Defense** | Safety | `TESTED` | `evals/cases/adversarial.jsonl` | 9 adversarial scenarios; 40/45 passed on eval v3 |
| **AEC Echo Cancellation** | Audio | `TESTED` | `src/b12/audio/aec.py:45` | 128-tap FIR NLMS, ERLE 30.41 dB |
| **Whisper ASR** | Audio | `TESTED` | `src/b12/audio/asr.py:35` | faster-whisper int8, WER 0.0 on test phrases, P50 2173 ms |
| **Piper TTS Clause Streaming** | Audio | `TESTED` | `src/b12/audio/tts.py:164` | Sentence clause streaming, P50 TTFA 1634 ms |
| **Silero VAD & Endpointing** | Audio | `TESTED` | `src/b12/audio/endpoint.py:40` | ONNX persistent LSTM state, endpoint P50 320 ms |
| **Duplex Conversational Barge-in** | Audio | `TESTED` | `src/b12/audio/duplex.py:65` | Instant speech cutoff (P50 < 0.04 ms) |
| **Speaker Biometrics** | Audio | `TESTED` | `src/b12/audio/speaker.py:50` | Voice enrollment, replay attack rejection |
| **8-Hour Physical Acoustic Soak** | Audio | `NOT_AVAILABLE` | — | Requires physical acoustic room environment |
| **Autonomous Goal Scheduler** | Autonomy | `TESTED` | `src/b12/autonomy.py:42` | Single instance via `scheduler.lock`, non-interactive grants |
| **Attention Policy (Quiet Mode)** | Autonomy | `TESTED` | `src/b12/attention.py:47` | Quiet hours, max 3 initiatives/hour, exponential backoff |
| **Idle Memory Reflection** | Autonomy | `TESTED` | `src/b12/reflection.py:35` | 6-hour cycle hypothesis generation and self-model update |
| **Memory Trim Maintenance Loop** | Autonomy | `TESTED` | `src/b12/maintenance.py:24` | 300s interval `malloc_trim(0)` arena compaction |
| **Long-Horizon Anchor Check (R17)** | Autonomy | `TESTED` | `scripts/daily_check.py:40` | Day-7 checkpoint verified (8.091 days) |
| **MotionController (Single Writer)** | Robotics | `TESTED` | `src/b12/robotics/motion.py:48` | Lease token, hard joint limits, velocity bounds, emergency stop |
| **Simulated Robot Transport** | Robotics | `TESTED` | `src/b12/robotics/transport.py:13` | Linear joint interpolation simulator |
| **Physical ROS2 / Serial Driver** | Robotics | `NOT_AVAILABLE` | — | No rclpy or hardware serial drivers present in repo |
| **SessionStore & Turn Persistence** | Journey | `TESTED` | `src/b12/sessions.py:59` | SQLite turns, checkpoints, evidence tags |
| **Snapshot & Deletion Replay** | Journey | `TESTED` | `src/b12/service.py:71` | SHA-256 manifests, deletions ledger replayed on restore |
| **Multi-Session Cross-Recall** | Journey | `TESTED` | `src/b12/agent.py:386` | Historical fact recall across distinct sessions |
| **Multi-Session Journeys (1–5)** | Journey | `NOT_AVAILABLE` / `EXPERIMENTAL` | — | Multi-day human interaction journey evaluation suite pending |

---

## 7. Automated Test Suite Audit & Findings

Execution of `uv run --no-sync pytest -q` across the test suite yielded:
- **Total Tests Collected**: 656
- **Passed**: 650 (99.1%)
- **Skipped**: 4 (opt-in tests requiring real models or hardware)
- **Failed**: 2 (0.3%)
- **Total Execution Time**: 159.92 seconds (~2m 39s)

### Root-Cause Diagnosis of the 2 Failures:

1. **`tests/e2e/test_cli.py::test_tools_lists_catalog_without_secrets` (Line 166)**:
   - *Error*: `assert (0 == 0 and 16 == 15)`
   - *Root Cause*: Commit `c8aca7d` (`feat(agent): working notes per turn`) introduced `note_add` (`turn.notes` capability), expanding the registered tool count from 15 to 16. The test assertion `len(tools) == 15` was not updated to 16.

2. **`tests/integration/test_tui.py::test_pet_shortcut_preserves_draft_and_control_panel_shortcut_opens_panel` (Line 311)**:
   - *Error*: `assert 49 < 24` (`Input(id='mem-query').region.y == 49`)
   - *Root Cause*: The TUI companion upgrade (merge commit `72a06d6` / `0947f2e`) added companion activity timeline and voice control sections to the slide-out control panel (`#panel`), extending its vertical height. At terminal size 80x24, the memory query input field now renders at y=49 inside the scrollable container rather than y < 24.

Neither failure represents a regression in core logic, security, or cognitive functionality.

---

## 8. Evaluation Architecture Assessment (`evals/`)

The repository includes a benchmark generator and runner in `evals/`:
- `evals/build_cases.py`: Generates corpus v4 with 109 test scenarios across 7 categories:
  - `ua` (20 cases): Ukrainian arithmetic, factual questions, reverse word strings, short explanations.
  - `en` (15 cases): English math, facts, and code-switching prompts.
  - `tools` (43 cases): Multi-step file search, line counting, file editing, command execution.
  - `memory` (14 cases): Fact recall, correction, namespace isolation, consent gating.
  - `behavior` (7 cases): Nuanced persona, refusal of flattery, reasonable disagreement.
  - `adversarial` (9 cases): Indirect prompt injections inside files/docs, privilege escalation, secret exfiltration.
  - `conversation` (1 case): 60-turn long-horizon interaction.
- `evals/runner.py`: Reproducible multi-repeat runner with per-case isolated working directories.
- `evals/scoring.py`: Deterministic scoring rules checking file contents, tool call exclusions, and substring matches.

### Gaps to Address for Comprehensive Capri Evaluation (`evals/capri_comprehensive/`):
To satisfy the R1–R5 evaluation requirements from `ORIGINAL_REQUEST.md`, the current benchmark needs to be expanded into `evals/capri_comprehensive/` with:
1. Structured YAML scenario definitions for Groups A–K (autobiographical memory, long-term continuity, cross-model continuity across Ollama models, complex reasoning, adversarial security, autonomy, voice, fault tolerance, and multi-session journeys).
2. Synthetic isolated fixtures (`fixtures/`) ensuring adversarial experiments never touch real host credentials or user files.
3. Automated runners with statistical confidence intervals and ablation configurations.
