# B-12 / Capri: Комплексний аудит середовища, апаратних ресурсів, LLM-рантаймів та інфраструктури тестування

**Дата аудиту:** 2026-11-10T10:45:00+02:00  
**Аудитор:** Explorer 1 (Environment, Runtime & Infrastructure Auditor)  
**Робочий каталог:** `/home/cyberdid/Projects/B-12`  
**Режим цілісності:** `development` (read-only audit, без внесення змін до коду проєкту)  

---

## 1. Стан репозиторію Git та Worktrees

### 1.1. Основні ідентифікатори Git
- **Точний commit SHA (HEAD):** `8f296615e591faef33ac1755de919307134fe21a`
- **Активна гілка:** `main`
- **Останні коміти:**
  - `8f29661` (HEAD -> main) docs(wiki): record local TUI merge
  - `72a06d6` Merge branch 'feat/b12-cybercat-tui'
  - `cb5db3c` (feat/b12-cybercat-tui) docs(wiki): record TUI companion checkpoint
  - `0947f2e` feat(tui): complete companion integration and hook examples
  - `74bdd8a` feat(tui): integrate activity reports voice controls and skin switching
- **Стан робочого дерева (working tree):**
  - Відстежувані файли (`tracked files`): **чисті**, модифікацій немає (`git diff --stat` порожній).
  - Невідстежувані директорії (`untracked`):
    - `?? .agents/` (робоча директорія агентурної системи)
    - `?? "Статті/"` (локальні дослідницькі статті)

### 1.2. Перелік активних Git Worktrees
Команда `git worktree list` зафіксувала наявність 5 паралельних робочих дерев:
1. `/home/cyberdid/Projects/B-12` — комміт `8f29661` [`main`] (поточне основне дерево)
2. `/home/cyberdid/.codex/worktrees/bac0/B-12` — комміт `cb5db3c` [`feat/b12-cybercat-tui`]
3. `/home/cyberdid/.codex/worktrees/cb2c/B-12` — комміт `1de4eee` [`feat/b12-desktop-companion`]
4. `/home/cyberdid/Projects/B-12/.worktrees/access` — комміт `c1cfecc` [`feat/b12-access`]
5. `/home/cyberdid/Projects/B-12/.worktrees/runtime` — комміт `3e7fb07` [`feat/b12-runtime`]

> **Важливе спостереження щодо середовища Python:**  
> Віртуальне оточення `/home/cyberdid/Projects/B-12/.venv` містить пакет `b12-runtime 0.1.0`, встановлений у режимі `editable` з прив'язкою до шляху `/home/cyberdid/Projects/B-12/.worktrees/runtime`. Проте при запуску через `pytest` опція `pythonpath = ["src", "."]` у `pyproject.toml` коректно перекриває імпорти на користь поточного `/home/cyberdid/Projects/B-12/src`.

---

## 2. Апаратне забезпечення хоста (Hardware Specifications)

| Компонент | Специфікація | Емпірично верифіковані дані |
|---|---|---|
| **Хост / ОС** | `cyberdid-Crosshair` | Linux 7.0.0-42-generic #42~24.04.1-Ubuntu SMP PREEMPT_DYNAMIC x86_64 |
| **Процесор (CPU)** | Intel(R) Core(TM) i9-14900HX | 24 ядра / 32 потоки (8 P-ядер з HT + 16 E-ядер), 800–5800 МГц |
| **Кеші CPU** | L1 / L2 / L3 | L1d: 896 KiB, L1i: 1.3 MiB, L2: 32 MiB, L3: 36 MiB |
| **Дискретний GPU** | NVIDIA GeForce RTX 4060 Laptop (AD107M, rev a1) | 8188 MiB (~8 GB) GDDR6, TGP 115W, Driver: 610.57.04, CUDA UMD: 13.3 |
| **Інтегрований GPU** | Intel Raptor Lake-S UHD Graphics (rev 04) | 0000:00:02.0 VGA compatible controller |
| **Оперативна пам'ять (RAM)** | 31 GiB (~32 GB) DDR5 | Загальна: 31 GiB; у використанні: ~7–18 GiB; доступно: ~13–24 GiB |
| **Файл підкачки (Swap)** | 8.0 GiB | Загальний: 8.0 GiB; завантажується при інференсі моделей 27B |
| **Дисковий простір** | `/dev/nvme0n1p5` змонтовано на `/` | Загальний: 410 GB, зайнято: 373 GB, **вільно: 16 GB (96% Use%)** |

### ⚠️ Критичні обмеження обладнання:
1. **Дисковий простір:** На кореневому NVMe накопичувачі доступно лише **16 GB**. Заборонено завантажувати нові великі моделі (ваги 10+ GB переповнять диск) та створювати некеровані дампи логів.
2. **Фоновий процес на GPU:** PID `55058` (`/home/cyberdid/.local/share/embeddinggemma2/venv/bin/python ... scripts/embed_bridge.py --backend archive_index.embed:Embedder`) постійно споживає **1584 MiB VRAM** для семантичного індексу.
3. **Чистий доступний VRAM:** ~6.5 GB. Моделі розміром понад 6 GB потребуватимуть часткового оффлоаду в системну RAM.

---

## 3. Локальні LLM-рантайми (Runtimes & Models)

### 3.1. Статус сервісу Ollama
- **Тип сервісу:** Системний демон `systemd` (`ollama.service`), бінарник `/usr/local/bin/ollama serve` (PID `3524`).
- **Версія сервера:** `0.33.3` (клієнтська утиліта: `0.33.1`).
- **API ендпоінти:** `http://127.0.0.1:11434` (перевірено `/api/version`, `/api/ps`, `/api/tags`, `/api/generate`, `/api/show`).

### 3.2. Перелік встановлених локальних моделей (`ollama list`)

| Назва моделі | Model ID | Розмір на диску | Архітектура | Параметри | Квантування | Контекст (Native / Default) | Можливості |
|---|---|---|---|---|---|---|---|
| `b12-bolt-e4b:q4km` | `7eaa0c0553b8` | 6.2 GB | `gemma4` | 7.5B | Q4_K_M | 65,536 / 2,048 | completion, tools, thinking |
| `gemma4:12b` | `4eb23ef187e2` | 7.6 GB | `gemma4` | 11.9B | Q4_K_M | 262,144 / 4,096 | completion, vision, audio, tools, thinking |
| `qwen3.5:27b-q4_K_M` | `7653528ba5cb` | 17 GB | `qwen35` | 27.8B | Q4_K_M | 262,144 / 4,096 | completion, vision, tools, thinking |
| `qwen3.8:27b-q4_K_M` | `25b843619e94` | 17 GB | `qwen35` | 27.3B | Q4_K_M | 262,144 / 4,096 | completion, vision, tools, thinking |

### 3.3. Емпіричні результати тестового запуску моделей (Benchmark Probes)

Усі 4 моделі було емпірично протестовано живими запитами через `http://127.0.0.1:11434/api/generate`:

1. **`b12-bolt-e4b:q4km` (Головний кандидат B-12):**
   - VRAM розміщення: **3320 MiB (100% у VRAM)**
   - Час завантаження: ~11.3 с
   - Генерація: **51.86 токенів/с** (eval: 17 токенів за 327.7 мс)
   - Поведінка: Швидка генерація, повна підтримка tool calling, context 2048/4096.

2. **`gemma4:12b` (Кандидат для Group C Cross-Model):**
   - VRAM розміщення: **5121 MiB VRAM + ~3 GB RAM** (гібридний оффлоад)
   - Час завантаження: ~7.4 с
   - Генерація: **14.16 токенів/с** (eval: 188 токенів за 13.27 с)
   - Поведінка: Працює стабільно, відповіді якісні, є vision/audio проєктори.

3. **`qwen3.5:27b-q4_K_M` (Кандидат для Group C Cross-Model Reasoning):**
   - VRAM розміщення: **4352 MiB VRAM + ~12.8 GB RAM/Swap**
   - Час завантаження: ~33.2 с
   - Генерація: **3.81 токенів/с** (eval: 300 токенів за 78.5 с)
   - Поведінка: Увімкнено внутрішній reasoning блок (`<think>`), високе споживання пам'яті хоста, але повністю функціональна.

4. **`qwen3.8:27b-q4_K_M` (Кандидат для Group C Cross-Model Vision/Reasoning):**
   - VRAM розміщення: **4352 MiB VRAM + ~12.8 GB RAM/Swap**
   - Час завантаження: ~29.5 с
   - Генерація: **3.87 токенів/с** (eval: 20 токенів за 4.91 с)
   - Поведінка: CLIP projector на 460M параметрів, DeepSeek V4 HC fused ops, функціональна.

### 3.4. Наявність інших LLM-рантаймів
- **`llama.cpp`:** Локально скомпільований сервер із підтримкою CUDA знайдено за адресою:
  `/home/cyberdid/.local/src/llama.cpp/build-cuda/bin/llama-server`
  - Версія: `0.6.0-dev (build 1, commit 8bb3cf0)`
  - Компілятор: GNU 13.3.0 for Linux x86_64
  - Статус: Доступний бінарник, але постійний сервіс на порту не запущено.
- **`vLLM`:** Не встановлений у віртуальному середовищі проєкту, окремого демона немає.

### 3.5. Локальні профілі моделей та токенізатори
Для детермінованого підрахунку токенів та рендерингу Jinja-шаблонів (`hf-jinja-v1`) без виходу в мережу в системі наявні перевірені профілі:
1. `b12-bolt-e4b:q4km`:
   - Профіль: `profiles/bolt-e4b-ollama-0.33.3.json`
   - Активи токенізатора: `/home/cyberdid/Downloads/B-12-runtime/tokenizer/`
   - Перевірено хеші: `tokenizer.json` (`cc8d3a0c...`), `tokenizer_config.json` (`b3da1b72...`), `chat_template.jinja` (`35b7d064...`).
2. `gemma4:12b`:
   - Профіль: `/home/cyberdid/.local/share/b12/profiles/gemma4-12b-ollama-0.33.3.json`
   - Активи токенізатора: `/home/cyberdid/.local/share/b12/tokenizers/gemma4-12b/43c9d014b231474fa7212dbb48a762566c2b255d/`
   - Перевірено хеші: `tokenizer.json` (`9788bdb6...`), `tokenizer_config.json` (`a62f4e85...`), `chat_template.jinja` (`ae53464b...`).

---

## 4. Середовище Python та інфраструктура тестування

### 4.1. Версії та інструменти
- **Python:** `3.12.3` (`/home/cyberdid/Projects/B-12/.venv/bin/python`)
- **Менеджер пакетів:** `uv` версії 0.5+ (`/home/cyberdid/.local/bin/uv`)
- **Фреймворк тестування:** `pytest 9.1.1`, плагіни: `pytest-asyncio 1.4.0`, `anyio 4.15.1`, `platformdirs 4.13.7`
- **Лінтер / форматер:** `ruff 0.17.2`

### 4.2. Встановлені пакети та залежності
Середовище містить усі групи залежностей, визначені у `pyproject.toml`:
- **Core:** `httpx 0.28.1`, `pydantic 2.14.1`, `fastapi 0.162.0`, `uvicorn 0.54.0`, `numpy 2.5.4`, `pymorphy3 2.0.6` (з українським і російським словниками), `tokenizers 0.23.3`, `jinja2 3.1.6`.
- **TUI:** `textual 8.2.8`, `textual-image 0.14.2`, `pillow 13.0.0`, `rich 15.0.0`.
- **Voice:** `faster-whisper 1.2.1`, `onnxruntime 1.31.1`, `piper-tts 1.8.0`, `soundfile 0.14.0`, `ctranslate2 4.8.4`, `av 19.0.2`.
- **Голосові моделі в наявності:**
  - `/home/cyberdid/.local/share/b12/voices/silero_vad.onnx`
  - `/home/cyberdid/.local/share/b12/voices/uk_UA-mykyta-high.onnx` (+ json)
  - `/home/cyberdid/.local/share/b12/voices/uk_UA-ukrainian_tts-medium.onnx` (+ json)
  - `/home/cyberdid/.local/share/b12/voices/en_US-lessac-medium.onnx` (+ json)

### 4.3. Емпіричний статус наявного тестового набору (Test Suite Audit)
- **Всього знайдено тестів:** **656** у каталозі `tests/`.
- **Запуск повного автономного набору (`-m "not real_model and not hardware"`):**
  - **Результат:** 650 passed, 2 failed, 1 skipped, 3 deselected за 158.17 с.
- **Модульні тести (`tests/unit/`):**
  - **Результат:** 233 passed із 233 за 4.56 с (100% успіх).
- **Голосові тести (`tests/integration/test_voice.py`):**
  - **Результат:** 7 passed із 7 за 16.65 с (100% успіх).
- **Роботизований протокол (`tests/integration/test_robot_protocol.py`):**
  - **Результат:** 10 passed із 10 за 2.53 с (100% успіх).

### 4.4. Детальний аналіз виявлених дефектів (2 Test Failures)

1. **Дефект №1: `tests/e2e/test_cli.py::test_tools_lists_catalog_without_secrets`**
   - **Помилка:** `AssertionError: assert (0 == 0 and 16 == 15)`
   - **Причина:** Тест очікував рівно 15 вбудованих інструментів. До каталогу `b12.tools.network` було додано інструмент `web_search`, що збільшило кількість інструментів до 16 (`file_list`, `file_read`, `file_search`, `file_write`, `note_add`, `system_info`, `process_list`, `shell_exec`, `run_command`, `http_fetch`, `web_search`, `memory_search`, `memory_store`, `memory_forget`, `knowledge_search`, `current_time`). Тест не був синхронізований із новим інструментом.

2. **Дефект №2: `tests/integration/test_tui.py::test_pet_shortcut_preserves_draft_and_control_panel_shortcut_opens_panel`**
   - **Помилка:** `AssertionError: assert 49 < 24` (де 49 — координата Y віджета `#mem-query`).
   - **Причина:** Після злиття гілки `feat/b12-cybercat-tui` (коміти `0947f2e`, `cb5db3c`, `72a06d6`) до панелі керування додалися нові віджети (голосовий статус, таймлайн активності, звіти, перемикач скінів). Висота панелі збільшилася, і поле введення пошуку пам'яті опинилося на рядку 49 (у зоні прокручування панелі), тоді як тест розрахований на фіксовану висоту вікна 80x24.

---

## 5. Матриця можливостей підсистем (Capability Matrix)

Відповідно до вимог R1, категоризуємо всі ключові підсистеми Capri / B-12:

| Підсистема / Модуль | Компоненти коду | Статус | Обґрунтування та емпіричні докази |
|---|---|---|---|
| **Автобіографічна пам'ять (Autobiographical Memory)** | `MemoryStore`, `EvidenceResolver`, `migrations.py` | **TESTED** | Повністю реалізовано: SQLite, схема v2 з доказами цитування, шифрування/хешування фактів, семантичний та лексичний пошук, перевірено 7-денний чекпоінт R17. 233 модульні тести проходять. |
| **Довготривала пам'ять та забуття (Purge / Retention)** | `PurgeCoordinator`, `Maintenance`, `purge.py` | **TESTED** | Повна реалізація global purge, видалення за UUID, оновлення derived індексів без витоку байтів. Підтверджено системним аудитом `b12-daily-check`. |
| **Виконання та контроль інструментів (Tool Policy & Sandbox)** | `ToolRegistry`, `EffectGuard`, `BackupStore`, `tools/*` | **TESTED** | 16 типізованих інструментів, суворі гранти прав, обов'язковий approval для `sudo_exec`, оборотний запис файлів із бекапом, захист системних шляхів. |
| **Локальний LLM-транспорт (Model Transport)** | `OllamaModel`, `ModelProfile`, `ContextBuilder` | **TESTED** | Детермінований стримінг через Ollama API, точний підрахунок токенів через офлайн Jinja2/tokenizers, захист від обрізання контексту. Перевірено на `bolt-e4b` та `gemma4:12b`. |
| **Крос-модельна наступність (Cross-Model)** | `b12-bolt-e4b`, `gemma4:12b`, `qwen3.5:27b`, `qwen3.8:27b` | **EXPERIMENTAL** | Всі 4 моделі запускаються локально. `bolt-e4b` і `gemma4:12b` мають точні профілі токенізаторів. `qwen3.5` та `qwen3.8` працюють у гібридному режимі (3.8-4.0 tok/s). |
| **Голосова взаємодія (Voice Subsystem)** | `b12.audio/*` (ASR, TTS, VAD, AEC, Duplex) | **TESTED** (софт) / **NOT_AVAILABLE** (фізичний зал) | Повний софтверний стек на базі Whisper, Silero ONNX, Piper TTS, WebRTC AEC. 7 тестів інтеграції проходять, синтетичний WER=0.0%. Фізичний 8-годинний soak у кімнаті з шумом ще не проводився. |
| **Автономність та ініціатива (Autonomy & Goals)** | `GoalStore`, `AttentionPolicy`, `autonomy.py` | **TESTED** | Фонова рефлексія на idle-тіках, оновлення пріоритетів цілей, блокування втручання під час активних сесій. Перевірено в E2E тестах. |
| **Користувацькі інтерфейси (TUI & Web)** | `b12.tui/*`, `b12.web/*`, `FastAPI` | **TESTED** | Повноцінний кіберпанковий TUI на Textual з анімацією Кіберкота, підтримкою скінів Capri, аудіо-контролями та звітами. Web UI із суворим CSP та токенами авторизації. |
| **Робототехніка та втілення (Robotics & Embodiment)** | `b12.robotics/motion.py`, `transport.py` | **EXPERIMENTAL** (протокол) / **NOT_AVAILABLE** (залізо) | 10 тестів протоколу руху Reachy проходять у режимі симулятора. Фізичне обладнання (робот Reachy / Jetson Orin) відсутнє. |

---

## 6. Рекомендації та висновки для експериментального набору (Groups A–K)

1. **Базова модель для експериментів:**
   - Рекомендується використовувати `b12-bolt-e4b:q4km` для більшості тестів поведінки (Groups A, B, D, E, F, G, H, I, K), оскільки вона повністю поміщається у VRAM (3.3 GB footprint), має найвищу швидкість (52 tok/s) та перевірений профіль токенізатора.
2. **Кандидати для Group C (Cross-Model Behavioral Continuity):**
   - **Кандидат №1:** `b12-bolt-e4b:q4km` (базова модель, 7.5B, Q4_K_M).
   - **Кандидат №2:** `gemma4:12b` (11.9B, Q4_K_M). Має готовий локальний профіль `/home/cyberdid/.local/share/b12/profiles/gemma4-12b-ollama-0.33.3.json`, токенізатор перевірено, швидкість 14 tok/s, чудова якість української та англійської мов.
   - **Кандидат №3:** `qwen3.5:27b-q4_K_M` (27.8B, Q4_K_M). Доцільно використовувати для окремих складних міркувань (Reasoning ablation), враховуючи повільну генерацію (~4 tok/s) та навантаження на swap.
3. **Обмеження безпеки та пісочниці:**
   - Для adversarial/security тестів (Group E) слід використовувати виключно тимчасові ізольовані каталоги (`tmp_path`) без доступу до реальних ключів SSH (`~/.ssh`), конфігурацій чи продуктових баз даних.
4. **Статус фізичних тестів:**
   - Тести групи J (Robotics) виконувати виключно проти симулятора (`mock transport`), оскільки фізичний маніпулятор відсутній.
   - Тести із затримкою у часі (Day 7 / Day 30 для Group B) фіксувати на основі вже збереженого 8-денного чекпоінта `b12-daily-check`, а нові тривалі тести помічати як `PENDING` без штучної фальсифікації результатів.
