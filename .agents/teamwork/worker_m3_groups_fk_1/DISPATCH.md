## 2026-11-10T10:00:10Z
You are Worker 2 (Scenario Author Groups F–K & Fixtures) for Milestone M3 of the Capri Comprehensive Evaluation project.

## Context & Inputs
Working directory: /home/cyberdid/Projects/B-12
Your state folder: /home/cyberdid/Projects/B-12/.agents/teamwork/worker_m3_groups_fk_1
MANDATORY: You MUST read ORIGINAL_REQUEST.md before starting work:
/home/cyberdid/Projects/B-12/.agents/teamwork/ORIGINAL_REQUEST.md
Also read PROJECT.md:
/home/cyberdid/Projects/B-12/.agents/teamwork/orchestrator_gen1/PROJECT.md

Read Explorer reports:
1. Schema & Canonical Template Guide:
   /home/cyberdid/Projects/B-12/.agents/teamwork/explorer_m3_schema_1/handoff.md
2. Groups F–K Scenario Catalog, Zero-Fabrication Rules & Fixtures Blueprint:
   /home/cyberdid/Projects/B-12/.agents/teamwork/explorer_m3_fixtures_1/handoff.md

## Exclusive Write Ownership
You own and write exclusively to:
- `evals/capri_comprehensive/scenarios/group_f_autonomy/` (AUT-01.yaml .. AUT-09.yaml)
- `evals/capri_comprehensive/scenarios/group_g_interaction/` (INT-01.yaml .. INT-08.yaml)
- `evals/capri_comprehensive/scenarios/group_h_voice/` (VOI-01.yaml .. VOI-08.yaml)
- `evals/capri_comprehensive/scenarios/group_i_reliability/` (REL-01.yaml .. REL-08.yaml)
- `evals/capri_comprehensive/scenarios/group_j_robotics/` (ROB-01.yaml .. ROB-06.yaml)
- `evals/capri_comprehensive/scenarios/group_k_journeys/` (JOURNEY-01.yaml .. JOURNEY-05.yaml)
- Fixture files for Groups F–K under `evals/capri_comprehensive/fixtures/`
Do NOT write to groups A–E (they are owned by Worker 1).

## MANDATORY INTEGRITY WARNING
DO NOT CHEAT. All implementations must be genuine. DO NOT hardcode test results, create dummy/facade implementations, or circumvent the intended task. A teamwork_auditor will independently verify your work. Integrity violations WILL be detected and your work WILL be rejected.

## Objectives & Critical Invariants
1. Author all 44 scenario YAML files under their respective group directories:
   - Group F (9 files): `AUT-01.yaml` through `AUT-09.yaml`
   - Group G (8 files): `INT-01.yaml` through `INT-08.yaml`
   - Group H (8 files): `VOI-01.yaml` through `VOI-08.yaml`
   - Group I (8 files): `REL-01.yaml` through `REL-08.yaml`
   - Group J (6 files): `ROB-01.yaml` through `ROB-06.yaml`
   - Group K (5 files): `JOURNEY-01.yaml` through `JOURNEY-05.yaml`
2. Every YAML file MUST strictly adhere to the schema and canonical template from `explorer_m3_schema_1/handoff.md`:
   - All enums in lowercase: `taxonomy` (`deterministic_software`, `real_model_behavioral`, `controlled_experimental`, `physical_acceptance`), `severity` (`critical`, `high`, `medium`, `low`), `execution_mode` (`automated_immediate`, `simulated_time`, `blocked_delay`, `blocked_hardware`).
   - `input:` used in turns (NOT `user:`).
   - `files:` is a dictionary mapping relative paths to content strings.
   - For file omissions: place `type: "file_contains"` under `forbidden_behaviors:` (do NOT use non-existent `file_not_contains`).
   - For memory assertions: use `memory_contains` or `memory_empty` (do NOT use non-existent `state_equals`).
   - Zero-Fabrication Invariant: Group J robotics scenarios (`ROB-01..06`) must specify `execution_mode: "blocked_hardware"`, `hardware_prereq: "reachy_actuator_bus"`.
   - Voice physical audio scenarios without live mic/rig must set `execution_mode: "blocked_hardware"` or `simulated_time` where audio mock telemetry exists.
3. Seed necessary synthetic fixtures in `evals/capri_comprehensive/fixtures/` for Groups F–K (mock sensor logs, audio mock telemetry, sqlite test databases).
4. Validation:
   - Run a Python one-liner to parse every single one of your 44 YAML files using `ScenarioDefinition.from_yaml_file()`. All 44 MUST load with zero errors.
   - Run `pytest evals/capri_comprehensive/tests/` to verify zero regressions.

## Output
Write your handoff report to:
/home/cyberdid/Projects/B-12/.agents/teamwork/worker_m3_groups_fk_1/handoff.md
Follow the Handoff Protocol (Observation, Logic Chain, Caveats, Conclusion, Verification Method). Include exact commands run and validation output.
When complete, send a message to the orchestrator.
