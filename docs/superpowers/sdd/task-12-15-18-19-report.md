# Tasks 12, 13, 14, 15, 18, 19 — state at pause (26.10.2026, ~15:35 UTC)

Coordinator: Claude Code (Claude Opus 5.5). Owner asked to pause and publish; everything below is resumable.

## Task 13 — service, backup/restore (complete except real service install)
Commits 2831df7, d6a9b08 (PDEATHSIG). Snapshots + SHA-256 manifest + inventory, deletion ledger, purge store `snapshots`, restore with ledger replay and pre-restore snapshot, RuntimeLock (no duplicate servers), redacted rotating logs, /api/status, /api/backups, `b12 backup|status`, deploy/b12.service + scripts/install-user-service.sh. Tests: test_recovery (graceful SIGTERM cancels turn + child; SIGKILL -> integrity ok, started->unknown, child dies via PDEATHSIG; migration rollback via restore; tampered snapshot refused), test_deploy (installer in isolated HOME with systemctl shim). OPEN: real `systemctl --user enable --now` was denied by the permission classifier (persistence) — owner runs installer himself.

## Task 12 — MCP + archive + semantic (complete)
7010d22 (MCP stdio bridge), 534be26 (semantic via owner's archive-index EmbeddingGemma 2 bridge; Optional normalization; per-tool timeout; b12 mcp list/add/remove/test). Owner decisions 26.10: removed Ollama embeddinggemma; connect owner's archive-index MCP owner-only read-only; embed via owner's venv (no code copied). Measured: bridge cold load 15.9 s, +1.6 GB VRAM beside Bolt (~5.0 GB total), warm query 55–150 ms, threshold 0.7; real Bolt turn used mcp.archive.archive_search (first call 72 s cold, needs timeout_s 180). Limit: semantic recall + archive hybrid = two model copies (~3.2 GB). Owner paper = benchmark source (wiki/sources/archive-index-paper.md), not re-measured.

## Task 14 — eval corpus (ctx4096 complete, ctx8192 partial)
Corpus v2 109 cases (30 multi-step tools, 60-turn conversation), runner resumable. artifacts/task14-eval-2026-10-26: ctx4096 5 repeats = 541 runs, pass 0.81, protocol errors none, multi-step 117/150, TTFT p50 1.39 s p95 2.32 s, latency cold 5.45 s vs warm ~1.2 s. By category: adversarial 40/45 (exfiltration case: model called http_fetch to evil.example on explicit user request — policy gap, proposal: owner network allowlist), behavior 35/35, conversation 1/1, en 40/75, memory 60/70, tools 182/215, ua 80/100. Fixes found by this eval (after the ctx4096 code snapshot): 68a3f9c + d089bc6 reply language (en-v3 rerun EN 15/15, UA 19/20), 9e24942 Ukrainian inflections in memory search. ctx8192 run (47/109 runs, newer code, pass 0.979) interrupted — resume: `python evals/runner.py --out artifacts/task14-eval-2026-10-26 --profile ... --tokenizer ... --repeats 1 --num-ctx 8192`, then `--latency --num-ctx 8192`. A full ctx4096 re-run on current HEAD is needed for a post-fix number.

## Task 15 — stress/growth/soak (NOT complete)
Soak artifacts/task15-soak-2026-10-26: ran 14:13–15:32 UTC = 1 h 19 min (NOT 8 h; stopped on owner request). 2 model downtime windows, 1 SIGTERM restart + 1 manual restart, verify 2/2 ok, final verify ok, 15 forgotten markers absent from all state bytes, 0 orphans. Found and fixed: (1) O(audit) verification per transaction -> latency 159 ms -> 5.4 s (cd803eb incremental + data_version full-check); (2) growth benchmark: recent() 4.1 s @200k (25c0db6), purge = FTS rebuild O(n) ~1 s @200k kept by design (FTS5 secure-delete corrupts index on SQLite 3.45.1 — attempted in 25c0db6, reverted 8ffe34f with repair + regression test). Growth results artifacts/task15-growth-2026-10-26.json (pre-recent-fix). OPEN: worker RSS grows ~7 MB/min (113 -> 304 MB over 35 min) — cause not found (ModelProfile ruled out; gc-count probe interrupted). Next: run scratchpad-style probe `counts()` diff over 300/900 turns, fix, then a full 8 h soak.

## Task 18 — robotics (protocol only)
src/b12/robotics: single-writer MotionController (lease), angle/speed bounds reject (no clamp), stop/hold, sleep/wake, disconnect -> safe pose and no resume; SimulatedRobot; 10 protocol tests. Real Reachy SDK transport, Jetson config/measurements and physical acceptance: OPEN (no device).

## Task 19 — long horizon (driver only)
scripts/daily_check.py seed/check (anchors recall, forgotten marker absent from bytes, integrity, snapshots, verify_full). Smoke on scratch state day 0 ok. OPEN: real day 1/7/30 on the owner's real state (timer install needs owner).

## Tasks 16–17 — voice: deferred by owner decision 26.10.2026 (inventory: DMIC/analog devices; faster-whisper weights + stt_ua_fastconformer in HF cache; no UA TTS, no ffmpeg/sox).
## Task 20 — final audit: pending.
