# Dispatch: Explorer M3 Catalog (Groups F–K) & Fixtures

Target: Investigate Groups F through K scenario specifications, interactions, pre-conditions, assertions, and synthetic fixtures.
Deliverable: handoff.md in /home/cyberdid/Projects/B-12/.agents/teamwork/explorer_m3_fixtures_1/


## 2026-11-10T09:50:10Z

You are Explorer 3 (Scenario Catalog Groups F–K & Fixtures) for Milestone M3 of the Capri Comprehensive Evaluation project.

## Context
Working directory: /home/cyberdid/Projects/B-12
Your state folder: /home/cyberdid/Projects/B-12/.agents/teamwork/explorer_m3_fixtures_1
MANDATORY: You MUST read ORIGINAL_REQUEST.md before starting work:
/home/cyberdid/Projects/B-12/.agents/teamwork/ORIGINAL_REQUEST.md
Also read PROJECT.md:
/home/cyberdid/Projects/B-12/.agents/teamwork/orchestrator_gen1/PROJECT.md
And authoritative specification:
/home/cyberdid/Projects/B-12/.agents/teamwork/spec_miner_survey_eval/analysis.md

## Objective
Detail the exact requirements for authoring the 44 scenario YAMLs in Groups F through K, plus the fixtures architecture:
- Group F: Autonomy & Initiative (`AUT-01` .. `AUT-09`, 9 scenarios)
- Group G: Human–AI Interaction (`INT-01` .. `INT-08`, 8 scenarios)
- Group H: Voice & Real-Time Interaction (`VOI-01` .. `VOI-08`, 8 scenarios)
- Group I: Reliability & Fault Tolerance (`REL-01` .. `REL-08`, 8 scenarios)
- Group J: Embodiment & Robotics (`ROB-01` .. `ROB-06`, 6 scenarios)
- Group K: Multi-Session Journeys (`JOURNEY-01` .. `JOURNEY-05`, 5 scenarios)

For EACH of the 44 scenarios:
1. Provide exact scenario ID, title, research hypothesis, taxonomy, severity, execution mode.
2. Note zero-fabrication protocol for blocked scenarios (e.g., ROB missing physical arm -> `BLOCKED_HARDWARE`, multi-day delay -> `BLOCKED_DELAY` or simulated time-warp).
3. Specify exact turn-by-turn interactions: actor_id, input prompt, expected behaviors, forbidden behaviors.
4. Specify ground truth reference answer and evaluation pass criteria.
5. Detail the comprehensive fixture layout needed under `evals/capri_comprehensive/fixtures/` across all 11 groups (e.g. synthetic docs, SQLite templates, mock audio metadata, mock network sinks, mock Reachy logs).

## Output
Write your comprehensive catalog, zero-fabrication rules, and fixture blueprints to:
/home/cyberdid/Projects/B-12/.agents/teamwork/explorer_m3_fixtures_1/handoff.md
Follow the Handoff Protocol (Observation, Logic Chain, Caveats, Conclusion, Verification Method).
When finished, send a brief message with the handoff path.
