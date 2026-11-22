---
type: report
updated: 2026-11-22
status: compiled
sources:
  - docs/superpowers/plans/2026-11-22-remaining-work-agy.md
  - reports/unified/oracle-review-ports-v1/README.md
  - evals/unified/scenario_sets/ports-live-v1.json
tags: [track-r5, track-g, run-pin, ports-live-v1, owner-gate]
---

# Track R5 — Run Pin & Prerequisites for Track G (`ports-live-v1`)

**Pin commit (`<PIN>`):** `12b7f45e05c71407a51349c116667223e7c70197` (`12b7f45` на гілці `feat/unified-dr2-dr3`, після завершення та інтеграції R1–R4, F1–F2, H4/H6 step 1/H7; фінальні документи R5 додають лише цей файл і запис у `wiki/log.md` без змін у коді, тестах чи фікстурах).

**Eval worktree:** `/home/cyberdid/Projects/B-12/.worktrees/eval-run` (переведено на detached `HEAD` після фінального коміту R5; моделі в межах R5 не запускалися, `unified-dr2-dr3` ніколи не використовується для модельних прогонів).

## Обов'язкові поля статусу й воріт власника

- Codex review of ports-live-v1: 22.11.2026 findings (`reports/unified/oracle-review-ports-v1/review-codex-on-fixed.json`: M89, M91 minor; M94, M95, M96 major) fixed 22.11.2026; owner re-review on updated `prompt-fixed.txt` / `sheet-fixed.json` required
- Freeze status: DRAFT (blocked pending clean Codex re-review of the 22.11.2026 oracle fixes; freeze only after a clean re-review)
- Colab budget (hours): NO CAP. Owner, 22.11.2026: "на всі кредити можна, скоро новий місяць". Model runs may be queued; the orchestrator stops Colab when the queue is empty.

## Перевірені артефакти перед Track G

| Артефакт | Статус | SHA-256 / перевірка |
|---|---|---|
| `reports/unified/oracle-review-ports-v1/prompt-fixed.txt` | На місці (25K) | `9369c581a33c4ba0ccfbfc00495ed2c994388f6dbc1f86ded5935215c4f41df0` |
| `reports/unified/oracle-review-ports-v1/sheet-fixed.json` | На місці (21K) | `b17ecf23b512f19f192e9aa3f3bf9cbcea98aad4830c0f06551a20fe17b0652f` |
| `evals/unified/scenario_sets/ports-live-v1.json` | `status: "DRAFT"` (не заморожено) | `89b01a7940b38af16e21fa3e21b5ae82e4cda080b28bab6b34916be73209da01`; `evals.unified.validate_scenarios` PASS |

## Інтегровані коміти у `<PIN>` (`63d16c3..12b7f45`)

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

## Блокери / Stop-and-Ask перед запуском Track G

1. **Codex blind oracle review (`ports-live-v1`):** власник запускає повторну сліпу рецензію на оновлених [prompt-fixed.txt](oracle-review-ports-v1/prompt-fixed.txt) / [sheet-fixed.json](oracle-review-ports-v1/sheet-fixed.json) з [schema.json](oracle-review-ports-v1/schema.json).
2. **Freeze (`ports-live-v1.json`):** після позитивної рецензії власника оновити статус маніфесту на `FROZEN` і зафіксувати фінальний SHA-256 у [oracle-review-ports-v1/README.md](oracle-review-ports-v1/README.md).
3. **Colab budget:** встановлено 22.11.2026 — без ліміту (кредити власника). Ліміт не є причиною відкладати прогони; зупинка черги — порожня черга в `jobs.tsv`.
4. **Перезапуск оркестратора (R4):** власник вручну перезапускає запущений `ops/remote/orchestrator.sh`, щоб підхопити `133780e`.
5. **H6 Step 2 (openWakeWord ONNX):** очікує окремого схвалення власника на завантаження (`melspectrogram.onnx`, `embedding_model.onnx`, вибір між `hey_jarvis_v0.1.onnx` під CC-BY-NC-SA-4.0 чи власним класифікатором «Капрі», а також `onnxruntime` vs пакет `openwakeword`).
6. **H7 (кандидат Q23):** рекомендація не витрачати бюджет Track G на LongMemEval-S / BEAM, а після Track G розглянути легкий bulk-ingestion retrieval-sufficiency прогін зрізу 50–100 питань LongMemEval-S (MIT).
