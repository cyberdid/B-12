# Gemma 12B follow-up: measured results

Snapshot: feature HEAD 1de4eee74776 with the previously recorded local persona changes. This is project-authored verification, not independent replication. Original production and test files were not modified.

## Controlled CPU prefix ablation

| Arm | Prefix characters | Final request characters | Original assertion passes |
|---|---:|---:|---:|
| Current persona | 1458 | 11344 | 0/3 |
| Committed-HEAD persona | 712 | 10598 | 0/3 |
| Removed persona | 0 | 9886 | 3/3 |
| Neutral, length/UTF-8 matched | 1458 | 11344 | 0/3 |

All arms produced 37 scripted requests. Non-system character counts matched at every round. The current final request decomposed into 4,693 system + 1,077 user + 47 assistant + 5,527 tool characters. Removing the 1,458-character prefix reduced the total from 11,344 to 9,886. Neutral replacement reproduced 11,344 despite changing the text. The committed persona also failed, so the latest uncommitted edit alone is not the sole explanation.

The history reducer budgets message content and keeps protected/latest content; it does not impose a universal bound on system/evidence plus the whole request. This experiment establishes size sensitivity of the unchanged character assertion in this fixture. It does not measure the quality of the persona, nor justify removing it from the live companion. Earlier 11,364 was measured using a different temporary path; these arms share one fixed path and retain their distinct raw values.

The synthetic fixture uses ByteLevel BPE with no merges, a 32,768-token context and output reserve 512. Maximum observed current-arm input was 32,014 synthetic tokens, below admission with its eight-token safety margin. These are not Gemma token counts. No production fix was applied.

## Gemma compatibility pilot

Local Ollama alias gemma4:12b, Q4_K_M, manifest 4eb23ef187e2c5462566d6a1d3bbbc2f1346d0b4327cbb66d58fffbcc9b2b05c; Ollama 0.33.3. Public instruction-tuned tokenizer/template assets were pinned to 43c9d014b231474fa7212dbb48a762566c2b255d. Local GGUF metadata names the base model repository; bitwise mapping to the instruction-tuned upstream weight revision is not established. The local manifest and asset hashes define the tested deployment.

Eight provider requests (four configurations × two repeats) all had exact local/provider input-token agreement. Admitted counts were 32, 27, 75 and 98 for Ukrainian text, emoji/code-switch, a schema and completed tool history. All eight ended with stop. Toy tool calls were recorded, never executed. This is a narrow compatibility calibration, not a long-context or task-reliability benchmark.

## Current-code Gemma task pilot

| Context | Executions | Passed | Distinct scenarios |
|---|---:|---:|---:|
| 4096 | 6 | 6 | 3 |
| 8192 | 6 | 6 | 3 |

Three hand-selected existing cases—ua-fact-0, tool-write-read-0, memory-store-recall-0—were each repeated twice at each context. Sixteen user turns exercised real local generation, file write/read and storage-backed memory recall in a new session. Scoring uses the existing runner and scorer unchanged. Results include check-level evidence and all model/tool states.

Output reserve 128; temperature 0; top_p 1; seed 42; maximum eight rounds and twelve tool calls. The experiment was bounded to 240 seconds. It is not comparable to the historical 109-case Bolt corpus with output reserve 512. With three selected scenarios and correlated repeats, the observed 12/12 is not an estimate of general reliability or superiority. No blinded persona or cross-model identity comparison was performed.

Both model probes acknowledged unloading their dedicated alias afterward; GPU inventory returned to its initial 15 MiB. No live Capri model setting, persona, memory or UI process was changed.

## Reproduction and remaining work

Use the same B-12 source snapshot and environment, run run_budget_probe.py with its pytest plugin, prepare the pinned assets, then calibrate_gemma.py and run_gemma_pilot.py. The original run scripts have explicit time/round limits. Raw JSON, JUnit and console outputs are bundled; private user state and model weights are not. Asset URLs/hashes and runtime/corpus/environment metadata are separate JSON files. A full Gemma corpus rerun, matched current-code Bolt/Gemma comparison, tool overhead/working-note/provenance ablations and blinded persona ratings remain unperformed.
