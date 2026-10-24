---
type: decisions
updated: 2026-10-24
status: proposed
sources: [raw/B-12_Master_Project_2026-10-24.md, wiki/sources/llm-wiki.md]
tags: [adr, baseline]
---
# Реєстр рішень

IDs ADR-001–010 збережено з §16 master brief. Це запропоновані baseline, а не доказ реалізації або окремого затвердження власником кожної технології. Нормативні вимоги відрізняються від інженерних кандидатів.

| ID | Зміст | Статус знання / умова перегляду |
|---|---|---|
| ADR-001 | Local-first, хмара опційна | Вимога з brief; offline behavior перевіряється окремо |
| ADR-002 | System 1 / System 2 | Архітектурна пропозиція; підтвердити неблокувальний interrupt |
| ADR-003 | Append-only event ledger + typed permissions | Пропозиція; lifecycle/delete суперечність ще відкрита |
| ADR-004 | ASR → LLM/memory → TTS | Запропонований v1 шлях; оцінити latency й UA |
| ADR-005 | AEC3 + Silero + Smart Turn | Кандидати; duplex/endpoint tests перед остаточним вибором |
| ADR-006 | Piper UA | Кандидат; перевірити голос, engine/voice licenses й TTFA |
| ADR-007 | Bolt E4B кандидат, Gemma A/B baseline | Bolt пройшов [перший desktop smoke test](bolt-first-test.md); є поведінкові й context-budget недоліки. A/B і Jetson ще відкриті; остаточного вибору немає |
| ADR-008 | Wireless бажаний, Lite простіший bring-up | Уподобання з brief; купівля й transport proof не підтверджені |
| ADR-009 | Curiosity/initiative керуються runtime | Архітектурна пропозиція; довгі trace evaluations |
| ADR-010 | Не заявляти свідомість або guaranteed personality | Межа інтерпретації поведінки з brief |

## DOC-001 — ведення LLM Wiki

**Статус: прийнято прямим дорученням власника 24.10.2026.** Незмінений master brief у `raw/`; тематичний синтез у `wiki/`; [AGENTS.md](../../AGENTS.md) задає workflow. Рішення стосується ведення проєкту, не вибору роботизованого стеку. Джерело методу — [картка LLM Wiki](../sources/llm-wiki.md).

## Нові рішення, які ще потрібні

- Lifecycle персональних payload і похідних даних, [memory](../topics/memory.md).
- Exact consent/control boundary та права інструментів, [architecture](../topics/architecture.md).
- Host authoritative memory й режим без ноутбука, [hardware](../topics/hardware.md).
- Вимірюваний voice SLO і pinned benchmark settings, [voice](../topics/voice.md).

Прийняте рішення доповнювати датою, підставою, альтернативами, наслідками та evidence. Нову редакцію позначати як таку, що замінює стару; зміни фіксувати в [журналі](../log.md). [Відкриті питання](open-questions.md) залишаються активними до появи доказів.
