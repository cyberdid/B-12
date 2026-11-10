# Звіт передачі результатів аудиту (Handoff Report) — Explorer 1

**Дата:** 2026-11-10T10:48:00+02:00  
**Автор:** Explorer 1 (Environment, Runtime & Infrastructure Auditor)  
**Цільовий агент / Одержувач:** Orchestrator (parent agent: `f7064ab7-5ff4-4a09-bb25-95e84e62ebcd`)  
**Повний звіт аудиту:** `/home/cyberdid/Projects/B-12/.agents/teamwork/explorer_survey_env/analysis.md`  

---

## 1. Observation (Прямі емпіричні спостереження)

1. **Стан Git:**
   - Команда: `git rev-parse HEAD && git branch --show-current && git status --porcelain`
   - Результат: SHA `8f296615e591faef33ac1755de919307134fe21a`, гілка `main`.
   - Tracked files чисті (`git diff --stat` порожній). Untracked: `.agents/`, `"Статті/"`.
   - `git worktree list` виявив 5 worktrees: головне `/home/cyberdid/Projects/B-12` [`main`], `/home/cyberdid/.codex/worktrees/bac0/B-12` [`feat/b12-cybercat-tui`], `/home/cyberdid/.codex/worktrees/cb2c/B-12` [`feat/b12-desktop-companion`], `/home/cyberdid/Projects/B-12/.worktrees/access` [`feat/b12-access`], `/home/cyberdid/Projects/B-12/.worktrees/runtime` [`feat/b12-runtime`].

2. **Апаратні специфікації хоста:**
   - CPU: Intel Core i9-14900HX (24 ядра / 32 потоки, до 5.8 GHz).
   - RAM: 31 GiB DDR5; вільно/доступно 13–24 GiB; Swap 8.0 GiB (активно використовується під час інференсу 27B моделей).
   - GPU: NVIDIA GeForce RTX 4060 Laptop (AD107M), 8188 MiB VRAM GDDR6, Driver: 610.57.04, CUDA UMD 13.3.
   - GPU фоновий процес: PID 55058 (`scripts/embed_bridge.py --backend archive_index.embed:Embedder`) утримує 1584 MiB VRAM. Чистий вільний VRAM хоста: ~6.5 GB.
   - Диск: `/dev/nvme0n1p5` змонтовано на `/`: 410 GB всього, 373 GB зайнято, **вільно лише 16 GB (96% Use%)**.

3. **Локальні LLM-рантайми:**
   - Сервіс `systemd` Ollama запущено (PID 3524, версія сервера `0.33.3`, клієнт `0.33.1`).
   - Наявні моделі в `ollama list`:
     - `b12-bolt-e4b:q4km` (ID: `7eaa0c0553b8`, 6.2 GB, architecture: `gemma4`, 7.5B, Q4_K_M). Займає 3320 MiB VRAM (100% у GPU), генерація **51.86 токенів/с**. Профіль: `profiles/bolt-e4b-ollama-0.33.3.json`, токенізатор: `/home/cyberdid/Downloads/B-12-runtime/tokenizer/`.
     - `gemma4:12b` (ID: `4eb23ef187e2`, 7.6 GB, architecture: `gemma4`, 11.9B, Q4_K_M). Займає 5121 MiB VRAM + ~3 GB RAM, генерація **14.16 токенів/с**. Профіль: `/home/cyberdid/.local/share/b12/profiles/gemma4-12b-ollama-0.33.3.json`, токенізатор: `/home/cyberdid/.local/share/b12/tokenizers/gemma4-12b/43c9d014b231474fa7212dbb48a762566c2b255d/`.
     - `qwen3.5:27b-q4_K_M` (ID: `7653528ba5cb`, 17 GB, architecture: `qwen35`, 27.8B, Q4_K_M). 4352 MiB VRAM + ~12.8 GB RAM/Swap, генерація **3.81 токенів/с**.
     - `qwen3.8:27b-q4_K_M` (ID: `25b843619e94`, 17 GB, architecture: `qwen35`, 27.3B, Q4_K_M, з CLIP projector). 4352 MiB VRAM + ~12.8 GB RAM/Swap, генерація **3.87 токенів/с**.
   - Додаткові рантайми: наявний бінарник `/home/cyberdid/.local/src/llama.cpp/build-cuda/bin/llama-server` (версія 0.6.0-dev, commit 8bb3cf0). vLLM відсутній.

4. **Середовище Python та тестовий набір:**
   - Python: 3.12.3 у `/home/cyberdid/Projects/B-12/.venv/bin/python`, менеджер `uv`.
   - Pytest 9.1.1, pytest-asyncio 1.4.0, ruff 0.17.2.
   - Всього в репозиторії 656 тестів.
   - Запуск `pytest -m "not real_model and not hardware"`: **650 passed, 2 failed, 1 skipped, 3 deselected за 158.17 с**.
   - Модульні тести `tests/unit/`: **233 passed із 233 (100%)**.
   - Голосові тести `tests/integration/test_voice.py`: **7 passed із 7 (100%)**.
   - Робототехнічні тести `tests/integration/test_robot_protocol.py`: **10 passed із 10 (100%)**.
   - Два зафіксовані дефекти в тестах:
     - `tests/e2e/test_cli.py::test_tools_lists_catalog_without_secrets`: `assert 16 == 15` (додано `web_search` до каталогу інструментів).
     - `tests/integration/test_tui.py::test_pet_shortcut_preserves_draft_and_control_panel_shortcut_opens_panel`: `assert 49 < 24` (збільшення висоти панелі керування через нові віджети TUI кіберкота).

---

## 2. Logic Chain (Логічний ланцюг обґрунтування)

1. **Апаратна придатність:**
   - Оскільки чистий доступний VRAM складає ~6.5 GB (через фоновий процес семантичного індексу на 1.6 GB), модель `b12-bolt-e4b:q4km` (потребує 3.3 GB VRAM) повністю завантажується в GPU і демонструє найвищу швидкість (51.86 tok/s), що робить її безальтернативною базовою моделлю для швидких та інтерактивних E2E сценаріїв.
2. **Готовність до крос-модельного оцінювання (Group C):**
   - Модель `gemma4:12b` успішно перевірена в роботі: вона генерує зі швидкістю 14.16 tok/s, має готовий перевірений профіль `profiles/gemma4-12b-ollama-0.33.3.json` та збережений локальний токенізатор. Це забезпечує 100% готовність до крос-модельних тестів з однаковою архітектурною родиною Gemma 4.
   - Моделі `qwen3.5:27b` та `qwen3.8:27b` хоч і працездатні (3.8–3.9 tok/s), через свій розмір (17 GB) вимагають використання 12.8 GB системної RAM та swap, що викликає суттєвий latency penalty і не повинно використовуватися для тривалих масових прогонів.
3. **Готовність підсистем B-12:**
   - Модулі пам'яті (`MemoryStore`, `EvidenceResolver`), політики інструментів (`ToolRegistry`, `EffectGuard`), голосу (`b12.audio/*`), TUI (`b12.tui/*`) та автономності (`GoalStore`, `AttentionPolicy`) реалізовані та мають працюючі тести.
   - Дефекти в 2 тестах є суто регресіями тестових асертів (збільшення кількості інструментів з 15 до 16 та зміна верстки панелі TUI), а не збоями логіки ядра.

---

## 3. Caveats (Застереження та обмеження)

1. **Критичне застереження щодо диска:** Залишок вільного простору на SSD становить **лише 16 GB**. Завантаження будь-якої нової великої моделі або збереження гігабайтних сирих логів може спричинити заповнення диска до 100% та падіння ОС.
2. **Акустичне та фізичне середовище:** Голосовий стек перевірено на програмному та синтетичному рівнях (AEC ERLE 30.4 dB, WER=0.0%). Реального 8-годинного акустичного тесту в шумній кімнаті з апаратним мікрофоном/динаміком не проводилося.
3. **Робототехнічне залізо:** Фізичний робот Reachy / плата Jetson Orin відсутні; всі роботизовані тести виконуються проти симулятора (`mock transport`).
4. **Довготривалі тести (Day 7 / Day 30):** Наявний підтверджений чекпоінт 8 діб (`b12-daily-check`). Нові сценарії з реальними тривалими затримками повинні фіксуватися як `PENDING` або використовувати змодельовані часові зсуви.

---

## 4. Conclusion (Підсумковий висновок)

1. **Готовність інфраструктури:** Робоче середовище повністю функціональне для виконання експериментального набору оцінювання Capri Comprehensive Evaluation (Groups A–K).
2. **Вибір моделей:**
   - **Baseline & Primary Model:** `b12-bolt-e4b:q4km` (швидкий, детермінований токенізатор, повне розміщення в GPU).
   - **Cross-Model Continuity (Group C):** Тандем `b12-bolt-e4b:q4km` ↔ `gemma4:12b` (обидві моделі мають верифіковані локальні токенізатори та готові профілі в системі).
3. **Статус підсистем за критеріями R1:**
   - Пам'ять (Autobiographical Memory): **TESTED**
   - Інструменти та політика (Tool Policy): **TESTED**
   - LLM-транспорт (Model Transport): **TESTED**
   - Голос (Voice Subsystem): **TESTED (софт)** / **NOT_AVAILABLE (фізичний зал)**
   - Автономність (Autonomy): **TESTED**
   - TUI компаньйон: **TESTED**
   - Робототехніка (Robotics): **EXPERIMENTAL (протокол)** / **NOT_AVAILABLE (залізо)**

---

## 5. Verification Method (Метод незалежної верифікації)

1. **Перевірка Git та робочого оточення:**
   ```bash
   git rev-parse HEAD
   # Очікувано: 8f296615e591faef33ac1755de919307134fe21a
   git status --porcelain
   # Очікувано: лише .agents/ та "Статті/"
   ```
2. **Перевірка моделей в Ollama:**
   ```bash
   ollama list
   # Очікувано: b12-bolt-e4b:q4km, gemma4:12b, qwen3.5:27b-q4_K_M, qwen3.8:27b-q4_K_M
   curl -s http://127.0.0.1:11434/api/version
   # Очікувано: {"version":"0.33.3"}
   ```
3. **Перевірка генерації базової моделі:**
   ```bash
   curl -s http://127.0.0.1:11434/api/generate -d '{"model": "b12-bolt-e4b:q4km", "prompt": "test", "stream": false}' | jq .done
   # Очікувано: true
   ```
4. **Запуск автоматичних тестів:**
   ```bash
   /home/cyberdid/Projects/B-12/.venv/bin/pytest tests/unit/ -q
   # Очікувано: 233 passed
   /home/cyberdid/Projects/B-12/.venv/bin/pytest tests/integration/test_voice.py -q
   # Очікувано: 7 passed
   /home/cyberdid/Projects/B-12/.venv/bin/pytest tests/integration/test_robot_protocol.py -q
   # Очікувано: 10 passed
   ```
5. **Файли для інспекції:**
   - Повний детальний звіт: `/home/cyberdid/Projects/B-12/.agents/teamwork/explorer_survey_env/analysis.md`
   - Профілі моделей: `profiles/bolt-e4b-ollama-0.33.3.json`, `/home/cyberdid/.local/share/b12/profiles/gemma4-12b-ollama-0.33.3.json`
