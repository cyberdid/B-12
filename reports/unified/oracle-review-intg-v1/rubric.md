# Blind oracle review rubric — live integration set v1

You review synthetic evaluation scenarios for a local Ukrainian-speaking assistant ("Capri", runtime B-12). C61: the owner asks for a SHORT conclusion that needs all twelve log files read (tools + evidence coverage, then a brief answer). M85–M88: one seeded memory state that different models will read; facts are judged here, style separately.

Each item: evaluator-only setup (synthetic files/memory; the model sees only the prompt and what tools/runtime return), two prompt variants, oracle (accepted outcomes, required evidence — `file:` means the file must be read by a completed tool call, `mem:` that the runtime offered that memory — forbidden effects, optional max_reply_chars). Clock: 2026-12-01T10:00+02:00.

Per family: is the oracle correct and unambiguous; would a correct assistant fail or a wrong one pass; are the variants equivalent natural Ukrainian without leaking the answer; is the length cap fair. Verdict `ok` / `minor` / `major` / `blocker`, one-sentence problem and fix. Do not invent problems.
