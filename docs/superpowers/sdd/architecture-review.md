---
type: architecture-review
updated: 2026-10-24
status: findings-open
sources: [docs/superpowers/specs/2026-10-24-b12-system-design.md, docs/superpowers/plans/2026-10-24-b12-full-system.md, raw/archive-index-public-7ad80dcdc7e3/src/archive_index/store.py, raw/archive-index-public-7ad80dcdc7e3/src/archive_index/search.py]
tags: [implementation, architecture, contracts, review]
---
# Незалежний review архітектури й плану

Перевірено spec, повний plan, AGENTS.md, поточний стан/журнал і тематичні architecture/memory/archive сторінки; для archive перевірено pinned source. Це review документів і меж інтеграції, не твердження про дефекти ще не реалізованого коду. Код і основні документи не змінювалися. **Вимога:** повний авторизований scope R01–R17 зберігається; нижче немає пропозиції обмежити продукт чатботом чи read-only tools.

Severity: **P1** — виправити контракт до реалізації відповідних consumers; **P2** — виправити до integration/acceptance gate. Усі fixes нижче — **пропозиції**; наведені суперечності/відсутні поля — **перевірені факти про документи**.

## P1-1. `forget() -> bool` не покриває визначений у spec результат забуття

**Доказ:** spec §5, рядки 58–62, вимагає purge всіх managed stores/index/cache/session transcripts, pending purge після restart; R05 додає backups. Plan Task 2, рядки 136–150, має лише `MemoryStore(path)`, `forget(id, actor) -> bool`, SQL/FTS cleanup і checkpoint. Sessions з'являються в Task 7, goals/reflections у Task 11, backup inventory у Task 13. Немає контракту, який повідомляє цим consumers про видалення або відділяє прийняте видалення від завершеного purge.

**Наслідок:** локальний SQL delete може повернути `True`, хоча текст залишається в history, derived index, reflection або backup; stale in-flight model turn може повторно записати забуте після завершення delete. Це реальна неузгодженість acceptance contract, а не суперечність append-only і фізичного видалення: spec уже правильно розділяє metadata/payload.

**Точне виправлення:** залишити `MemoryStore` локальним storage primitive, але визначити application `forget()` з `PurgeReceipt(operation_id, target_ids, state=pending|complete|failed, pending_stores, error_code)`. У тій самій транзакції спочатку записувати payload-free tombstone/pending operation та closure залежностей; усі read/write adapters перевіряють deletion revision. Простий persisted outbox + idempotent purge hooks для sessions/index/cache/goals/backups достатній; окремий сервіс не потрібний. Успіх тільки після підтвердження всіх зареєстрованих managed stores. Restart продовжує pending операції до видачі цих даних. Для активних turns, що вже отримали evidence, потрібен invalidate/cancel і перевірка revision перед новим persistence. Описати межу: зовнішній початковий файл не видаляється автоматично, але automatic re-ingestion забутого source потребує нового явного control рішення.

**Gate:** fault між кожними двома purge hooks; зайнятий WAL reader/checkpoint failure; concurrent recall→forget→late reflection; restart і restore старого managed backup. Перевірити payload bytes і терми індексу, а не лише відсутність SQL row. Source text, source paths, tool arguments і user-entered actor names не повинні потрапляти в незмінний audit hash chain.

## P1-2. Actor DTO і `grant: dict` не задають межу довіри та відкликання

**Доказ:** spec §4/§5/§8 вимагає actor/consent/grants з authenticated control. Plan Task 1, рядки 82–86, визначає publicly constructible frozen Actor; Task 5, рядок 192, приймає `actor` і `grant: dict`; Task 7, рядок 215, приймає одночасно `session_id` та `actor`. Task 9 тестує authenticated control, але не визначає resolver, session-to-actor binding чи перевірку застарілого grant.

**Наслідок:** strict bool validation не доводить контрольне походження `True`; незалежні implementers можуть довіритися JSON Actor, застосувати owner actor до guest session або продовжити write після відкликання consent. Це прогалина контракту; сам по собі constructible Python Actor не є вразливістю всередині trusted process.

**Точне виправлення:** зафіксувати, що Actor — лише resolved snapshot, API не десеріалізує його з body. Auth/session service повертає server-owned `ExecutionContext(actor_id, session_id, turn_id/task_id, grant_id, control_revision, deadline, cancel)`. Registry і persistence перевіряють актуальний grant/consent через control store перед ефектом/записом; session.actor_id має збігатися. Control updates збільшують revision та інвалідовують старі snapshots. Grant мінімально має actor/session binding, allowed capabilities, expiry/revocation і scope. Guest identity ніколи не успадковує owner full-host grant; no-consent впливає й на durable goals, tool transcripts та observability payloads.

**Gate:** client-supplied owner/consent rejected/ignored; session ID іншого actor; revoked grant під час model wait; consent revoked під час tool execution до transcript commit. Після revocation пояснити, чи старі дозволені записи зберігаються, чи викликається explicit forget; це різні операції.

## P1-3. Generic arbitrary command grant суперечить обіцянці контролю руйнівних/зовнішніх дій без конкретної policy

**Доказ:** spec §8, рядки 84–88, одночасно вимагає реального повного host access, argv commands, approvals для destructive дій та окремого дозволу на messaging/publication. Plan Tasks 5–6 задає capability на рівні tool й owner full-host grant, але не правило для довільного `python -c ...`, `sh -c ...`, завантажуваного executable чи MCP tool із будь-якими side effects.

**Наслідок:** argv усуває випадкову shell interpolation, але не обмежує дії самого процесу. Фіксований risk class `shell_exec` або blacklist назв не може виконати заявлену policy: той самий interpreter може читати файл, видаляти дані або надсилати повідомлення. Попередня авторизація користувачем implementation/test роботи залишається чинною; проблема — майбутня runtime policy B-12.

**Точне виправлення:** явно розділити уже авторизовані typed capabilities/task grants і arbitrary-code execution. Повторно використовувати чинний scoped owner grant для дозволеної задачі. Для невідомої дії поза ним створювати reviewable approval конкретного executable/argv/cwd і оголошених ефектів; довільний code execution чесно позначати як такий, що може мати будь-які ефекти в межах OS permissions, а не як гарантовано non-destructive. Якщо потрібна enforceable заборона network/filesystem класів — запускати конкретний клас у відповідному OS boundary; це не обов'язкова нова загальна sandbox infrastructure. Для MCP права задає trusted local catalog mapping, не remote annotations.

**Gate:** synthetic commands через interpreter, helper executable і MCP не отримують ширших повноважень за task grant; generic host grant сам не авторизує explicit send/publish tool. Реальні reversible writes/commands у схваленій задачі проходять без повторних зайвих запитів.

## P1-4. Немає контракту pending approval, відновлення tool execution і невизначеного результату

**Доказ:** Task 5 `.execute() -> ToolResult`, Task 7 `.turn() -> dict`; Task 9 `/api/approvals` і Task 10 pending UI не задають state machine. Spec §4 вимагає originating task/turn ID і side effects; Task 1 ToolCall/ToolResult (рядки 92–98) їх не містить. Task 7 тестує duplicate IDs лише всередині loop; restart semantics зовнішнього ефекту не визначені.

**Наслідок:** implementers можуть трактувати approval як звичайну tool помилку й попросити модель повторити call; approval може застосуватися до змінених args; crash після фактичного write, але до result commit, може повторити дію. Timeout/cancel не означає «ефекту не було».

**Точне виправлення:** визначити `ApprovalRequest(id, actor/session/turn, tool_name, canonical_args_hash, grant_revision, expires_at)` зі станами pending/approved/denied/expired/consumed; після approve продовжується саме збережений call, не новий model proposal. Tool execution записує `(turn_id, call_id, args_hash, state)` до ефекту, має exactly-once admission, але не обіцяє exactly-once зовнішній effect. Після crash неоднозначний started call переходить в `unknown_outcome` і не replay автоматично. До ToolResult додати `side_effects` і однозначний `effect_state=none|applied|partial|unknown`; private деталі ефектів зберігати як deletable payload. Pending wait не тримає GPU semaphore, control lock або нездатний до cancellation session lock.

**Gate:** approve змінених args/іншої session/після expiry; cancel pending approval; kill між effect і result persistence; повторний call ID з іншими args; HTTP/MCP timeout після remote commit.

## P1-5. Pre-inference token admission потребує одного точного request contract

**Доказ:** Task 4 `build(...) -> list[dict]` і окремий `chat(messages, tools=...)`; spec §7 вимагає fit з system/tools/evidence/output reserve та перевірку actual counts. План не зв'язує admission зі справді відправленими tools/options/template і не визначає allowance chat-template overhead. Task 1 default 4096 уже заданий, хоча spec §7 та plan self-review ставлять real validation перед production change.

**Наслідок:** UTF-8 bytes лише content не покривають template control tokens/tool serialization; caller може змінити schemas після admission. `prompt_eval_count <= num_ctx` сам по собі не доводить відсутності truncation, бо backend може повернути count уже обрізаного prompt.

**Точне виправлення:** `ContextBuilder` повертає immutable `AdmittedRequest(messages, tools, num_ctx, output_reserve, input_upper_bound, template/model_revision, request_fingerprint, dropped_ids)`, model відправляє саме його. Або аналогічна одна внутрішня функція з тими ж інваріантами. За exact tokenizer рахувати final model template; fallback потребує перевіреного template-specific overhead та caps на кількість messages/tool schemas, а не bytes content alone. Unknown template/model revision інвалідує профіль. Зберігати active user request і всі незавершені tool-call/result groups. Якщо один required tool result не вміщується, structured overflow або explicit bounded result із truncation metadata, не silent eviction. 4096/8192 застосовувати як evaluation profiles до проходження реального gate; baseline не змінювати непомітно.

**Gate:** schema-heavy, Cyrillic/emoji, many short messages, long multi-call result groups, boundary-fitting inputs; перевірити independent prompt token estimate/actual count і збереження boundary instructions. Метрики мають розділяти transport TTFT, first content, final duration; cache state/digest/options/host зберігати для кожного реального run. Failed/truncated cases залишаються failures, не latency successes.

## P1-6. Archive document identity і evidence identity ще не сумісні з canonical memory

**Доказ:** Task 3 повертає stable evidence ID/source/locator/text, Task 2 приймає `evidence_ids` і перевіряє scope, але немає shared evidence resolver чи document revision contract. Pinned `store.py:17` має глобальний `path UNIQUE`; `replace_document()` (`:179`) замінює документ за path. Pinned chunk IDs — SQLite integers. Project prefix filters вже правильно відзначені у wiki й spec.

**Наслідок:** якщо один Store містить кількох actors, індексування того самого path може замінити чужий документ навіть за exact search guard. Mutable/reused chunk IDs можуть прив'язати reflection до іншої редакції; canonical evidence validator або відхилить усі knowledge IDs, або пропустить неперевірені source references. Exact post-filter після top-k також може втратити authorized hits, витіснені чужими.

**Точне виправлення:** обрати до Task 3 один простий storage layout: окремий derived Store на actor scope або wrapper-owned namespace key `(scope_id, canonical_path)` із перевіреним mapping. Stable evidence key включає opaque document ID + revision/content identity + locator; raw SQLite rowid не є canonical evidence ID. Невеликий `EvidenceRef`/resolver визначає owner, revision, validity/deletion state для canonical memory й knowledge. Update/delete інвалідовує references/derived reflections за правилом. Authorization звужує candidates до ranking/limit; індексування теж вимагає consent до будь-якого durable text.

**Gate:** два actors індексують однаковий абсолютний path; один оновлює/видаляє, інший не змінюється; authorized hit поза global top-k; document update після reflection; chunk rowid reuse після delete; revoked consent до ingestion.

## P2-7. Contracts неповні для незалежних implementers

**Доказ:** spec §4 каже UUID, UTC і versioned JSON, plan Task 1 має arbitrary strings IDs/created_at і no version. Observation/Audit/Session/Goal у spec не мають concrete produced contracts. `handler`, `cancel`, `on_delta`, `on_event`, `grant`, statuses та error codes не типізовані; `.turn()` return/event shape не описані. Task 8 створює CLI до Task 9 auth без bootstrap interface.

**Точне виправлення:** до відповідних tasks записати короткий shared interface appendix і contract tests, без роздування framework:

- Відрізнити generated internal UUID від actor namespace/provider call IDs; UTC-aware timestamp, schema version для durable/wire envelopes. Не змушувати зовнішній provider call ID бути UUID.
- `CancelToken` із cancellable wait; monotonic deadline; `ToolHandler(arguments, execution_context) -> ToolResult`; `ToolSpec` із risk/timeout/output bound.
- Один `TurnResult` і events `turn_started`, `text_delta`, `tool_started`, `tool_result`, `approval_pending`, `turn_completed`, `turn_failed`, `turn_cancelled`; IDs, sequence, payload ownership і terminal semantics.
- Session/control resolver для CLI/API, shared application factory/lifecycle; CLI працює через той самий authorization і purge boundary.
- Task 3 оголосити pyproject/lockfile ownership: pinned lexical modules імпортують `numpy` і `pymorphy3`; UA/RU dictionaries потрібні для morphology gate. Vendor package має бути всередині installable src layout або явно включений у package discovery. Це не вимагає Torch чи upstream full dependency set.

**Gate:** consumer imports/typed fixture без доступу до internals; installed-wheel test, а не лише pytest із repository cwd. API/UI implementers використовують той самий event fixture.

## P2-8. Goal persistence не задає продовження довгих задач і доказ завершення

**Доказ:** spec §4 Goal містить intent/evidence/status/budget/review/tools; §10 вимагає restart. Task 11 конкретизує лише persisted status, scheduler, initiative cap і synthetic experiment; немає public GoalStore/runner interface, ownership, durable checkpoint, consumed budget чи completion evidence. Turn limits Task 7 самі не є long-running goal lifecycle.

**Наслідок:** система може зберігати назву goal, але після restart починати роботу заново, скидати витрачений budget або завершити goal за словами моделі. Quiet/ініціатива може помилково зупиняти дозволену фонову роботу, хоча spec забороняє саме background speech.

**Точне виправлення:** Goal має actor/scope, control-grant reference, immutable original intent, acceptance criteria/evidence IDs, checkpoint/next action, consumed budgets і status transition reason. Runner відновлює checkpoints та перевіряє чинність grant; user pause/cancel, failed/blocked/review-needed і achieved не змішуються. Completion — перевірений criterion/result, не лише model proposal. Quiet mode відділити від execution pause. Goal payload, checkpoints і reflection references підпорядкувати consent/forget. Один persisted scheduler із process-ownership guard достатній; distributed orchestration не потрібна.

**Gate:** restart після кількох steps не дублює effect, не скидає budget, зберігає intent; зміна user priorities не переписує початкову ціль мовчки; completion без evidence відхиляється; реальні day 1/7/30 виміри залишаються окремими незавершеними gates.

## Що вже узгоджено й не потребує перепроєктування

Append-only audit + deletable payload — послідовне рішення; проблема тільки в повному purge coordination. Окремі canonical FTS і knowledge archive Store не конкурують за authority. Local-first + optional owner-authorized HTTP/MCP сумісні. Один writer приводів і незалежні audio/control cancellation paths правильно зафіксовані. Real tools, великі model evals, physical hardware evidence й реальні тривалі спостереження явно присутні; скорочувати їх немає підстав. Pinned vendoring, SQLite, asyncio й прості typed protocols достатні для запропонованих виправлень.

## Порядок внесення уточнень

До Task 2: opaque metadata, evidence identity, control snapshot semantics, local-vs-global forget receipt. До Task 3: scope storage key і evidence resolver. До Tasks 4–7: admitted request, execution context, grants/approvals, effect outcomes, handler/events. До Tasks 8–11: shared application/session control та goal contracts. Task 13 підключає backup hook до вже визначеного purge lifecycle. Усі зміни контрактів фіксувати в execution ledger; це не зупиняє поточну авторизовану роботу.
