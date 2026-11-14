# Deep research: behavior of a small local LLM companion (B-12 / Capri)

Write the final report in Ukrainian. Keep technical identifiers (model names, parameters, API fields, paper titles) in their original language.

## Context

I am building Capri, a local-first AI companion (persona with a dry, slightly cyberpunk character) that runs on the owner's own workstation. Architecture invariants that any recommendation must respect:

- **Local-first.** Inference runs on the owner's machine through Ollama 0.33.3. No cloud LLM in the loop.
- **Swappable model.** The runtime must work with different local models, so recommendations should not depend on one model's quirks.
- **Deterministic control channel.** Permissions, identity, consent and approvals come from the runtime, never from model text. Motion and audio never block on the LLM.
- **Traceable memory.** Every recalled fact has a source record.

Hardware: laptop with an RTX 4060 (8 GB VRAM), 32 cores, ~32 GB RAM.

Models:

- **Primary model ("Bolt").** A Gemma 4 E4B-class build, Q4_K_M GGUF, ~6.2 GB. It partly spills to CPU when anything else uses the GPU.
- **Alternative: gemma4:12b.** Runs largely on CPU on this GPU.
- **Also tested remotely:** gemma4:26b (MoE A4B) and gemma4:31b.

Request shape on every turn:

- System prompt of ~1,700 tokens: ~500 tokens of persona plus ~1,200 tokens of rules about tools, memory, file review and honesty.
- 17 tool schemas, ~780 tokens.
- Recalled memories ("Evidence") appended to the system message, then the chat history.
- Settings: num_ctx 8192, `think: false`, streaming, temperature 0–0.7 depending on the scenario.
- Typical prompt size: ~3,200 tokens.

Evaluation: an 80-scenario automated suite run through the real runtime in a sandbox, plus manual labeling of failures. Results on the current code:

| Model | Passed (of 80) |
|---|---|
| Bolt | 48 |
| gemma4:12b | 43 |
| gemma4:26b | 41 |
| gemma4:31b | 43 |

22 scenarios fail on all four models, so they are system or prompt problems, not model-size problems. Three repeats per model are running to measure run-to-run variance.

## Problems to research (security is out of scope)

1. **Verbosity in casual turns.** Persona questions ("Who are you and what is your role?") and emotional messages ("I've spent 6 hours on a segfault, I'm exhausted") get 600–1,100 characters where ~300 is the target. The persona already says "be laconic in everyday talk, complete in technical answers".
   - **Measured negative result (important constraint).** Adding an explicit rule ("answer greetings, questions about yourself, tiredness or emotions in 1–3 short sentences, ≤ ~300 characters, no lists") did shorten replies 2–5×. It also made the small model skip tool calls on technical questions (a diagnostic task that needs reading files: 0/2 passes vs 2/2 without the rule) and once switched the reply language to Russian.
   - A follow-up wording ("brevity applies to text, not to work: check with tools first") did not restore tool use.
   - I need length control that does not degrade tool use or language adherence in a ~4B model.
2. **Time to first token (TTFT).** Targets are 1.5–2.0 s for short voice-like turns. Measured TTFT:

   | Model | P50 | P95 |
   |---|---|---|
   | Bolt | ~1.7 s | ~8.1 s |
   | gemma4:12b | ~5 s | ~11 s |

   - A quick A/B (full prompt vs persona-only prompt, 1,200 fewer tokens) showed no TTFT gain. That A/B ran while another GPU program was active, so it is inconclusive.
   - Things I want to understand:
     - how Ollama and llama.cpp prompt or KV-cache reuse works across requests, and what breaks it (for example, evidence inserted into the system message, changing tool lists);
     - effects of num_batch, flash attention, KV-cache quantization, keep_alive, partial offload and speculative/MTP draft models on TTFT;
     - per-turn tool-schema pruning or dynamic tool selection;
     - prefix ordering that keeps the static part cacheable.
3. **Contradiction detection.** Given two documents that disagree (one spec says 24 V, another 12 V), the model reads both but answers without flagging the contradiction. I want techniques that make a small model reliably surface conflicts in tool outputs or retrieved evidence, ideally with a cheap deterministic or verifier step rather than a longer prompt.
4. **Preference adherence.** Stored owner preferences (for example "temperatures in Celsius", "my editor is Neovim") are in context. The model applies some (units) and ignores others (editor). Research how to inject and enforce user preferences for small models: structured preference blocks, retrieval of only relevant preferences, post-generation checks, few-shot examples.
5. **Proactive initiative.** On "Hi, how are you?" the companion should sometimes bring up an unresolved issue from memory (for example "the current sensor disconnected over USB on Nov 8"). This is not implemented. Research designs for proactive, non-annoying initiative in companion agents, such as:
   - tracking open loops or unresolved items;
   - salience and recency scoring;
   - rate-limiting and timing;
   - surfacing at session start vs mid-conversation;
   - relevant work on reflection and memory streams (e.g. Generative Agents, MemGPT/Letta-style memory, proactive dialogue research).

## What I need from the research

For each problem:

1. **Approaches.** The 3–6 most promising approaches, ranked by expected effect for a ~4B–12B local model under the invariants above.
2. **Per-approach detail:**
   - mechanism;
   - evidence (papers, benchmarks, maintainer docs or issues, credible engineering write-ups) with links and dates;
   - expected effect size if reported;
   - risk to tool use, language adherence and latency;
   - implementation cost;
   - whether it is model-agnostic.
3. **Prompt-only vs non-prompt options.** Separate prompt-only fixes from structural ones: intent routing (casual vs task mode), per-intent generation limits, post-generation length or format enforcement, a second cheap "style pass", constrained decoding or grammars, verifier steps, retrieval changes, and lightweight fine-tuning or LoRA (mark this as optional and estimate its cost).
4. **Fragility of small models.** Explicitly address why a single brevity instruction can suppress tool calls in small models (instruction interference, competing objectives), and how to add constraints without that side effect. Cite evidence if it exists. Otherwise say clearly that it is an informed hypothesis.
5. **Measurement plan.** A concrete A/B protocol suitable for an 80-scenario suite with 3 repeats per arm, given that 1–3 verdicts flip between identical runs:
   - how many repeats are needed;
   - which statistics to use (paired comparisons, McNemar, bootstrap);
   - how to avoid overfitting prompts to keyword-based checks.

## Rules for the research

- **Prefer recent sources (2024–2026)** and state the date of each one. Note when a finding comes from an older model generation and may not transfer.
- **Mark the evidence level** of each claim: peer-reviewed, preprint, official docs, maintainer comment, blog or anecdote. Do not present anecdotes as established facts.
- **Ollama and llama.cpp specifics.** Cite the exact docs, issue or PR, and say which version it applies to. Behavior changes quickly between releases.
- **Unknowns.** If something is unknown or contested, say so. Do not invent numbers, papers or features.
- **Finish with a prioritized action list.** At most 8 items, each with: what to change, expected benefit, main risk, and how to verify it with the suite.
