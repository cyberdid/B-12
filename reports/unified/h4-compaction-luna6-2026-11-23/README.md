# H4 compaction recall on gpt-6-luna — 23.11.2026

`evals/unified/compaction_recall.py`: a deterministic 40-turn synthetic owner chat with 12
planted facts in the middle; questions answered only from the post-admission context.
Runtime commit `c83b3b5`, admission with the gemma4:12b profile/tokenizer at `num_ctx` 8192
(the runtime's budget), answers by **gpt-6-luna** through `subscription_bridge` (codex). One run.

| Policy | Exact recall | Relaxed recall | Fact present after admission |
|---|---|---|---|
| `trim` | 0/12 | 0.00 | 0/12 |
| `trim+memory` | **10/12** | **1.00** | 12/12 |

The two non-exact answers add a unit/word («зелений чай сенча», «115200 бод»). Reading: trim alone
loses the mid-conversation facts; memory recall puts every one back, and a frontier model then
answers from it. `prompt_tokens` are 0 — the bridge does not report provider counts (admitted
counts by the runtime tokenizer are ~4.9–5.1k in the run log). Model fields in `result.json`
name gemma4:12b because the runtime profile is gemma's; the answering model is gpt-6-luna.
`summary` policy not implemented (gated on these results).
