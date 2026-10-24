# B-12: специфікація повної системи

Дата: 24.10.2026. Статус: затверджений власником напрям реалізації; інженерні рішення нижче можна уточнювати за evidence. Власник прямо доручив великий план, реалізацію, звичайні та великі тести, tool calling і дав дозвіл на повний доступ до своєї системи. Додаткове погодження самого початку реалізації не потрібне.

## 1. Мета й межа готовності

Створити B-12 як локального постійного компаньйона: природний UA/EN діалог, автобіографічні спогади, джерела знань, реальні інструменти комп’ютера, контекстна ініціатива, голос і контрольована фізична присутність через апаратний адаптер. Заміна LLM, перезапуск процесу або закриття браузера не стирають дозволений досвід.

Це продовження всього master brief, а не лише чатова оболонка. Desktop є першим середовищем. Відсутні Reachy/персональний Jetson не імітуються як фізично перевірені; відповідні адаптери, тести протоколу й hardware acceptance залишаються в матриці вимог. Відсутність обладнання не блокує реалізацію desktop, голосового й когнітивного стеку.

Готовність визначається реальним запуском користувача, тестами після restart, реальними tool-result turns і тривалими прогонами. Кількість написаних тестів сама по собі не є готовністю.

## 2. Встановлений baseline

- Ubuntu 24.04.5, Python 3.12, i9-14900HX, RTX 4060 Laptop 8GB, RAM 32GB.
- Ollama 0.33.3, `b12-bolt-e4b:q4km`, перевірений NVIDIA GGUF/revision/hash; baseline JSON у `benchmarks/bolt-e4b-smoke-2026-10-24/report.json`.
- Warm decode близько 62–64 tok/s, uncached short-text first-content ~0,17–0,56 с; це не voice latency. Cold ~30 с.
- Context 2048 дав truncation з утратою instructions. Runtime повинен запобігати цьому до запиту.
- `archive-index-public` review на pinned commit; 17 core tests пройшли. Canonical B-12 memory kernel не знайдено, тому його контракт реалізується явно.
- Repository поки містить дослідження й benchmark code. Документація зберігається за LLM Wiki workflow.

## 3. Архітектура

```text
Browser / CLI / Audio / Reachy adapter
                ↓ authenticated control + observations
API → Session manager → Attention / Scheduler
                ↓
Context builder ← Canonical memory + Knowledge retrieval
                ↓
Model adapter (Ollama Bolt, replaceable)
                ↓ typed proposals
Tool registry → Policy → Execution → Results → next model turn
                ↓
Audit events / permitted memory / metrics / UI stream
```

`asyncio` orchestration; одна обмежена черга GPU reasoning, незалежні cancellation/audio/control paths. SQLite canonical ledger і payload store; derived search rebuildable. FastAPI на loopback, CLI та Web UI. Зовнішні framework залежності невеликі: httpx, pydantic, FastAPI/uvicorn; audio/robotics extras окремі. Не встановлювати повний Torch stack лише задля lexical retrieval.

## 4. Контракти

Усі часові мітки UTC, IDs UUID, JSON серіалізація версійована. Python public interfaces фіксуються у плані; зміни контрактів записуються в execution ledger.

| Об’єкт | Обов’язкові дані |
|---|---|
| Actor | `id`, `owner`, `consent`; actor походить з authenticated control, не з LLM arguments |
| Observation | `id`, `kind`, `source`, `timestamp`, `payload`, `ttl`, `actor_id` |
| MemoryRecord | `id`, `owner_id`, `kind`, `text`, `source`, `created_at`, `evidence_ids` |
| Audit event | sequence, UUID, type, actor ID, target IDs, timestamp, previous hash, hash; без персонального payload |
| ToolCall | call ID, name, JSON arguments, originating turn/task ID |
| ToolResult | call ID, status, JSON content, duration, side effects, truncation flag, error code |
| ModelReply | content, structured tool calls, metrics, finish reason; reasoning text не зберігається |
| Session | ID, authenticated actor, bounded working messages, memory/control settings, task cancellation |
| Goal | ID, intent, evidence IDs, status, resource budget, next review, allowed tools |

## 5. Пам’ять і життєвий цикл

Canonical audit metadata append-only. Персональний payload розміщено окремо, його можна фізично видаляти; audit містить лише opaque target IDs. SQLite `secure_delete`, контроль WAL/checkpoint та явна процедура видалення. Не обіцяти очищення зовнішніх filesystem snapshots або невідомих резервних копій; наші backups мають inventory і виконуваний purge.

Persist дозволено тільки Actor з control-channel consent. Відмова відбувається до запису payload, derived text чи logs. OWNER і consented GUEST мають точні незалежні namespaces; prefix filtering не є авторизацією. Guest без consent працює з volatile session history.

Facts, episodes, procedures, reflections, preferences і self-model мають source/evidence. Залежні reflections та search entries видаляються/інвалідовуються каскадно. Успішний `forget` означає відсутність payload у всіх керованих stores/index/cache/session transcripts. Failures не приховуються; pending purge блокує видачу відповідних даних після restart.

Retrieval повертає обмежені релевантні memories з джерелами. Semantic rank не є confidence факту. Memory growth, skill acquisition і weight fine-tuning — різні механізми; fine-tuning не потрібний для початкового досвідного навчання.

## 6. Knowledge retrieval та archive-index

Повторно використати pinned lexical processing/ranking і, де доречно, Store/search з archive-index з Apache notices. Canonical memory не підмінювати mutable archive DB. Окремий B-12 knowledge index для дозволених файлів; глобальний персональний архів підключається як контрольований owner-only source adapter, а не як загальнодоступна пам’ять гостя.

Exact authorization застосовується перед передачею фрагментів моделі. VectorCache invalidation залежить від revision, включно з видаленням. Lexical path не завантажує embedding model. Semantic backend активується лише після benchmark сумарного VRAM/latency.

## 7. Model/context runtime

Один інтерфейс адаптера з реальним Ollama streaming і tool calling. Cancellation закриває stream, припиняє наступні tools, не зберігає неповний turn як підтверджений факт. Timeout, connection error, malformed stream, missing terminal event і output limit мають різні коди й видимі UI states.

Token admission відбувається до inference: system, tool schemas, evidence, user message й output reserve. System/control content не обрізається. Спочатку відкидаються найстаріші зайві working turns, потім нерелевантні evidence; останній user request не мовчки скорочується. Якщо exact tokenizer доступний — використовувати його; без нього консервативна UTF-8 bound має забезпечувати fit і відмову для надмірного input. Вимірювання фактичного prompt count перевіряє це припущення.

Контексти 4096/8192 перевірити до зміни production defaults. Temperature/seed, thinking, model digest, cache state і options записуються в run metadata. `think=false` — default розмови; повільний reasoning може бути окремим task profile.

## 8. Реальні системні tools

Потрібні tools: system information, process listing, file list/read/search/write, bounded command execution, working-directory tasks, memory search/store/forget, knowledge search, current time, HTTP fetch та catalog discovery. MCP client підтримує зовнішні server tools із тим самим policy/result контрактом. Tools працюють реально, а не повертають hardcoded demonstrations.

Повний доступ означає доступ процесу до host у межах Linux permissions, включно із записом і командами. Не обмежувати продукт лише read-only commands. Наявне sudo може використовуватися лише через trusted control grant для конкретного класу задач; permission errors показувати чесно.

Кожний tool має JSON schema, capabilities/risk class, timeout, output bound і audit result. `shell_exec` використовує argv і process group, cancellation/timeout зупиняє дочірні процеси. File writes atomic з rollback/backup там, де замінюється файл. Results зіставляються з call ID; model ніколи не вигадує успішне виконання.

Сесійний owner grant і full-host mode задаються control/config, не model JSON. Незворотні/руйнівні дії отримують explicit approval або відмову з точним поясненням. Не потрібне повторне погодження кожної дозволеної читальної чи зворотної задачі. Надсилання повідомлень іншим і публікація не дозволяються одним generic tool grant.

## 9. Tool loop та поведінка

Не більше 8 model rounds і 16 tool calls на один turn за замовчуванням; ліміти конфігуровані owner control. Незалежне обмеження загального часу й cancellation. Обробка декількох calls, unknown tools, invalid arguments, permission denial, timeout і tool exception має дати моделі структурований error result і не запускати дію повторно без підстав.

B-12 говорить UA, підтримує EN/code-switch, не підлещується і може аргументовано не погодитися. Відділяє observed / reported / inferred; не видає persona за свідомість. Quiet mode є runtime invariant: background proposals не починають мовлення. Відповідь на прямий user request залишається можливою.

## 10. Автономність

Goal store, scheduled tasks, curiosity candidates, idle reflections, preferences/self-model і attention state переживають restart. Система може повернутися до незавершеної теми й запропонувати експеримент без user turn. Cooldown, quiet hours, recent ignored initiative, максимум 3 неекстрених ініціативи/годину за замовчуванням, CPU/GPU budgets і owner stop — детерміністичні.

Reflection записує evidence-backed hypothesis, не arbitrary personality rewrite. Background workers не блокують audio/control paths і не створюють необмежені goals. Кожна автономна дія має originating goal/event і коротку перевірювану причину. Не зберігати приховані міркування моделі.

## 11. Інтерфейс та експлуатація

CLI: `b12 doctor`, `b12 chat`, `b12 serve`, memory review/export/forget, tool listing, eval run. Web UI: streaming conversation, tool activity/results, consent controls, memory/evidence viewer, goals, quiet mode, pending approvals, cancel, health/resources. UI не підмінює виконання tools декоративними повідомленнями.

Loopback default, authenticated owner bootstrap token з mode 0600. Browser origin перевіряється для write/control requests. Немає unauthenticated host execution API. Сесії гостей мають окремий actor/scope. Runtime state не потрапляє у Git. User service стартує без root, має restart policy, rotating metadata logs, graceful shutdown, schema migrations і backup/restore/forget procedures.

## 12. Голос і сенсори

Desktop PTT → VAD → ASR → runtime → sentence-streaming TTS, UA/EN. Потрібні реальні записи/відтворення, UA voice licensing, first meaningful audio timing, stop/cancel. Mic mute та consent відокремлені. Raw mic volatile за замовчуванням.

Наступний audio gate: AEC render reference, endpoint, barge-in, background-media filtering, speaker recognition з явним enrollment. Speaker similarity не є авторизацією. 8h duplex soak і noise/TV/GPU-load tests; ціль <1,5 с first meaningful audio вимірюється окремо, не замінюється earcon або model TTFT.

Reachy adapter: один writer, bounded angles/speed, interruption, sleep, disconnect/reconnect і safe state. Hardware test не закривається mock. Jetson adapter: profile окремих/спільних models, thermal/unified RAM/audio dropouts та degraded mode без ноутбука.

## 13. Матриця приймання

| ID | Вимога | Обов’язковий доказ |
|---|---|---|
| R01 | План, traceability, project history | Ця spec, implementation plan, execution ledger, wiki updates |
| R02 | Реальний локальний model adapter | Streaming Ollama, errors/cancel, exact options/digest у artifacts |
| R03 | Context не втрачає instructions | Oversize rejection, long-history tests і фактичні prompt counts |
| R04 | Persistent memory | Store→process restart→recall з evidence; no-consent/guest isolation |
| R05 | Забуття | Payload + derived + dependent + session/backup purge, restart check |
| R06 | Реальні tools і host access | File write/read, process/command, timeout/cancel, actual side effects у test sandbox |
| R07 | Model-driven tool loop | Реальний Bolt → tool → result → grounded final, multi-round tasks |
| R08 | Knowledge/archive reuse | Pinned source notices, exact scopes, freshness після update/delete |
| R09 | Companion/self-model | UA/EN rubric, evidence-backed reflection, preference revision history |
| R10 | Автономність | Scheduler/restart, quiet/cooldown/cancel, реальний initiative trace |
| R11 | CLI/Web/API | Browser/CLI acceptance, auth boundary, memory/tools controls |
| R12 | Стабільний сервіс | Install/run instructions, restart recovery, metrics, backup/restore |
| R13 | Великі model/tool тести | Не менше 100 versioned сценаріїв; 5 repeats; 50–100-turn conversations; raw artifacts і failures |
| R14 | Stress/soak | 8h software soak, concurrent/control failures, growth/load corpus, no silent loss |
| R15 | Голос | Реальні UA/EN ASR/TTS, meaningful-audio timings, interrupt; 8h duplex gate |
| R16 | Robot/Jetson | Адаптери/protocol tests та окремі physical acceptance artifacts на наявному обладнанні |
| R17 | Long-horizon memory | Реальні 1/7/30-day recall, review/forget і daily recovery evidence |

R13 включає tool argument validation, prompt injection у tool output/documents, false memory, guest leakage, repeated failures, network unavailable, malformed JSON, quiet-mode reasoning, 30 multi-step tool tasks і fault injection. Автоматичні checks відділяються від людської мовної/поведінкової оцінки. Жодна велика метрика не приховує failed cases.

## 14. Порядок реалізації

1. Відтворюваний Python package, contracts, canonical memory і tests.
2. Реальний model/context adapter та host tools.
3. Інтегрований agent loop + persistence + lexical knowledge.
4. CLI/Web/API та local service.
5. Goals/initiative/reflection, MCP та semantic retrieval.
6. Model eval corpus, великі інтеграційні/failure/load/soak tests і виправлення.
7. Реальний desktop voice, duplex, identity/consent controls.
8. Robot/Jetson, довготривалі спостереження й фінальний requirement audit.

Цей порядок не зменшує обсяг цілі. Кожна наступна сесія продовжує незавершені R01–R17 за evidence й execution ledger; ціль залишається active до завершення повної матриці або явної зміни вимог власником.

## 15. Уточнення після незалежного architecture review

Ці контракти є обов’язковими для відповідних tasks; вони усувають прогалини плану, не звужують full-host scope.

### 15.1. Server-owned control та execution provenance

Actor — внутрішній resolved DTO, не доказ авторизації сам по собі. CLI/API/application factory отримують actor з ControlStore/SessionStore; request body не приймає owner/consent/grant. Операція має ExecutionContext: actor_id, session_id, turn_id, optional task_id, grant_id, control_revision, monotonic deadline і cancellation event. Session має точний actor binding. Перед кожним effect/persistence control resolver перевіряє current revision, consent/capability та expiry/revocation. Відкликання consent забороняє нові записи; забуття старих записів — окрема явна операція.

ToolCall містить optional application UUID turn_id/task_id; registry заповнює/перевіряє їх із trusted context. ToolResult має side_effects, outcome_unknown та machine error_code. Provider call ID залишається opaque. Durable/wire envelopes schema_version=1; MemoryRecord created_at — ISO8601 UTC, memory/evidence IDs — application UUID.

### 15.2. Local delete та global purge

MemoryStore.forget(id, actor) — storage primitive лише для власних canonical payload/FTS/evidence tables; його bool ніколи не означає завершення R05 в усьому application. До публічного memory_forget підключається PurgeCoordinator.

PurgeReceipt: operation_id UUID, target_ids tuple UUID, state pending|complete|failed, pending_stores tuple strings, error_code optional. Canonical transaction спочатку фіксує payload-free tombstone/outbox та transitive dependency IDs, потім приховує/видаляє payload. Registered managed stores (canonical, knowledge, sessions, goals, backups, active turns) отримують idempotent purge hooks. Complete можливе лише після їхнього acknowledgement та фізичного canonical checkpoint/cleanup. Busy WAL reader або failed hook залишає pending/failed з чесним результатом. Startup відновлює pending operations до видачі affected data.

Deletion revision інвалідовує контекст активних turns; late tool/reflection commit зі старою revision відхиляється. Backup restore replay-ить deletion ledger перед доступом до відновленого payload. Source files поза керованими stores не видаляються автоматично; re-ingestion forgotten source потребує нового explicit control рішення. Audit не містить user text, paths, arguments, raw actor display names або payload hashes як підміни payload erasure.

### 15.3. Evidence identity і index namespace

EvidenceRef: opaque UUID, owner scope ID, kind memory|document|tool_result, source opaque ID, revision/content identity, locator, active flag. Shared resolver перевіряє scope/revision/deletion до запису reflection й видачі контексту. Canonical memory IDs можуть одночасно бути evidence IDs; knowledge rowids не використовуються як stable references.

Окремий archive Store file на actor scope усуває global path UNIQUE collision; actor scope maps до server-generated filename, не raw user path. Candidate authorization відбувається до top-k. Source update/delete інвалідовує old revision references та dependent projections за явним правилом.

### 15.4. Arbitrary code, approvals та uncertain outcomes

Typed tools використовують уже надані task/session capabilities без повторного підтвердження. Arbitrary executable/interpreter у full-host mode чесно має будь-які effects у межах OS permissions; argv не є sandbox. Для конкретного execution потрібен чинний explicit arbitrary-execution task grant або reviewable approval exact executable/argv/cwd/declared effects. Не стверджувати, що blacklist команд гарантує заборону destructive/network effects. Для enforceable narrower mode потрібен OS boundary; коли він недоступний, відмова або explicit full-execution approval, а не удавана ізоляція. MCP capabilities задає trusted local catalog.

Approval записує actor/session/turn/call, canonical arguments hash, capability, expiry і одноразове рішення; після approve повторно перевіряється grant/revision. Tool lifecycle persist-ить proposed/approved/started/completed/failed/cancelled/unknown. Non-idempotent call після crash або timeout з можливими effects не повторюється автоматично; reconciliation використовує operation key або контрольне рішення. Outcome_unknown не маскується як clean failure без effects.

### 15.5. Immutable admitted request та terminal events

ContextBuilder повертає AdmittedRequest з messages, tools, num_ctx, output_reserve, input_upper_bound, template/model revision, request fingerprint і dropped IDs. Model adapter відправляє саме цей snapshot; інша serialisation/schema анулює admission. Required active user і tool-call/result groups атомарні; overflow required data повертає structured error або explicit bounded result, не silent eviction. Profile/template/model changes інвалідовують tokenizer/overhead calibration.

TurnResult та events спільні для CLI/API/Web/audio: turn_started, text_delta, tool_started, tool_result, approval_pending, turn_completed, turn_failed, turn_cancelled. Кожен event має turn/session IDs, monotonic sequence, payload ownership; рівно один terminal event. Waiting approval не є завершеним turn; resume/cancel зберігає call identity. CancelToken/asyncio.Event та monotonic deadline передаються через model, tool і background paths.

### 15.6. Durable goals

Goal зберігає actor/scope, grant reference, immutable original intent, acceptance criteria/evidence IDs, checkpoint/next action, consumed budgets і status reason. Restart не дублює effect і не скидає budget. Achieved потребує перевіреного evidence, не лише model proposal. Quiet mode керує initiative speech окремо від execution pause. Один scheduler з process ownership guard; goal/checkpoint payload підпорядковується consent/forget.
