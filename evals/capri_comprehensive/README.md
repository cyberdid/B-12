# Capri Comprehensive Evaluation Framework (`evals/capri_comprehensive`)

The **Capri Comprehensive Evaluation Framework** is a modular, reproducible, and statistically rigorous evaluation engine designed to evaluate the **B-12 / Capri AI Companion**. Its central research objective is to empirically determine whether Capri acts as a genuine autonomous, persistent, and adaptable AI companion or an ephemeral tool-calling language model.

---

## 1. Directory Structure

```text
evals/capri_comprehensive/
├── README.md                      # Framework architecture, setup, and usage CLI guide
├── methodology.md                 # 4-tier taxonomy, zero-fabrication rules, Wilson CIs, RQ1-RQ10
├── fixtures/                      # Isolated synthetic documents, fake credentials, mock databases
│   ├── documents/                 # Synthetic documents for retrieval and injection tests
│   ├── fake_credentials/          # Mock SSH keys and disposable API tokens
│   └── mock_databases/            # Pre-seeded SQLite ledgers and actor profiles
├── scenarios/                     # Structured YAML definitions (92 scenarios across 11 groups)
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
│   └── group_k_journeys/          # Journey-01 .. Journey-05 (Multi-session compound journeys)
├── evaluators/                    # Core evaluation modules
│   ├── schema.py                  # Pydantic V2 models for Scenario YAML and execution reports
│   ├── deterministic.py           # Substring, regex, tool call, memory, and exit code rules
│   ├── sandboxed_env.py           # Ephemeral sandbox directory manager with host secrets guard
│   └── judge.py                   # Independent LLM judge harness (no self-evaluation)
├── runners/                       # Execution orchestrators
│   ├── runner.py                  # Single scenario runner with latency and token telemetry
│   ├── suite_runner.py            # Batch scenario runner across groups (parallel/sequential, JUnit XML)
│   └── ablation_runner.py         # 5-dimension ablation orchestrator (Memory, Context, Gating, Tools, Model)
├── statistical_analysis/          # Statistical measurement engines
│   ├── metrics.py                 # Wilson score binomial CIs and bootstrap latency percentiles
│   └── aggregator.py              # Aggregates execution reports into 15-column CSV & Markdown
├── reports/                       # Formal deliverables and evaluation matrices
│   ├── CAPRI_COMPREHENSIVE_EVALUATION.md
│   ├── CAPRI_SCENARIO_MATRIX.csv
│   ├── CAPRI_MODEL_CONTINUITY.md
│   ├── CAPRI_SECURITY_EVALUATION.md
│   └── CAPRI_LONG_TERM_PROTOCOL.md
├── artifacts/                     # Raw execution traces (turn_trace.jsonl, latencies.json)
└── tests/                         # Framework verification suite
```

---

## 2. Quickstart & CLI Usage

### 2.1 Run a Single Scenario

To execute a single scenario YAML specification:

```bash
uv run python -m evals.capri_comprehensive.runners.runner \
    evals/capri_comprehensive/scenarios/group_a_memory/MEM-01.yaml
```

Output:
```text
Scenario: MEM-01 [EXECUTED_PASS]
Duration: 120.5ms (Turns: 1)
  Turn 0: PASS | 120.5ms
```

### 2.2 Run the Evaluation Suite (Batch Execution)

Run all scenarios across all groups or filter by specific groups:

```bash
# Run all discovered scenarios
uv run python -m evals.capri_comprehensive.runners.suite_runner \
    --junit evals/capri_comprehensive/reports/junit_report.xml \
    --json evals/capri_comprehensive/reports/suite_results.json

# Run only Memory and Security groups in parallel with 4 workers
uv run python -m evals.capri_comprehensive.runners.suite_runner \
    --group group_a_memory \
    --group group_e_security \
    --parallel --workers 4
```

### 2.3 Run Systematic Ablation Studies

Execute scenarios under controlled ablation dimensions:

```bash
# Run all 5 ablation dimensions on a scenario
uv run python -m evals.capri_comprehensive.runners.ablation_runner \
    evals/capri_comprehensive/scenarios/group_a_memory/MEM-01.yaml

# Run a specific dimension (e.g. Memory: FULL vs RAW vs OFF)
uv run python -m evals.capri_comprehensive.runners.ablation_runner \
    evals/capri_comprehensive/scenarios/group_a_memory/MEM-01.yaml \
    --dimension A1_MEMORY
```

### 2.4 Aggregate Reports into CSV Matrix and Markdown Summary

To aggregate individual scenario execution artifacts into the mandatory 15-column CSV scenario matrix:

```bash
uv run python -c "
from evals.capri_comprehensive.runners.suite_runner import SuiteRunner
from evals.capri_comprehensive.statistical_analysis.aggregator import EvaluationAggregator

suite = SuiteRunner()
reports = suite.run_suite()
agg = EvaluationAggregator(reports)
agg.write_scenario_matrix_csv('evals/capri_comprehensive/reports/CAPRI_SCENARIO_MATRIX.csv')
agg.generate_markdown_summary('evals/capri_comprehensive/reports/CAPRI_COMPREHENSIVE_EVALUATION.md')
"
```

---

## 3. Scientific Invariants & Zero-Fabrication Mandate

1. **Zero-Fabrication Principle:**
   - Tests requiring physical robotics actuators (Reachy) or hardware transducers are recorded as `BLOCKED_HARDWARE` with explicit hardware requirements noted.
   - Tests requiring longitudinal temporal delays (7-day, 30-day) are recorded as `BLOCKED_DELAY` or `PENDING` (with simulated time-warp variants reported separately).
   - Under no circumstances is an unexecuted test marked as `PASS`.
2. **Independent Model Judge Invariant:**
   - The evaluated model is strictly forbidden from acting as its own evaluator (`judge.py`).
   - If `b12-bolt-e4b:q4km` is evaluated, an independent model (e.g. `gemma4:12b` or `qwen3.5:27b`) or deterministic rules must serve as the judge.
3. **Sandbox Isolation Invariant:**
   - All tests execute in disposable temp directories (`SandboxedEnvironment`).
   - Host secrets (`~/.ssh`, `~/.gnupg`, `~/.local/state/b12/secrets`) are strictly forbidden from read or write access (`is_path_safe`).
4. **Statistical Rigor:**
   - Binomial pass rates include Wilson score 95% confidence intervals.
   - Latencies (P50, P90, P95) include non-parametric bootstrap confidence intervals (1,000 resamples).
