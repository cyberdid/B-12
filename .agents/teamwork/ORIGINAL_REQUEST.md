# Original User Request

## Initial Request — 2026-11-10T08:32:12Z

Act as a multidisciplinary research and engineering evaluation team (Senior AI Agent Systems Researcher, Cognitive Architecture Researcher, LLM Evaluation Scientist, Memory Systems Engineer, AI Safety and Security Researcher, Reliability and Fault-Tolerance Engineer, Statistical Experimental Design Specialist, Human–AI Interaction Researcher, Robotics and Embodied AI Engineer) to design, implement, execute, and critically analyze a comprehensive experimental evaluation of the B-12 / Capri AI companion. The objective is to determine whether Capri behaves as a reliable, persistent, adaptable AI companion rather than merely a language model connected to tools and a database.

Working directory: /home/cyberdid/Projects/B-12
Integrity mode: development

## Requirements

### R1. Environment and Repository Audit
Inspect and document the current repository state, Git commit SHA, active branch, dirty working tree state, hardware environment (CPU, GPU, VRAM, RAM), local LLM runtime (Ollama version, installed models, quantization, context profiles), and test dependencies, compiling an initial capability matrix (IMPLEMENTED / TESTED / EXPERIMENTAL / NOT_AVAILABLE).

### R2. Reproducible Experimental Architecture in evals/capri_comprehensive/
Construct a modular evaluation framework in `evals/capri_comprehensive/` with structured scenario definitions (YAML), synthetic fixtures in `fixtures/`, evaluators in `evaluators/`, runners in `runners/`, statistical analysis tools in `statistical_analysis/`, reports in `reports/`, and artifacts in `artifacts/`. Every scenario must specify unique ID, research hypothesis, initial state, interactions, expected/forbidden behaviors, ground-truth, evaluation method, severity, success/failure criteria, and required artifacts.

### R3. Comprehensive Experiment Implementation & Execution
Implement and execute the evaluation suite across the defined experiment groups:
- Group A: Autobiographical Memory (MEM-01..10)
- Group B: Long-Term Continuity (LT-01..08)
- Group C: Cross-Model Behavioral Continuity (CM-01..10) using models discovered during the local Ollama/vLLM audit
- Group D: Complex Reasoning & Research (RE-01..08)
- Group E: Security & Adversarial Robustness (SEC-01..12)
- Group F: Autonomy & Initiative (AUT-01..09)
- Group G: Human–AI Interaction (INT-01..08)
- Group H: Voice & Real-Time Interaction (VOI-01..08)
- Group I: Reliability & Fault Tolerance (REL-01..08)
- Group J: Embodiment & Robotics (ROB-01..06)
- Group K: Multi-Session Journeys (Journeys 1–5)
Separate results into deterministic software tests, real-model behavioral tests, controlled experimental tests, and physical acceptance tests. Execute all immediately runnable automated tests; mark tests requiring real-time delays (Day 7/Day 30) or missing physical hardware as BLOCKED or PENDING without fabricating passes.

### R4. Isolated Sandbox and Safety Constraints
All destructive, privileged, adversarial, and network-related experiments must run in isolated environments using synthetic data, disposable test directories, fake credentials, and local mock services. Never run red-team tests against real owner secrets, SSH keys, personal files, or production databases. Do not grant production host access to adversarial test agents. Do not modify production data, delete user files, or alter system services. Do not push commits or create a PR.

### R5. Ablations, Statistical Analysis & Deliverables
Execute systematic ablations, compute statistical metrics with confidence intervals (avoiding single aggregate scores that conceal failures), and produce:
1. `reports/CAPRI_COMPREHENSIVE_EVALUATION.md`
2. `reports/CAPRI_SCENARIO_MATRIX.csv`
3. `reports/CAPRI_MODEL_CONTINUITY.md`
4. `reports/CAPRI_SECURITY_EVALUATION.md`
5. `reports/CAPRI_LONG_TERM_PROTOCOL.md`
6. Raw execution artifacts and visualizations
Answer research questions RQ1–RQ10 and provide the mandatory technical classification judgment on Capri's operational status.

## Acceptance Criteria

### Audit & Capability Assessment
- [ ] Audit report records exact commit SHA, active branch, environment hardware specs, Ollama version, and model profiles.
- [ ] Capability matrix clearly categorizes all major subsystems (memory, tools, voice, autonomy, robotics) as IMPLEMENTED, TESTED, EXPERIMENTAL, or NOT_AVAILABLE.

### Framework Structure
- [ ] Directory `evals/capri_comprehensive/` contains README.md, methodology.md, scenarios/ (YAML files for Groups A–K), fixtures/, evaluators/, runners/, and reports/.
- [ ] Every scenario YAML defines unique ID, hypothesis, pre-conditions, interaction sequence, expected/forbidden behaviors, and objective success/failure criteria.

### Scientific & Experimental Integrity
- [ ] Results strictly distinguish between deterministic unit/integration tests, real LLM behavioral tests, controlled experiments, and physical acceptance tests.
- [ ] Tests that cannot run due to missing hardware or real-time delays are explicitly recorded as BLOCKED, PENDING, or NOT_EXECUTED with zero fabricated passes.
- [ ] Real-model evaluation does not use the evaluated model as sole self-judge.

### Safety & Sandboxing
- [ ] Adversarial prompt injection, exfiltration, and tool abuse experiments run entirely within synthetic disposable sandboxes.
- [ ] Host secrets, SSH keys, personal files, and network services outside local mock sinks remain untouched.

### Reports & Deliverables
- [ ] All 5 required report documents and CSV scenario matrix are generated with inspectable evidence and statistical confidence intervals.
- [ ] Formal answers to RQ1–RQ10 and definitive technical judgment on Capri's operational status are documented.
