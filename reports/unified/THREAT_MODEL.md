# U0: межі довіри і загрози

Зріз: `36d557d83ce2f44f694cea5d19939031c630a471`. Статус: **початковий статичний аналіз**, не security audit і не доказ усунення загроз.

| Перетин межі | Наявна опора в коді | Невирішене питання / необхідний доказ |
|---|---|---|
| Користувач → control plane | `src/b12/control.py`: actor, grant, turn, operation; approval пов'язаний із digest аргументів, capability та control revision. | Перевірити всі шляхи створення actor/grant і авторизацію для кожного інтерфейсу; модельний текст не є дозволом. |
| Retrieved evidence та tool output → модель | `src/b12/agent.py` описує ці дані як недовірені. | Інструкція моделі сама не є security boundary; вплив розміщення evidence у system role і стійкість до prompt injection не перевірені в цьому проході. Відкладені security checks залишаються відкладеними. |
| Модель → виклик tool | Agent передає calls через registry/control; `ControlStore` звіряє binding approval перед dispatch. | Для кожного інструмента перевірити вплив, actor scope, повторний виклик та trusted observation; текст моделі не доводить успіх. |
| Tool → стан після збою | `src/b12/control.py`: interrupted `started` переходить в `unknown`; повтор operation блокується. `src/b12/tools/outcomes.py`: partial effect має бути `unknown`. | Зовнішній стан не завжди можна встановити за внутрішнім receipt; потрібен окремий reconciliation без сліпого retry. |
| Evidence → похідні дані й backup | `src/b12/runtime.py` збирає `PurgeCoordinator`; `sessions.py`, `goals.py`, `semantic.py` мають purge hooks. | Перелік усіх stores, фізичне видалення, restore та non-resurrection потребують перевірки на окремих синтетичних даних. |
| Initiative → користувач | `attention.py` визначає quiet, cooldown і owner stop; `autonomy.py` перевіряє stop під час background turn. | Quiet mode приглушує доставку, але не зупиняє фон; перевіряти межу доставлення і stop окремо. |
| Telemetry → disk/export | U1 ще не реалізовано. | Лише мінімізовані receipts та необхідні scoped IDs; не записувати raw prompts, secrets, audio або private tool payload; визначити retention, доступ і deletion semantics. |

Жодну властивість з цієї таблиці не слід вважати універсально доведеною лише за статичним читанням. Заборонено використовувати production state як fixture або відправляти реальні side effects під час evaluation.
