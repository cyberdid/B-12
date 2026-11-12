# Project: B-12 / Capri Comprehensive Evaluation

## Architecture

The B-12 / Capri Comprehensive Evaluation Framework (`evals/capri_comprehensive/`) evaluates whether Capri functions as a genuine persistent, adaptable, reliable AI companion rather than a stateless LLM wrapper.

```
evals/capri_comprehensive/
├── README.md                      # Framework documentation, usage, and quickstart
├── methodology.md                 # Scientific methodology, taxonomy, statistical protocols
├── scenarios/                     # Structured YAML scenario definitions (92 scenarios)
│   ├── group_a_memory/            # MEM-01 .. MEM-10 (Autobiographical memory)
│   ├── group_b_continuity/        # LT-01 .. LT-08 (Long-term continuity & retention)
│   ├── group_c_cross_model/       # CM-01 .. CM-10 (Cross-model behavioral invariance)
│   ├── group_d_reasoning/         # RE-01 .. RE-08 (Complex reasoning & research)
│   ├── group_e_security/          # SEC-01 .. SEC-12 (Adversarial robustness & sandboxing)
│   ├── group_f_autonomy/          # AUT-01 .. AUT-09 (Autonomy & initiative loops)
│   ├── group_g_interaction/       # INT-01 .. INT-08 (Human–AI interaction & empathy)
│   ├── group_h_voice/             # VOI-01 .. VOI-08 (Voice & real-time interaction)
│   ├── group_i_reliability/       # REL-01 .. REL-08 (Reliability & fault tolerance)
│   ├── group_j_robotics/          # ROB-01 .. ROB-06 (Embodiment & robotics protocols)
│   └── group_k_journeys/          # Journey 1 .. 5 (Multi-session compound journeys)
├── fixtures/                      # Isolated synthetic environments, documents, mocks
├── evaluators/                    # Evaluation logic: deterministic, heuristic, model judge
│   ├── deterministic.py           # Substring, regex, tool call, memory state assertions
│   ├── judge.py                   # External model judge (never self-evaluating)
│   └── sandboxed_env.py           # Synthetic disposable jail/working directory manager
├── runners/                       # Test runners & execution engines
│   ├── runner.py                  # CLI runner executing scenario YAMLs with repetitions
│   ├── suite_runner.py            # Batch execution orchestrator across all groups
│   └── ablation_runner.py         # Systematic ablation orchestrator (5 ablation designs)
├── statistical_analysis/          # Statistical computation tools
│   ├── metrics.py                 # Wilson score intervals, bootstrap percentiles
│   └── aggregator.py              # Aggregates raw outputs into CSV matrix and tables
├── artifacts/                     # Raw execution logs, JSON outputs, traces
└── reports/                       # Generated formal deliverables
    ├── CAPRI_COMPREHENSIVE_EVALUATION.md
    ├── CAPRI_SCENARIO_MATRIX.csv
    ├── CAPRI_MODEL_CONTINUITY.md
    ├── CAPRI_SECURITY_EVALUATION.md
    └── CAPRI_LONG_TERM_PROTOCOL.md
```

## Feature Inventory

| # | Feature / Group | Description | Milestone | Source |
|---|---|---|---|---|
| 1 | R1: Environment & Runtime Audit | Git SHA, hardware specs, Ollama models, test suite audit | M1 | Survey |
| 2 | R1: Capability Matrix | Subsystem classification (IMPLEMENTED/TESTED/EXPERIMENTAL/NOT_AVAILABLE) | M1 | Survey |
| 3 | R2: Evaluation Engine Core | YAML loader, schema validator, execution dispatcher | M2 | R2 |
| 4 | R2: Deterministic Evaluators | Assertions on tool calls, memory state, file outputs, text | M2 | R2 |
| 5 | R2: Sandbox Manager | Disposable directory isolation, mock services, safe red-teaming | M2 | R4 |
| 6 | R2: Statistical Analysis Tools | Wilson score CI, bootstrap percentiles, ablations aggregator | M2 | R5 |
| 7 | Group A: Autobiographical Memory | MEM-01..10: Core facts, corrections, provenance, encryption | M3 | R3 |
| 8 | Group B: Long-Term Continuity | LT-01..08: Session resumption, 7/30d retention, purge cascade | M3 | R3 |
| 9 | Group C: Cross-Model Continuity | CM-01..10: bolt-e4b vs gemma4:12b vs qwen3.5:27b invariance | M3 | R3 |
| 10 | Group D: Complex Reasoning | RE-01..08: Persist mode, note_add, multi-file synthesis | M3 | R3 |
| 11 | Group E: Security & Adversarial | SEC-01..12: Indirect injection, exfiltration, approval bypass | M3 | R3 |
| 12 | Group F: Autonomy & Initiative | AUT-01..09: Quiet hours, backoff, idle reflection, goals | M3 | R3 |
| 13 | Group G: Human–AI Interaction | INT-01..08: Persona consistency, refusal of flattery, ethics | M3 | R3 |
| 14 | Group H: Voice & Real-Time | VOI-01..08: Barge-in (<40ms), AEC, VAD, ASR WER, TTS TTFA | M3 | R3 |
| 15 | Group I: Reliability & Faults | REL-01..08: Model timeouts, crash recovery, malformed output | M3 | R3 |
| 16 | Group J: Embodiment & Robotics | ROB-01..06: Single writer lease, joint limits, emergency stop | M3 | R3 |
| 17 | Group K: Multi-Session Journeys | Journeys 1–5: Multi-day onboarding, research, recovery arcs | M3 | R3 |
| 18 | R3: Automated Test Execution | Execute deterministic & real-model tests via local Ollama | M4 | R3 |
| 19 | R3: Blocked & Pending Handling | Protocol for missing hardware (ROB) & time delays (7/30d) | M4 | R3 |
| 20 | R5: Systematic Ablation Studies | 5 Ablations: Memory, Context, Tools, Gating, Model Swap | M4 | R5 |
| 21 | R5: Deliverable Report 1 | CAPRI_COMPREHENSIVE_EVALUATION.md (RQ1-10, verdict) | M5 | R5 |
| 22 | R5: Deliverable Report 2 | CAPRI_SCENARIO_MATRIX.csv (92 rows x 15 columns) | M5 | R5 |
| 23 | R5: Deliverable Report 3 | CAPRI_MODEL_CONTINUITY.md (Cross-model analysis) | M5 | R5 |
| 24 | R5: Deliverable Report 4 | CAPRI_SECURITY_EVALUATION.md (Adversarial red-team audit) | M5 | R5 |
| 25 | R5: Deliverable Report 5 | CAPRI_LONG_TERM_PROTOCOL.md (Day 7 / Day 30 protocol) | M5 | R5 |
| 26 | R5: Raw Execution Artifacts | JSON logs, metrics summaries, verification traces | M5 | R5 |

## Milestones

| # | Name | Scope | Dependencies | Status |
|---|------|-------|-------------|--------|
| M1 | Survey & Audit | Complete environment, hardware, model runtime, and test suite audit | None | DONE |
| M2 | Framework & Engine Architecture | Build `evals/capri_comprehensive/` structure, schema, evaluators, runner, stats | M1 | DONE |
| M3 | Scenario Definitions (Groups A–K) | Author all 92 scenario YAMLs, synthetic fixtures, test vectors | M2 | DONE |
| M4 | Execution, Ablations & Stats | Run automated suite, execute 5 ablations, record blocked/pending | M3 | DONE |
| M5 | Reports & Deliverables | Produce 5 formal reports, 15-column CSV, RQ1–RQ10 synthesis | M4 | DONE |

## Interface Contracts

### Scenario Definition (YAML) ↔ Evaluation Runner
- **Schema**: Validated against Pydantic model `ScenarioDefinition`
- **Fields**:
  - `id`: String `[A-Z]{3}-[0-9]{2}` or `JOURNEY-[0-9]{2}`
  - `name`: Human readable title
  - `group`: Enumeration `[A-K]`
  - `taxonomy`: `DETERMINISTIC_SOFTWARE` | `REAL_MODEL_BEHAVIORAL` | `CONTROLLED_EXPERIMENTAL` | `PHYSICAL_ACCEPTANCE`
  - `severity`: `CRITICAL` | `HIGH` | `MEDIUM` | `LOW`
  - `research_hypothesis`: String statement of companion hypothesis
  - `pre_conditions`: Dictionary (runtime config, initial memories, actor grants, disposable files)
  - `interactions`: List of turns `[{user: str, expected_tools: [...], forbidden_tools: [...], expected_patterns: [...], forbidden_patterns: [...]}]`
  - `evaluation`: Multi-rule assertion dictionary (rules, thresholds, timeouts)
  - `ground_truth`: Authoritative reference or expected state

### Runner ↔ Statistical Analysis Engine
- **Input**: Raw execution JSON results per scenario run (status, latencies, tokens, tool_calls, passed_assertions, failed_assertions)
- **Output**:
  - Binomial metric intervals: Wilson score confidence intervals at 95% confidence level
  - Latency metrics: Bootstrap 95% confidence intervals for P50, P90, P95
  - Aggregated rows matching the 15-column CSV matrix schema:
    `Scenario_ID,Group,Name,Taxonomy,Severity,Target_Subsystem,Hypothesis,Execution_Status,Raw_Score,CI_95_Low,CI_95_High,P50_Latency_ms,P95_Latency_ms,Ablation_Sensitivity,Failure_Reason`

### Red-Team Security Evaluator ↔ Host Sandbox Isolation
- **Constraint**: Isolated mock environment (`tmp_path`)
- **Isolation Invariant**: Zero access to `~/.ssh`, `~/.local/state/b12/secrets`, systemd services, or network outside local mock loopback.

## Code Layout

- Implementation Target: `/home/cyberdid/Projects/B-12/evals/capri_comprehensive/`
- Core Runtime Target: `/home/cyberdid/Projects/B-12/src/b12/` (Read-only for evaluation)
- Deliverables Target: `/home/cyberdid/Projects/B-12/evals/capri_comprehensive/reports/`
- Artifacts Target: `/home/cyberdid/Projects/B-12/evals/capri_comprehensive/artifacts/`
