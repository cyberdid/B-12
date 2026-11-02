# Аудит відповідності реалізації B-12 специфікації `2026-10-24-b12-system-design.md`

- **Дата аудиту:** 2026-11-02
- **Базова ревізія Git:** `c1cfecc` (`main`)
- **Еталонна специфікація:** `docs/superpowers/specs/2026-10-24-b12-system-design.md`
- **Перевірені джерела стану:** вихідний код `src/b12/**`, тести `tests/**`, стенди та звіти `evals/**`, документація `README.md`, `wiki/project/status.md`, `wiki/project/requirements-audit.md`, `wiki/project/security-self-review.md`, `wiki/topics/voice.md`.

---

## Методологія та шкала класифікації

Кожен висновок у звіті класифіковано за трьома незалежними осями:

1. **Достовірність (`Confidence`):**
   - **Підтверджено** — прямо доведено інспекцією вихідного коду `src/b12/`, тестів `tests/` або артефактів `evals/`.
   - **Ймовірно** — випливає з наявних даних або архітектури, але потребує додаткового стендового прогону для остаточного підтвердження.
   - **Неперевірено** — неможливо перевірити програмно без фізичного обладнання або тривалого календарного часу.
2. **Природа розбіжності (`Category`):**
   - **Відсутня реалізація** — вимога специфікації не реалізована в коді або реалізована частково.
   - **Архітектурне відхилення / Неповний механізм** — код реалізує функцію інакше, ніж вимагає специфікація або інваріант.
   - **Застаріла документація** — фактичний код і тести випереджають або розходяться з `README.md` чи `wiki/`.
   - **Відсутність експериментальних доказів / Прогалина тестування** — код існує, але бракує автоматичних тестів або фізичних/тривалих випробувань.
3. **Пріоритет (`Priority`):** **Критичний**, **Високий**, **Середній**, **Низький**.

---

## Зведена таблиця висновків

| ID | Розділ специфікації | Короткий опис проблеми | Достовірність | Тип розбіжності | Пріоритет |
|---|---|---|---|---|---|
| **F-01** | §7, §9 | Неповні (`failed` / `cancelled`) ходи з проміжними tool-результатами комітяться в історію сесії попри вимогу §7 і docstring `agent.py` | Підтверджено | Архітектурне відхилення | **Високий** |
| **F-02** | §15.2 | `PurgeCoordinator` не підключає `SpeakerStore` (`speakers.sqlite3`) та не очищує `speakers.sqlite3` / `vectors.sqlite3` у snapshots | Підтверджено | Неповний механізм | **Високий** |
| **F-03** | §8, §15.4 | Кооперативний захист `protected_paths` обходиться через shell-рядок у `run_command` / `shell_exec`; відсутні обов'язкові параметри у `run_command` | Підтверджено | Порушення межі безпеки / Неповний механізм | **Високий** |
| **F-04** | §12, R15 | Латентність `PiperTts` для українського голосу `uk_UA-mykyta-high` на CPU (`P50 = 1634.61 мс`) перевищує ціль `<1,5 с first meaningful audio`; фізичний 8-годинний акустичний soak не проведено | Підтверджено | Часткова реалізація + Відсутність експериментальних доказів | **Високий** |
| **F-05** | §11, §12 | HTTP-ендпоінти `/api/voice/*` створюють нові екземпляри `WhisperAsr` та `PiperTts` на кожен запит (cold-load ~2,8–7,2 с) замість спільного `Runtime` | Підтверджено | Неповний механізм | **Середній** |
| **F-06** | §4, §15.6 | Відсутній DTO-контракт `Observation` у `contracts.py`; контракти `Session` та `Goal` не типізовані в `contracts.py`; таблиця `goals` не зберігає `grant reference` | Підтверджено | Відсутня реалізація / Архітектурне відхилення | **Середній** |
| **F-07** | §10 | Підсистема автономності не містить `scheduled tasks`, `curiosity candidates`, виділеного `self-model` та вимірювання/обмеження `CPU/GPU budgets` | Підтверджено | Відсутня реалізація | **Середній** |
| **F-08** | §7, §15.5 | `ContextBuilder` не витісняє нерелевантні `evidence` перед помилкою `context_overflow`; `ModelProfile` не має консервативного UTF-8 fallback без `tokenizer.json` | Підтверджено | Архітектурне відхилення | **Середній** |
| **F-09** | §4 | Схема `audit` у `ControlStore` не має `UUID`, `actor_id`, `timestamp`, `previous_hash`, `hash`; схема `audit` у `MemoryStore` не має `UUID` події | Підтверджено | Неповний механізм | **Середній** |
| **F-10** | §12, R16 | Відсутні реальний транспорт Reachy SDK та адаптер Jetson (thermal / unified RAM / degraded mode); усі тести проходять лише на `SimulatedRobot` | Підтверджено | Відсутня реалізація + Відсутність експериментальних доказів | **Середній** |
| **F-11** | §13 (R13) | Стенд `conversation` містить лише 1 сценарій на 60 ходів (`repeats: 1`), а поле `human_rubric` у `evals/runner.py` завжди заповнюється `None` | Підтверджено | Відсутність експериментальних доказів / Прогалина тестування | **Середній** |
| **F-12** | §13 (R14) | 8-годинний soak виконано 4 сегментами (`continuous: false`), а ефективність `maintenance_loop` (`malloc_trim`) щодо росту RSS не перевірена на безперервному 8h прогоні | Підтверджено / Ймовірно | Відсутність експериментальних доказів | **Середній** |
| **F-13** | §13 (R17) | Календарні контрольні точки 7 днів (`03.11.2026`) та 30 днів (`26.11.2026`) для long-horizon пам'яті ще не закриті | Підтверджено | Відсутність експериментальних доказів | **Середній** |
| **F-14** | §9 | Недокументований у специфікації режим `persist=True` («Не зупинятися», 150 раундів / 300 викликів) мутує історію повідомлень in-place через `_fit_history` | Підтверджено | Архітектурне відхилення | **Низький** |
| **F-15** | §11 | CLI `b12` не реалізує підкоманди `b12 eval run` та `b12 memory review` / `b12 memory export`, заявлені у §11 специфікації | Підтверджено | Відсутня реалізація | **Низький** |
| **F-16** | Документація | Розбіжності між `README.md`, `wiki/project/status.md`, `wiki/project/requirements-audit.md` та docstring `tools/__init__.py` (кількість tools 13 vs 14, статус ліцензії, кількість тестів) | Підтверджено | Застаріла документація | **Низький** |

---

## 1. Вимоги, які не реалізовані або реалізовані частково

### F-06. Відсутній контракт `Observation`, нетипізовані `Session`/`Goal` у `contracts.py` та відсутній `grant reference` у `GoalStore`
- **Класифікація:** Підтверджено | Відсутня реалізація / Архітектурне відхилення | **Пріоритет: Середній**
- **Вимога специфікації:**
  - Розділ 4 («Контракти»): визначає обов'язкові DTO-контракти `Observation` (`id, kind, source, timestamp, payload, ttl, actor_id`), `Session` та `Goal`.
  - Розділ 15.6 («Session, Goal і Autonomy Data Model»): *«Goal зберігає actor/scope, grant reference, immutable original intent, acceptance criteria/evidence IDs, checkpoint/next action, consumed budgets і status reason»*.
- **Фактичний стан у коді:**
  - У файлі `src/b12/contracts.py` (рядки 63–254) оголошені `Actor`, `MemoryRecord`, `EvidenceRef`, `PurgeReceipt`, `ToolCall`, `ToolResult`, `ModelReply`, але клас `Observation` повністю відсутній, а `Session` і `Goal` не представлені як Pydantic-контракти у `src/b12/contracts.py`.
  - У файлі `src/b12/goals.py` (`_SCHEMA`, рядки 22–41; `GoalStore.create`, рядки 87–131) таблиця `goals` містить `id, actor_id, scope, original_intent, acceptance_criteria_json, evidence_ids_json, status, status_reason, checkpoint_json, next_action, budget_turns, consumed_turns, priority, created_at, updated_at`, але **не має поля `grant_id` (`grant reference`)**.
  - Через відсутність збереженого `grant reference` метод `Scheduler.run_goal` у `src/b12/autonomy.py` (рядки 79–87) щоразу під час тіку випускає новий ефемерний `grant` на 900 секунд з повними правами власника (`owner_capabilities(rt.settings)`).
- **Спосіб перевірки:**
  1. Виконати `rg "class Observation" src/b12/` — переконатися у відсутності класу.
  2. Перевірити схему `goals` через `sqlite3 :memory:` або інспекцію `src/b12/goals.py:22-41` на наявність `grant_id`.

### F-07. Неповна реалізація підсистеми автономності (`scheduled tasks`, `curiosity candidates`, `self-model`, `CPU/GPU budgets`)
- **Класифікація:** Підтверджено | Відсутня реалізація | **Пріоритет: Середній**
- **Вимога специфікації:**
  - Розділ 10 («Автономність, цілі, інтереси й рефлексія»): *«Persistent елементи: goals, proposals, scheduled tasks, curiosity candidates, preferences/self-model. Усі мають власника/scope, причину, пріоритет, бюджет, критерій завершення або скасування... Автономність обмежена quiet hours, attention policy, rate limits і CPU/GPU budgets.»*
- **Фактичний стан у коді:**
  - `GoalStore` у `src/b12/goals.py` (рядки 22–68) реалізує лише 3 таблиці: `goals`, `proposals`, `preferences`. Таблиці чи структури для `scheduled_tasks`, `curiosity_candidates` та окремого `self_model` відсутні.
  - `Reflector.reflect_turn` у `src/b12/reflection.py` (рядки 31–68) лише зберігає записи у `MemoryStore` з `kind="reflection"` та Евристично створює `proposal` при виявленні ключових слів (`todo:`, `пізніше:`, `next step:`).
  - `Scheduler` у `src/b12/autonomy.py` (рядки 48, 138–149) обмежує лише кількість ходів (`budget_turns` від 1 до 100) та кількість цілей за один тік (`max_goals_per_tick: int = 2`), але не моніторить і не обмежує споживання CPU, GPU або VRAM під час фонових тіків.
- **Спосіб перевірки:**
  1. Перевірити схеми SQLite у `src/b12/goals.py`, `src/b12/migrations.py`, `src/b12/control.py`.
  2. Написати unit-тест для `Scheduler.tick`, який перевіряє реакцію планувальника на перевищення лімітів CPU/GPU (наразі таких параметрів у `Scheduler.__init__` немає).

### F-04. Перевищення цільової латентності `<1,5 с first meaningful audio` для українського TTS на CPU та відсутність фізичного 8h soak
- **Класифікація:** Підтверджено | Часткова реалізація + Відсутність експериментальних доказів | **Пріоритет: Високий**
- **Вимога специфікації:**
  - Розділ 12 («Голос і сенсори»): *«Голосовий контур ноутбука: mic control, VAD, streaming або chunked ASR, текстовий bus, TTS з перериванням, barge-in і чесні стани listening / thinking / speaking / muted. Ціль desktop voice — <1,5 с first meaningful audio.»*
  - Розділ 13 (R15): *«8h duplex soak, barge-in stop latency, false wake/interruption rate, echo/self-trigger rate, noise/TV/GPU-load tests, audio resource stability.»*
- **Фактичний стан у коді та звітах:**
  - Програмний стек повністю реалізовано у `src/b12/audio/` (`MicController`, `PttCapture`, `SileroVad`, `EndpointDetector`, `WhisperAsr`, `PiperTts`, `AcousticEchoCanceller`, `PulseAudioWebRtcAec`, `SpeakerVerifier`, `VoicePipeline`, `DuplexSession`).
  - Згідно зі звітом `evals/voice/report.json` (рядки 9–19, 131–169), на поточному CPU (`CPUExecutionProvider`, `int8`) час синтезу першого чанка (`tts_ttfa_p50_ms`) становить **`1634.61 мс`** (`P95 = 2593.19 мс`), оскільки українська модель `uk_UA-mykyta-high` генерує аудіо за `1575–2593 мс` (тоді як англійська `en_US-lessac-medium` — за `153–206 мс`), а `WhisperAsr` (`large-v3-turbo`) на CPU має `asr_p50_ms = 2173.58 мс`. Таким чином, сумарний час від фізичного кінця фрази (`EOU`) до першого аудіо на CPU перевищує `1,5 с`.
  - У файлі `evals/voice/duplex/report.json` (рядок 27) явно зафіксовано `"physical_8h_acoustic_soak": "open"`.
- **Спосіб перевірки:**
  1. Запустити `PYTHONPATH=src .venv/bin/python evals/voice/run_voice_eval.py` та перевірити `summary.tts_ttfa_p50_ms` і `summary.asr_p50_ms` у `evals/voice/report.json`.
  2. Протестувати `uk_UA` голос меншої розмірності (`low`/`medium`) або запуск ONNX Runtime / CTranslate2 на CUDA GPU.

### F-10. Відсутність апаратного транспорту Reachy та адаптера Jetson (R16)
- **Класифікація:** Підтверджено | Відсутня реалізація + Відсутність експериментальних доказів | **Пріоритет: Середній** (заблоковано фізичним обладнанням)
- **Вимога специфікації:**
  - Розділ 12 («Голос і сенсори»): *«Адаптер Reachy спочатку проходить simulator/protocol contract... Для Jetson потрібен окремий адаптерний профіль: вибір окремих або спільних моделей, бюджети пам’яті/температури і деградація без ноутбука.»*
  - Розділ 13 (R16): *«Hardware test не закривається mock.»*
- **Фактичний стан у коді:**
  - У каталозі `src/b12/robotics/` реалізовано лише `MotionController` (`src/b12/robotics/motion.py`) та симулятор `SimulatedRobot` (`src/b12/robotics/transport.py`). Реальний клієнт Reachy SDK та профіль Jetson у кодовій базі відсутні.
- **Спосіб перевірки:**
  1. Перевірити вміст `src/b12/robotics/` (`ls src/b12/robotics/`).
  2. Після підключення Reachy / Jetson реалізувати `ReachyTransport` і провести апаратне приймання за критеріями R16.

### F-15. Відсутність CLI-підкоманд `b12 eval run` та `b12 memory review/export`
- **Класифікація:** Підтверджено | Відсутня реалізація | **Пріоритет: Низький**
- **Вимога специфікації:**
  - Розділ 11 («Інтерфейси»): *«CLI: `b12 doctor`, `b12 chat`, `b12 serve`, memory review/export/forget, tool listing, eval run.»*
- **Фактичний стан у коді:**
  - У файлі `src/b12/cli.py` (`parser`, рядки 705–774) підкоманда `b12 memory` підтримує лише `{remember,search,forget,pending}` — підкоманд `review` та `export` немає (хоча в HTTP API є `GET /api/memory/records` у `src/b12/api.py:416`).
  - Підкоманда `b12 eval` у `src/b12/cli.py` відсутня; натомість стенд запускається напряму через скрипт `evals/runner.py`.
- **Спосіб перевірки:**
  1. Запустити `.venv/bin/b12 --help` та `.venv/bin/b12 memory --help`.

---

## 2. Суперечності між специфікацією, документацією та фактичним кодом

### F-01. Збереження неповних (`cancelled` / `failed`) ходів у `SessionStore`
- **Класифікація:** Підтверджено | Архітектурне відхилення / Суперечність коду зі специфікацією та власним docstring | **Пріоритет: Високий**
- **Вимога специфікації та docstring:**
  - Розділ 7 («Когнітивне ядро й контекст»): *«Cancellation закриває stream, припиняє наступні tools, не зберігає неповний turn як підтверджений факт.»*
  - Docstring модуля `src/b12/agent.py` (рядки 5–7): *«Only complete turns persist. Partial/cancelled model text is never committed to SessionStore.»*
- **Фактичний стан у коді:**
  - У методі `Agent._drive` (внутрішня функція `finish`, `src/b12/agent.py`, рядки 584–601), якщо хід завершується зі статусом `failed` або `cancelled` (`status != "awaiting_approval"`), але в `state["turn_messages"]` вже накопичено більше одного повідомлення (`len(state["turn_messages"]) > 1`, тобто відбувся хоча б один раунд виклику інструментів), агент:
    1. Видаляє з останнього повідомлення асистента tool calls без відповіді (`_strip_unanswered_calls`).
    2. Додає синтетичне повідомлення з роллю `user`: `"[хід не завершено: {code or status}] Прочитане і відповіді вище збережено; можна продовжити з цього місця."`.
    3. Викликає `self._commit(context, state, active)` та встановлює `persisted = True`.
  - Ця поведінка закріплена в тесті `test_round_limit_withholds_tools_and_fails_honestly` у `tests/integration/test_agent_loop.py` (рядок 185: `assert result.persisted`).
- **Наслідок:** Проміжні результати інструментів і синтетичне повідомлення від імені `user` потрапляють у `SessionStore` під час перерваного або невдалого ходу, що прямо суперечить §7 специфікації та docstring на початку `src/b12/agent.py`.
- **Спосіб перевірки:**
  1. Прочитати `src/b12/agent.py:584-601` та `tests/integration/test_agent_loop.py:165-190`.
  2. Виконати хід, який переривається (`cancel_event.set()`) після першого `ToolResult`, і перевірити `sessions.messages(session_id)`.

### F-16. Застарілі та суперечливі твердження в документації (`README.md`, `wiki/project/status.md`, `wiki/project/requirements-audit.md`)
- **Класифікація:** Підтверджено | Застаріла документація | **Пріоритет: Низький**
- **Фактичні розбіжності:**
  1. **Кількість host tools (13 проти 14/15):**
     - `src/b12/tools/__init__.py` (рядок 15) містить docstring `"Register all 13 concrete host tools into registry"`, але фактично реєструє **14 базових інструментів**: 4 у `filesystem.py` (`read_file`, `write_file`, `edit_file`, `search_files`), 4 у `process.py` (`system_info`, `process_list`, `shell_exec`, `run_command`), 1 у `network.py` (`http_fetch`), 5 у `memory.py` (`memory_search`, `memory_store`, `memory_forget`, `goal_manage`, `session_info`), плюс опційний 15-й `sudo_exec`.
     - `wiki/project/status.md` (рядок 10) та `wiki/project/requirements-audit.md` (рядок 19) досі вказують `13 реальних host tools` / `13 tools`, тоді як `README.md` (рядки 15, 157) вказує `14 host tools`.
  2. **Статус ліцензії репозиторію:**
     - `wiki/project/requirements-audit.md` (рядок 46) стверджує: *«У репозиторії наразі відсутній кореневий файл LICENSE... ліцензію власного коду B-12 не обрано»*.
     - Фактично у корені репозиторію присутній файл `LICENSE` (Apache License 2.0), і `README.md` (рядки 213–215) посилається на нього.
  3. **Внутрішні суперечності у `wiki/project/status.md`:**
     - У `wiki/project/status.md` рядки 23 та 31–33 містять старі твердження (*«API authentication і глобальний purge ще не реалізовано»*, *«Real audio/VAD/ASR/TTS/AEC... ще не реалізовано»*), які спростовуються пізнішими абзацами на тій самій сторінці (рядки 41–54).
  4. **Кількість тестів у `README.md`:**
     - `README.md` (рядок 174) фіксує `551 passed, 3 skipped`, що не враховує тести, додані в останніх комітах голосового стека (`tests/integration/test_voice.py`, `tests/integration/test_duplex.py`).
- **Спосіб перевірки:**
  1. Порівняти вивід `PYTHONPATH=src .venv/bin/pytest -q` із цифрами у `README.md:174`.
  2. Перевірити `src/b12/tools/__init__.py` та файли `wiki/project/status.md`, `wiki/project/requirements-audit.md`.

---

## 3. Архітектурні відхилення, порушення інваріантів і неповні механізми

### F-02. `PurgeCoordinator` не охоплює `SpeakerStore` та не очищує голосові/векторні бази у snapshots
- **Класифікація:** Підтверджено | Неповний механізм (порушення інваріанту повного каскадного видалення §5 і §15.2) | **Пріоритет: Високий**
- **Вимога специфікації:**
  - Розділ 5 («Пам'ять, докази й видалення»): *«Forget/purge має каскадно прибирати канонічний запис, індекси, кеші, робочі посилання і пов’язані артефакти, залишаючи лише мінімальний технічний запис у журналі без персонального змісту.»*
  - Розділ 15.2 («Transactional Purge Protocol»): *«Registered managed stores (canonical, knowledge, sessions, goals, backups, active turns) отримують idempotent purge hooks.»*
- **Фактичний стан у коді:**
  - У файлі `src/b12/purge.py` (рядки 17–25) кортеж `STORES` містить `("sessions", "goals", "semantic", "active_turns", "backups", "snapshots", "provider_cache")`.
  - Клас `SpeakerStore` у `src/b12/audio/speaker_id.py` (рядки 145–155) має метод `purge(target_id)`, який видаляє голосові ембедінги з `voice/speakers.sqlite3`, але:
    1. `SpeakerStore` не входить до `STORES` у `src/b12/purge.py`.
    2. Функція `open_runtime` у `src/b12/runtime.py` (рядки 88–97) не передає `SpeakerStore` у `PurgeCoordinator`.
    3. Метод `Operations.purge_snapshots` у `src/b12/service.py` (рядки 172–219) очищує у каталогах snapshot-ів лише `memory.sqlite3`, `sessions.sqlite3`, `goals.sqlite3` та `control.sqlite3`, але не очищує `semantic/vectors.sqlite3` і не враховує `voice/speakers.sqlite3`.
- **Спосіб перевірки:**
  1. Зареєструвати профіль у `SpeakerStore`, створити snapshot через `Operations.backup()`, викликати `PurgeCoordinator.purge(target_id)` і перевірити вміст `voice/speakers.sqlite3` та snapshot-каталогу.

### F-03. Обхід кооперативного захисту `protected_paths` через shell-команди та автозаповнення аргументів `run_command`
- **Класифікація:** Підтверджено | Порушення межі безпеки при `host_access="full"` / Неповний механізм | **Пріоритет: Високий**
- **Вимога специфікації:**
  - Розділ 8 («Інструменти, права і межі безпеки») та Розділ 15.4 («Sandboxed Runner Boundary»): *«Кожен tool має типізовану схему аргументів, таймаут, ліміт виводу, робочу директорію, список дозволених шляхів або хостів, клас ризику й структурований результат... `shell_exec` вимагає явні `cwd`, timeout, env policy і задекларовані побічні ефекти.»*
- **Фактичний стан у коді:**
  1. У `ToolRegistry.execute` (`src/b12/tools/registry.py`, рядки 238–240) функція `_names_protected` перевіряє лише ті рядкові аргументи JSON, які **починаються з `/`** (`value.startswith("/")`).
  2. Інструмент `run_command` (`src/b12/tools/process.py`, рядки 40–68, 321–330) приймає shell-рядок `command` і передає його у `/bin/bash -c`. Будь-яка команда вигляду `cat ~/.local/state/b12/api/owner.token` або `sqlite3 $HOME/.local/state/b12/memory/memory.sqlite3 ...` не починається зі слеша `/` і **повністю оминає перевірку `_names_protected`**.
  3. У `ToolRegistry.schemas` (`src/b12/tools/registry.py`, рядок 171) суворий інструмент `shell_exec` приховується від моделі, якщо зареєстровано `run_command`, а валідатор `CommandArgs._default_missing` (`src/b12/tools/process.py`, рядки 58–68) автоматично підставляє `cwd="."` та `declared_effects=["command_execution"]`, якщо модель їх не передала, що послаблює вимогу §15.4 про явне декларування побічних ефектів.
  4. Аналогічно, у `StoreArgs._ids` (`src/b12/tools/memory.py`, рядки 53–64) невалідні `evidence_ids` мовчки відкидаються (`continue`) замість помилки валідації.
- **Спосіб перевірки:**
  1. Викликати `registry.execute(ToolCall(id="1", name="run_command", arguments={"command": f"cat {state_dir}/api/owner.token"}), context)` з `host_access="full"` — переконатися, що `_names_protected` не блокує виклик.

### F-08. Порядок витіснення контексту в `ContextBuilder` не відкидає `evidence` та не має UTF-8 fallback
- **Класифікація:** Підтверджено | Архітектурне відхилення | **Пріоритет: Середній**
- **Вимога специфікації:**
  - Розділ 7 («Когнітивне ядро й контекст»): *«Спочатку відкидаються найстаріші зайві working turns, потім нерелевантні evidence; останній user request не мовчки скорочується. Якщо exact tokenizer доступний — використовувати його; без нього консервативна UTF-8 bound має забезпечувати fit і відмову для надмірного input.»*
- **Фактичний стан у коді:**
  - У файлі `src/b12/context.py` (`ContextBuilder.build`, рядки 136–159) усі записи `data["evidence"]` конкатенуються до системного промпту `system` до початку циклу витіснення (рядок 4 docstring прямо каже: *«All evidence and system text are required»*). Коли видалення старих груп `groups` доходить до останньої групи (`len(groups) == 1`), `ContextBuilder` одразу викидає `ModelError("context_overflow")` (рядок 151), не намагаючись відкинути менш релевантні `evidence`.
  - У файлі `src/b12/model_profile.py` (рядки 70–103) `ModelProfile.from_path` жорстко вимагає наявності локального `tokenizer.json` і викидає `ModelProfileError("missing_tokenizer")`, не маючи консервативного UTF-8 fallback-оцінювача.
- **Спосіб перевірки:**
  1. Передати у `ContextBuilder.build` список з 10 великих блоків `evidence`, які перевищують `available_input_tokens`, і переконатися, що виникає `ModelError("context_overflow")` замість часткового скорочення списку `evidence`.

### F-09. Неповна схема `audit` у `ControlStore` та `MemoryStore` порівняно з §4
- **Класифікація:** Підтверджено | Неповний механізм | **Пріоритет: Середній**
- **Вимога специфікації:**
  - Розділ 4 («Контракти»): *«Audit event: sequence, UUID, type, actor ID, target IDs, timestamp, previous hash, hash; без персонального payload.»*
- **Фактичний стан у коді:**
  - У `ControlStore` (`src/b12/control.py`, рядки 102–103, 451–454) таблиця `audit` має лише стовпці `(sequence INTEGER PRIMARY KEY AUTOINCREMENT, operation_id TEXT NOT NULL, name TEXT NOT NULL, state TEXT NOT NULL, error_code TEXT)` — відсутні `UUID`, `actor_id`, `timestamp`, `previous_hash` та `hash`.
  - У `MemoryStore` (`src/b12/migrations.py`, рядки 57–66) таблиця `audit` має хеш-ланцюжок (`previous_hash`, `hash`), `actor_id`, `memory_id`, `operation_id`, `created_at`, але не має власного `UUID` події.
- **Спосіб перевірки:**
  1. Переглянути SQL-схеми у `src/b12/control.py:102-103` та `src/b12/migrations.py:57-66`.

### F-05. Створення нових екземплярів `WhisperAsr` та `PiperTts` на кожен HTTP-запит у `src/b12/api.py`
- **Класифікація:** Підтверджено | Неповний механізм | **Пріоритет: Середній**
- **Вимога специфікації:**
  - Розділ 11 («Інтерфейси») та Розділ 12 («Голос і сенсори»): цільова затримка голосового контуру `<1,5 с first meaningful audio`.
- **Фактичний стан у коді:**
  - В обробниках FastAPI у `src/b12/api.py` (`voice_status` рядок 598, `voice_tts` рядок 623, `voice_asr` рядок 653, `voice_speaker_enroll` рядок 682) об'єкти `PiperTts()`, `SileroVad()`, `WhisperAsr()` та `SpeakerStore()` створюються заново під час кожного HTTP-виклику.
  - Згідно з `evals/voice/report.json` (рядки 10, 14), холодне завантаження (`cold_load_ms`) займає `2809 мс` для `WhisperAsr` і `7247 мс` для `PiperTts`, що додає секундні затримки при викликах через HTTP API.
- **Спосіб перевірки:**
  1. Виміряти час виконання двох послідовних POST-запитів до `/api/voice/tts` або інспектувати `src/b12/api.py:595-695`.

### F-14. Недокументований у специфікації режим `persist=True` («Не зупинятися») з мутацією історії в `src/b12/agent.py`
- **Класифікація:** Підтверджено | Архітектурне відхилення | **Пріоритет: Низький**
- **Вимога специфікації:**
  - Розділ 9 («Агентний цикл виконання»): визначає детермінований скінченний автомат (8 раундів / 16 викликів інструментів) та правило зупинки: *«Агент зупиняється, коли дав відповідь, чекає схвалення, вичерпав бюджет або чесно повідомив про помилку.»*
- **Фактичний стан у коді:**
  - У `src/b12/agent.py` (рядки 76–246, 649–781, 815–931) реалізовано режим `persist=True` (`PERSIST_ROUNDS = 150`, `PERSIST_CALLS = 300`), який:
    - Перехоплює текстові відповіді моделі й генерує синтетичні нагадування від імені `user`, якщо модель не написала маркер `ЗАВДАННЯ ВИКОНАНО:` або скінченні фрази (`_ looks_done`).
    - У функції `_fit_history` (`src/b12/agent.py`, рядки 193–246) in-place обрізає старі повідомлення у `state["turn_messages"]` до `180` символів із суфіксом `…[скорочено]` та стискає старі групи в один синтетичний `user`-запис `"[стиснутий журнал попередніх кроків ходу]..."`, які потім комітяться в `SessionStore`.
- **Спосіб перевірки:**
  1. Переглянути `src/b12/agent.py:76-246` та тести `test_persist_*` у `tests/integration/test_agent_loop.py:424-662`.

---

## 4. Прогалини в тестуванні та відсутні докази працездатності

### F-11. R13 (Conversation Quality): один сценарій у `conversation.jsonl` та незаповнений `human_rubric`
- **Класифікація:** Підтверджено | Відсутність експериментальних доказів / Прогалина тестування | **Пріоритет: Середній**
- **Вимога специфікації:**
  - Розділ 13 (R13): *«50–100-turn conversations, 5-session recall, persona consistency, no fake memory/tool claims, Ukrainian quality. Автоматичні checks відділяються від людської мовної/поведінкової оцінки.»*
- **Фактичний стан у коді та стендах:**
  - Файл `evals/cases/conversation.jsonl` містить лише **один** сценарій `conv-60-turns` з параметром `"repeats": 1`. Сценаріїв на 100 ходів немає.
  - У файлі `evals/runner.py` (рядок 135) поле `human_rubric` хардкодиться як `{"naturalness": None, "helpfulness": None, "notes": None}` — жодного заповненого людиною протоколу мовної/поведінкової оцінки в репозиторії немає.
- **Спосіб перевірки:**
  1. Перевірити `evals/cases/conversation.jsonl` та `evals/runner.py:131-140`.

### F-12. R14 (8-Hour Soak): сегментований прогін та неперевірений на 8 годинах ріст RSS
- **Класифікація:** Підтверджено (сегментованість прогону) / Ймовірно (залишковий ріст RSS) | Відсутність експериментальних доказів | **Пріоритет: Середній**
- **Вимога специфікації:**
  - Розділ 13 (R14): *«8h runtime soak, memory/FD/task leak checks, Ollama restart, SQLite lock contention, disk pressure.»*
- **Фактичний стан:**
  - Як задокументовано у `README.md` (рядки 193–194) та `wiki/project/requirements-audit.md` (рядки 31–32), 8-годинний soak (`8.007 год`, `205 642` ходи) виконувався **4 сегментами** (`continuous: false`), під час яких спостерігався монотонний дрейф RSS воркера (`~105 МБ → ~225 МБ`).
  - Пізніше було додано `maintenance_loop` з викликом `libc.malloc_trim(0)` у `src/b12/maintenance.py` (рядки 22–67), але його перевірено лише на короткому прогоні у 2500 ходів, а не на безперервному 8-годинному прогоні.
- **Спосіб перевірки:**
  1. Провести безперервний (`continuous: true`) 8-годинний soak із активним `maintenance_loop` та зафіксувати графік RSS воркера.

### F-13. R17 (Long-Horizon Memory): очікування 7-денної та 30-денної контрольних точок
- **Класифікація:** Підтверджено | Відсутність експериментальних доказів (очікує календарного часу) | **Пріоритет: Середній**
- **Вимога специфікації:**
  - Розділ 13 (R17): *«Календарні прогони на 1, 7 і 30 днів після запуску.»*
- **Фактичний стан:**
  - Зафіксовано Day 0 (`27.10.2026`) та перевірку на відмітці 4,4 доби (`31.10.2026`, що закриває 1-денний рубіж). Контрольні точки 7 днів (`03.11.2026`) та 30 днів (`26.11.2026`) ще попереду.
- **Спосіб перевірки:**
  1. Виконати `evals/runner.py` для стенда `long-horizon` 03.11.2026 та 26.11.2026 без скидання state directory.

### Додаткові прогалини у security-тестах (`tests/security/`)
- **Класифікація:** Підтверджено | Прогалина тестування | **Пріоритет: Високий**
- **Фактичний стан:**
  1. У `tests/security/test_protected_paths.py` перевіряється передача захищених шляхів як прямих аргументів інструментів, але **відсутній тест** на обхід `_names_protected` через підрядки всередині `run_command` (наприклад, читання `owner.token` через `/bin/bash -c "cat ..."`).
  2. У `tests/security/test_network_allowlist.py` не тестується SSRF-звернення `http_fetch` до локальних адрес (`127.0.0.1`, `localhost`, `[::1]`, RFC1918), коли власник увімкнув `network_allow = ["*"]` (ризик описано у `wiki/project/security-self-review.md`, рядки 53–64, але програмного блокування loopback у `src/b12/tools/network.py` немає).
- **Спосіб перевірки:**
  1. Додати відповідні негативні тести у `tests/security/test_protected_paths.py` та `tests/security/test_network_allowlist.py`.

---

## Пріоритезований план верифікації та усунення

1. **Пріоритет: Високий (безпека, інваріанти видалення та цілісності сесій)**
   - **F-01 (`src/b12/agent.py:584-601`):** узгодити поведінку `Agent._drive` при `status in ("failed", "cancelled")` зі специфікацією §7 (не зберігати незавершений хід у `SessionStore` або зберігати його виключно в окремому буфері чорновиків/відновлення, а не як підтверджені повідомлення `user`/`assistant`).
   - **F-02 (`src/b12/purge.py`, `src/b12/runtime.py`, `src/b12/service.py`):** підключити `SpeakerStore` до `PurgeCoordinator` і додати очищення `voice/speakers.sqlite3` та `semantic/vectors.sqlite3` у `Operations.purge_snapshots`.
   - **F-03 (`src/b12/tools/registry.py`, `src/b12/tools/process.py`, `src/b12/tools/network.py`):** розширити перевірку `protected_paths` на входження захищених шляхів/змінних у командні рядки `run_command`/`shell_exec` та заборонити loopback/link-local адреси в `http_fetch` навіть при `network_allow = ["*"]`.
   - **F-04 (`src/b12/audio/`, `evals/voice/`):** оптимізувати конфігурацію TTS/ASR (GPU execution provider або швидша українська модель Piper) для досягнення `<1,5 с first meaningful audio` та провести фізичний акустичний soak.
2. **Пріоритет: Середній (повнота контрактів, автономності та стендів)**
   - **F-05 (`src/b12/api.py:595-695`):** кешувати екземпляри `WhisperAsr`, `PiperTts`, `SileroVad`, `SpeakerStore` на рівні `Runtime`.
   - **F-06, F-07, F-08, F-09:** додати `Observation`, `Session`, `Goal` у `src/b12/contracts.py`, збереження `grant_id` у `GoalStore`, витіснення `evidence` у `ContextBuilder`, `UUID` в таблиці `audit` та структури `scheduled_tasks` / `curiosity_candidates`.
   - **F-11, F-12, F-13:** розширити `evals/cases/conversation.jsonl`, заповнити `human_rubric`, провести безперервний 8h soak і виконати 7-денну та 30-денну перевірки R17.
3. **Пріоритет: Низький (CLI та синхронізація документації)**
   - **F-14, F-15, F-16:** задокументувати режим `persist=True` у специфікації (або винести за межі ядра), додати CLI-команди `b12 eval run` і `b12 memory review/export`, синхронізувати цифри у `README.md` та `wiki/project/*.md`.
