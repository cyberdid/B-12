# Рев'ю додаткових змін (`0c6643f..HEAD`, Track R3 — 2026-11-22)

**Мета:** перевірити всі зміни в `src/b12/agent.py`, `src/b12/control.py`, `src/b12/runtime.py`, `evals/unified/judge_sheet.py`, `evals/unified/build_scenario_drafts.py`, `evals/unified/score_u2_u3.py` у діапазоні `0c6643f..HEAD` (включаючи проміжні коміти `00f64e5`..`63d16c3` та виправлення гігієни `45fdcbd` R1 / `7ade6fe` R2), перевірити відсутність змін поведінки при вимкнених прапорцях і сформулювати вердикт. У межах R3 код не змінювався.

**Зведений вердикт:** **PASS** (після фіксів R1 `45fdcbd` та R2 `7ade6fe`). Жодна зміна не змінює `SYSTEM_PROMPT`, схеми інструментів або поведінку моделі за вимкнених прапорців (`tests/fixtures/prompt_surface/owner_default.json` без змін). Правило `unexecuted_claim` у `evals/unified/score_u2_u3.py` (R2) змінює лише eval-скорер і потребує повторного скорингу порівнюваних arms у Track G.

---

## Детальний розбір по файлах

### 1. `src/b12/agent.py`
- **Коміти:** `00f64e5` (C1a), `45fdcbd` (R1).
- **Що змінено:**
  - У `00f64e5`: додано `self._tainted_history: set[str] = set()` у `Agent.__init__`; у `_record_call_outcome` при завершенні інструмента з `tool.capability == "network.http"` додано `self._tainted_history.add(context.turn_id)`; у `_commit()` додано `tainted = bool(state.get("tainted") or context.turn_id in self._tainted or context.turn_id in self._tainted_history)` і, коли `tainted` істинне, запис `self.control.set_meta(f"tainted_turn:{context.turn_id}", "1")` після `sessions.commit_turn(...)`.
  - У `45fdcbd` (R1): додано `_TAINT_HISTORY_MAX = 1024`, `self._tainted_order: deque[str] = deque(maxlen=_TAINT_HISTORY_MAX)` і метод `_record_tainted_history()`, який обмежує `_tainted_history` до 1024 останніх унікальних `turn_id` (витісняючи найстаріший зі `_tainted_order` та `_tainted_history`), зберігаючи при цьому довготривалий запис у `control.meta`.
- **Чому:** `MemoryReviewer` (ADR-020) мусить виключати мережеві ходи, навіть якщо `self._tainted` очищається в `_commit()`/`finish()` або якщо хід переривався через `awaiting_clarify`/`awaiting_approval` чи стався в попередній сесії процесу. Обмеження в R1 запобігає необмеженому росту in-memory set у довготривалих процесах.
- **Чи змінює поведінку при вимкнених прапорцях:**
  - Відповідь моделі, системний промпт, інструменти й логіка `memory_taint=False` не змінюються (`owner_default.json` без змін).
  - **Спостережений побічний ефект:** коли `memory_review=False`, `_commit()` все одно записує `tainted_turn:<turn_id> = "1"` у таблицю `meta` (`control.sqlite3`) після завершеного `network.http` ходу. Це безпечний обліковий запис (читається лише у `MemoryReviewer._is_tainted` при `memory_review=True`) і не впливає на поведінку агента, однак має бути зафіксовано як зміна у `control.meta`.
- **Вердикт:** **PASS** (необмежене зростання `_tainted_history` вже виправлено в R1 `45fdcbd`; прибирання старих ключів `tainted_turn:*` за віком можна буде додати в окрему задачу лише за потреби при масштабах >10^5 ходів).

### 2. `src/b12/control.py`
- **Коміти:** `00f64e5` (C1a).
- **Що змінено:** додано read-only метод `ControlStore.turn_task_id(self, turn_id: str) -> str | None` (`SELECT task_id FROM turns WHERE id=?`).
- **Чому:** дає змогу `MemoryReviewer._is_goal_turn()` перевірити, чи належить хід до фонового завдання цілі (`control.task_goal(task_id)`), щоб виключати технічні/автономні ходи з огляду пам'яті.
- **Чи змінює поведінку при вимкнених прапорцях:** ні; метод не викликається, доки `memory_review=False`, і не змінює схему чи стан БД.
- **Вердикт:** **PASS**.

### 3. `src/b12/runtime.py`
- **Коміти:** `fbc4957` (C1b), `9474ed5` (`fix(memory)`).
- **Що змінено:** у `open_runtime()` підключено `sessions.on_clear_turns = _on_clear_turns`, який для кожного очищеного `turn_id` викликає `memory.forget_by_locator(actor, f"turn:{turn_id}", source="post_turn_review")`.
- **Чому:** очищення сесії (`SessionStore.clear_session`) має забувати залежні факти (і очищувати `review_pending`), створені `MemoryReviewer` із `source="post_turn_review"` для цих ходів, але не видаляти пам'ять, явно записану моделлю з іншим `source` (`9474ed5`).
- **Чи змінює поведінку при вимкнених прапорцях:** якщо `memory_review=False` і `post_turn_review`-записів не існує, `forget_by_locator(..., source="post_turn_review")` знаходить 0 цілей і є no-op. Якщо `memory_review` раніше вмикався і лишив записи, їхнє очищення при `clear_session` відповідає інваріанту забуття залежних копій. (Примітка: `forget_by_locator` перевіряє `startswith(prefix)`, але через унікальний UUID4 у `turn:{turn_id}` із фільтром `source="post_turn_review"` колізій префіксів немає.)
- **Вердикт:** **PASS**.

### 4. `evals/unified/judge_sheet.py`
- **Коміти:** `a128743` (`ports-live-v1`).
- **Що змінено:** у `_facts(setup)` до переліку ключів додано `"synthetic_sessions"` і `"review_tick"`.
- **Чому:** сліпим суддям для сценаріїв `ports-live-v1` (`M93` conversation recall та `M94` post-turn memory review) потрібні синтетичні попередні сесії та факт спрацювання `review_tick` як ground-truth факти сетапу.
- **Чи змінює поведінку при вимкнених прапорцях:** ні; eval-інструмент, додає поля лише за `setup.get(key) is not None`, тому листи попередніх наборів (`u2-u3-locked-v2`, `u5-application-locked-v1`, `intg-live-v1`) лишаються незмінними.
- **Вердикт:** **PASS**.

### 5. `evals/unified/build_scenario_drafts.py`
- **Коміти:** `a128743` (`ports-live-v1`).
- **Що змінено:** у `build_set()` додано гілку `elif review_status != "UNREVIEWED"` для `notes` маніфесту, яка відображає частковий статус огляду (наприклад, `DRAFT_PENDING_OWNER_REVIEW:...`), не змішуючи його з `UNREVIEWED` або `FROZEN`.
- **Чому:** коректне маркування `ports-live-v1` після сліпого рев'ю Gemini в очікуванні рев'ю Codex власником.
- **Чи змінює поведінку при вимкнених прапорцях:** ні; eval-інструмент генерації маніфестів, не впливає на `FROZEN` або `UNREVIEWED` набори та не торкається runtime.
- **Вердикт:** **PASS**.

### 6. `evals/unified/score_u2_u3.py`
- **Коміти:** `a128743` (`ports-live-v1`), `7ade6fe` (R2).
- **Що змінено:**
  - У `a128743`: до `TOOLS` додано `"conversation_search"` і `"clarify"` (до R2 використовувалися лише в `_evidence` для `tool:...` та у `forbidden_effects`). Функція `_claimed_tools` у базовому дифі `0c6643f..63d16c3` була відсутня.
  - У `7ade6fe` (R2, за рішенням координатора): додано `_claimed_tools(text: str) -> set[str]` (`set(re.findall(r"\b([a-z]+_[a-z]+)\b", (text or "").lower())) & TOOLS`), перевірку `unexecuted_claim` (`FAIL`) у `score()` для згаданих у `reply` інструментів без виклику в `tool_calls`, документування правила в module docstring (зокрема, чому `clarify` без підкреслення не спрацьовує на англійське слово `clarify`, а буквальне `conversation_search` без виклику фіксується) та примітку в `evals/unified/README.md` про повторний скоринг.
- **Чому:** підтримка нових інструментів `ports-live-v1` (`M93` вимагає `tool:conversation_search`) і формалізація правила щодо нездійснених текстових згадок назв інструментів.
- **Чи змінює поведінку при вимкнених прапорцях:**
  - На runtime B-12 не впливає (eval-скорер).
  - Зміни `a128743` (`TOOLS`) не впливали на старі заморожені набори (`u2-u3-locked-v2`, `u5-application-locked-v1`, `intg-live-v1`), бо вони не містять `conversation_search`/`clarify` у `required_evidence_ids`/`forbidden_effects`.
  - Зміна R2 (`7ade6fe`, `_claimed_tools` -> `unexecuted_claim`) **змінює правила детерміністичного скорера** для записів, де відповідь моделі буквально згадує будь-яку snake_case назву інструмента з `TOOLS` без його виклику. Тому в Track G (G2.5) усі порівнювані arms мають бути перераховані цією версією `score_u2_u3.py`.
- **Вердикт:** **PASS** (у межах R2 `7ade6fe`; вимагає повторного скорингу в Track G).
