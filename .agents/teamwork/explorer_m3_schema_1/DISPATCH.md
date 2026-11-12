# Dispatch: Explorer M3 Schema

Target: Investigate schema.py, runner.py, deterministic.py, and validate exact schema for all 92 scenario YAMLs.
Deliverable: handoff.md in /home/cyberdid/Projects/B-12/.agents/teamwork/explorer_m3_schema_1/


## 2026-11-10T09:50:10Z

You are Explorer 1 (Schema & Runner Architecture) for Milestone M3 of the Capri Comprehensive Evaluation project.

## Context
Working directory: /home/cyberdid/Projects/B-12
Your state folder: /home/cyberdid/Projects/B-12/.agents/teamwork/explorer_m3_schema_1
MANDATORY: You MUST read ORIGINAL_REQUEST.md before starting work:
/home/cyberdid/Projects/B-12/.agents/teamwork/ORIGINAL_REQUEST.md
Also read PROJECT.md:
/home/cyberdid/Projects/B-12/.agents/teamwork/orchestrator_gen1/PROJECT.md
And reference specification:
/home/cyberdid/Projects/B-12/.agents/teamwork/spec_miner_survey_eval/analysis.md

## Objective
Investigate the scenario schema implementation and runner loading requirements:
1. Read `evals/capri_comprehensive/evaluators/schema.py`, `evals/capri_comprehensive/runners/runner.py`, and `evals/capri_comprehensive/evaluators/deterministic.py`.
2. Document every required and optional field of `ScenarioDefinition`, `InteractionTurn`, `ExpectedBehavior`, `ForbiddenBehavior`, `GroundTruth`, and `EvaluationConfig`.
3. Note all exact enum values for `ScientificTaxonomy`, `ScenarioSeverity`, `ExecutionStatus`, and behavior `type` (e.g. `content_contains`, `content_not_contains`, `tool_called`, `tool_not_called`, `script_cyrillic`, `state_equals`, `file_contains`, `file_not_contains`).
4. Identify any discrepancies between the example YAML in `spec_miner_survey_eval/analysis.md` and `schema.py` (e.g., field names, enum capitalization or casing, pre_condition structures).
5. Provide a pristine, fully verified canonical template YAML and a checklist that the Worker must adhere to when authoring the 92 scenario YAMLs.

## Output
Write your complete findings and instructions to:
/home/cyberdid/Projects/B-12/.agents/teamwork/explorer_m3_schema_1/handoff.md
Follow the Handoff Protocol (Observation, Logic Chain, Caveats, Conclusion, Verification Method).
When finished, send a brief message with the handoff path.
