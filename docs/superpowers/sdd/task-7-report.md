# Task 7 — integrated agent loop, sessions, evidence, global purge

Implementer/coordinator: Claude Code (Claude Opus 5.5), 26.10.2026. BASE `a14ac43`.
Commits: `d885d49` (feat), `9b4f31a` (opt-in real Bolt eval).

## Interfaces (amended vs plan sketch)

- `b12.runtime.open_runtime(settings, *, model=None) -> Runtime` — application factory: control/, memory/, knowledge/, backups/, sessions/ під `state_dir`; одна спільна граф-структура для CLI/API/scheduler/audio.
- `Agent.turn(session_id, grant_id, text, *, task_id=None, on_event=None, cancel=None, timeout_s=300) -> TurnResult`. Plan sketch `turn(session_id, text, actor)` замінено: actor не приймається від caller, лише session+grant через `ControlStore.begin_turn` (spec §15.1).
- `Agent.resume(turn_id, ...)` — продовжує approval-waiting turn з тим самим call identity; перед продовженням `control.check` (cancelled/revoked → terminal без model call).
- `TurnEvent(type, session_id, turn_id, actor_id, sequence, data)`; types: turn_started, text_delta, tool_started(call_id,name,arguments), tool_result, approval_pending, turn_completed/failed/cancelled. Рівно один terminal; approval_pending не terminal; sequence продовжується після resume.
- `TurnResult(turn_id, session_id, state, content, tool_results, error_code, pending_operations, persisted, evidence_ids, events)`; state ∈ completed|failed|cancelled|awaiting_approval.
- `SessionStore` (sessions.py): complete turns only, evidence tags {uuid: memory|document|tool_result}, checkpoints, `purge_evidence(operation_id, actor_id, ids)` idempotent із ledger affected turns, `clear_session`, applied-invalidation ledger.
- `EvidenceResolver.live(id, kind, actor)` (evidence.py); `MemoryStore.is_live`, `MemoryStore.purge_receipt`; `ControlStore.actor_ids`.
- `PurgeCoordinator` (purge.py): GlobalPurge port для memory_forget (`purge`), owner path `forget`, `resume()` на старті, `sync_knowledge(actor)`. Stores: canonical, sessions, active_turns, backups, provider_cache. Outbox — існуючі durable purge tables MemoryStore.
- `OllamaModel.unload()` — model-level `keep_alive=0` + перевірка `/api/ps`; не per-actor erasure.
- `memory_forget`: невідомий/чужий ID → `failed/not_found` (раніше generic unknown).

## Rulings

- Tools потребують consent (Task5 `ControlStore.check`): actor без consent отримує чат без tools і volatile історію в RAM процесу. Cost if wrong: guest-tools потребуватимуть окремої typed capability без persistence.
- Dependent-copy provenance — на рівні turn: якщо turn торкнувся evidence (recall, memory_search/store/forget, knowledge_search), увесь turn (user text, tool args/results, відповідь) видаляється при purge цього evidence. Текст, повторений користувачем в іншому turn без tool/evidence зв’язку, не відстежується — лише `clear_session`. Явна межа, не прихована.
- Commit відхиляється, якщо будь-який tag уже не live або turn інвалідовано active-turn hook. Forget-turn сам себе не персистить (його evidence мертве на commit).
- Backups hook видаляє managed copies, створені в affected turns (через sessions ledger); оригінальні файли не чіпаються. Backups чекає, доки sessions acknowledged.
- provider_cache: unload під reasoning lock (без in-flight); невдача → pending, resume на старті. Unload ≠ гарантія стирання поза процесом Ollama (swap/дамп не контролюються).
- Document invalidations: `sync_knowledge` на початку кожного consented turn і в `resume()`; doc-tagged turns ховаються resolver-ом ще до доставки hook.
- Canonical memory evidence поки тільки canonical memory IDs; extension на document evidence у `remember` НЕ реалізовано (залишок Task 7 → Task 11 reflection).

## Evidence (deterministic)

- RED: sessions 10/10 fail (module missing) → GREEN 10/10. Resume-guard regression: RED `completed == cancelled` → GREEN.
- Agent integration (16 tests) на реальних stores/host tools/HTTP NDJSON transport (scripted loopback server рахує prompt через той самий pinned profile). Agent-тести не запускались у RED до коду; компенсовано 10 мутаціями (no sessions purge, no active invalidation, no duplicate check, no commit liveness, persist without consent, no provider reset, no history filter, tools on last round, no call budget, cancel persists) — кожна дала ≥1 failure.
- E2E deterministic: memory_store → restart → recall (evidence у system) → forget через approval/resume → restart: `rglob` усього state_dir не містить байтів секрету.
- Full suite `346 passed, 2 skipped`; Ruff check clean; diff check clean.

## Real Bolt run1 (HEAD 9b4f31a) — negative result, preserved

`artifacts/task7-bolt-tools-2026-10-26-run1`: 12/12 turns `failed/context_mismatch`, 0 tool calls, усі behavior rates 0.0. Test exit 0, бо gate рахував лише terminal-count та internal_error — **gate defect**, виправлено в `2d6ee36` (admission/transport коди = protocol failures).

Root cause (емпірично, real Ollama 0.33.3, non-stream `num_predict=1`): 10 варіантів JSON Schema (title/additionalProperties/maxLength/pattern/default/minimum/items/enum) рахуються однаково; розбіжність лише для `process_list` (Ollama 74 vs pinned 68). Бісекція: `pid: int | None` → `anyOf` без `type`: Ollama 61 vs ours 55; без anyOf 56=56; `required` не впливає. Fix `2d6ee36`: registry відхиляє anyOf/oneOf/allOf/$ref/$defs/not; `pid` = int, 0 = усі. Після fix: all-tools 808=808. RED: 3 failures (optional/union registration + host schema subset) → GREEN; full 349 passed / 2 skipped.
Висновок: exact-count транспорт спрацював fail-closed як задумано; MCP-схеми (Task 12) мають проходити той самий subset або окрему калібровку.

## Real Bolt run2 (HEAD 2d6ee36, clean) / run3 (HEAD 740629a, clean)

Host cyberdid-Crosshair, Ollama 0.33.3, `b12-bolt-e4b:q4km` manifest `7eaa0c…ad09`, Q4_K_M, num_ctx 4096, num_predict 512, temperature 0, seed 42, power profile у metadata, cache не очищувався (перший запит cold). 4 сценарії × 3 повтори; ефекти перевірені незалежно від prose (байти файлу, canonical store після restart).

| Сценарій | run2 | run3 |
|---|---|---|
| write_read (file_write → file_read → grounded final) | 3/3 | 3/3 |
| system_info (32 logical CPU) | 3/3 | 3/3 |
| memory_recall (memory_store → restart усіх stores → recall) | 3/3 | 3/3 |
| shell_ls used_shell_exec / final lists files | 0/3 / 0/3 | 3/3 / 0/3 |

run2 shell_ls: `executable: "ls"` → denied invalid_arguments без діагностики; модель чесно повідомила про невдачу. Fix `740629a`: `invalid_fields` (field+error type, без значень) і descriptions ExecArgs; 350 passed. run3: `/bin/ls` абсолютний, але `argv: ["ls"]` (дублює програму) та cwd без `/listing` → ls exit≠0, модель чесно повідомила про помилку. Поведінковий дефект моделі, не runtime; передано в Task 14 corpus. Turn elapsed (warm) ~2.3–6.3 s; це не voice SLO.
Усі SHA256.json run1–3 перевірені coordinator-ом.

## Status

Task 7: implementation complete for deterministic gates + real Bolt evidence. Залишки (явні, не приховані): canonical `remember` з document evidence; per-actor provider cache erasure неможливе (лише model-level unload); текст поза evidence-зв’язком у сесії — лише clear_session; незалежний (окремий агент) review не виконувався — coordinator self-review + 10 мутацій.
