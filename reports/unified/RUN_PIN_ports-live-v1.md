---
type: report
updated: 2026-11-22
status: compiled
sources:
  - docs/superpowers/plans/2026-11-22-remaining-work-agy.md
  - reports/unified/oracle-review-ports-v1/README.md
  - reports/unified/oracle-review-ports-v1/codex-review-2.json
  - evals/unified/scenario_sets/ports-live-v1.json
tags: [track-r5, track-g, run-pin, ports-live-v1, owner-gate]
---

# Track R5 — Run Pin & Prerequisites for Track G (`ports-live-v1`)

**Freeze commit (`<FREEZE_COMMIT>`):** `4f5ad44c103ec33e4137f3b9c3ca863db8a16e96` (`4f5ad44` на гілці `feat/unified-dr2-dr3`, після завершення R1–R4, F1–F2, H4/H6 step 1/H7, виправлення зауважень Codex round 1, чистої рецензії Codex round 2 `514178e` і заморозки `ports-live-v1`; попередні R5/pin-документи додають лише цей файл і запис у `wiki/log.md` без змін у коді, тестах чи фікстурах).

**Попередній run pin (`R5`):** `12b7f45e05c71407a51349c116667223e7c70197` (`12b7f45`).

**Eval worktree:** `/home/cyberdid/Projects/B-12/.worktrees/eval-run` (переведено на detached `HEAD` коміту фіналізації цього піну; моделі в межах заморозки не запускалися, `unified-dr2-dr3` ніколи не використовується для модельних прогонів).

## Обов'язкові поля статусу й воріт власника

- Codex review of ports-live-v1: 22.11.2026 round 2 clean (8/8 ok in reports/unified/oracle-review-ports-v1/codex-review-2.json)
- Freeze status: FROZEN (коміт заморозки `4f5ad44c103ec33e4137f3b9c3ca863db8a16e96`, SHA-256 `4ee145e95243bc16a83ccdd0271f4fd8c3780ed677f4513a5f968d25189d7505`)
- Colab budget (hours): NO CAP. Owner, 22.11.2026: "на всі кредити можна, скоро новий місяць". Model runs may be queued; the orchestrator stops Colab when the queue is empty.

## Перевірені артефакти перед Track G

| Артефакт | Статус | SHA-256 / перевірка |
|---|---|---|
| `reports/unified/oracle-review-ports-v1/prompt-fixed.txt` | На місці (25K) | `9369c581a33c4ba0ccfbfc00495ed2c994388f6dbc1f86ded5935215c4f41df0` |
| `reports/unified/oracle-review-ports-v1/sheet-fixed.json` | На місці (21K) | `b17ecf23b512f19f192e9aa3f3bf9cbcea98aad4830c0f06551a20fe17b0652f` |
| `reports/unified/oracle-review-ports-v1/codex-review-2.json` | 8/8 `ok` (M89–M96) | Коміт `514178e` (0 minor, 0 major, 0 blocker) |
| `evals/unified/scenario_sets/ports-live-v1.json` | `status: "FROZEN"` (16 сценаріїв) | `4ee145e95243bc16a83ccdd0271f4fd8c3780ed677f4513a5f968d25189d7505`; `evals.unified.validate_scenarios` PASS; `pytest tests/unified/test_ports_live_v1.py` 8/8 PASS |

## Інтегровані коміти у `<FREEZE_COMMIT>` (`63d16c3..4f5ad44`)

- **Track R (гігієна):**
  - `45fdcbd` — R1: обмеження `Agent._tainted_history` (`deque(maxlen=1024)` + durable `control.meta`).
  - `7ade6fe` — R2: `_claimed_tools` (`unexecuted_claim`) і документація правила у `score_u2_u3.py` / `evals/unified/README.md` (усі arms у G2.5 мають бути перескоровані цією версією).
  - `133780e` — R4: `trap cleanup TERM INT`, `kill -TERM -- "-$DRIVER_PID"` і `B12_ORCH_DRYRUN=1` в `ops/remote/orchestrator.sh` + `tests/ops/test_orchestrator_term.sh`.
  - `821539c` — R3: `REVIEW_extra_changes_2026-11-22.md`, `TRACK_R_hygiene_2026-11-22.md`, запис у `wiki/log.md`.
- **Track F (ADR-021 skills):**
  - `8cf159e` — F1: `SkillStore`, `skill_view`, `Settings.skills=False`, `--skills` у `run_u2_u3.py`.
  - `adac2d6` — F2: `propose`/`approve`/`reject`/`pin`/`unpin`, JSONL `.ledger.jsonl`, `curate`, `source_forgotten`, `skill_propose`, CLI `b12 skills`, `Scheduler.curate_skills_idle`.
  - `55026af` — звіт `TRACK_F_skills_2026-11-22.md` і запис у `wiki/log.md`.
- **Track H (решта портів):**
  - `2717d87` — H4: `evals/unified/compaction_recall.py` (`trim` vs `trim+memory`, без `summary`).
  - `1b0efde` — H6 step 1: `WakeDetector` (`src/b12/audio/wake.py`), вікно `wake` у `LiveSession`, `Settings.wake_word=False` (без завантаження ONNX).
  - `dfcba6c` — H7: картка `wiki/sources/eywa-2026-11-22.md` (Eywa `arXiv:2605.30771`, LongMemEval-S / BEAM).
  - `12b7f45` — звіт `TRACK_H_remaining_ports_2026-11-22.md` і запис у `wiki/log.md`.
- **Track R5 + рецензії та заморозка `ports-live-v1`:**
  - `d7bde13`, `123407a`, `724b14e` — R5 pin та бюджет Colab (`NO CAP`).
  - `1618097` — Codex blind review round 1 (`review-codex-on-fixed.json`: 3 major, 2 minor).
  - `f389c25` — виправлення зауважень Codex round 1 (M89, M91, M94–M96) і оновлення `prompt-fixed.txt` / `sheet-fixed.json`.
  - `514178e` — Codex review round 2 (`codex-review-2.json`: 8/8 `ok`).
  - `1ff1a63` — рішення власника про повне відкладення wake word (H6 step 2 скасовано).
  - `4f5ad44` — заморозка `ports-live-v1` (`FROZEN`, `FROZEN_REVIEW_STATUS`, тести та [oracle-review-ports-v1/README.md](oracle-review-ports-v1/README.md)).

## Статус воріт перед запуском Track G

1. **Codex blind oracle review (`ports-live-v1`):** пройдено — round 2 чистий (`8/8 ok` у [codex-review-2.json](oracle-review-ports-v1/codex-review-2.json), коміт `514178e`).
2. **Freeze (`ports-live-v1.json`):** виконано в `4f5ad44` (`status: "FROZEN"`, SHA-256 `4ee145e95243bc16a83ccdd0271f4fd8c3780ed677f4513a5f968d25189d7505`, зафіксовано в [oracle-review-ports-v1/README.md](oracle-review-ports-v1/README.md)).
3. **Colab budget:** встановлено 22.11.2026 — `NO CAP` (кредити власника). Зупинка черги — порожня черга в `jobs.tsv`.
4. **Оркестратор (`ops/remote/orchestrator.sh`, R4 `133780e`):** запускається або перезапускається власником вручну з `B12_REPO=/home/cyberdid/Projects/B-12/.worktrees/eval-run` (агенти самі оркестратор не запускають).
5. **H6 Step 2 (openWakeWord ONNX):** повністю відкладено за рішенням власника `1ff1a63` (завантаження моделей і навчання скасовано, `wake_word=False`).
6. **H7 (кандидат Q23):** рекомендація не витрачати бюджет Track G на LongMemEval-S / BEAM, а після Track G розглянути легкий bulk-ingestion retrieval-sufficiency прогін зрізу 50–100 питань LongMemEval-S (MIT).
