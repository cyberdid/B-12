# Dispatch: Explorer M4 Ablations

Target: Investigate ablation_runner.py, the 5 ablation dimensions, statistical aggregation with metrics.py, and CSV matrix generation.
Deliverable: handoff.md in /home/cyberdid/Projects/B-12/.agents/teamwork/explorer_m4_ablations_1/


## 2026-11-10T10:32:12Z
You are Explorer 3 (Ablations & Statistical Pipeline) for Milestone M4 of the Capri Comprehensive Evaluation project.

## Context & Inputs
Working directory: /home/cyberdid/Projects/B-12
Your state folder: /home/cyberdid/Projects/B-12/.agents/teamwork/explorer_m4_ablations_1
MANDATORY: You MUST read ORIGINAL_REQUEST.md before starting work:
/home/cyberdid/Projects/B-12/.agents/teamwork/ORIGINAL_REQUEST.md
Also read PROJECT.md:
/home/cyberdid/Projects/B-12/.agents/teamwork/orchestrator_gen1/PROJECT.md

## Objective
Investigate the 5 systematic ablations and statistical analysis pipeline for Milestone M4:
1. Inspect `evals/capri_comprehensive/runners/ablation_runner.py`, `evals/capri_comprehensive/statistical_analysis/metrics.py`, and `evals/capri_comprehensive/statistical_analysis/aggregator.py`.
2. Verify the 5 ablation dimensions:
   - `A1_MEMORY`: Autobiographical memory ablation (no memory vs full memory)
   - `A2_CONTEXT`: Context window degradation (2048 vs 4096 vs 8192)
   - `A3_GATING`: Deterministic policy gating (enabled vs disabled)
   - `A4_TOOLS`: Tool execution vs raw generation (tools allowed vs forbidden)
   - `A5_MODEL`: Model swap behavioral continuity (`b12-bolt-e4b:q4km` vs `gemma4:12b`)
3. Check the statistical metrics computation: Wilson score intervals at 95% confidence, bootstrap percentiles for latencies (P50, P90, P95).
4. Verify the 15-column schema for `CAPRI_SCENARIO_MATRIX.csv`:
   `Scenario_ID,Group,Name,Taxonomy,Severity,Target_Subsystem,Hypothesis,Execution_Status,Raw_Score,CI_95_Low,CI_95_High,P50_Latency_ms,P95_Latency_ms,Ablation_Sensitivity,Failure_Reason`
5. Detail the exact commands and workflow for the Worker to run the ablations and statistical aggregation cleanly.

## Output
Write your findings and ablation execution plan to:
/home/cyberdid/Projects/B-12/.agents/teamwork/explorer_m4_ablations_1/handoff.md
Follow the Handoff Protocol. Include commands and verbatim test outputs.
When complete, send a message to the orchestrator.


## 2026-11-10T13:12:15Z
You are an Explorer for Milestone M4 Remediation (Capri Comprehensive Evaluation).
Working directory: /home/cyberdid/Projects/B-12
State folder: /home/cyberdid/Projects/B-12/.agents/teamwork/explorer_m4_ablations_1

MANDATORY INPUT FILES:
- Read /home/cyberdid/Projects/B-12/.agents/teamwork/ORIGINAL_REQUEST.md before starting work.
- Read /home/cyberdid/Projects/B-12/.agents/teamwork/orchestrator_gen2/PROJECT.md
- Read /home/cyberdid/Projects/B-12/.agents/teamwork/orchestrator_gen2/DEAD_ENDS.md
- Read /home/cyberdid/Projects/B-12/.agents/teamwork/orchestrator_gen2/GATE_STATUS.md
- Read the FULL Reviewer 2 report: /home/cyberdid/Projects/B-12/.agents/teamwork/reviewer_m4_2/handoff.md
- Read the FULL Reviewer 1 report: /home/cyberdid/Projects/B-12/.agents/teamwork/reviewer_m4_1/handoff.md

TASK:
Milestone M4 Gate FAILED with REQUEST_CHANGES due to critical integrity violations in ablation and tooling architecture:
1. `evals/capri_comprehensive/runners/ablation_runner.py` lines 77 and 80 set `metadata["gating_mode"]` and `metadata["tools_mode"]`, but `runner.py` never inspects or applies these settings.
2. In `evals/capri_comprehensive/runners/runner.py:_call_ollama_bridge()`, the request payload sends no `tools` array to Ollama API (`/api/chat`). Consequently, local models receive no tool definitions, cannot perform native function calling, and ablations A3_GATING and A4_TOOLS generated identical request structures.

Your mission:
1. Investigate `evals/capri_comprehensive/runners/ablation_runner.py` and `evals/capri_comprehensive/runners/runner.py`.
2. Inspect how Ollama `/api/chat` expects the `tools` parameter (e.g. OpenAI-compatible format: `[{"type": "function", "function": {"name": ..., "description": ..., "parameters": ...}}]`).
3. Plan how `runner.py` should inspect `scenario.metadata.get("gating_mode")`:
   - `DETERMINISTIC`: Enforce strict gating/validation and security system prompt constraints.
   - `PROMPT_ONLY`: Relax deterministic filters and rely purely on soft prompt instruction.
4. Plan how `runner.py` should inspect `scenario.metadata.get("tools_mode")` and supply `tools` to Ollama:
   - `FULL`: Full JSON schema with rich descriptions and parameter constraints.
   - `STRICT`: Compact schema with parameter types and strict requirements.
   - `MINIMAL`: Bare-bones schema with function names only.
   - When tools are called by the model in `/api/chat` response (`message.tool_calls`), how `runner.py` extracts them and records them in `turn_result["tool_calls"]`.
5. Provide a concrete, step-by-step fix strategy with exact code diffs/proposals for Worker M4.
6. Write your comprehensive handoff report to `/home/cyberdid/Projects/B-12/.agents/teamwork/explorer_m4_ablations_1/handoff.md`.
7. Send a message to your parent upon completion.
