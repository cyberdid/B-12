---
type: status
updated: 2026-10-25
status: active
sources: [wiki/sources/master-brief.md, wiki/project/analysis.md]
tags: [progress, next]
---
# Стан проєкту

На початку імпорту 24.10.2026 `/home/cyberdid/Projects/B-12` була порожньою текою без Git. Дослідницький baseline збережено commit `78daaef` на `main`; реалізація йде у worktree `.worktrees/runtime`, branch `feat/b12-runtime`. Офіційний Bolt E4B встановлено поза Git як тестовий Ollama alias. Є перевірений foundation package; agent runtime, аудіопайплайн і результати Jetson/robot acceptance ще не готові.

## Наявне

- Незмінений [master brief](../../raw/B-12_Master_Project_2026-10-24.md), SHA-256 і маніфест 116 зовнішніх URL.
- [Тематична wiki](../index.md), [аналіз](analysis.md), [кандидати рішень](decisions.md), [питання](open-questions.md), [дорожня карта](roadmap.md).
- [Постійні правила агента](../../AGENTS.md) за запитаним LLM Wiki workflow.
- Вибіркова [незалежна перевірка](../sources/external-checks.md) NVIDIA Research та README; решта матеріалів мають явну межу достовірності.
- [Аудит локальної системи](../sources/system-audit-2026-10-24.md): RTX 4060 Laptop 8GB, i9-14900HX, 32GB RAM; CUDA й Ollama server 0.33.3 доступні. Є окремий store з Gemma E2B/E4B, ще не інтегрованими в B-12.
- [Власний тест Bolt](bolt-first-test.md): SHA-256 перевірено; alias `b12-bolt-e4b:q4km`, 100% GPU, context 2048; 26 запитів, з них 3 overflow timing observations виключені. Warm decode ~62–64 tok/s; uncached ~440/1160/1700 tokens дають median first-content ~0,17/0,42/0,56 с. Є поведінкові недоліки й ризик truncation; модель залишається кандидатом.
- [Review archive-index-public](../sources/archive-index-public.md): 16 source files за pinned commit, 17 core tests passed; synthetic lexical/provenance і cache-refresh probe виконані без production DB/embedding load. Наявна локальна інсталяція відрізняється від public source; retrieval ще не підключено до B-12.

## Не підтверджено

Старий SQLite kernel, попередні latency measurements, купівлю Reachy/особистого Jetson, full-duplex, українську якість моделей, simultaneous residency Bolt/Cosmos/voice та тривалу автономну роботу. Окремі дослідження voice згадані в brief, але їхніх оригіналів у `raw/` немає.

## Активний етап

**Доручення власника:** реалізувати повноцінну систему з великим планом, звичайними/великими тестами, tools і повним host access. [Implementation/spec/ledger](implementation.md) задають поточний execution path; повторний дозвіл на старт не потрібний. **Перевірений факт:** foundation, canonical memory і lexical derived retrieval завершені в межах Tasks 1–3, незалежні review пройдені, 132 tests passed. Global purge hooks і agent integration ще не підключені. Наступний gate — streaming model/context admission. Власник відновив роботу 25.10 після явної паузи. Ціль active і не обмежена попередніми smoke tests. Наступні абзаци зберігають попередній дослідницький baseline.

**M0 — частково:** вимоги систематизовані; контракти лише перелічено, права/retention потребують рішення, software-only heartbeat не реалізований. Для M1 виконано початкову model evaluation, але ядро й порівняльний A/B не реалізовані. M2–M6 не початі.

**Поточний пріоритет за дорученням власника:** тест нової NVIDIA моделі. Інвентаризація, pinned download, SHA-256, імпорт і початковий smoke/prefill test завершені. Наступний запропонований крок — UA/EN regression corpus, виправлення prompt grounding для quiet-mode/технічних пояснень і перевірка context 4096/8192 з явним token budget. [Результат і межі](bolt-first-test.md). Це не завершення M1 й не фінальне схвалення моделі.

**Уточнення після наданого репозиторію:** пошук можна повторно використати з archive-index. Найближчий запропонований вертикальний зріз — окрема B-12 index DB → evidence/context builder → наявний Bolt alias, із дозволеними synthetic events, exact scope, cache invalidation і token budget. [План і межі](../topics/archive-retrieval.md). Canonical memory/consent runtime ще потребує розробки; приватний архів не імпортовано.

Походження старого kernel залишається відкритим. Його пошук та Event/Memory/Consent contracts можна продовжити після першого model test. Q15 про характеристики host закрито в межах read-only аудиту; див. [питання](open-questions.md).

При наступній сесії починати з цього стану, оновлювати його лише за новими доказами та дописувати [журнал](../log.md).
