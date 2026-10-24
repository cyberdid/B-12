---
type: questions
updated: 2026-10-24
status: open
sources: [raw/B-12_Master_Project_2026-10-24.md, wiki/project/analysis.md]
tags: [unknowns, validation]
---
# Відкриті питання

Q1–Q12 зберігають порядок §14 master brief; Q13–Q18 додані аналізом і експериментами. Усі відкриті, крім Q15, закритого аудитом характеристик локального host. Питання не є вимогою зараз відповісти на всі: наступна робота може уточнювати їх поступово.

| ID | Питання | Як закрити |
|---|---|---|
| Q1 | Де попередній B-12 source repo? | Точний path/URL/revision і огляд складу |
| Q2 | Що справді реалізовано в memory kernel? | Schema, tests, запуск і сирі логи; за відсутності — рішення про новий PoC |
| Q3 | Lite чи Wireless? | Media proof, сценарій використання, бюджет і підтверджене рішення |
| Q4 | Чи працює Wireless full-duplex/barge-in? | Audio-only latency/reconnect/AEC test на доступному обладнанні |
| Q5 | Чи вміщуються Bolt/Cosmos/voice у 8GB? | Окремий і joint profiling цільової конфігурації |
| Q6 | Чи відповідає Bolt українським сценаріям? | [Перший smoke test](bolt-first-test.md) дав зрозумілу українську, правильний JSON/tool proposal і поведінкові недоліки. Потрібні UA/EN corpus, rubric та порівняння; питання не закрито |
| Q7 | Де виконувати LLM, memory й vision? | Host profiles, latency і offline/degraded-mode test |
| Q8 | Яка мінімальна модель/детектор зору потрібна? | Task-based порівняння light detector/VLM та Cosmos on-demand |
| Q9 | Який фізичний UX mute/consent? | Control contract і негативний тест: LLM-текст не встановлює згоду |
| Q10 | Що в v1 означає самостійне навчання? | Окремі критерії memory growth, skill acquisition і weight training |
| Q11 | Які інструменти дозволені автономно? | Allowlist, resource limits, permissions, cancellation tests |
| Q12 | Який баланс тиші й ініціативи? | Quiet-mode policy і оцінка доречних/небажаних втручань |
| Q13 | Як реалізувати забуття при append-only? | Payload/index/reflection/cache/backup lifecycle і deletion verification |
| Q14 | Що живе volatile до дозволу на запис? | Event flow з TTL/retention та тест відсутності durable витоку |
| Q15 | Який локальний host доступний зараз? | **Закрито для характеристик:** [аудит 24.10.2026](model-test-readiness.md) встановив CPU/GPU/RAM/ОС/runtime/storage. Продуктивність і прийнятний бюджет під навантаженням ще не виміряні |
| Q16 | Що саме означає voice <1,5 с? | Початок/кінець виміру, перцентиль, сценарій, число повторів |
| Q17 | Які точні версії та ліцензії кандидатів? | Для першого Bolt тесту pinned GGUF/revision/hash, Ollama 0.33.3 та tensor equivalence перевірено. Повний license inventory, голоси й інші кандидати ще відкриті |
| Q18 | Як запобігти втраті instructions при context overflow? | [Тест 2048](bolt-first-test.md) виявив truncation з утратою інструкцій; потрібні явний token budget, контроль відмови/скорочення й regression tests до довгих діалогів |

Q1/Q2/Q13/Q14 залишаються фундаментальними для runtime. Перший Bolt smoke test завершено; наступні дослідження мають уточнювати Q6/Q17/Q18. Конкретний [наступний крок](status.md), [аналіз ризиків](analysis.md) та [дорожня карта](roadmap.md) пов’язують питання з роботою.

Наданий [archive-index-public](../sources/archive-index-public.md) закриває пошук кандидата для retrieval, але не Q1/Q2 про походження історичного B-12 ledger. Перед reuse лишаються exact policy scope, invalidation після запису й окремий огляд відмінної локальної інсталяції.
