---
type: status
updated: 2026-10-26
status: active
sources: [wiki/sources/master-brief.md, wiki/project/analysis.md]
tags: [progress, next]
---
# Стан проєкту

На початку імпорту 24.10.2026 `/home/cyberdid/Projects/B-12` була порожньою текою без Git. Дослідницький baseline збережено commit `78daaef` на `main`; реалізація йде у worktree `.worktrees/runtime`, branch `feat/b12-runtime`. Офіційний Bolt E4B встановлено поза Git як тестовий Ollama alias. Реалізовані foundations, canonical memory, lexical retrieval, pinned-profile model/context adapter, reviewed server-owned tool control, 13 реальних host tools, agent loop із sessions і global purge; owner CLI, автентифікований loopback API і Web UI; автономність, голос і фізичні acceptance ще попереду.

## Наявне

- Незмінений [master brief](../../raw/B-12_Master_Project_2026-10-24.md), SHA-256 і маніфест 116 зовнішніх URL.
- [Тематична wiki](../index.md), [аналіз](analysis.md), [кандидати рішень](decisions.md), [питання](open-questions.md), [дорожня карта](roadmap.md).
- [Постійні правила агента](../../AGENTS.md) за запитаним LLM Wiki workflow.
- Вибіркова [незалежна перевірка](../sources/external-checks.md) NVIDIA Research та README; решта матеріалів мають явну межу достовірності.
- [Аудит локальної системи](../sources/system-audit-2026-10-24.md): RTX 4060 Laptop 8GB, i9-14900HX, 32GB RAM; CUDA й Ollama server 0.33.3 доступні. Є окремий store з Gemma E2B/E4B, ще не інтегрованими в B-12.
- [Перший smoke test Bolt](bolt-first-test.md): SHA-256 перевірено; alias `b12-bolt-e4b:q4km`, context 2048; 26 запитів, з них 3 overflow timing observations виключені. Warm decode ~62–64 tok/s; є поведінкові недоліки. Пізніше truncation risk закрито лише для pinned profile, див. наступний пункт; модель лишається кандидатом.
- [Review archive-index-public](../sources/archive-index-public.md): 16 source files за pinned commit, 17 core tests passed; synthetic lexical/provenance і cache-refresh probe виконані без production DB/embedding load. Pinned lexical modules тепер інтегровані через actor-scoped derived index; приватний production archive не імпортовано.
- [Model transport](../topics/model-transport.md): Task 4 reviewed; run4 — 15/15 реальних запитів до локального Bolt alias із exact prompt counts на сценаріях до 3928 токенів. Це перевірка pinned профілю, не універсального truncation proof чи голосового SLO. Model profile залишається explicit, alias default context — 2048.
- [Agent loop](../topics/agent-loop.md): Task 7 model→tools→results, events, sessions/provenance, PurgeCoordinator; real Bolt run2/run3 без protocol failures.
- [Tool control](../topics/tool-control.md): Task 5 reviewed у `bc07196`; Task 6 host tools — `7d7809e` після двох fix rounds. Filesystem/process/HTTP/memory handlers перевірені на temp/local fixtures. API authentication і глобальний purge ще не реалізовано.

## Не підтверджено

Старий SQLite kernel і його попередні latency results не знайдені; це не стосується нового Task 2 MemoryStore. Не перевірено купівлю Reachy/особистого Jetson, full-duplex, загальну українську якість моделей, simultaneous residency Bolt/Cosmos/voice та тривалу автономну роботу. Окремі дослідження voice згадані в brief, але їхніх оригіналів у `raw/` немає.

## Активний етап

**Доручення власника:** реалізувати повноцінну систему з великим планом, звичайними/великими тестами, tools і повним host access. [Implementation/spec/ledger](implementation.md) задають поточний execution path; повторний дозвіл на старт не потрібний. **Перевірений факт:** Tasks 1–7 реалізовані; Task 7 `740629a`, full suite 350 passed / 2 skipped, Ruff clean; реальний Bolt виконує file write/read, system_info і memory recall після restart (3/3 у run2/run3). Task 8 owner CLI `964709b` (361 passed / 2 skipped; живий запуск із реальним Bolt). Task 9 API/auth `9632cdc` (382 passed / 2 skipped). Task 10 Web UI `6610f85` (headless Chrome acceptance 20/20, реальний Bolt). Наступний gate — Task 11 автономність. Global purge hooks, API authentication, voice, robotics і тривалі acceptance також попереду. Власник відновив роботу 25.10 після явної паузи. Ціль active і не обмежена попередніми smoke tests. Наступні абзаци зберігають дослідницький baseline.

**M0 — частково:** versioned contracts, canonical memory/revocation primitives, server-owned owner/guest control та grant/approval lifecycle є. System heartbeat і retention/global-purge coordinators ще потрібні. Для M1 є memory, lexical retrieval, pinned Bolt transport і strict tool policy/registry, реальні host handlers; agent/session loop, idle reflection та A/B ще немає. M2–M6 не початі.

**Початковий Bolt smoke test:** зберігається як історичний baseline у [своєму звіті](bolt-first-test.md); його truncation на 2048 був підставою створити явний admission adapter. Новий run4 вимірює інший pinned renderer і чітко вказаний context 4096. Модель іще кандидат: Ukrainian quality corpus, tool performance, A/B і голосовий SLO залишаються відкритими.

**Уточнення після наданого репозиторію:** pinned lexical adapter в окремих actor stores ідентифікує evidence UUID/revisions, а context adapter admission-check-ить його. [Поточний код і межі](../topics/archive-retrieval.md). Cross-store resolver та purge coordinator ще потребують agent/control integration; приватний архів не імпортовано.

Походження старого kernel залишається відкритим. Його пошук та Event/Memory/Consent contracts можна продовжити після першого model test. Q15 про характеристики host закрито в межах read-only аудиту; див. [питання](open-questions.md).

При наступній сесії починати з цього стану, оновлювати його лише за новими доказами та дописувати [журнал](../log.md).
