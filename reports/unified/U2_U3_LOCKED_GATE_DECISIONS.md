---
type: decision
updated: 2026-11-18
status: owner_decided
sources: [reports/unified/U2_BREVITY_REPRODUCTION.md, reports/unified/U3_MEMORY_BASELINE_PROTOCOL.md, raw/CAPRI_DR2_DR3_MASTER_PLAN_2026-11-15.md, reports/unified/baseline/u2u3-smoke-2026-11-18.json]
tags: [U2, U3, gate, splits, scoring, margin]
---

# U2/U3 gate before freeze and the locked run — owner decisions, 18.11.2026

**Вимога власника** (відповіді в чаті Claude Code, 18.11.2026):

1. **Splits.** Поточні 60 сімейств (`u2-u3-draft-v4`) — `dev`/`validation`: їх уже проганяли на Bolt і правили (v2→v4), отже вони засвічені. Для `locked_test` пишуться **нові** сімейства (не менше 30 runnable на трек), з такими самими двома сліпими перевірками oracle до freeze. Їх не запускати на моделі до freeze.
2. **Semantic scoring у locked run:** два сліпі model-судді — Codex `gpt-6-luna` і agy **Gemini 4 Hydrogen** — плюс власник вирішує розбіжності (як у smoke-прогоні 18.11).
3. **Margin для U2:** зміну беремо в Capri, якщо вона покращує verified safe completion rate на рівні сімейства щонайменше на **+10 п.п.** без погіршення безпеки (forbidden effects, unsafe actions).

Наслідки для плану: locked-набір будується як окремий scenario set зі `split: locked_test`; U2 потребує ≥20 agentic і ≥10 casual/no-tool/ask сімейств, U3 — ≥30 runnable. Класи, які зараз BLOCKED (C20, C24–C26, C30, M28, M29) і ініціативні C27–C29 (немає event-каналу до U7), до 30 runnable не зараховуються.
