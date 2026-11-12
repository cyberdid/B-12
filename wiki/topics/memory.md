---
type: topic
updated: 2026-11-12
status: partially_implemented
sources: [raw/B-12_Master_Project_2026-10-24.md, src/b12/memory.py, tests/integration/test_memory_restart.py, tests/security/test_memory_isolation.py, src/b12/semantic.py, evals/capri_comprehensive/runners/semantic_calibration.py, tests/unit/test_memory.py]
tags: [memory, privacy, consent]
---
# Пам’ять і приватність

**Зі слів brief §5:** ранній SQLite append-only kernel і заміри retrieval існували. У цій теці немає їхнього коду, схеми чи логів. Не використовувати згадані 150 мс або ~1 с на 200 спогадах як наш baseline.

**Перевірений факт, нова реалізація:** Task 2 (`d18441c`) створює власний canonical MemoryStore; старий історичний kernel цим не знайдено й не імпортовано. Independent spec/quality review пройдені; 23 storage tests і загальний suite 117 пройшли на цьому checkpoint. [Реалізація та межі](../project/implementation.md).

**Пропозиція:** observations → policy/identity/consent → дозволені durable events → candidate memories → контрольований запис → lexical/metadata index → за потреби semantic index → consolidation/reflection. Наявність спостереження не створює дозволу на довготривале збереження.

Working, episodic, semantic, autobiographical, procedural, social, research і self-model — логічні види пам’яті. Їх не обов’язково реалізовувати як вісім баз. Кожен довготривалий висновок має посилатися на дозволені джерела та розрізняти спостереження, чужі слова й гіпотезу. [Рефлексія](autonomy.md) не підміняє первинні свідчення.

**Інваріанти з brief:** `consent_given` походить з контрольного/апаратного шляху; OWNER/GUEST не визначається лише текстом; гості не отримують постійного voiceprint за замовчуванням; raw mic не архівується автоматично. Speaker verification не є самодостатньою авторизацією. Власне TTS і фонове медіа фільтруються перед записом.

## Суперечності та стан вирішення

1. **Append-only і видалення.** У новому canonical store append-only стосується payload-free audit; персональний payload/evidence/FTS фізично очищується через secure delete, FTS rebuild та WAL checkpoint. Durable tombstone/outbox фіксуються перед очищенням; busy/failed cleanup не стає complete. Це перевірено локально. Task 7 додав global `PurgeCoordinator` із hooks sessions/active turns/backups/provider cache ([деталі й межі](agent-loop.md)); goals hook з’явиться разом із goals (Task 11). Початкові варіанти redaction/cryptographic erasure замінено цим конкретним storage рішенням; SSD remanence і зовнішні snapshots тестами не доведені.
2. **Short-term log і відсутність згоди.** Назва «короткотривалий» не гарантує volatile storage. До перевірки політики персональний observation має лишатися в пам’яті процесу з TTL; durable ledger не повинен отримувати заборонений зміст навіть тимчасово. Це запропоноване уточнення контракту.
3. **Успадковані дані.** Рефлексія або embedding також може містити видалену інформацію. Потрібні залежності від evidence IDs та перевірка каскадного видалення.

**Перевірка:** recall через 1/7/30 днів; суперечності; reboot; відсутність доступу гостя до owner-пам’яті; відмова записати без згоди; повне видалення й відкликання; P50/P95 retrieval для 200/2 000/20 000/200 000 подій. [Аналіз](../project/analysis.md) пояснює порядок робіт, [питання](../project/open-questions.md) відстежують невизначеність.

## Наявний кандидат для derived retrieval

Власник надав [archive-index-public](../sources/archive-index-public.md). Review підтвердив готові SQLite FTS5/search/provenance компоненти; 17 базових тестів пройшли. Це дозволяє [повторно використати пошук](archive-retrieval.md), залишивши canonical events/consent окремим шаром. Mutable index не замінює append-only історію, а постійний VectorCache потребує invalidation після змін. Попередній B-12 kernel цим не знайдено.

## Ізоляція акторів, згода і резерв диска (12.11.2026)

- **Перевірений факт:** пам'ять відокремлена за `actor_id` на рівні SQL. Через рантайм гість не отримує ні записів власника, ні шляху до його домашньої теки; системний промпт називає роль співрозмовника з контрольного каналу. Попередній «витік» MEM-05 спричиняв стенд оцінки, що обходив рантайм.
- **Перевірений факт:** без згоди промпт прямо каже моделі, що пам'ять вимкнена.
- **Перевірений факт:** запис у пам'ять відхиляється з `disk_space_low` до будь-якої зміни, якщо вільного місця менше за `min_free_mb` (типово 50).
- **Перевірений факт (калібрування семантичного порогу):** на 24 питаннях сценаріїв і 570 явно нерелевантних парах EmbeddingGemma 2 дає медіану близькості 0,64 і 90-й перцентиль 0,70 для нерелевантного. Поріг 0,65 пропустив би 39% шуму, 0,68 — 15%, 0,7 — 9%. Тому поріг `min_score = 0,7` залишено; запис про Neovim (0,68) у JOURNEY-04 від шуму не відділяється. Артефакт: `evals/capri_comprehensive/artifacts/semantic_calibration.json` (локально), скрипт `runners/semantic_calibration.py`.
- **Перевірений факт:** актуальні вподобання співрозмовника (`GoalStore.current_preferences`, останнє не відкликане значення кожного ключа, до 16) додаються до системного повідомлення як дані, лише за згоди і лише його власні. Раніше модель їх не бачила зовсім. На Bolt це допомогло з одиницями температури (LT-07), але не з редактором.
- **Перевірений факт:** `memory_store` приймає `supersedes` — id старих записів, які замінює новий факт. Вони стають `stale` з причиною `superseded`: лишаються видимими власнику й не стираються, але не беруть участі в автоматичному пригадуванні; `memory_search` показує статус. Чужі або вигадані id відхиляються до запису. У фінальному прогоні ні Bolt, ні gemma механізмом не скористались (MEM-07).
- **Перевірений факт:** оскільки моделі не передавали `supersedes` самі, `memory_store` тепер повертає до трьох старіших живих записів, що мають з новим фактом щонайменше два спільні змістові слова (`similar_active`), з підказкою. Новий інструмент `memory_supersede(memory_id, replaced_by)` знімає старий запис з ужитку на користь нового (запис лишається, не стирається; лише живі записи того самого актора; не можна замінити запис ним самим).
