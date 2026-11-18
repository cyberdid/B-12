---
type: source
updated: 2026-11-18
status: compiled
sources: [raw/CAPRI_DR2_DR3_MASTER_PLAN_2026-11-15.md, raw/source-manifest.json]
tags: [master-plan, DR2, DR3, MVP, proposed]
---
# Unified master plan DR2/DR3

## Походження і межі

- **Вимога власника / джерело:** локальний файл `/home/cyberdid/Downloads/CAPRI_DR2_DR3_MASTER_PLAN_2026-11-15.md`, редакція 1.0 від 15.11.2026.
- Незмінну копію збережено в [`raw/`](../../raw/CAPRI_DR2_DR3_MASTER_PLAN_2026-11-15.md). SHA-256: `e350d34cadfd3316dba91e379932f11535a70f3c14aac964ecea3b862d35fb9c`; той самий digest записано у [`source-manifest.json`](../../raw/source-manifest.json).
- Перевірено: керівне резюме, стан/прогалини, архітектурні інваріанти, U0–U10 roadmap, definition of done та межі тверджень. Інші тематичні розділи індексовано за заголовками, але не повністю перевірено в цьому проході.
- Це **пропозиція та критерії майбутньої роботи**, а не доказ реалізації, вимірювання або приймання. Сам документ зазначає базовий кодовий зріз `36d557d83ce2f44f694cea5d19939031c630a471`; виконання перевіряється за фактичним HEAD, кодом і артефактами.
- GitHub URL, згаданий у документі, позначений у маніфесті як згаданий, але не перевірений незалежно.

## Синтез для проєкту

План об'єднує два шари однієї системи:

1. **DR2 — Memory & Continuity:** канонічні епізоди/твердження, temporal validity, provenance, суперечності, forgetting, scoped preferences та перевірка впливу пам'яті на рішення.
2. **DR3 — Cognitive Control & Autonomy:** типізована задача, розділення `plan / execute / verify / render`, permissions, task recovery, initiative, cancellation та тиша/відкладення.

Запропоновані інваріанти: local-first; модель змінна; runtime є джерелом істини для дозволів і стану; кожна дія має перевірюваний результат; `model_said_done` не дорівнює `verified_done`; невідомий side effect не повторюється наосліп; реальні, синтетичні й симульовані результати обліковуються окремо.

### Roadmap та gate-статуси

| Етап | Зміст | Поточний статус у цьому worktree |
|---|---|---|
| U0 | baseline, threat model, evaluation contracts | Частково: audit/ledger є; acceptance і ретест усіх сценаріїв відкриті |
| U1 | common IDs, privacy-safe telemetry та causal trace | Scaffolding є; повний contract і верифікатор відкриті |
| U2 | control/style A/B, router, verifier | Історичні результати збережені; нові arms не завершені |
| U3 | memory continuity baseline і snapshots | Synthetic snapshot scaffolding є; повний frozen benchmark не завершений |
| U4–U9 | temporal memory, preferences, durable tasks, initiative, model swap, journeys | Не прийняті як завершені за цим аудитом |
| U10 | незалежний аудит і release gate | Не розпочато як фінальна acceptance |

Ці оцінки — поточне зіставлення артефактів у worktree з вимогами плану, не твердження про весь production/main стан.

## Підстави та навігація

- [Unified master plan (raw)](../../raw/CAPRI_DR2_DR3_MASTER_PLAN_2026-11-15.md)
- [MVP acceptance ledger](../../reports/unified/MVP_ACCEPTANCE_LEDGER.md)
- [U0 baseline audit](../../reports/unified/U0_BASELINE_AUDIT.md)
- [MVP readiness](../../reports/unified/MVP_READINESS_2026-11-18.md)
- [Scenario execution paths and retest order](../../reports/unified/SCENARIO_EXECUTION_PATH_AUDIT.md)

## Відкриті питання

- Чи кожен U0/U1 exit criterion забезпечений тестом з runtime-faithful oracle та артефактами?
- Які з 92 historical scenario IDs повторно перевірені на поточному code/runtime/model snapshot?
- Які U4–U9 механізми виправдовують складність виміряною користю та які мають лишитися proposed?
- Які blocked real-time, voice, hardware і Day 7/Day 30 gates входять у MVP-визначення власника, а які потребують окремої фізичної/часової acceptance?
