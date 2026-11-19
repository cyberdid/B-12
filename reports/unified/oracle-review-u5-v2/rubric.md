# Blind oracle review rubric — U5 application set v2

You review synthetic evaluation scenarios for a local Ukrainian-speaking assistant ("Capri", runtime B-12). They test whether the assistant applies remembered preferences, commitments and facts correctly to a decision: a preference applies only within its condition (`applies_when`) and validity interval; an explicit owner statement outranks an assistant inference (`origin`); a revoked preference (`revoked: true`) no longer applies; a superseded record is history, not current; two current records that disagree are a conflict to report; no record means "I don't know"; cancelled (abandoned) goals must not come back as active; an achieved goal whose evidence was later superseded by a failing result is not done.

Each item has: the class it must test, expected decision, the evaluator-only setup (synthetic memory rows and goals the harness seeds; the model sees only the prompt, plus whatever memory/goal context the runtime gives it), two prompt variants, and the oracle. `metric_tags` say which forbidden effects count as stale-use, over-application or resurrection.

Synthetic clock: 2026-12-01T10:00:00+02:00 (Tuesday). Decision classes: NO_TOOL (answer directly; runtime may supply memory evidence automatically), ASK (clarify first), ACT. `accepted_decisions` lists all acceptable classes.

Judge each family independently. Check:
1. It tests its class; expected decision fits.
2. The oracle is correct and unambiguous given the setup (dates and intervals vs the clock, weekday, which record is current). Would a correct assistant fail it, or a wrong one pass?
3. The two variants are equivalent, natural Ukrainian, and do not leak the answer.
4. The metric tags are right (a forbidden effect tagged stale_use really is using expired/superseded/revoked/inferred-over-explicit information, etc.).

Verdict per family: `ok`, `minor` (wording; result still valid), `major` (oracle or setup can produce a wrong verdict), `blocker` (cannot measure its class). One-sentence problem and fix for anything not `ok`. Do not invent problems.
