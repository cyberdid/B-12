# BRIEFING — 2026-11-10T13:25:00Z

## Mission
Investigate and design remediation for M4 Gate failure: connect ablation_runner.py settings (gating_mode, tools_mode) to runner.py execution, implement Ollama /api/chat tool calling payload support (FULL, STRICT, MINIMAL), extract tool_calls from responses, and provide concrete step-by-step diffs and plan for Worker M4.

## 🔒 My Identity
- Archetype: explorer
- Roles: [explorer, synthesis]
- Working directory: /home/cyberdid/Projects/B-12
- State folder: /home/cyberdid/Projects/B-12/.agents/teamwork/explorer_m4_ablations_1
- Original parent: 0e57a143-8545-4357-9c76-267457e6414f
- Milestone: M4 - Systematic Ablations & Statistical Analysis
- Remediation Parent: 9ecc6249-32cc-48fe-ada7-ff8ec7dc5a4f
- Remediation Mission: M4 Gate Failure Remediation (Ablations & Tooling Architecture)

## 🔒 Key Constraints
- Read-only investigation — do NOT implement / modify production source code
- Inspect ablation_runner.py, metrics.py, aggregator.py
- Verify 5 ablation dimensions (A1_MEMORY, A2_CONTEXT, A3_GATING, A4_TOOLS, A5_MODEL)
- Verify Wilson score 95% CI and latency bootstrap percentiles
- Verify 15-column schema for CAPRI_SCENARIO_MATRIX.csv
- Deliver handoff.md following the 5-component protocol
- Remediation Constraints:
  - Investigate `ablation_runner.py` and `runner.py`
  - Inspect Ollama `/api/chat` `tools` parameter formatting
  - Plan `runner.py` handling of `gating_mode` (`DETERMINISTIC`, `PROMPT_ONLY`)
  - Plan `runner.py` handling of `tools_mode` (`FULL`, `STRICT`, `MINIMAL`) and model response tool extraction (`message.tool_calls` -> `turn_result["tool_calls"]`)
  - Provide concrete step-by-step diffs/proposals for Worker M4

## Current Parent
- Conversation ID: 9ecc6249-32cc-48fe-ada7-ff8ec7dc5a4f
- Updated: 2026-11-10T13:25:00Z

## Investigation State
- **Explored paths**:
  - `evals/capri_comprehensive/runners/ablation_runner.py`
  - `evals/capri_comprehensive/runners/runner.py`
  - `evals/capri_comprehensive/evaluators/schema.py`
  - `evals/capri_comprehensive/evaluators/deterministic.py`
  - `evals/capri_comprehensive/tests/test_stress_m2.py`, `test_stress_m4.py`
  - `src/b12/tools/registry.py`, `src/b12/tools/__init__.py`
  - Live Ollama `/api/chat` endpoints on `127.0.0.1:11434`
- **Key findings**:
  - Root cause confirmed: `runner.py` line 361-365 sent no `tools` array to Ollama `/api/chat`, and ignored `scenario.metadata["gating_mode"]` and `tools_mode`.
  - Ollama native tool calling verified with `b12-bolt-e4b:q4km`. Model emits `message.tool_calls` when tools array is present in request.
  - Benchmarked `tools_mode`: `FULL` (177 prompt tokens), `STRICT` (133 prompt tokens), `MINIMAL` (101 prompt tokens) on RE-01. Monotonic and measurable.
  - Benchmarked `gating_mode`: `DETERMINISTIC` (190 prompt tokens, strict refusal, zero tool calls) vs `PROMPT_ONLY` (148 prompt tokens, soft prompt, divergent latency) on SEC-01.
  - Created `proposed_tools.py` with 10 standard B-12 tool schemas and `evaluate_policy_guard`.
  - Created `runner_patch.diff` for clean drop-in implementation by Worker M4.
- **Unexplored areas**:
  - Parallel Explorer `explorer_m4_runner_1` is handling the deterministic facade remediation (`_dispatch_deterministic_turn`).

## Key Decisions Made
- Encapsulate tool schemas and policy guard in `evals/capri_comprehensive/evaluators/tools.py` to keep `runner.py` clean and modular.
- Connect `scenario.metadata["gating_mode"]` and `scenario.metadata["tools_mode"]` directly in `ScenarioRunner._call_ollama_bridge()`.

## Artifact Index
- DISPATCH.md — Received dispatch instructions
- BRIEFING.md — Persistent memory index
- progress.md — Heartbeat and progress log
- proposed_tools.py — Modular tool definition and policy guard implementation
- runner_patch.diff — Unified diff patch for runner.py
- verify_tools_ablation.py — Verification script for metadata mutations
- verify_tool_definitions.py — Verification script for schema modes
- handoff.md — 5-component handoff report for Orchestrator and Worker
