### Spec Compliance

- ❌ **Issues found:** три Important порушення binding brief/spec §15.5: schema/protocol validation можна обійти при реконструкції admitted DTO (`src/b12/context.py:87`); sync callback порушує deadline/cancellation contract (`src/b12/model.py:241`); malformed terminal не завжди повертає structured `ModelError` (`src/b12/model.py:262`).
- ✅ Решта перевіреного scope реалізована: усі п’ять названих brief файлів мають відповідні hunks; profile/config/dependency support у дозволеному scope. Immutable snapshot та exact admission — `src/b12/context.py:38`, `src/b12/context.py:145`; реальний native transport — `src/b12/model.py:195`; socket tests — `tests/integration/test_ollama_transport.py:15`; opt-in real calibration — `tests/e2e/test_real_ollama.py:26`. Intentional amended `chat(request, ...)` API відповідає binding override (`src/b12/model.py:148`).
- ⚠️ **Cannot verify from diff:** evidence authorization/current visibility, shared control resolver, tool execution/grants, propagation cancellation через agent/tools та рівно один application terminal event належать наступним tasks (`docs/superpowers/specs/2026-10-24-b12-system-design.md:187`, `wiki/topics/model-transport.md:14`). Provider KV-cache purge явно unresolved (`wiki/topics/model-transport.md:34`); це не пропуски Task 4.
- ⚠️ **Межі доказів:** atomic deployment identity між preflight і POST потребує зовнішньої coordination (`wiki/topics/model-transport.md:22`). Calibration підтверджує pinned deployment/corpus, а не всі майбутні profiles/prompts, combined voice/VLM residency чи універсальну відсутність truncation (`wiki/topics/model-transport.md:40`, `wiki/topics/model-transport.md:44`).

### Strengths

- `src/b12/context.py:51`, `src/b12/context.py:56`, `src/b12/context.py:87`: nested freeze, detached payload та повторна перевірка profile/model/template/count/budgets захищають від звичайної мутації caller-owned data. Revision identity перевіряється окремо від fingerprint.
- `src/b12/context.py:145`, `src/b12/context.py:178`: старі user turns видаляються цілком; latest user та його tool rounds, system/evidence/tools required. Tests перевіряють overflow і atomic eviction (`tests/unit/test_context.py:67`).
- `src/b12/model_profile.py:49`, `src/b12/model_profile.py:58`, `src/b12/model_profile.py:75`: hash і parse тих самих asset bytes, вимкнення saved truncation/padding, explicit sandbox renderer; profile mismatch fail closed.
- `src/b12/model.py:44`, `src/b12/model.py:224`, `src/b12/model.py:265`, `src/b12/model.py:313`: split inline reasoning filtering відбувається до callback; native thinking не копіюється; prompt count порівнюється точно; output/wire/line bounded.
- `tests/integration/test_ollama_transport.py:168`: event/deadline/task cancellation перевірено real socket fixture із server-side EOF під час blocked read. `tests/e2e/test_real_ollama.py:73`, `tests/e2e/test_real_ollama.py:188`: opt-in calibration записує provenance, public replies, repeated cases та незалежні text/tool assertions; mixed cache й n=3 задокументовано.

### Issues

#### Critical (Must Fix)

- Не виявлено.

#### Important (Should Fix)

1. **Реконструйований admitted DTO обходить structural/protocol admission.** `src/b12/context.py:87` перевіряє fingerprint, identity і rendered count, але обмеження fields/roles/tool groups/schema існують лише в builder (`src/b12/context.py:121`, `src/b12/context.py:183`). Public dataclass constructor та `dataclasses.replace` виконують у `__post_init__` лише freeze (`src/b12/context.py:51`). Тому додавання `images` до user message з перерахованим fingerprint може залишити той самий text-token count і пройти `validate`; adapter потім надсилає саме цей payload (`src/b12/model.py:190`, `src/b12/model.py:207`). Попередній focused synthetic probe зафіксував `FORGED_IMAGES: accepted; input_tokens=33`; статичний повторний перегляд підтвердив відсутню перевірку. Це порушення fail-closed unsupported protocol contract для звичайного reconstructed DTO, а не заява про захист від hostile Python process. **Виправлення:** shared structural validator для builder і кожного snapshot перед count/send, включно з допустимими fields/roles, required system/latest-user, complete tool groups і tools schema. Додати regression для direct construction/replace з recomputed fingerprint, unsupported fields та orphan/incomplete tools; легальні snapshots мають лишитися accepted.

2. **Sync callback блокує event loop і дозволяє success після deadline.** `src/b12/model.py:241` викликає callback безпосередньо в event loop; `asyncio.wait`/cancellation watcher (`src/b12/model.py:165`) у цей час не працюють. Якщо terminal buffered, operation може завершитися до обробки timer, а `chat` повертає `operation.result()` без повторної monotonic deadline/event перевірки (`src/b12/model.py:174`). Попередній real-socket probe: `time.sleep(0.3)` у callback при deadline `started + 0.1` завершився **SUCCESS hi через 0.371 s**; code path це пояснює. Гарантія bounded callbacks у `wiki/topics/model-transport.md:26` не виконується; блокуються також інші tasks event loop. **Виправлення:** визначити й реалізувати nonblocking/cancellable delivery policy для підтриманих callbacks, перевіряти deadline/cancel перед terminal success, чесно описати cooperation та side effects. Thread offload сам по собі не гарантує припинення callback side effects після cancel. Додати regression з blocking sync callback, buffered terminal та async callback cancellation. Наявний blocked-read test (`tests/integration/test_ollama_transport.py:168`) цього випадку не покриває.

3. **List/object `done_reason` виходить як `TypeError`.** `src/b12/model.py:262` робить set membership до type validation. JSON terminal із коректними counters і `done_reason: []` або `{}` спричиняє `TypeError: unhashable type`, що не обгортається HTTP-only handlers (`src/b12/model.py:281`). Попередній focused probe зафіксував саме `TypeError` для `[]`; Python membership semantics однозначно підтверджує причину. Transport cleanup зберігається, але consumer задокументованих ModelError codes отримує неструктуровану protocol exception замість `invalid_terminal`. **Виправлення:** перевірити `isinstance(reason, str)` перед membership; додати list/object cases до real socket fixture test (`tests/integration/test_ollama_transport.py:135`).

#### Minor (Nice to Have)

- Окремих findings немає.

### Checks and Evidence

- Повторний read-only review охопив code/test/documentation hunks пакета `88459da..b673212` у bounded ranges, brief і spec §7/§15.5. Changed production files окремо не перечитувалися; git commands, source/test/raw/evidence edits і nested agents не виконувалися. У великому lockfile range tool скоротив частину registry wheel metadata; це обмеження перегляду dependency metadata, не прихований пропуск production коду.
- Named cross-API risk — non-builder construction paths: focused `rg` для `AdmittedRequest(...)`, `replace(request, ...)`, `.validate(...profile)` у `src`/`tests` підтвердив єдиний поточний production constructor у builder (`src/b12/context.py:161`) та публічні replacement paths у tests (`tests/unit/test_context.py:127`, `tests/unit/test_context.py:174`). Відсутність поточних application consumers не робить validator повним для задекларованого public DTO.
- Named renderer risk — fields, не охоплені count: focused read-only `rg` у pinned локальному `chat_template.jinja` показав content/tool-call rendering; окреме message field `images` не рендериться. Snapshot.payload передає всі message fields (`src/b12/context.py:59`), тому повторний text count не замінює schema validation. Synthetic fixture також ігнорує `images` (`tests/conftest.py:23`).
- Нових probes, suite, marked model run або GPU run не запускалося: причинні paths достатньо видно в коді; конкретні результати попереднього reviewer probe збережено вище як історичні докази. Coordinator повідомив fresh exact-code suite **179 passed, 1 skipped** та перевірку **15/15** committed calibration responses/hashes. Ці перевірки не покривають три наведені edge cases; їх не заявлено як власний повторний run reviewer.

### Assessment

**Task quality: Needs fixes.**

**Reasoning:** Admission/profile/transport добре розділені, socket tests перевіряють реальну поведінку, calibration має конкретні межі та provenance. Три Important gaps порушують fail-closed schema admission, deadline/cancellation і structured terminal-error contracts, тому Task 4 gate ще не проходить.
