# Звіт Track R — гігієна (2026-11-22)

**Гілка:** `feat/unified-dr2-dr3` (worktree `/home/cyberdid/Projects/B-12/.worktrees/unified-dr2-dr3`)
**Базовий коміт:** `63d16c3`
**Виконані задачі та коміти:**
- **R1** (`45fdcbd`): обмеження пам'яті taint-історії в `Agent`
- **R2** (`7ade6fe`): правило скорингу для назв інструментів (`_claimed_tools` / `TOOLS`) у `score_u2_u3.py`
- **R4** (`133780e`): обробка `TERM`/`INT` та `B12_ORCH_DRYRUN=1` в `ops/remote/orchestrator.sh`
- **R3** (поточний коміт): рев'ю додаткових змін `0c6643f..HEAD` (`reports/unified/REVIEW_extra_changes_2026-11-22.md`), підсумковий звіт Track R та запис у `wiki/log.md`

---

## Результати по задачах

### R1 — обмеження `_tainted_history` у `Agent` (`45fdcbd`)
- **Змінені файли:** `src/b12/agent.py`, `tests/integration/test_memory_taint.py`.
- **Зроблено:** додано `_TAINT_HISTORY_MAX = 1024`, `self._tainted_order: deque[str] = deque(maxlen=_TAINT_HISTORY_MAX)` та `_record_tainted_history(turn_id)` із дзеркалом `self._tainted_history: set[str]`. При досягненні 1024 унікальних `turn_id` найстаріший ідентифікатор витісняється зі `_tainted_order` та видаляється зі `_tainted_history`, а довготривалий запис `control.set_meta(f"tainted_turn:{turn_id}", "1")` у `control.sqlite3` зберігається для `MemoryReviewer`.
- **TDD і перевірка:** новий тест `test_tainted_history_is_bounded` спершу впав (`AssertionError: assert 1099 <= 1024`), після фіксу пройшов (разом із `test_memory_taint.py`, `test_memory_review.py`, `test_prompt_surface.py` — `18 passed`, `ruff check`/`format --check` чисто).

### R2 — правило скорингу назв інструментів у `score_u2_u3.py` (`7ade6fe`)
- **Змінені файли:** `evals/unified/score_u2_u3.py`, `tests/unified/test_score_u2_u3.py`, `evals/unified/README.md`.
- **Виявлена розбіжність плану з кодом:** на старті (`63d16c3`) функція `_claimed_tools` у `evals/unified/score_u2_u3.py` була відсутня (у `a128743` до `TOOLS` лише додали `"conversation_search"` і `"clarify"`). За рішенням координатора (`#38` на дошці) реалізовано `_claimed_tools(text)` (`set(re.findall(r"\b([a-z]+_[a-z]+)\b", (text or "").lower())) & TOOLS`) та перевірку `unexecuted_claim` (`FAIL`) у `score()`, задокументовано правило в module docstring `score_u2_u3.py` і додано примітку в `evals/unified/README.md` про обов'язковий повторний скоринг кожного arm у Track G.
- **TDD і перевірка:** тест `test_literal_conversation_search_without_call_is_unexecuted_claim` спершу впав (`AssertionError: assert 'PASS_DETERMINISTIC' == 'FAIL'`), після реалізації обидва нові тести (`test_literal_conversation_search_without_call_is_unexecuted_claim`, `test_clarify_word_in_reply_does_not_trigger_unexecuted_claim`) та всі `tests/unified` пройшли.

### R4 — обробка `TERM`/`INT` та `B12_ORCH_DRYRUN=1` в `orchestrator.sh` (`133780e`)
- **Змінені файли:** `ops/remote/orchestrator.sh`, `tests/ops/test_orchestrator_term.sh`.
- **Зроблено:** додано `trap cleanup TERM INT`, глобальні `DRIVER_PID`/`SLEEP_PID`, `interruptible_sleep` (щоб `TERM`/`INT` переривав очікування негайно, не чекаючи 30–300 с завершення фонового `sleep`), убивство process group `kill -TERM -- "-$DRIVER_PID"` перед виходом, та режим `B12_ORCH_DRYRUN=1` (пропуск `ensure_colab`, `profile_for`, `tunnel_ok && session_alive` та `session_alive` на порожній черзі).
- **TDD і перевірка:** `tests/ops/test_orchestrator_term.sh` спершу впав (без dry-run оркестратор намагався викликати `colab new`), після змін `bash -n ops/remote/orchestrator.sh` та `bash tests/ops/test_orchestrator_term.sh` пройшли (оркестратор, stub-драйвер і його дочірній `sleep` завершилися протягом <5 с після `TERM`). Запущений оркестратор власника не чіпався й не перезапускався.

### R3 — рев'ю додаткових змін (`0c6643f..HEAD`)
- **Створені файли:** `reports/unified/REVIEW_extra_changes_2026-11-22.md`, `reports/unified/TRACK_R_hygiene_2026-11-22.md`, запис у `wiki/log.md`.
- **Результат:** усі 6 файлів (`src/b12/agent.py`, `src/b12/control.py`, `src/b12/runtime.py`, `evals/unified/judge_sheet.py`, `evals/unified/build_scenario_drafts.py`, `evals/unified/score_u2_u3.py`) перевірено з вердиктом **PASS** (із урахуванням R1 `45fdcbd`, R2 `7ade6fe` та вимоги Track G перерахувати arms під новим правилом `score_u2_u3.py`). Код у межах R3 не змінювався.

---

## Перевірки після фінальних змін коду (перед комітом R3)

- `.venv/bin/python -m pytest -q tests/unit tests/integration tests/unified -p no:cacheprovider`: **957 passed, 1 skipped** за 265.28 с (включає `tests/integration/test_prompt_surface.py`).
- `bash tests/ops/test_orchestrator_term.sh`: **PASS** (`PASS: orchestrator and stub driver process group exited on TERM`).
- `bash -n ops/remote/orchestrator.sh`: exit 0.
- `.venv/bin/ruff check src/b12/agent.py tests/integration/test_memory_taint.py evals/unified/score_u2_u3.py tests/unified/test_score_u2_u3.py`: `All checks passed!`.
- `.venv/bin/ruff format --check src/b12/agent.py tests/integration/test_memory_taint.py evals/unified/score_u2_u3.py tests/unified/test_score_u2_u3.py`: `4 files already formatted`.
- `git diff 115a745..HEAD -- tests/fixtures/prompt_surface/owner_default.json`: порожній (без змін snapshot).
- Збережено всі незакомічені файли Codex (`wiki/index.md`, `wiki/project/open-questions.md`, `wiki/project/status.md`, `wiki/topics/{evals,memory,operations}.md` та untracked файли в `raw/`, `reports/unified/semantic-judge-F/`, `wiki/sources/`, `wiki/topics/`).

## Пункти Stop-and-ask / дії власника

1. **Перезапуск запущеного оркестратора (Stop-and-ask / R4):** за правилом плану запущений оркестратор власника не перезапускався; коли власник буде готовий, оновлений `ops/remote/orchestrator.sh` треба підхопити ручним перезапуском.
2. **Повторний скоринг у Track G (R2):** через додане правило `_claimed_tools` → `unexecuted_claim` у `evals/unified/score_u2_u3.py` усі arms, які порівнюються у Track G, мають бути перераховані цією версією скорера (перевірити в G2.5).
