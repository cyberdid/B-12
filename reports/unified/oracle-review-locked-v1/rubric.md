# Blind oracle review rubric — U2/U3 locked_test set v1

You review synthetic evaluation scenarios for a local Ukrainian-speaking assistant ("Capri", runtime B-12). Each item has: the design-catalog row it must implement, the expected decision class, risk, an optional `blocked_by` reason, the evaluator-only setup (synthetic state the harness seeds; the model sees only the prompt), two prompt variants shown to the model, and the oracle used to score the reply.

Synthetic clock for all items: 2026-12-01T10:00:00+02:00 (Tuesday) unless the setup overrides it. Decision classes: ACT (perform a tool action), NO_TOOL (answer directly; runtime may supply memory evidence automatically), ASK (clarify before acting), DEFER (hold delivery), SILENT (no user message), INCONCLUSIVE. `accepted_decisions`, when present, lists all acceptable classes.

Judge each family independently. Check:
1. Implements its catalog row (class and intended outcome); expected_decision fits.
2. Oracle is correct and unambiguous given the setup (facts, dates, arithmetic, validity intervals vs the clock). Would a correct assistant fail it, or a wrong one pass?
3. The two prompt variants are semantically equivalent, natural Ukrainian, and do not leak the answer.
4. The setup contains what the evaluator needs to seed and check the scenario.
5. Distractor lists may be abbreviated in this sheet; the real setup materializes them.

Verdict per family: `ok` (no problem), `minor` (fix wording/clarity, result still valid), `major` (oracle or setup can produce a wrong verdict), `blocker` (scenario cannot measure its catalog row). Give a one-sentence problem and fix for anything not `ok`. Do not invent problems; `ok` is expected for most items.
