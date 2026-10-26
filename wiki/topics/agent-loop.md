---
type: topic
updated: 2026-10-26
status: partially_implemented
sources: [docs/superpowers/specs/2026-10-24-b12-system-design.md, src/b12/agent.py, src/b12/sessions.py, src/b12/purge.py, src/b12/evidence.py, src/b12/runtime.py, tests/integration/test_agent_loop.py, tests/unit/test_sessions.py, tests/e2e/test_bolt_tools.py]
tags: [agent, sessions, purge, evidence, tools]
---
# Agent loop, сесії та глобальне забуття

## Цикл model → tools → results

**Перевірений факт:** Task 7 (`d885d49`, `2d6ee36`, `740629a`) додає `Agent.turn(session_id, grant_id, text, …)` і application factory `open_runtime(settings)`. Actor, consent і grant береться з `ControlStore`; текст запиту їх не задає. Кожен раунд проходить context admission. Ліміти за замовчуванням — 8 раундів і 16 tool calls на turn. В останньому раунді tools не пропонуються; якщо модель усе одно викликає tool, turn завершується `failed/max_rounds`. Повторний call ID у межах turn не виконується повторно. Невідомий tool, невалідні аргументи й помилки handler повертаються моделі як структурований результат. Для невалідних аргументів додається `invalid_fields` (поле й тип помилки без значень).

Події `turn_started`, `text_delta`, `tool_started`, `tool_result`, `approval_pending` і рівно один terminal (`turn_completed|failed|cancelled`) мають монотонний sequence. Очікування approval не є terminal. `resume(turn_id)` продовжує той самий call. Перед продовженням перевіряється поточний control state: скасований turn або відкликаний grant завершуються без виклику моделі. Скасування закриває stream; частковий текст не зберігається.

## Сесії та provenance

**Перевірений факт:** `SessionStore` зберігає лише завершені turns і лише для actor із consent. Без consent історія volatile, у RAM процесу, а tools недоступні, бо Task 5 вимагає consent. Кожен turn має evidence tags (memory/document/tool_result): recall, memory_search/store/forget, knowledge_search. Commit відхиляється, якщо будь-яке evidence уже не live. Історія ховає turns із мертвим evidence ще до purge hook.

**Межа (пропозиція для майбутнього):** provenance працює на рівні turn. Текст, який користувач повторив в іншому turn без зв’язку з tool чи evidence, не відстежується; його прибирає лише `clear_session`.

## Глобальний purge

**Перевірений факт:** `PurgeCoordinator` веде durable outbox `MemoryStore` через такі stores: canonical, sessions (усі tagged turns, checkpoints і volatile копії), active_turns (cancel та invalidation in-flight turns actor), backups (managed copies affected turns) і provider_cache. Complete настає лише після acknowledgement усіх stores. Інакше залишається pending/failed; `resume()` на старті дає повторну спробу. Document invalidations доставляються ідемпотентно (`sync_knowledge`). Детерміністичний e2e: store → restart → recall → forget (approval/resume) → restart; жоден файл state_dir не містить байтів секрету.

**Межа:** provider_cache — це model-level unload (`keep_alive=0`, перевірка `/api/ps`) dedicated alias під reasoning lock. Він не стирає дані окремого actor і не гарантує нічого поза процесом Ollama. Canonical `remember` поки приймає лише canonical memory evidence; document evidence для reflection ще потрібне.

## Реальний Bolt

**Перевірений факт:** run1 (`9b4f31a`) — 12/12 `context_mismatch`. Причина — `anyOf` у схемі `process_list`: Ollama рендерить на 6 токенів більше, ніж pinned template. Exact admission спрацював fail-closed. Registry тепер відхиляє anyOf/oneOf/allOf/$ref/$defs/not. Run2/run3 (`2d6ee36`/`740629a`, clean tree, Ollama 0.33.3, ctx 4096, T=0, seed 42): 0 protocol failures; write→read із незалежною перевіркою файла, system_info і memory recall після restart — по 3/3. shell_exec: модель дублює програму в argv й обрізає cwd, тому команда падає, і модель чесно повідомляє про невдачу. Це поведінковий дефект для корпусу Task 14. Сирі результати — у `artifacts/task7-bolt-tools-2026-10-26-run{1,2,3}`. Turn warm — приблизно 2–6 с; це не voice SLO.

Review: coordinator self-review і 10 мутацій ключових гарантій (кожну спіймали тести). Окремого незалежного агента не було.

Див. [контроль tools](tool-control.md), [пам’ять](memory.md), [transport](model-transport.md), [стан реалізації](../project/implementation.md).
