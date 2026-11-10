# Dispatch: Explorer M4 Models

Target: Investigate local Ollama model runtime, responsiveness, latency baselines, and execution parameters for b12-bolt-e4b:q4km and gemma4:12b.
Deliverable: handoff.md in /home/cyberdid/Projects/B-12/.agents/teamwork/explorer_m4_models_1/

## 2026-11-10T10:32:12Z

You are Explorer 1 (Model Runtime & LLM Bridge) for Milestone M4 of the Capri Comprehensive Evaluation project.

## Context & Inputs
Working directory: /home/cyberdid/Projects/B-12
Your state folder: /home/cyberdid/Projects/B-12/.agents/teamwork/explorer_m4_models_1
MANDATORY: You MUST read ORIGINAL_REQUEST.md before starting work:
/home/cyberdid/Projects/B-12/.agents/teamwork/ORIGINAL_REQUEST.md
Also read PROJECT.md:
/home/cyberdid/Projects/B-12/.agents/teamwork/orchestrator_gen1/PROJECT.md

## Objective
Investigate the local model runtime and Ollama bridge execution for Milestone M4:
1. Verify Ollama service status at `http://127.0.0.1:11434/api/tags` and list of installed models.
2. Confirm responsiveness and baseline latencies (TTFT, token evaluation rate) for:
   - Primary model: `b12-bolt-e4b:q4km` (or active alias)
   - Secondary model: `gemma4:12b`
3. Test a quick one-turn generation via `ScenarioRunner._call_ollama_bridge()` for both models.
4. Assess VRAM usage and NVMe disk headroom (must not download any new large models, 16GB free NVMe limit).
5. Recommend optimal execution parameters (timeouts per turn, context window handling, temperature settings) for the Worker running the full 92-scenario evaluation.

## Output
Write your findings and execution recommendations to:
/home/cyberdid/Projects/B-12/.agents/teamwork/explorer_m4_models_1/handoff.md
Follow the Handoff Protocol. Include commands and verbatim test outputs.
When complete, send a message to the orchestrator.
