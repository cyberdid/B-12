# Task 5 — registry, server-owned control та policy

Дата: 2026-10-26. Статус implementer: **DONE**, coordinator review — окремий gate.
Base: `623d4f00b1b166ddb5c631ca81a64619e0f7e80a`.
Worktree: `/home/cyberdid/Projects/B-12/.worktrees/runtime`, branch `feat/b12-runtime`.
Один implementer, без вкладених agents/reviewers. Технічна реалізація й self-review не є незалежним review.

## Артефакти й вимоги

Нові файли: `src/b12/control.py`, `src/b12/tools/{__init__,registry,policy}.py`,
`tests/unit/test_registry.py`, `tests/security/test_tool_policy.py`.
Наявні contracts/config/context/model/memory/retrieval не змінено.
Прочитано AGENTS.md, index/status/recent log, exact task brief, spec §15.1/15.4/15.5,
binding plan amendments і попередні task reports/APIs. Архів не перечитувався.

**Перевірений факт:** strict registry викликає реальний harmless temp-file handler лише після
argument validation, current server control resolution та persisted start. Повного host tool
набору/agent/API цей task не реалізує. Full-host scope залишається чинною вимогою Task6.

## Контрольна межа

`ControlStore(path: Path)` приймає **виділену managed directory**. Нова directory має 0700,
DB 0600; existing managed root/DB permissions також звужуються до 0700/0600. Відсутні батьки
створюються 0700; permissions на наявних батьках не змінюються. Root symlink відхиляється,
DB відкривається з `O_NOFOLLOW`. SQLite DELETE journal успадковує private DB permissions;
`secure_delete=ON`, `synchronous=FULL`. SQLite same-thread connection; transactions `BEGIN IMMEDIATE`.

Actor/session/task/grant/turn/operation IDs генерує server як UUID. Actor `owner`/`consent` із
довільного DTO не є доказом. Session точно прив’язана до actor; grant — до actor/session
і optional task. Registry приймає лише виданий ControlStore `ExecutionContext`; bearer credential
зберігається private і не друкується в repr. Поточна runtime issuance окремо зв’язує context із
точним deadline та Event; заміна їх через dataclass replace не проходить resolver.

Усі mutators, `begin_turn`, `resume_turn`, `cancel_turn`, `decide_approval` — **trusted
server control APIs**, не transport authentication endpoint. Task7/9 application factory
має самостійно аутентифікувати оператора/сесію й не передавати сюди model/client поля як
доказ. Credential/ExecutionContext не можна серіалізувати в client history або model prompt.
Власник trusted ControlStore object і handler code перебуває всередині цієї межі довіри.

## API для Tasks 6–7

`b12.control`:

- `ExecutionContext`: frozen/slotted dataclass із `actor_id,session_id,turn_id,task_id,grant_id,
  control_revision,deadline,cancel,credential`. Deadline — absolute `time.monotonic()`;
  cancel — той самий `asyncio.Event`, що передається model path. Credential прихований у repr.
- `ControlError(code)`: sanitized machine error. Невідомий/довільний code нормалізується до
  `handler_failed`, тому exception string/path/user text не потрапляє в audit/result.
- `create_actor(*, owner=False, consent=False) -> Actor`: generated persistent actor ID.
- `resolve_actor(actor_id) -> Actor`: поточний server-owned frozen DTO для storage consumers.
  Сам DTO все одно не дає дозволу dispatch; потрібен `check` відповідного context.
- `create_session(actor_id) -> str`, `create_task(session_id) -> str`: generated exact bindings.
- `issue_grant(actor_id,session_id,capabilities: tuple[str,...], *, task_id=None,ttl_s=3600,
  full_execution=False) -> str`: trusted control issuance. Typed grants можна явно видати гостю;
  owner grant для іншого actor/session не приймається. Full execution потребує owner recipient
  та існуючої task. Capabilities exact-match, без wildcard або implicit messaging permission.
- `set_consent(actor_id,consent)`: literal bool, кожне рішення increment-ить actor revision;
  старий context не оновлюється автоматично. `revoke_grant(grant_id)` revokes і increment-ить revision.
- `begin_turn(session_id,grant_id, *, task_id=None,deadline,cancel=None) -> ExecutionContext`:
  exact grant binding. `resume_turn(turn_id, *, deadline,cancel=None)` повертає оригінальну
  persisted identity/revision з новим process-local issuance; stale revision не освіжається.
  Resume — явний trusted application крок, а не автоматичне виконання tools.
- `check(ctx,capability=None) -> sqlite3.Row`: перед effect перевіряє issued credential,
  exact actor/session/task/grant/turn, current consent/revision, revoked/expiry, cancellation,
  monotonic deadline та exact capability. Row є internal trusted grant, не wire envelope.
- `cancel_turn(turn_id)`: durable cancel bit, runtime Event, pending/approved operations →
  `cancelled`, started → `unknown`, private approval digests erased. Restart не скасовує cancel.
- `decide_approval(operation_id,approve: bool)`: literal one-shot owner control decision;
  саме рішення не запускає handler. Caller має надати owner review оригінального immutable call.
- `expire_approvals()`: explicit service maintenance hook для expiry й digest erasure;
  також викликається на startup/prepare/decision. Idle service мусить планувати maintenance.
- `operation(ctx,call) -> dict|None`: ID/name/state/error_code поточного exact call;
  `audit_events() -> list[dict]`: payload-free persisted ordered lifecycle metadata.
- `prepare(ctx,call,capability,arbitrary, *, approval_ttl_s=300,approval_required=False)` та
  `finish(operation_id,state,code=None)` — internal trusted registry lifecycle APIs;
  їх не слід викликати з model/client input. `close()` закриває SQLite connection.

`b12.tools.registry`:

- `ToolRegistry(control, *, timeout_s=30)`.
- `register(name,description,argument_model,handler,capability, *, risk=Risk.TYPED)`.
  Unique trusted ASCII identifier names/capabilities; Pydantic models мають strict=True,
  extra=forbid. Nested object models також мають forbid extras; runtime strict validation
  застосовується до кожного виклику. Sync handlers відхиляються до виконання.
- `schemas(context) -> list[dict]`: native function envelopes для дозволених capabilities;
  stable registration order, fresh deep copies. Підготувати їх **перед** ContextBuilder admission;
  не додавати tools/messages/options до вже створеного AdmittedRequest. Task4 API не змінено.
- `async execute(call: ToolCall, context: ExecutionContext, *, cancel=None) -> ToolResult`.
  Це binding-spec replacement початкового Actor/grant-dict sketch. Actor або forged context
  дає `invalid_context`; жодний grant dict не приймається. Optional cancel мусить бути тим
  самим Event із context. Origins із call перевіряються або доповнюються server context.
  Call/result IDs і name exact-associated. Arguments deep-copy snapshot-яться до першого await.
- Shared `Handler = Callable[[BaseModel,EffectGuard],Awaitable[dict[str,Any]]]`.
  Handler отримує вже валідовану model instance; повертає finite-JSON dict. Result bounds,
  provenance та специфічні process/network exit semantics належать Task6 handler contracts.
- `Risk.TYPED`: already-granted typed actions без повторних prompt.
  `Risk.ARBITRARY`: explicit task full-execution grant АБО exact approval;
  registration вимагає required `executable,argv,cwd,declared_effects`.
  `Risk.DESTRUCTIVE`: exact approval обов’язковий навіть за generic task grant.
- `approval_pending` містить `content.operation_id` та оригінальні result call/name IDs.
  Це стан очікування, не successful effect/final turn. Task7 зберігає оригінальну call identity
  й resubmit-ить той самий immutable call після owner control decision.
- Denial codes: invalid_context/arguments, unknown_tool, origin_mismatch, cancel_mismatch,
  consent_required, grant_revoked/expired, stale_control, capability_denied,
  approval_denied/expired/mismatch, replay_blocked. Немає raw exception text у результаті.
  Pre-proposal denials повертаються structured; durable lifecycle audit починається з valid
  proposed operation. Rejected-request telemetry для application може використовувати ці codes.

`b12.tools.policy.EffectGuard`:

- `guard.check()` безпосередньо перед **кожним** effect/persistence у Task6, особливо після await
  або повільної підготовки. Перевіряє current server control та persisted active operation.
- `guard.context`, `guard.cancel` (shared Event), `guard.deadline` (minimum turn/per-call deadline),
  `guard.operation_id` (generated UUID для downstream idempotency/provenance).
- Handler має бути async, cooperative/nonblocking і propagate cancellation. Registry скасовує
  та await-ить handler/watcher cleanup. Blocking async handler не може отримати late success;
  Python не може примусово preempt-ити блокування або arbitrary code, що ігнорує cancellation.
- Real subprocess cleanup/process groups/HTTP transports — Task6. EffectGuard не rollback і не
  sandbox; зміна контролю не може фізично скасувати вже виконану OS операцію.

## Approvals, privacy й restart

Private approval: exact actor/session/turn/call keyed lookup + canonical finite JSON arguments
SHA-256, exact capability, revision, expiry, decision. Identity lookup HMAC використовує
server-generated scope/turn IDs і opaque provider call ID; це **control identity key**, не
хеш user payload. Raw call ID, arguments, paths, stdout, display names до lifecycle/audit не пишуться.
Capability/name походять trusted catalog. Audit має лише sequence, generated operation UUID,
trusted tool name, fixed state/error code. SQL triggers забороняють audit UPDATE/DELETE;
це не signed/tamper-proof ledger проти власника filesystem.

Digest живе лише в private short-lived approvals table. Consume атомарний зі `started`;
після consume/deny/cancel/expiry digest → NULL. Expiry erasure commit-иться окремо, тому denial
rollback не відновлює digest. Permanent audit не містить digest. Не заявляється erasure unmanaged
snapshots/backups/SSD або захист від іншого процесу з тими самими OS permissions.

Persisted lifecycle: proposed → approved → started → completed; approval denial → failed;
pending cancel → cancelled; possible-effect failure/timeout/cancel/crash → unknown.
Startup переводить abandoned started у unknown без handler execution. Повтор exact call
блокується для completed/failed/cancelled/unknown і навіть concurrent started. Unknown дає
outcome_unknown=True. Результати/output не кешуються і не replay-яться як успіх.

Task7 має зберігати turn/call identity, а не створювати новий turn/call для автоматичного retry.
Idempotent reconciliation/owner recovery після unknown ще не реалізовано; без нього retry
заблокований. Це навмисно консервативно і для handler failures/read-only calls.
Відкриття другого ControlStore над active store також консервативно інвалідовує started;
production application має володіти одним runtime store/process lifecycle.

Arbitrary execution в full-host mode може мати довільні effects у межах Linux permissions.
Argv не є sandbox; blacklist гарантій немає. Generic full-execution не додає registry
capabilities для external messaging/publication; arbitrary OS code технічно може мати network
і destructive effects, що є частиною explicit full-execution approval, а не enforceable narrow mode.
Task6/7/9 authentication, real host tools, persisted content sessions, purge/retention integration,
owner review UI, agent resume і операційний scheduler залишаються downstream.

## TDD та verification evidence

Усі команди в цьому worktree, `.venv` symlink на Downloads, з
`UV_CACHE_DIR=/home/cyberdid/Downloads/B-12-runtime/uv-cache` та `uv run --no-sync`.

1. Початкові 15 behavioral tests написано до production. Перший focused run: **15 setup assertion
   errors**, missing `b12.control`; після окремого direct bootstrap assertion:
   `pytest -q tests/unit/test_registry.py -k control_boundary` → **1 failed, 15 deselected**,
   `AssertionError: server-owned control boundary missing`. Bootstrap-only test згодом прибрано
   як зайвий після реальних behavioral tests. Перший production focused run двох файлів →
   **1 failed, 30 passed**: explicit denied approval повертав replay_blocked. Fix → **31 passed**.
2. Додаткові regressions перед production fixes: **5 failed, 39 passed**. Відтворено підміну
   context deadline/Event, effect після per-call deadline, nested extras та відновлення expired
   approval digest через transaction rollback. Після fixes → **44 passed**.
3. Durable pending cancel і окремий guest typed grant: focused RED → **2 failed, 24 deselected**
   (cancel_turn відсутній, recipient owner restriction). Fix і додаткові restart/concurrency
   behavioral checks → **48 passed**.
4. Self-review privacy/risk RED → **2 failed, 22 deselected**: довільний ControlError code
   потрапив у result/audit; destructive risk відсутній. Fix, final cleanup/format → **49 passed**
   in 1.85s. Це observed RED/GREEN; початковий setup-error run явно відділений від failures.
5. Після стабілізації production ordinary full suite виконано **один раз**:
   `uv run --no-sync pytest -q` → **257 passed, 1 skipped in 4.70s**.
   Skipped — opt-in real model test. `uv run --no-sync ruff check src tests` → **All checks passed**.
   `git diff --check` → exit 0. Після full suite production/tests не змінювалися.

49 focused cases перевіряють real harmless filesystem effects, strict integer/path/extra/LLM
approval rejection, unknown tool association, forged Actor/context/revision/deadline/Event,
exact guest/session/grant bindings, grant expiry/revocation/consent, schemas isolation, one-shot
cross args/call/turn/session replay, approval expiry/revision/deny/digest erasure, explicit task
execution, destructive risk, messaging capability separation, cooperative timeout/Event/Task.cancel,
real persisted started-effect crash, pending/approved/failed/cancelled restart, no duplicate effects,
concurrent call dispatch, private permissions, payload-free audit й late revision guard.

Production archive DB, приватні user files, GPU/model/service, `raw/` і finished artifacts не
читалися/не змінювались тестами. Shared production APIs попередніх Tasks не змінено.

Implementation commit: `0ecc6cd` — `feat(control): enforce durable tool grants and exact approvals`.
Report зберігається у coordinator-owned ignored `.superpowers/sdd` разом із попередніми reports;
до source commit не додано. Після commit tracked worktree clean.

## Fix round 1 — I1 та M1, 2026-10-26

FIX_BASE: `0ecc6cd5d62c7337ddd522fef1c89ab5c5cf1448`.
Джерело review: `task-5-review.md`, I1 Important та M1 Minor. Цей розділ **замінює**
попередній dict-only Handler interface й опис expiry лише як digest erasure. Інші контрольні
межі чинні. Виконавець один; без subagents або незалежного self-review замість reviewer.

### I1 — validated outcome та правдиві ToolResult metadata

Новий `src/b12/tools/outcomes.py` є спільним контрактом для Task6:

- `HandlerOutcome`: Pydantic strict/frozen/extra-forbid; `status` тільки
  `completed|failed|unknown`, finite-JSON `content`, tuple typed `SideEffect`, literal boolean
  `truncated`, optional fixed `error_code`. Весь serialized handler outcome — максимум
  `MAX_OUTCOME_BYTES = 65536` UTF-8 bytes. Handler мусить сам bound-ити збір stdout/stderr/read
  buffers: final validation не обмежує пам’ять, уже виділену ним.
- `completed` вимагає відсутності error і лише confirmed completed side effects.
  `failed` — явне trusted-code твердження про **відсутність effect**, fixed error обов’язковий,
  side_effects мають бути порожні. Partial/possible effects → `unknown` із fixed error.
  Реальні effects довільного OS коду registry не виявляє; це обов’язок trusted handler.
- `HandlerErrorCode`: `handler_failed`, `permission_denied`, `not_found`, `unsupported`,
  `process_failed`, `network_failed`, `cleanup_failed`, `deadline_exceeded`, `cancelled`,
  `coordinator_unavailable`. Довільний текст/path не допускається як error code.
- `SideEffect(kind,state,evidence_ids=(),artifact_ids=())`: kinds `file_write`,
  `process_execution`, `http_request`, `memory_write`, `memory_forget`, `knowledge_write`;
  state `completed|possible`; references — tuple generated UUID strings, максимум 64 references
  кожного виду, максимум 64 effects. Handler не має полів call/name/actor/session/grant/operation.
  Registry додає власний generated `operation_id` до кожного serialized side effect.
- `validated_outcome(value)` після await перевіряє exact DTO types/declared fields, включно з
  nested extras; бере deep-copied snapshot і повторно strict-validate-ить його. Таким чином
  frozen model_copy/model_construct або ручна зміна __dict__/nested content не обходять статус,
  finite JSON, UUID, extra-forbid або 64KiB limit. Invalid output → fixed
  `invalid_handler_outcome`, persisted unknown без claimed success.
- `Handler` тепер `(BaseModel,EffectGuard) -> Awaitable[HandlerOutcome]`;
  dict/ToolResult більше не є легальним handler return. Наявні synthetic handlers мігровано.
  `ToolRegistry.execute` сам встановлює call/name/duration, переносить content/truncated/effects,
  виводить `outcome_unknown` зі status та `finish`-ить той самий completed/failed/unknown стан.
  Guard повторно перевіряється після await/cleanup і перед normal lifecycle finish.
- Unknown return зберігає bounded stdout/cleanup/evidence. Для timeout/Event handler може
  завершити cooperative cleanup вже запущених ресурсів і повернути typed unknown замість
  повторного CancelledError. Registry cancel+await cleanup зберігає цей task result, повторно
  валідовує, примусово повертає unknown із первинним timeout/cancel code та metadata. Навіть
  late completed/failed return не дає success. Поточні consent/revision/grant перевіряються
  перед доставкою evidence; при їхній зміні content не видається. Нові task effects після
  interruption заборонені; exception не відновлює право виконання.
- External `Task.cancel()` самої registry coroutine і далі propagate-иться після cleanup,
  lifecycle unknown; поверненого ToolResult у цьому випадку немає. Blocking/uncooperative
  Python handler не має hard-preemption guarantee. Жодного OS sandbox/blacklist claim не додано.
- Output/effect metadata залишаються actor-authorized result payload, а не audit: permanent
  lifecycle/audit містять лише ті самі generated operation IDs/trusted names/fixed codes/states.

Оновлено `.superpowers/sdd/2026-10-24-b12-full-system/task-6-brief.md`, окремий binding amendment
закріплює точний новий контракт, statuses/error vocabulary, effects/provenance, 64KiB, cleanup-only
unknown return і відсутність late success. Brief/report залишаються coordinator-owned ignored
workflow artifacts, як попередні task reports; source fix commit містить runtime/tests.

### M1 — terminal approval expiry

`ControlStore._expire_approvals` у тій самій IMMEDIATE transaction бере один wall-clock cutoff,
переводить відповідні proposed/approved operations у `failed/approval_expired`, дописує audit
і очищує private digest/decision. Startup, maintenance і prepare використовують цю процедуру.
Вже expired approval зі старої версії теж terminalize-иться; terminal operations повторно не
transition-яться. Prepare для persisted expiry повертає fixed approval_expired, не generic replay.
Registry не виконує expired call, а failed/audit переживають restart.

### Observed RED/GREEN та фінальна перевірка

Команди виконано в тому самому worktree з
`UV_CACHE_DIR=/home/cyberdid/Downloads/B-12-runtime/uv-cache`, `uv run --no-sync`.

1. Нові outcome/effect/truncation/spoofing та expiry regressions написані до production:
   `pytest -q tests/unit/test_registry.py tests/security/test_tool_policy.py -k
   'outcome or truncation_propagate or expiry_terminal'` → **13 failed, 49 deselected**.
   11 direct assertions: missing typed handler-outcome module; 2 state assertions:
   proposed/approved замість failed/approval_expired. Після нового контракту, registry mapping,
   expiry fix і міграції попередніх handlers → **62 passed in 2.78s**.
2. Real temp-file + interrupted cooperative cleanup evidence: `pytest -q
   tests/unit/test_registry.py -k interrupted_cleanup` → **2 failed, 34 deselected**:
   content/effects/truncation були втрачені для timeout та Event cancel. Після preserve-and-force
   unknown path → **64 passed in 2.53s** (focused pair).
3. Self-review cyclic mutated outcome regression: `pytest -q tests/unit/test_registry.py -k
   malformed_handler_outcome` → **1 failed, 9 passed, 28 deselected**: generic handler_failed
   замість invalid_handler_outcome. Додано sanitized RecursionError handling в normal validation
   та cleanup evidence path. Fixed code malformed error_code також перевірено. Final focused:
   `pytest -q tests/unit/test_registry.py tests/security/test_tool_policy.py` →
   **66 passed in 2.98s**. Ruff clean.
4. Full ordinary suite **один раз після стабілізації fix production**:
   `uv run --no-sync pytest -q` → **274 passed, 1 skipped in 5.45s**.
   `uv run --no-sync ruff check src tests` → **All checks passed**.
   `git diff --check` → exit 0. Після цього source/tests не змінювалися.

Self-review зіставив status→ToolResult→finish, registry-owned IDs/provenance, post-await snapshot,
finite/bounded Unicode bytes, nested bypass, real file effects, failed no-effect assertion,
unknown evidence retention, timeout/cancel fixed outer code, no-replay та transactional expiry audit.
Production user files/archive/model/GPU, raw і finished artifacts не змінювались.

Implementation fix завершено; **Task5 gate очікує незалежного rereview**. Task6 не розпочато.

Fix commit: `bc071966003ebf6ef9ee4ed26351465eb64adfc3` —
`fix(tools): preserve validated handler outcomes and expire lifecycle`.
Scoped review diff: `task-5-fix-review.diff`, exact `0ecc6cd..bc07196` runtime/tests,
новий outcomes module включено. Tracked worktree clean після commit.
