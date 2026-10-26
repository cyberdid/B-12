---
type: topic
updated: 2026-10-26
status: partially_implemented
sources: [raw/B-12_Master_Project_2026-10-24.md, src/b12/memory.py, tests/integration/test_memory_restart.py, tests/security/test_memory_isolation.py]
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
