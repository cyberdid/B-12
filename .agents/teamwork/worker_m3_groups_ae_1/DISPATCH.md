## 2026-11-10T10:00:10Z
You are Worker 1 (Scenario Author Groups A–E) for Milestone M3 of the Capri Comprehensive Evaluation project.

## Context & Inputs
Working directory: /home/cyberdid/Projects/B-12
Your state folder: /home/cyberdid/Projects/B-12/.agents/teamwork/worker_m3_groups_ae_1
MANDATORY: You MUST read ORIGINAL_REQUEST.md before starting work:
/home/cyberdid/Projects/B-12/.agents/teamwork/ORIGINAL_REQUEST.md
Also read PROJECT.md:
/home/cyberdid/Projects/B-12/.agents/teamwork/orchestrator_gen1/PROJECT.md

Read Explorer reports:
1. Schema & Canonical Template Guide:
   /home/cyberdid/Projects/B-12/.agents/teamwork/explorer_m3_schema_1/handoff.md
2. Groups A–E Scenario Catalog & Blueprint:
   /home/cyberdid/Projects/B-12/.agents/teamwork/explorer_m3_catalog_1/handoff.md

## Exclusive Write Ownership
You own and write exclusively to:
- `evals/capri_comprehensive/scenarios/group_a_memory/` (MEM-01.yaml .. MEM-10.yaml)
- `evals/capri_comprehensive/scenarios/group_b_continuity/` (LT-01.yaml .. LT-08.yaml)
- `evals/capri_comprehensive/scenarios/group_c_cross_model/` (CM-01.yaml .. CM-10.yaml)
- `evals/capri_comprehensive/scenarios/group_d_reasoning/` (RE-01.yaml .. RE-08.yaml)
- `evals/capri_comprehensive/scenarios/group_e_security/` (SEC-01.yaml .. SEC-12.yaml)
- Fixture files for Groups A–E under `evals/capri_comprehensive/fixtures/`
Do NOT write to groups F–K (they are owned by Worker 2).

## MANDATORY INTEGRITY WARNING
DO NOT CHEAT. All implementations must be genuine. DO NOT hardcode test results, create dummy/facade implementations, or circumvent the intended task. A teamwork_auditor will independently verify your work. Integrity violations WILL be detected and your work WILL be rejected.

## Objectives & Critical Invariants
1. Author all 48 scenario YAML files under their respective group directories:
   - Group A (10 files): `MEM-01.yaml` through `MEM-10.yaml`
   - Group B (8 files): `LT-01.yaml` through `LT-08.yaml`
   - Group C (10 files): `CM-01.yaml` through `CM-10.yaml`
   - Group D (8 files): `RE-01.yaml` through `RE-08.yaml`
   - Group E (12 files): `SEC-01.yaml` through `SEC-12.yaml`
2. Every YAML file MUST strictly adhere to the schema and canonical template from `explorer_m3_schema_1/handoff.md`:
   - All enums in lowercase: `taxonomy` (`deterministic_software`, `real_model_behavioral`, `controlled_experimental`, `physical_acceptance`), `severity` (`critical`, `high`, `medium`, `low`), `execution_mode` (`automated_immediate`, `simulated_time`, `blocked_delay`, `blocked_hardware`).
   - `input:` used in turns (NOT `user:`).
   - `files:` is a dictionary mapping relative paths to content strings.
   - For file omissions: place `type: "file_contains"` under `forbidden_behaviors:` (do NOT use non-existent `file_not_contains`).
   - For memory assertions: use `memory_contains` or `memory_empty` (do NOT use non-existent `state_equals`).
   - For longitudinal delays (`LT-02`), set `execution_mode: "blocked_delay"`, `raw_score: 0.0`.
   - Red-team security tests (`SEC-01..12`) must use disposable sandbox paths and dummy credentials.
3. Seed necessary synthetic fixtures in `evals/capri_comprehensive/fixtures/` for Groups A–E (e.g., sample documents for RE-01, RE-05, SEC-01, dummy ssh keys/secrets).
4. Validation:
   - Run a Python one-liner to parse every single one of your 48 YAML files using `ScenarioDefinition.from_yaml_file()`. All 48 MUST load with zero errors.
   - Run `pytest evals/capri_comprehensive/tests/` to verify zero regressions.

## Output
Write your handoff report to:
/home/cyberdid/Projects/B-12/.agents/teamwork/worker_m3_groups_ae_1/handoff.md
Follow the Handoff Protocol (Observation, Logic Chain, Caveats, Conclusion, Verification Method). Include exact commands run and validation output.
When complete, send a message to the orchestrator.
