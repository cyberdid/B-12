# Handoff Report: Evaluation Framework & Scenario Taxonomy Specification

**Agent:** Explorer 3 (Spec Miner: Evaluation Framework & Scenario Taxonomy)  
**State Folder:** `/home/cyberdid/Projects/B-12/.agents/teamwork/spec_miner_survey_eval/`  
**Output Analysis:** `/home/cyberdid/Projects/B-12/.agents/teamwork/spec_miner_survey_eval/analysis.md`  
**Parent Agent:** `f7064ab7-5ff4-4a09-bb25-95e84e62ebcd`  
**Timestamp:** 2026-11-10T08:42:00Z  
**Type:** Hard Handoff (Task Complete)

---

## 1. Observation

1. **User Request & Requirements (`.agents/teamwork/ORIGINAL_REQUEST.md`)**:
   Lines 10–45 specify requirements R1 (Audit), R2 (Reproducible Architecture in `evals/capri_comprehensive/`), R3 (Comprehensive Execution across Groups A–K), R4 (Isolated Sandboxing & Safety Constraints), and R5 (Ablations, Statistical Analysis & Deliverables: 5 reports, CSV matrix, RQ1–RQ10).
2. **Group and Scenario Scope**:
   Lines 19–30 of `ORIGINAL_REQUEST.md` designate the 11 scenario groups:
   - Group A: Autobiographical Memory (`MEM-01..10`, 10 scenarios)
   - Group B: Long-Term Continuity (`LT-01..08`, 8 scenarios)
   - Group C: Cross-Model Continuity (`CM-01..10`, 10 scenarios)
   - Group D: Complex Reasoning & Research (`RE-01..08`, 8 scenarios)
   - Group E: Security & Adversarial Robustness (`SEC-01..12`, 12 scenarios)
   - Group F: Autonomy & Initiative (`AUT-01..09`, 9 scenarios)
   - Group G: Human–AI Interaction (`INT-01..08`, 8 scenarios)
   - Group H: Voice & Real-Time Interaction (`VOI-01..08`, 8 scenarios)
   - Group I: Reliability & Fault Tolerance (`REL-01..08`, 8 scenarios)
   - Group J: Embodiment & Robotics (`ROB-01..06`, 6 scenarios)
   - Group K: Multi-Session Journeys (`Journeys 1–5`, 5 multi-phase compound scenarios)
   Total scenario inventory = **92 distinct scenarios**.
3. **Existing Evaluation Infrastructure (`evals/`)**:
   - `evals/cases/*.jsonl` contains 109 legacy cases across 7 categories (ua, en, tools, memory, behavior, adversarial, conversation).
   - `evals/runner.py` and `evals/scoring.py` implement deterministic rule evaluation (`contains`, `tool_called`, `script`, `file_equals`, `memory_empty`) and sandboxing with per-run directories.
   - `evals/ollama_broker.py` implements a private Unix domain socket broker (mode 0600) restricting Ollama to pinned-model calls without host network exposure.
4. **Architectural Invariants & Companion Requirements (`raw/B-12_Master_Project_2026-10-24.md` & `wiki/topics/`)**:
   - `raw/B-12_Master_Project_2026-10-24.md` §5.2 enumerates cognitive memory tiers (working, episodic, semantic, autobiographical, procedural, social, research, self-model).
   - Invariants from `AGENTS.md`: local-first; swappable model; non-blocking motion/audio; single writer to actuators; deterministic permission control path; memory provenance tracking; zero secret leakage.
   - Voice SLOs (`wiki/topics/evals.md`): Warm TTFT $\le 1.0$s (P50 $\approx 0.78$s measured on Bolt E4B), cold TTFT $\approx 10$s.

---

## 2. Logic Chain

1. **Step 1 (Decomposition):** From Observation 1, the user's objective is to determine whether Capri acts as a genuine autonomous, persistent AI companion rather than an ephemeral tool-calling LLM wrapper. To evaluate this objectively, the 5 core requirements (R1–R5) were deconstructed into an operational engineering and scientific testing protocol.
2. **Step 2 (Scenario Enumeration):** From Observation 2, every designated ID across Groups A–K (totaling 92 scenarios) was mapped to a concrete research hypothesis, input interaction sequences, expected behaviors, forbidden behaviors, ground truth evidence requirements, target subsystems, taxonomy classification, and severity ratings.
3. **Step 3 (Schema Standardization):** From Observation 3 and R2, a unified YAML schema was specified for all scenario definitions, incorporating pre-conditions (runtime settings, initial actors, memories, files), interaction turns, multi-rule assertions, performance criteria (max TTFT), and evaluation methods.
4. **Step 4 (Scientific Taxonomy & Integrity):** From Observation 2 and R3, tests were partitioned into four categories:
   - *Deterministic Software Tests* (binary evaluation, zero LLM)
   - *Real-Model Behavioral Tests* (tested against local Ollama models via broker, evaluated by external deterministic rules or independent judge)
   - *Controlled Experimental Tests* (multi-trial parameter variations with statistical confidence intervals)
   - *Physical Acceptance Tests* (actuators, microphone/speaker rigs, multi-day wall clock delays)
   A state machine was instituted establishing the **Zero-Fabrication Principle**: any test requiring missing hardware (Reachy arms) or multi-day delays (7/30 days) is strictly marked `BLOCKED_HARDWARE` or `BLOCKED_DELAY / PENDING`, with zero fabricated passes.
5. **Step 5 (Statistical & Ablation Protocol):** From R5, single aggregate pass rates were replaced with Wilson score intervals for binomial metrics and bootstrap percentiles for latencies. Five systematic ablation experiments were designed (Memory ON/OFF/Raw, Context Scaling, Deterministic vs Prompt Gating, Tool Bounds, Model Swapping).
6. **Step 6 (Deliverables Mapping):** The five required report deliverables and 15-column CSV scenario matrix layout were formally defined to structure downstream report generation.

---

## 3. Caveats

1. **Physical Hardware Availability:** Reachy robotic arm hardware and specialized binaural acoustic fixtures are currently absent on the host environment; all physical tests in Group J (ROB-01..06) and physical voice tests in Group H (VOI-04..08) must be executed either via software mocks/emulators or marked `BLOCKED_HARDWARE` in accordance with the Zero-Fabrication rule.
2. **Real-Time Multi-Day Delays:** Real-time 7-day and 30-day temporal persistence in Group B (LT-02) and Group K (Journey 4) cannot be run instantaneously; they require a dual-track strategy: automated simulated time-warp tests (mock timestamps in SQLite ledger) and a long-term protocol document (`CAPRI_LONG_TERM_PROTOCOL.md`) for real-time tracking.
3. **Model Availability Dependency:** Group C (CM-01..10) assumes availability of models audited by Explorer 1 (`explorer_survey_env`). If certain model weights are not loaded locally in Ollama, those specific model permutations will be marked `NOT_AVAILABLE`.

---

## 4. Conclusion

The specification mining and scenario taxonomy mapping for the Capri comprehensive evaluation suite is complete. All 92 scenarios, requirements R1–R5, acceptance criteria, YAML schema, four-tier taxonomy, statistical protocols, RQ1–RQ10 framework, and 5 report deliverables are comprehensively specified in:
`/home/cyberdid/Projects/B-12/.agents/teamwork/spec_miner_survey_eval/analysis.md`

This document provides the authoritative blueprint for:
1. Constructing the target evaluation framework in `evals/capri_comprehensive/`.
2. Implementing the 92 YAML scenario files.
3. Conducting statistical execution, ablations, and generating all 5 required reports.

---

## 5. Verification Method

1. **Document Inspection:**
   Verify presence and comprehensive structure of `analysis.md`:
   ```bash
   test -f /home/cyberdid/Projects/B-12/.agents/teamwork/spec_miner_survey_eval/analysis.md
   wc -l /home/cyberdid/Projects/B-12/.agents/teamwork/spec_miner_survey_eval/analysis.md
   ```
2. **Scenario Count & Group Coverage Verification:**
   Verify that all 92 scenarios and 11 groups are defined:
   ```bash
   grep -E "^\| \*\*(MEM|LT|CM|RE|SEC|AUT|INT|VOI|REL|ROB)-[0-9]{2}\*\*|Journey [1-5]" /home/cyberdid/Projects/B-12/.agents/teamwork/spec_miner_survey_eval/analysis.md | wc -l
   # Expected count: 92
   ```
3. **Research Questions Verification:**
   Verify all ten research questions (RQ1–RQ10) are formally detailed:
   ```bash
   grep -E "\*\*RQ[0-9]{1,2}\*\*" /home/cyberdid/Projects/B-12/.agents/teamwork/spec_miner_survey_eval/analysis.md
   ```
4. **Deliverables Specification Verification:**
   Verify that all 5 report deliverables and CSV matrix schema are defined:
   ```bash
   grep -E "CAPRI_COMPREHENSIVE_EVALUATION|CAPRI_SCENARIO_MATRIX|CAPRI_MODEL_CONTINUITY|CAPRI_SECURITY_EVALUATION|CAPRI_LONG_TERM_PROTOCOL" /home/cyberdid/Projects/B-12/.agents/teamwork/spec_miner_survey_eval/analysis.md
   ```
