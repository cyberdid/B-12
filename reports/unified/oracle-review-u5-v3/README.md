# U5 v3 blind oracle review pack

Status: reviewed by two independent local model families; frozen successor created. This v3 draft remains immutable and was not run as an evaluation corpus.

- Set: `evals/unified/scenario_sets/u5-application-v3.json` (48 DRAFT variants, 24 families).
- Manifest SHA-256: `b6aee9bdfbe4d686de9e65207f403e0c9429378b146e7b7ab810e4eb6fa6ec5d`.
- Blind-review result: [REVIEW-RESULT.md](REVIEW-RESULT.md), with raw prompts and responses under `reviews/`; both reviewers returned `ok` for all 24 families (24/24 agreement).
- Frozen successor: [`u5-application-locked-v1.json`](../../../evals/unified/scenario_sets/u5-application-locked-v1.json), SHA-256 `170559858370a5ef02ecb362f6664a51632bf60cb1e6fe462b331cde882b1ea0`.
- Reviewers: local Ollama `gemma4:12b` (`4eb23ef187e2`, Q4_K_M) and `b12-bolt-e4b:q4km` (`7eaa0c0553b8`, Q4_K_M), with temperature 0, seed 781, context 8192. The second reviewer shares a model family with the U5 target; the cross-family Gemma review provides a separate perspective. This is model-assisted review, not human certification.
- No U5 arm responses or arm labels were shown to reviewers. Both received the same prompt shards and scenario/oracle material in separate contexts.
- v3 clarification: M61/M62 ask whether a reminder time fits the owner's rule, without asking Capri to schedule/send one; M83 asks for the applicable wake-up time without asking Capri to set an alarm. This aligns the task wording with `NO_TOOL` decisions while retaining the scope/validity tests.
- v2 is preserved as `RETIRED` at `evals/unified/scenario_sets/u5-application-v2.json`; its preflight issue and old review materials are archived in `reports/unified/oracle-review-u5-v2/`.
- Reviewer input: `prompt.txt`; structured response schema: `schema.json`; `sheet.json` is the machine-readable item list.
- The pack contains synthetic evaluator setups and proposed oracles, but no Capri task outputs. See [review result](REVIEW-RESULT.md) and [machine-readable metadata](blind-review-summary.json) for the review scope and limitations.
