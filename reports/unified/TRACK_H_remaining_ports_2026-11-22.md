# Track H — звіт про виконання (H4, H6 Step 1, H7)

**Дата:** 2026-11-22  
**Гілка / worktree:** підготовлено в `.worktrees/tmp-track-h` (`tmp/track-h-20261122`: `86d5058`, `f6ac0f8`, `0c73898`), інтегровано у `.worktrees/unified-dr2-dr3` (`feat/unified-dr2-dr3`: H4 `2717d87`, H6 step 1 `1b0efde`, H7 `dfcba6c`)  
**Обмеження виконання дотримано:** жодного запуску реальних моделей, жодного завантаження локального GPU чи Colab, жодного завантаження ONNX-моделей, `summary`-політику в H4 не реалізовано, `tests/fixtures/prompt_surface/owner_default.json` не змінено.

---

## 1. H4: Compaction-recall harness (`evals/unified/compaction_recall.py`)

- **Коміт:** `2717d87` у `feat/unified-dr2-dr3` (з `86d505869dbdc04b3cfb2653961bf1a0c634dc3a`, `eval(unified): compaction-recall harness for trim vs trim+memory (H4)`)
- **Файли:**
  - `evals/unified/compaction_recall.py`
  - `tests/unified/test_compaction_recall.py`
- **Реалізація:**
  - Генератор синтетичної української розмови власника `build_synthetic_conversation()` створює 40 ходів (6 вступних фонових ходів → 12 ходів із закладеними синтетичними фактами `F01..F12` посередині → 22 завершальні фонові ходи; жодних реальних персональних даних).
  - Політики: лише `trim` (існуючий `Agent.history_turns` + `ContextBuilder` / `_fit_history` без записів у `MemoryStore`) та `trim+memory` (ті самі ходи плюс 12 закладених фактів у `MemoryStore`, які підтягуються через `Agent._recall` у блок `Evidence (untrusted data):`). Політика `summary` (`history_summary`) у цьому треку не реалізується і явно відхиляється з `ValueError`.
  - Питання проганяються по одному над незалежною копією засіяного `state_dir` із грантом `("eval.post_admission",)` (0 інструментів у схемі — відповідь формується виключно з post-admission контексту).
  - Exact-match scorer (`score_exact_match`) порівнює нормалізовану відповідь з еталонним значенням (`1.0` / `0.0`); додатково логується `relaxed_recall` (`score_contains_match`) і кількість `prompt_tokens` (`prompt_eval_count`) на кожну політику.
- **Перевірка (після правок H4, без реальної моделі):**
  - `tests/unified/test_compaction_recall.py` (5 тестів) + `tests/integration/test_prompt_surface.py` (1 тест): **6 passed in 17.71s**.
  - Зі `scripted_ollama` (читач post-admission повідомлень): `trim` показав `recall = 0.0` (0/12), `trim+memory` показав `recall = 1.0` (12/12) як при `num_ctx=32768` (`history_turns=20`), так і при `num_ctx=16384` (`history_turns=60` — коли середина витісняється `ContextBuilder`).
  - `ruff check` і `ruff format --check` пройшли чисто.
- **Наступний крок (Track G):** прогін `h4-compaction` на Colab (`gemma4:12b`) після замороження та визначення бюджету власником; реалізація `summary` (`history_summary`) — лише за рішенням власника, якщо `trim+memory` дасть recall `< 0.8`.

---

## 2. H6: Wake word (local) — Step 1 завершено, Step 2 на Stop-and-Ask

- **Коміт:** `1b0efde` у `feat/unified-dr2-dr3` (з `f6ac0f889da00256654e7f76d1ea687e9af5114b`, `feat(audio): local wake word gating, 2s refractory, RAM ring buffer (H6 step 1, wake_word off)`)
- **Файли:**
  - `src/b12/audio/wake.py`
  - `src/b12/audio/__init__.py`
  - `src/b12/audio/live.py`
  - `src/b12/config.py`
  - `tests/unit/test_config.py`
  - `tests/integration/test_wake_word.py`
- **Реалізація Step 1:**
  - Створено `WakeDetector` (`src/b12/audio/wake.py`) з методом `feed(frame) -> bool`, порогом `threshold=0.5`, рефрактерним періодом `refractory_s: float = 2.0` і кільцевим буфером `collections.deque` на `ring_buffer_s: float = 1.5` виключно в оперативній пам'яті (без жодних записів на диск). Без завантаженої моделі чи зовнішнього `scorer` `score()` повертає `0.0`.
  - У `LiveSession` (`src/b12/audio/live.py`) додано режим `mode="wake"` (`wake_detector`, `wake_window_s: float = 8.0`, `clock`): висловлювання з `Segmenter` приймаються (передаються в ASR та `DuplexSession.process_cleaned_utterance`) лише протягом 8 с після спрацювання `wake_detector.feed(...)`; поза вікном емітиться подія `wake_ignored`. За замовчуванням `mode="always"`, тож поведінка без прапорця не змінюється.
  - Додано прапорець `Settings.wake_word: bool = False` у `src/b12/config.py` (внесено до env bool tuple в `Settings.from_env` і до `tests/unit/test_config.py`).
- **Перевірка (після правок H6 Step 1 та інтеграції поверх Track F у `unified-dr2-dr3`, без реальної моделі):**
  - `tests/integration/test_wake_word.py` (5 тестів, включно з обов'язковими `test_utterances_before_wake_are_ignored`, `test_window_closes_after_8_seconds`, `test_ring_buffer_never_persists`), `tests/integration/test_live_duplex.py`, `tests/unit/test_config.py` (із прапорцями `skills` і `wake_word`) і `tests/integration/test_prompt_surface.py`: **82 passed in 56.18s**.
  - `ruff check` і `ruff format --check` пройшли чисто.

### Stop-and-Ask для H6 Step 2 (завантаження ONNX-моделі openWakeWord)

Реальні ONNX-файли **не завантажувалися** і нові пакети **не встановлювалися**. Інформацію нижче зібрано через `search_web` (**2026-11-22**) за публічними метаданими `dscripka/openWakeWord` (`v0.5.1`):

| Файл | Роль у пайплайні | Source URL (`v0.5.1`) | Приблизний розмір | Ліцензія |
|---|---|---|---|---|
| `melspectrogram.onnx` | 1-й етап: 16 kHz PCM → mel-спектрограма | `https://github.com/dscripka/openWakeWord/releases/download/v0.5.1/melspectrogram.onnx` | ~1.0–1.1 MB | Apache-2.0 / базовий DSP (атрибуція openWakeWord) |
| `embedding_model.onnx` | 2-й етап: mel-спектрограма → 96-вимірний speech embedding | `https://github.com/dscripka/openWakeWord/releases/download/v0.5.1/embedding_model.onnx` | ~1.3–1.33 MB | Apache-2.0 / похідна від Google `speech_embedding` (атрибуція Google + openWakeWord) |
| `hey_jarvis_v0.1.onnx` | 3-й етап: класифікатор фрази активації («Hey Jarvis», приклад із коробки) | `https://github.com/dscripka/openWakeWord/releases/download/v0.5.1/hey_jarvis_v0.1.onnx` | ~165 KB (інші варіанти/голови ~100 KB–1.2 MB) | **CC-BY-NC-SA-4.0** (обмеження NonCommercial на передтреновані ваги) |

- **Сумарний розмір базового стеку (3 файли):** ~2.6 MB. (Точний розмір у байтах і SHA-256 не знімалися, бо завантаження заборонено до схвалення власника.)
- **Питання до власника (Stop-and-Ask):**
  1. Чи схвалюєте ви завантаження спільних моделей `melspectrogram.onnx` (~1,1 MB) та `embedding_model.onnx` (~1,33 MB) з `dscripka/openWakeWord` (`v0.5.1`)?
  2. Чи використовувати тимчасово передтренований класифікатор `hey_jarvis_v0.1.onnx` (~165 KB, ліцензія **CC-BY-NC-SA-4.0**, тільки для локального R&D без комерційного поширення) для перевірки Step 2, чи відкласти Step 2 до натренування власного ONNX-класифікатора для фрази «Капрі» / «Hey Capri» без NC-обмеження?
  3. Чи запускати ці 3 ONNX-файли напряму через уже наявний у середовищі `onnxruntime` + `numpy` (без додавання пакета `openwakeword` до залежностей, за аналогією з `SileroVad`), чи встановлювати бібліотеку `openwakeword`? *(Рекомендація: почати з чистого `onnxruntime` без нових залежностей, але це потребує окремої перевірки збігу mel/embedding-передобробки.)*

---

## 3. H7: Eywa (`arXiv:2605.30771`) та зовнішні бенчмарки пам'яті

- **Створено картку джерела:** [wiki/sources/eywa-2026-11-22.md](../../wiki/sources/eywa-2026-11-22.md).
- **Дотримання меж достовірності (`AGENTS.md`):**
  - Дані про Eywa (`https://arxiv.org/abs/2605.30771`, `https://eywa.to/research`), LongMemEval-S (`https://github.com/xiaowu0162/LongMemEval`) і BEAM (`https://github.com/mohammadtavakoli78/BEAM`) отримано через `search_web` **2026-11-22**. Знімки сторінок у `raw/` не збережено; повний PDF та сирі JSON-артефакти не читалися.
  - Заявлені цифри Eywa (LoCoMo C1–C4 **90,19 %** на Claude Sonnet 4.6, LongMemEval-S **88,2 %** retrieval-sufficiency, BEAM 700-питальний зріз **81,45 %** mean nugget / **85,29 %** `pass@score ≥ 0.5`) явно позначено як **заяви авторів**.
- **Оцінка доцільності LongMemEval-S / BEAM на B-12:**
  - **BEAM** (MIT код / CC BY-SA 4.0 датасет, до 10M токенів на розмову, 2000 питань): **не запускати** в цьому циклі (надмірний масштаб і вартість).
  - **LongMemEval-S** (MIT, 500 питань по ~30–40 сесій / ~115K токенів): без **bulk ingestion без модельного ходу** прогін через LLM-екстрактор (~57,5M токенів) нереалістично дорогий; прямий запис у `SessionStore` + `messages_fts` / `MemoryStore` без LLM на запис швидкий (хвилини на CPU), але 500 QA-ходів на `gemma4:12b` коштують ~1,5–3,5 год Colab і покривають лише англомовний контекст.
- **Відкрите питання для власника (кандидат Q23) із рекомендацією:**
  - Не витрачати бюджет Track G на LongMemEval-S / BEAM; після завершення Track G розглянути окремо легкий bulk-ingestion адаптер (без виклику LLM при завантаженні) для контрольного зрізу **50–100 питань LongMemEval-S** (перш за все безмодельний retrieval-sufficiency прогін).

---

## 4. Підсумок Stop-and-Ask перед інтеграцією

1. **H6 Step 2:** підтвердити завантаження ONNX-файлів openWakeWord (`melspectrogram.onnx`, `embedding_model.onnx`, вибір класифікатора з урахуванням CC-BY-NC-SA-4.0 vs власної фрази «Капрі», та вибір `onnxruntime` vs `openwakeword`).
2. **H4 / H7:** підтвердити пріоритет Track G (`h4-compaction` у `G2.2`) і чи планувати після Track G 50–100-питальний retrieval-sufficiency зріз LongMemEval-S через bulk ingestion (Q23).
