## 2026-11-10T12:59:51Z
You are the Forensic Integrity Auditor for the Milestone M4 Gate of the Capri Comprehensive Evaluation project.

## Context & Inputs
Working directory: /home/cyberdid/Projects/B-12
Your state folder: /home/cyberdid/Projects/B-12/.agents/teamwork/auditor_m4
MANDATORY: You MUST read ORIGINAL_REQUEST.md before starting work:
/home/cyberdid/Projects/B-12/.agents/teamwork/ORIGINAL_REQUEST.md
Also read PROJECT.md:
/home/cyberdid/Projects/B-12/.agents/teamwork/orchestrator_gen1/PROJECT.md
And Worker M4 report:
/home/cyberdid/Projects/B-12/.agents/teamwork/worker_m4_execution_1/handoff.md

## Scope & Forensic Mandate
Conduct an exhaustive forensic integrity audit across the Milestone M4 execution artifacts, outputs, and model calls:
1. Verify Non-Fabrication of LLM Calls:
   - Inspect `turn_trace.jsonl` across real-model scenarios (`MEM-01`, `CM-01`, `CM-05`, `RE-01`, `INT-01`): verify genuine Ollama token generation, non-zero `tokens_prompt`, `tokens_completion`, `ttft_ms`, and authentic assistant text.
   - Ensure responses are NOT echoed from `reference_answer` or hardcoded strings.
2. Verify Zero-Fabrication of Blocked Scenarios:
   - Check all 14 blocked scenarios: confirm `BLOCKED_*` status, `raw_score == 0.0`, and zero fake passes.
3. Verify Genuine Ablations:
   - Inspect `artifacts/ablations/`: confirm all 5 files contain genuine experimental variations and real timings.
4. Verify Workspace Boundary & Secrets:
   - Confirm zero real host secrets in fixtures or artifacts.
   - Run `git status --porcelain` to ensure clean boundaries outside `evals/capri_comprehensive/`.
5. Run `uv run pytest evals/capri_comprehensive/tests/`.

## Output
Write your forensic audit report and explicit binary verdict (`CLEAN` or `INTEGRITY VIOLATION`) to:
/home/cyberdid/Projects/B-12/.agents/teamwork/auditor_m4/handoff.md
Follow the Handoff Protocol. Include commands and verbatim audit evidence.
When finished, send a message to the orchestrator.
