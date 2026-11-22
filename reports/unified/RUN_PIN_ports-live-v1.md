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

**Pin commit (`<PIN>`):** `12b7f45e05c71407a51349c116667223e7c70197` (`12b7f45` на гілці `feat/unified-dr2-dr3`, після завершення та інтеграції R1–R4, F1–F2, H4/H6 step 1/H7; наступний коміт Track R5 додає лише цей файл і запис у `wiki/log.md` без змін у коді, тестах чи фікстурах).  
**Eval worktree:** `/home/cyberdid/Projects/B-12/.worktrees/eval-run` (переведено на detached `HEAD` після коміту R5; моделі в межах R5 не запускалися, `unified-dr2-dr3` ніколи не використовується для модельних прогонів).

## Обов'язкові поля статусу й воріт власника

- Codex review of ports-live-v1: PENDING_OWNER
- Freeze status: DRAFT_PENDING_OWNER_REVIEW (awaiting owner's Codex review)
- Colab budget (hours): PENDING_OWNER (do not queue model runs until set by owner)

## Перевірені артефакти перед Track G

| Артефакт | Статус | SHA-256 / перевірка |
|---|---|---|
| `reports/unified/oracle-review-ports-v1/prompt-fixed.txt` | На місці (23K) | `bacfaa6425ee4ec513ebdccb4592aacf7b70050a32f28c112e3301c5ac25977e` |
| `reports/unified/oracle-review-ports-v1/sheet-fixed.json` | На місці (21K) | `15a1f4ee534ee1d7438e9852200f86eb258f61e6e4ca4dc1167e023a3fa8e95e` |
| `evals/unified/scenario_sets/ports-live-v1.json` | `status: "DRAFT"` (не заморожено) | `415d100e1b672a4ecba90ae007eb58115524fc27e2beabd9523c715acc026915`; `evals.unified.validate_scenarios` PASS |

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

1. **Codex blind oracle review (`ports-live-v1`):** власник запускає сліпий огляд на [prompt-fixed.txt](oracle-review-ports-v1/prompt-fixed.txt) / [sheet-fixed.json](oracle-review-ports-v1/sheet-fixed.json) з [schema.json](oracle-review-ports-v1/schema.json).
2. **Freeze (`ports-live-v1.json`):** після позитивної рецензії власника оновити статус маніфесту на `FROZEN` і зафіксувати фінальний SHA-256 у [oracle-review-ports-v1/README.md](oracle-review-ports-v1/README.md).
3. **Colab budget (hours):** власник задає числовий ліміт годин у цьому файлі; до появи числа модельні завдання у `jobs.tsv` ставити заборонено.
4. **Перезапуск оркестратора (R4):** власник вручну перезапускає запущений `ops/remote/orchestrator.sh`, щоб підхопити `133780e`.
5. **H6 Step 2 (openWakeWord ONNX):** очікує окремого схвалення власника на завантаження (`melspectrogram.onnx`, `embedding_model.onnx`, вибір між `hey_jarvis_v0.1.onnx` під CC-BY-NC-SA-4.0 чи власним класифікатором «Капрі», а також `onnxruntime` vs пакет `openwakeword`).
6. **H7 (кандидат Q23):** рекомендація не витрачати бюджет Track G на LongMemEval-S / BEAM, а після Track G розглянути легкий bulk-ingestion retrieval-sufficiency прогін зрізу 50–100 питань LongMemEval-S (MIT).
