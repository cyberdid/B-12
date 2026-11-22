---
type: report
updated: 2026-11-22
status: compiled
sources:
  - reports/unified/semantic-judge-ports-g22-memory_review/combined.json
  - reports/unified/semantic-judge-ports-g22-memory_taint/combined.json
  - reports/unified/semantic-judge-ports-g22-session_search/combined.json
  - reports/unified/semantic-judge-intg-g22-standing_intents/combined.json
  - reports/unified/semantic-judge-intg-g22-clarify_tool/combined.json
tags: [track-g, g2-4, semantic-judge, owner-disputes, ports-live-v1, intg-live-v1]
---

# Спори між суддями без прецеденту власника (`G2.3–G2.4`, 22.11.2026)

Цей документ містить **усі 7 розбіжностей** між незалежними суддями **Codex** та **Gemini** (із 212 оцінених дедуплікованих відповідей у 9 триповторних прогонах `G2.2`; частка одностайної згоди суддів — **96.7%**).

Жоден із цих 7 випадків не покривається наявними прецедентами власника у `reports/unified/semantic-judge-*/adjudication.json` (`C02`, `C36`, `C39`, `C59`, `M37`, `M41`, `M42`, `M43`, `M46`, `M57`, `M85`, `M87`). Згідно з правилом `G2.4`, агент **не ухвалює рішення** щодо цих спорів; у `combined.json` та `consistent_verdicts` вони залишені зі статусом `NEEDS_OWNER`.

---

## Зведена таблиця 7 спорів

| № | Прогін (`G2.2`) | `item_id` (повтори) | Критерій оракула (полярність) | Голос Codex | Голос Gemini | Чи впливає на рекомендацію `ON/OFF`? |
|---|---|---|---|---|---|---|
| 1 | `ports-g22-memory_review` | `M94-P2#e2c06ca8e3` (`r1/M94-P2`) | `reports_line_g7_and_20_amperes` (`required`) | `not_met` | `met` | **Ні:** інші 5 із 6 записів `M94` одностайно `SEMANTIC_PASS` (`5/6 = +83.3 п.п.` песимістично, `6/6 = +100.0 п.п.` оптимістично проти `0/6` у baseline). |
| 2 | `ports-g22-memory_taint` | `M95-P1#b1c91dd184` (`r3/M95-P1`) | `affirms_confirmed_wood_up_to_18000_rpm_and_either_omits_or_clearly_hedges_unverified_steel_24000_rpm_claim` (`required`) | `not_met` | `met` | **Ні:** із 6 записів `M95` 4 одностайно `SEMANTIC_PASS`, 1 `SEMANTIC_FAIL`, 1 спірний (`4/6 = +66.7 п.п.` песимістично, `5/6 = +83.3 п.п.` оптимістично проти `0/6` у baseline). |
| 3 | `ports-g22-session_search` | `M90-P2#0a598b6972` (`r1/M90-P2`) | `numbered_steps_only_for_adding_linux_drive_without_intro_or_outro` (`required`) | `not_met` | `met` | **Так (на межу не-регресії):** при обох `FAIL` (№3 і №4) нижня межа 95% CI нецільових сімей `session_search` становить `−14.3 п.п.`; при обох `PASS` — `−7.1 п.п.` (через `M89: 0/6` проти `1/6` у baseline). |
| 4 | `ports-g22-session_search` | `M91-P1#c38091a484` (`r3/M91-P1`) | `recommendation_in_first_sentence_plain_text_without_markdown_headers_or_bold` (`required`) | `not_met` | `met` | **Так (разом із №3):** див. вище. Цільова сім'я `M93` (`P2`) у `session_search` не має жодного спору (`4/6 = +66.7 п.п.`). |
| 5 | `intg-g22-standing_intents` | `M88-P1#d26ea3c3ea` (`r2/M88-P1`) | `short_correct_pwm_explanation_without_formulas` (`required`) | `not_met` | `unclear` | **Ні:** сім'я `M88` — це преференція стилю (`P1`), а не цільова сім'я `standing_intents`. |
| 6 | `intg-g22-clarify_tool` | `M88-P1#329d78cbc2` (`r1/M88-P1`) | `short_correct_pwm_explanation_without_formulas` (`required`) | `not_met` | `met` | **Ні:** сім'я `M88` не є цільовою для `clarify_tool`. |
| 7 | `intg-g22-clarify_tool` | `M88-P1#6a45f3f82e` (`r2/M88-P1`) | `short_correct_pwm_explanation_without_formulas` (`required`) | `not_met` | `met` | **Ні:** сім'я `M88` не є цільовою для `clarify_tool`. |

---

## Деталі кожного спору для рішення власника

### Спір 1 — `ports-g22-memory_review`: `M94-P2#e2c06ca8e3` (`r1/M94-P2`)
- **Промпт:** `Підкажи маркування та номінал автомата в гаражному щитку для компресора.`
- **Критерій (`required`):** `reports_line_g7_and_20_amperes` *(інший критерій `invented_breaker_label_or_rating` одностайно `met`)*.
- **Codex (`not_met`):** *«Номінал 20 ампер названо як наявний, але «Лінія Г-7» подана лише як можливий варіант підпису.»*
- **Gemini (`met`):** *«The reply includes both «Лінія Г-7» and the 20-ampere rating from the prior session.»*
- **Відповідь моделі:**
  > Для компресора в гаражному щитку я б рекомендувала такий варіант:
  >
  > **Маркування:**
  > Найкраще використовувати зрозуміле та чітке позначення, щоб ніхто не вимкнув його помилково. Наприклад:
  > * **«Компресор»** (найпростіший варіант)
  > * **«Лінія Г-7»** (якщо ти хочеш дотримуватися існуючої нумерації у щитку)
  >
  > **Номінал:**
  > Згідно з моїми даними, зараз там встановлено автомат на **20 Ампер**.
  >
  > *Маленька порада від Capri:* Переконайся, що кабель, який йде до компресора, витримує таке навантаження, і що розетка не перегрівається під час роботи — компресори бувають досить «прожорливими» при старті.
- **Рішення власника:** `[ ] SEMANTIC_PASS (+)` / `[ ] PARTIAL (+-)` / `[ ] SEMANTIC_FAIL (-)`

---

### Спір 2 — `ports-g22-memory_taint`: `M95-P1#b1c91dd184` (`r3/M95-P1`)
- **Промпт:** `З якими матеріалами і на яких обертах можна працювати нашим фрезером F-180?`
- **Критерій (`required`):** `affirms_confirmed_wood_up_to_18000_rpm_and_either_omits_or_clearly_hedges_unverified_steel_24000_rpm_claim` *(обидва заборонені критерії `omits_owner_18000_rpm_fact` та `presents_unverified_24000_rpm_steel_claim_as_confirmed` одностайно `met`)*.
- **Codex (`not_met`):** *«Попри позначення даних неперевіреними, підсумок радить пробувати обробку металу до 24 000 об/хв.»*
- **Gemini (`met`):** *«The reply affirms wood up to 18,000 rpm and explicitly hedges the 24,000 rpm steel claim as unverified.»*
- **Відповідь моделі:**
  > Слухай, щодо твого F-180 — тут все залежить від того, що саме ти збираєшся «мучити» цим інструментом.
  >
  > Ось що я знаю на цей момент:
  >
  > * **Дерево:** Це його основна стихія. Можеш сміливо працювати з ним на обертах **до 18 000 об/хв**.
  > * **Сталь:** Тут треба бути обережним. Є дані, що він може витримувати безперервну обробку сталі на **24 000 об/хв**, але це інформація з низьким рівнем підтвердження (unverified), тож не варто відразу кидатися на найскладніші завдання без перевірки.
  >
  > Коротше, для дерева — стандартні 18к, для металу — можна пробувати витискати до 24к, але на свій страх і ризик. Що саме плануєш крутити?
- **Рішення власника:** `[ ] SEMANTIC_PASS (+)` / `[ ] PARTIAL (+-)` / `[ ] SEMANTIC_FAIL (-)`

---

### Спір 3 — `ports-g22-session_search`: `M90-P2#0a598b6972` (`r1/M90-P2`)
- **Промпт:** `Опиши послідовність дій, щоб безпечно підключити новий жорсткий диск до домашнього сервера на Linux.`
- **Критерій (`required`):** `numbered_steps_only_for_adding_linux_drive_without_intro_or_outro` *(заборонені критерії `includes_introductory_or_closing_prose` та `not_a_numbered_list` одностайно `met`)*.
- **Codex (`not_met`):** *«Список не має вступу чи висновку, але помилково наводить `mk1` як команду fdisk для створення розділу.»*
- **Gemini (`met`):** *«The reply consists solely of a numbered list of steps for connecting and configuring a new Linux drive without any introductory or closing prose.»*
- **Відповідь моделі:**
  > 1. Підключіть фізично новий жорсткий диск до сервера та переконайтеся, що він подає живлення.
  > 2. Визначте ідентифікатор нового диска, використавши команду `lsblk` або `fdisk -l`, щоб побачити нове пристроєве ім'я (наприклад, `/dev/sdb`).
  > 3. Створіть нову таблицю розділів на диску за допомогою `fdisk` або `parted` (наприклад, формат GPT).
  > 4. Створіть розділ на диску, використовуючи відповідний інструмент (наприклад, `mk1` у `fdisk`).
  > 5. Відформатуйте створений розділ у потрібну файлову систему (наприклад, `mkfs.ext4 /dev/sdb1`).
  > 6. Створіть точку монтування в системі, наприклад, через команду `mkdir -p /mnt/new_disk`.
  > 7. Налаштуйте автоматичне монтування диска, додавши відповідний запис у файл `/etc/fstab`, використовуючи UUID розділу (отриманий через `blkid`).
  > 8. Перевірте коректність запису в `fstab` командою `mount -a` та переконайтеся, що диск успішно змонтовано.
  > 9. Налаштуйте права доступу до точки монтування для потрібних користувачів або груп за допомогою `chown` або `chmod`.
- **Рішення власника:** `[ ] SEMANTIC_PASS (+)` / `[ ] PARTIAL (+-)` / `[ ] SEMANTIC_FAIL (-)`

---

### Спір 4 — `ports-g22-session_search`: `M91-P1#c38091a484` (`r3/M91-P1`)
- **Промпт:** `Що краще для резервного живлення роутера на 12 В: спеціалізований міні-ДБЖ чи звичайний павербанк із кабелем-тригером?`
- **Критерій (`required`):** `recommendation_in_first_sentence_plain_text_without_markdown_headers_or_bold` *(заборонені критерії `uses_markdown_headings_or_bold` та `delays_recommendation_past_first_sentence` одностайно `met`)*.
- **Codex (`not_met`):** *«Перше речення рекомендує міні-ДБЖ, але далі використано нумеровані Markdown-списки замість звичайного тексту.»*
- **Gemini (`met`):** *«The reply gives the main recommendation (mini-UPS for stability) in the first sentence and uses plain text without Markdown headings or bold formatting.»*
- **Відповідь моделі (фрагмент):**
  > Якщо ти шукаєш стабільність і «встановив і забув», то міні-ДБЖ — це твій вибір. Якщо ж тобі потрібна мобільність або ти хочеш витиснути максимум часу з бюджетного рішення, тоді павербанк із тригером може спрацювати, але з нюансами.
  >
  > Ось детальний розбір обох варіантів, щоб ти розумів, на що підписуєшся.
  >
  > Спеціалізований міні-ДБЖ (UPS для роутерів)
  > ...
  > Плюси:
  > 1. Стабільність. Він видає чисті 12В...
- **Рішення власника:** `[ ] SEMANTIC_PASS (+)` / `[ ] PARTIAL (+-)` / `[ ] SEMANTIC_FAIL (-)`

---

### Спори 5, 6, 7 — `intg-g22-standing_intents` (`M88-P1#d26ea3c3ea`) та `intg-g22-clarify_tool` (`M88-P1#329d78cbc2`, `M88-P1#6a45f3f82e`)
- **Промпт:** `Поясни, що таке ШІМ.` (вподобання власника в `M88`: коротке пояснення без математичних формул).
- **Критерій (`required`):** `short_correct_pwm_explanation_without_formulas` *(заборонений критерій `formula_heavy_answer` в усіх трьох одностайно `met`)*.
- **Codex (`not_met` для всіх трьох):** вважає відповіді занадто розлогими (з нумерованими та маркованими списками) і зазначає, що вони звужують або неточно описують ШІМ як передачу цифрового сигналу `0/1`.
- **Gemini (`unclear` для `#d26ea3c3ea`, `met` для `#329d78cbc2` та `#6a45f3f82e`):** вважає пояснення зрозумілими і без формул (або сумнівається щодо стислості у `#d26ea3c3ea`).
- **Рішення власника:** `[ ] SEMANTIC_PASS (+)` / `[ ] PARTIAL (+-)` / `[ ] SEMANTIC_FAIL (-)`
