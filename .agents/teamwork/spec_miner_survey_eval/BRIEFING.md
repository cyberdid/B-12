# BRIEFING — 2026-11-10T08:42:30Z

## Mission
Perform comprehensive requirement extraction and specification mapping for the Capri comprehensive evaluation suite (Groups A–K, YAML schema, scientific categorization, statistical methodology, research questions RQ1–RQ10, and 5 deliverables).

## 🔒 My Identity
- Archetype: teamwork_spec_miner
- Roles: spec_miner, requirement_analyst, evaluation_designer
- Working directory: /home/cyberdid/Projects/B-12
- State folder: /home/cyberdid/Projects/B-12/.agents/teamwork/spec_miner_survey_eval
- Original parent: f7064ab7-5ff4-4a09-bb25-95e84e62ebcd
- Milestone: Survey Phase — Evaluation Suite Specification & Taxonomy (COMPLETED)

## 🔒 Key Constraints
- Read-only on codebase and production artifacts; no implementation, no modification of production files.
- All evaluation definitions must ensure scientific integrity: no fabricated passes, explicit BLOCKED / PENDING / NOT_AVAILABLE status for blocked tests.
- Real LLM evaluation must not use the evaluated model as sole self-judge.
- Security / adversarial tests must specify isolated synthetic sandbox constraints.
- Full coverage of Groups A–K, RQ1–RQ10, 5 formal reports, CSV matrix, and exact YAML schema.

## Current Parent
- Conversation ID: f7064ab7-5ff4-4a09-bb25-95e84e62ebcd
- Updated: 2026-11-10T08:42:30Z

## Task Summary
- **What to build**: Specification report (`analysis.md`) and handoff report (`handoff.md`) covering all Capri evaluation requirements, scenario inventories, YAML schema, execution taxonomy, statistical protocols, and deliverables.
- **Success criteria**: Complete mapping of R1–R5, acceptance criteria, scenario definitions for all 92 scenarios across Groups A–K, schema, taxonomy, RQ1–RQ10, and deliverable specs.
- **Interface contracts**: YAML scenario definition schema, evaluator contracts, CSV scenario matrix schema.
- **Code layout**: Target evaluation suite in `evals/capri_comprehensive/` (to be implemented in subsequent milestones).

## Key Decisions Made
- Deconstructed requirements into formal, verifiable specifications.
- Structured scenario groups into atomic scenario specifications with research hypotheses, inputs, expected/forbidden behaviors, ground truth, severity, and taxonomy classification.
- Established strict taxonomy distinguishing deterministic, real-model behavioral, controlled experimental, and physical acceptance tests.
- Formalized Zero-Fabrication invariant: tests with missing hardware (Reachy) or real-time delays (7/30 days) are recorded as BLOCKED_HARDWARE or BLOCKED_DELAY.
- Specified Wilson score intervals for binomial metrics and bootstrap percentiles for latencies across 5 systematic ablations.
- Formally articulated research questions RQ1–RQ10 and 15-column CSV scenario matrix layout.

## Artifact Index
- `/home/cyberdid/Projects/B-12/.agents/teamwork/ORIGINAL_REQUEST.md` — Authoritative requirements source
- `/home/cyberdid/Projects/B-12/.agents/teamwork/spec_miner_survey_eval/DISPATCH.md` — Incoming dispatch prompt
- `/home/cyberdid/Projects/B-12/.agents/teamwork/spec_miner_survey_eval/BRIEFING.md` — Persistent working memory
- `/home/cyberdid/Projects/B-12/.agents/teamwork/spec_miner_survey_eval/progress.md` — Liveness & progress tracking
- `/home/cyberdid/Projects/B-12/.agents/teamwork/spec_miner_survey_eval/analysis.md` — Full technical specification analysis (692 lines)
- `/home/cyberdid/Projects/B-12/.agents/teamwork/spec_miner_survey_eval/handoff.md` — Structured 5-component handoff
