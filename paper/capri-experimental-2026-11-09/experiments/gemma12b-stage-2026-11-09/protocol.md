# Controlled CPU context-budget experiment

Registered before execution, 2026-11-09. Question: is the existing fixed-character assertion sensitive to the persona prefix length, holding the scripted file-reading sequence and runtime constant?

Four arms: current persona; committed-HEAD persona; removed persona prefix; neutral prefix matched to current persona in character count and UTF-8 byte lengths. Only the Agent constructor's system_prompt argument changes in an in-memory pytest plugin. No production source is edited. Three interleaved repetitions per arm, identical disposable basetemp path. Existing test and its <10000-character assertion remain unchanged. All original failures are retained.

Capture every actual scripted HTTP request's message characters by role, synthetic rendered token counts with/without schemas, request number and input/output limits. The fixture is synthetic ByteLevel BPE with no merges, not a Gemma or Bolt tokenizer. This experiment cannot estimate real model reasoning, persona quality, security or actual Gemma overflow. The neutral prefix is a size control, not a usable assistant prompt. No deployment setting changes and no GPU inference.

Gemma 4 12B is the selected next-stage candidate. Record local digest, Q4_K_M and Ollama version separately; download only tokenizer metadata if accessible. A model benchmark is not admitted until a compatible calibrated profile exists. Results in this CPU experiment must not be attributed to Gemma.


## Registered Gemma calibration pilot

After offline admission succeeded for two text requests, register at most eight provider requests: Ukrainian, emoji/code-switch, a tool schema and a completed tool-call history, two repetitions each. Context 4096, output reserve 32, temperature 0, seed 42, thinking off. Per-call deadline 45 s; experiment deadline 180 s. This exercises only OllamaModel/ContextBuilder, not Agent execution. Tool calls are recorded but never executed. All prompts are synthetic and no private memory is provided. Abort after a deployment/count mismatch; no production profile is activated. Require exact provider/local count equality for every completed calibration request, even though the adapter tolerates a lower count. Record truncation/length termination and protocol errors separately. Clean up only the dedicated alias loaded by this probe, with an initially empty /api/ps.

This is a narrow compatibility pilot, not an eight-case reliability benchmark. It excludes long-context boundaries, long-session memory correctness, comparative persona evaluation, physical voice and causal task-performance comparisons.


## Registered small end-to-end Gemma pilot

After 8/8 exact calibration requests, run three frozen current-corpus cases: ua-fact-0, tool-write-read-0, memory-store-recall-0. Two repetitions at contexts 4096 and 8192 (12 executions, up to 16 user turns). Output reserve 128, temperature 0, top_p 1, seed 42; max_rounds 8, max_tool_calls 12, provider timeout 45 s, global experiment budget 240 s. Existing runner.run_case and scorer are imported unchanged; explicit Settings select Gemma because the runner CLI otherwise defaults to Bolt. Each case gets fresh disposable stores and sandbox; memory scenario creates a new session for each turn. Existing runner grants are unchanged and not applied to live user state. No adversarial network, shell or destructive scenario is selected. Retain raw checks, tool arguments, errors and all failures. Restore the loaded Gemma alias after the run. This tiny selected pilot cannot establish a model ranking or substitute for the full corpus; contexts are the only intended factor within this pilot. Historical 512-output-token Bolt results are not a controlled comparator.
