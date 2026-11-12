## 2026-11-10T09:50:10Z

You are Explorer 2 (Scenario Catalog Groups A–E) for Milestone M3 of the Capri Comprehensive Evaluation project.

## Context
Working directory: /home/cyberdid/Projects/B-12
Your state folder: /home/cyberdid/Projects/B-12/.agents/teamwork/explorer_m3_catalog_1
MANDATORY: You MUST read ORIGINAL_REQUEST.md before starting work:
/home/cyberdid/Projects/B-12/.agents/teamwork/ORIGINAL_REQUEST.md
Also read PROJECT.md:
/home/cyberdid/Projects/B-12/.agents/teamwork/orchestrator_gen1/PROJECT.md
And authoritative specification:
/home/cyberdid/Projects/B-12/.agents/teamwork/spec_miner_survey_eval/analysis.md

## Objective
Detail the exact requirements for authoring the 48 scenario YAMLs in Groups A through E:
- Group A: Autobiographical Memory (`MEM-01` .. `MEM-10`, 10 scenarios)
- Group B: Long-Term Continuity (`LT-01` .. `LT-08`, 8 scenarios)
- Group C: Cross-Model Behavioral Continuity (`CM-01` .. `CM-10`, 10 scenarios)
- Group D: Complex Reasoning & Research (`RE-01` .. `RE-08`, 8 scenarios)
- Group E: Security & Adversarial Robustness (`SEC-01` .. `SEC-12`, 12 scenarios)

For EACH of the 48 scenarios:
1. Provide exact scenario ID, title, research hypothesis, taxonomy, severity, execution mode.
2. Specify exact pre-conditions (runtime settings, actors, initial memories/preferences, mock files/services).
3. Specify exact turn-by-turn interactions: actor_id, input prompt (Ukrainian/English as specified), expected behaviors, and forbidden behaviors.
4. Specify ground truth reference answer and evaluation pass criteria.
5. Identify any specific synthetic fixture files needed under `evals/capri_comprehensive/fixtures/` for these groups (e.g., mock documents for RE-01, RE-05, SEC-01, SEC-02, mock SSH keys/tokens for SEC-05, SEC-08).

## Output
Write your comprehensive catalog and implementation blueprint to:
/home/cyberdid/Projects/B-12/.agents/teamwork/explorer_m3_catalog_1/handoff.md
Follow the Handoff Protocol (Observation, Logic Chain, Caveats, Conclusion, Verification Method).
When finished, send a brief message with the handoff path.
