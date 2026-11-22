---
type: report
updated: 2026-11-22
status: compiled
sources:
  - docs/superpowers/plans/2026-11-22-remaining-work-agy.md
  - docs/superpowers/plans/2026-11-20-hermes-market-ports.md
  - reports/unified/ADR-021-skills-procedural-memory.md
  - src/b12/skills.py
  - src/b12/tools/skills.py
  - tests/integration/test_skills.py
tags: [track-f, skills, adr-021, procedural-memory]
---

# Звіт Track F — Навички як процедурна пам'ять (ADR-021, прапорець `skills`)

**Робочий worktree / гілка:** підготовлено в `.worktrees/tmp-track-f` (`tmp/track-f-20261122`: `709f5a2`, `450736a`), інтегровано у `.worktrees/unified-dr2-dr3` (`feat/unified-dr2-dr3`).  
**Коміти у `feat/unified-dr2-dr3`:** F1 — `8cf159e`, F2 — `adac2d6`, звіт і журнал — поточний коміт.

## Підсумок реалізації (**перевірений факт**)

Уся нова поведінка ізольована за прапорцем `Settings.skills: bool = False` у [config.py](../../src/b12/config.py) (додано в env bool tuple `B12_SKILLS` у `Settings.from_env` та в `RUNTIME_FLAGS` / `--skills` у [run_u2_u3.py](../../evals/unified/run_u2_u3.py)). При вимкненому `skills=False` каталог інструментів (`17` інструментів у `b12 tools`) та поверхня системного промпту (`tests/fixtures/prompt_surface/owner_default.json`) залишаються незмінними.

### F1: сховище, індекс і `skill_view` (`709f5a2`)

- **Сховище `SkillStore` (`src/b12/skills.py`):**
  - Корінь `state_dir / "skills"` (права `0o700`, відмова при симлінку).
  - Розбір YAML frontmatter на стандартній бібліотеці без зовнішніх залежностей (`parse_frontmatter`, `validate_frontmatter`): обов'язкові непорожні `name` та `description` довжиною до `60` символів; навички без коректного frontmatter вважаються `invalid` і не індексуються.
  - `SkillStore.list() -> list[dict]` повертає записи `{name, description, status}` (`active | stale | archived | source_forgotten`), скануючи активний корінь і `skills/.archive/`.
  - `SkillStore.index(limit=20)` і `SkillStore.render_index(limit=20)` показують лише `active` навички (до `20` записів, описи обрізані до `60` символів).
  - `SkillStore.view(name, path="") -> str` примусово обмежує доступ всередині `skills/<name>/`: заборонені `..`, абсолютні шляхи, `\`, NUL та будь-які симлінки на рівні теки навички або відносних компонентів (`O_NOFOLLOW`, `resolve().is_relative_to(...)`); при виході за межі піднімається `ValueError("path outside skill")`.
- **Інструмент `skill_view` (`src/b12/tools/skills.py`):**
  - Capability `memory.read`, доступний лише власнику (`actor.owner`), реєструється через `register_host_tools(..., skill_store=..., skills=settings.skills)` у [tools/__init__.py](../../src/b12/tools/__init__.py) та [runtime.py](../../src/b12/runtime.py).
- **Системний промпт (`src/b12/agent.py`):**
  - При `settings.skills=True` (і для власника з `consent=True`) `Agent._build_system` додає блок індексу навичок після стабільної частини системного промпту (у `volatile` при `stable_prefix=True`, або після `intents_line` при `stable_prefix=False`), не змінюючи байти кешованого префікса.

### F2: пропозиції, схвалення, JSONL-журнал і куратор

- **Стейджинг і схвалення (`src/b12/skills.py`, `src/b12/tools/skills.py`):**
  - `SkillStore.propose(name, content, *, turn_id, session_id=None, actor_id=None) -> str` зберігає pending-пропозицію разом з unified diff (`difflib.unified_diff`) у `skills/.pending/<pending_id>.json` (`0o600`, `O_NOFOLLOW`) і ніколи не записує `SKILL.md`.
  - Інструмент `skill_propose(name, content)` (capability `memory.write`, лише `actor.owner`) лише стейджить пропозицію у `.pending/`.
  - `SkillStore.approve(pending_id)` атомарно записує `SKILL.md` (`0o600`, temp+fsync+replace), зберігає провенанс (`source_turn_id`, `source_session_id`, `source_actor_id`) у `skills/.metadata.json` і дописує JSONL-запис у `skills/.ledger.jsonl` з полями `{actor, action, name, sha256_before, sha256_after, turn_id, at}` (файл JSONL, без змін схеми SQLite).
  - `SkillStore.reject(pending_id)` видаляє pending-файл без зміни `SKILL.md` і фіксує подію `reject` у `.ledger.jsonl`.
  - `SkillStore.pin(name)` / `unpin(name)` позначають навичку як `pinned` для захисту від куратора.
- **Детермінований куратор і `Scheduler` (`src/b12/skills.py`, `src/b12/autonomy.py`):**
  - `SkillStore.curate(now)`: без використання протягом `14` днів → статус `stale`; `30` днів → переміщення теки навички до `skills/.archive/<name>/` і статус `archived`; `pinned` та `source_forgotten` не чіпаються.
  - `Scheduler.curate_skills_idle()` викликається в `Scheduler.run()` після `review_memory_idle()` з інтервалом `7` днів (`last_skill_curate`), прапорцем `settings.skills` та тими самими захистами `_busy(actor_id)` і `rt.attention.execution_allowed(actor_id)` (`owner_stop`).
- **Очищення вихідної сесії (`src/b12/sessions.py`, `src/b12/runtime.py`, `src/b12/cli.py`):**
  - `SessionStore.clear_session` викликає `on_clear_turns` та `on_clear_session`; у `open_runtime` обидва хуки викликають `SkillStore.mark_source_forgotten(...)`, що переводить залежні навички у статус `source_forgotten` без видалення `SKILL.md`, вилучає їх із модельного індексу та створює сповіщення у `goals.add_proposal(..., decision="inbox", reason="source_forgotten")`.
- **CLI (`src/b12/cli.py`):**
  - Додано підкоманду `b12 skills list|show|pending|diff|approve|reject|pin|unpin` (`cmd_skills`); `cmd_session_clear` додає `source_forgotten_skills` у JSON-відповідь при появі таких навичок.

## Перевірки (**перевірений факт**)

1. **Тести Track F (`tests/integration/test_skills.py`):**
   - F1: `test_view_refuses_paths_outside_the_skill`, `test_index_lists_active_skills_only_with_the_flag`, `test_invalid_frontmatter_is_not_indexed`.
   - F2: `test_skill_propose_stages_and_never_writes`, `test_approve_writes_and_ledgers_hashes`, `test_curator_marks_stale_then_archives_and_spares_pinned`, `test_forgetting_the_source_session_marks_source_forgotten`, `test_skills_cli_and_scheduler_curate`.
2. **Конфіг, prompt surface та eval-раннер:**
   - `tests/unit/test_config.py` (включно з `test_skills_is_opt_in_and_environment_configurable`).
   - `tests/unified/test_run_u2_u3.py` (`--skills` і `test_skills_flag_reaches_run_scenario`).
   - `tests/integration/test_prompt_surface.py` — пройдено без змін `tests/fixtures/prompt_surface/owner_default.json`.
3. **Прогін у `.worktrees/tmp-track-f` після фінальних правок F2:**
   - `.venv/bin/python -m pytest -q tests/unit tests/integration tests/unified tests/security tests/e2e/test_cli.py -p no:cacheprovider` → **`1090 passed, 1 skipped` (273.22s)** (модельні тести використовують `scripted_ollama`).
   - `.venv/bin/ruff check --no-cache` та `.venv/bin/ruff format --check --no-cache` по 13 змінених/нових файлах → `All checks passed!`, `13 files already formatted`.
4. **Аудит та інтеграція у `.worktrees/unified-dr2-dr3` (`feat/unified-dr2-dr3`):**
   - Після перенесення F1 (`8cf159e`): `tests/integration/test_skills.py`, `tests/unit/test_config.py`, `tests/unified/test_run_u2_u3.py`, `tests/integration/test_prompt_surface.py`, `tests/integration/test_memory_taint.py` → **`97 passed in 13.86s`**, `ruff check` і `ruff format --check` по 10 файлах чисті.
   - Після перенесення F2 (`adac2d6`): `tests/integration/test_skills.py`, `tests/unit/test_config.py`, `tests/unified/test_run_u2_u3.py`, `tests/integration/test_prompt_surface.py`, `tests/integration/test_autonomy.py`, `tests/e2e/test_cli.py -k "not real_model"` → **`129 passed in 27.82s`**, `ruff check` і `ruff format --check` по 8 файлах чисті.

## Межі та наступні кроки (**потребує перевірки / рішення власника**)

- Живі модельні оцінювання (`gemma4:12b` на Colab) не запускалися (Track G).
- Прапорець `Settings.skills` залишається `False` за замовчуванням до вимірювань `ports-skills` і рішення власника за [ADR-021](ADR-021-skills-procedural-memory.md).
- Жодних змін схеми SQLite чи нових залежностей у `pyproject.toml` не вносилося (журнал ведеться у JSONL-файлі `skills/.ledger.jsonl`).
