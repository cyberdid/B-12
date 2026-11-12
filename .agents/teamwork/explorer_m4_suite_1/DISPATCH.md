# Dispatch: Explorer M4 Suite Runner

Target: Investigate suite_runner.py, batch execution options, sequential process safety, artifact directory setup, and timeout limits.
Deliverable: handoff.md in /home/cyberdid/Projects/B-12/.agents/teamwork/explorer_m4_suite_1/


## 2026-11-10T10:32:12Z
You are Explorer 2 (Suite Execution & Process Safety) for Milestone M4 of the Capri Comprehensive Evaluation project.

## Context & Inputs
Working directory: /home/cyberdid/Projects/B-12
Your state folder: /home/cyberdid/Projects/B-12/.agents/teamwork/explorer_m4_suite_1
MANDATORY: You MUST read ORIGINAL_REQUEST.md before starting work:
/home/cyberdid/Projects/B-12/.agents/teamwork/ORIGINAL_REQUEST.md
Also read PROJECT.md:
/home/cyberdid/Projects/B-12/.agents/teamwork/orchestrator_gen1/PROJECT.md

## Objective
Investigate the suite execution runner for Milestone M4:
1. Inspect `evals/capri_comprehensive/runners/suite_runner.py` and `evals/capri_comprehensive/runners/runner.py`.
2. Verify how all 92 scenarios across Groups A–K are executed:
   - 14 blocked scenarios: verify instant pass-through with `status=BLOCKED_*` and `raw_score=0.0`.
   - Deterministic scenarios: verify execution without LLM overhead where applicable.
   - Real-model behavioral scenarios: verify Ollama bridge dispatch.
3. Assess environment and process isolation: check if running sequential scenarios inside one process could leak environment variables or if running via `SuiteRunner` handles sandbox cleanup cleanly.
4. Verify output artifacts destination: ensure raw traces and JSON outputs are written to `evals/capri_comprehensive/artifacts/` organized by scenario ID without disk bloat.
5. Provide a step-by-step execution plan for the Worker to run the full suite cleanly and reliably.

## Output
Write your findings and execution blueprint to:
/home/cyberdid/Projects/B-12/.agents/teamwork/explorer_m4_suite_1/handoff.md
Follow the Handoff Protocol. Include commands and verbatim test outputs.
When complete, send a message to the orchestrator.
