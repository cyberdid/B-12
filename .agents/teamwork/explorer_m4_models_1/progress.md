# Progress: Explorer M4 Models

Last visited: 2026-11-10T10:43:00Z
Status: COMPLETED — Handoff report delivered to orchestrator

## Checklist
- [x] Create BRIEFING.md, DISPATCH.md, progress.md
- [x] Read ORIGINAL_REQUEST.md and PROJECT.md
- [x] Check Ollama service status (`http://127.0.0.1:11434/api/tags`) and list installed models
- [x] Check NVMe disk headroom and VRAM usage (`df -h`, `nvidia-smi`)
- [x] Measure baseline latencies (TTFT, token evaluation rate) for `b12-bolt-e4b:q4km` and `gemma4:12b`
- [x] Test `ScenarioRunner._call_ollama_bridge()` for both models
- [x] Discover critical edge cases:
  - `b12-bolt-e4b:q4km` default `num_predict=192` causes `content=""` when thinking tokens exhaust the limit
  - `model: any_swappable` in Group C is unmapped in runner (raises HTTP 404)
  - `model: "none"` in deterministic scenarios is unhandled in runner (raises HTTP 404)
- [x] Synthesize findings & recommend optimal execution parameters
- [x] Write handoff.md following 5-component protocol
- [x] Notify orchestrator
