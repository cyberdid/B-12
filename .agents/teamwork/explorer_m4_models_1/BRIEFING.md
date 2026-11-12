# BRIEFING — 2026-11-10T10:42:00Z

## Mission
Investigate local model runtime and Ollama bridge execution for Milestone M4 (latencies, VRAM, headroom, ScenarioRunner._call_ollama_bridge test, recommendations).

## 🔒 My Identity
- Archetype: explorer
- Roles: Model Runtime & LLM Bridge Investigator
- Working directory: /home/cyberdid/Projects/B-12
- State folder: /home/cyberdid/Projects/B-12/.agents/teamwork/explorer_m4_models_1
- Original parent: 0e57a143-8545-4357-9c76-267457e6414f
- Milestone: M4 (Capri Comprehensive Evaluation - Model Runtime)

## 🔒 Key Constraints
- Read-only investigation — do NOT implement
- Must not download any new large models (16GB free NVMe limit)
- Verify Ollama service status and installed models
- Baseline latencies (TTFT, token eval rate) for b12-bolt-e4b:q4km and gemma4:12b
- Test ScenarioRunner._call_ollama_bridge() for both models
- Assess VRAM usage and NVMe disk headroom
- Recommend optimal execution parameters

## Current Parent
- Conversation ID: 0e57a143-8545-4357-9c76-267457e6414f
- Updated: not yet

## Investigation State
- **Explored paths**:
  - Ollama service endpoint `/api/tags`, `/api/version`, `/api/show`
  - Host hardware: NVMe partition `/`, NVIDIA RTX 4060 Laptop VRAM, DDR5 RAM
  - `evals/capri_comprehensive/runners/runner.py` and `suite_runner.py`
  - `ScenarioRunner._call_ollama_bridge()` live calls
  - Benchmark script `measure_models.py`
- **Key findings**:
  - Ollama 0.33.3 active; installed models: `b12-bolt-e4b:q4km` (6.2 GB), `gemma4:12b` (7.6 GB), `qwen3.5:27b` (17 GB), `qwen3.8:27b` (17 GB).
  - NVMe free space is 16 GB (97% used); zero new model downloads permitted.
  - VRAM: RTX 4060 Laptop (8188 MiB total). Background embedder (PID 55058) takes 1584 MiB. Free VRAM ~6581 MiB.
  - `b12-bolt-e4b:q4km`: 100% GPU offload, ~3.3 GB in Ollama, TTFT ~41-44 ms (warm), generation ~62-63 tok/s.
  - `gemma4:12b`: 37%/63% CPU/GPU split, ~8.1 GB in Ollama, TTFT ~6.4-8.5 s (cold) / ~998 ms (warm), generation ~14.8-15.7 tok/s.
  - Models cannot co-exist in VRAM; Ollama swaps them sequentially.
  - Critical discovery 1: `b12-bolt-e4b:q4km` modelfile defaults to `num_predict 192`. If model uses inline reasoning (`thinking`), it exhausts 192 tokens on thinking and leaves `content=""`. Fix: pass `num_predict >= 512` or `think: False`.
  - Critical discovery 2: `target_model == "any_swappable"` in Group C is unmapped in `ScenarioRunner._call_ollama_bridge()`, causing HTTP 404. Fix: map `"any_swappable"` to `"gemma4:12b"`.
  - Critical discovery 3: Deterministic scenarios with `model: "none"` fail with HTTP 404 if no custom `turn_executor` is passed. Fix: bypass Ollama when `target_model == "none"`.
- **Unexplored areas**: None. All objectives fully characterized.

## Key Decisions Made
- Empirically benchmarked cold & warm latencies across both primary and secondary models.
- Verified `num_ctx=2048`, `4096`, and `8192` memory footprint.
- Formulated execution parameters for Worker (sequential batching, 120s timeout for Gemma, `num_predict=512`, mapping rules).

## Artifact Index
- DISPATCH.md — incoming dispatch records
- BRIEFING.md — persistent situational awareness
- progress.md — liveness heartbeat
- measure_models.py — empirical latency & VRAM measurement script
- handoff.md — final comprehensive handoff report
