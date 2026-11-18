# U0 baseline audit — початковий запис

Дата: 2026-11-18. Статус: **незавершено**; цей файл не є freeze або acceptance U0.

## Зріз і походження

- Базовий commit: `36d557d83ce2f44f694cea5d19939031c630a471`, branch реалізації `feat/unified-dr2-dr3`.
- Робоча гілка створена як окремий worktree. Основний checkout містить незакомічені документи DR2/DR3; вони не входять до commit baseline. Оригінал плану: `../../../../raw/CAPRI_DR2_DR3_MASTER_PLAN_2026-11-15.md` у основному checkout; SHA-256 `e350d34cadfd3316dba91e379932f11535a70f3c14aac964ecea3b862d35fb9c` за попередньою фіксацією. Це зовнішній відносно worktree файл, його треба включити у відтворюваний пакет окремим кроком.
- Python 3.12.3; Linux 7.0.0-43-generic x86_64. Це дані хоста, не доказ модельного запуску.
- `config.example.toml` пропонує `b12-bolt-e4b:q4km`, `num_ctx=8192`, `output_tokens=512`; фактична конфігурація запуску, digest, model profile, runtime, power state та доступність моделі ще не зафіксовані. Приклад конфігурації не є manifest експерименту.

## Початкова карта компонентів за статичним читанням

| Компонент | Доказ у коді | Межа перевірки |
|---|---|---|
| Memory | `src/b12/memory.py`: `MemoryStore`; `src/b12/migrations.py`; `src/b12/semantic.py` | Повну інвентаризацію сховищ і purge ще не завершено. |
| Agent | `src/b12/agent.py`: `Agent`, turn events та перевірка cancellation | Реальне виконання не перевірене цим аудитом. |
| Authorization | `src/b12/control.py`: `ControlStore`, approval binding, cancellation, recovery interrupted → unknown | Код не доводить повне покриття всіх зовнішніх ефектів. |
| Goals and initiative | `src/b12/goals.py`, `autonomy.py`, `attention.py` | Готовність довготривалого crash-safe workflow не доведена. |
| Sessions | `src/b12/sessions.py`: `SessionStore`, checkpoints для approval | Не тотожне загальному durable task ledger. |
| Model profile | `profiles/bolt-e4b-ollama-0.33.3.json`, `src/b12/context.py`, `src/b12/model_profile.py` | Сумісність фактичної інсталяції та інших моделей не встановлена. |

## Результати та наступні докази

- Статична інвентаризація в процесі. Існують `tests/unit/test_memory.py`, `test_memory_migration.py`, `test_context.py`, `test_sessions.py`, `tests/integration/test_agent_loop.py`, `test_memory_restart.py`, `tests/security/test_memory_isolation.py`. Наявність файлів не означає успішного проходження.
- Детерміновані тести: VERIFIED 75 passed in 0.87s для tests/unit/test_context.py, test_memory.py, test_memory_migration.py, test_sessions.py та test_attention.py (Python 3.12.3, локальний dev venv; 2026-11-18). Це subset, не весь suite і не live acceptance. Real-model, GPU і longitudinal: NOT_EXECUTED. Історичні результати не переназначені цьому commit.
- Security dependency: розміщення untrusted evidence в system role потребує окремого аналізу; стійкість до prompt injection не встановлена. Відкладені security checks не оголошуються виконаними.
- Потрібні до U0 exit: manifest середовища без секретів; повний аудит trust boundaries та stores; ізольовані synthetic fixtures; schema сценаріїв і manifest; перевірка oracle, splits, runtime-faithful path; детерміновані regression результати та відтворення вибраних історичних артефактів.
- У1, U2 і U3 не виконані. Жоден наступний gate не вважається закритим цим записом.

- Початковий аналіз меж довіри: [THREAT_MODEL.md](THREAT_MODEL.md); це статична ревізія, не завершений security audit.

- Додано чернетки `evals/unified/manifest.schema.json` і `scenarios.schema.json` з поясненням семантичних обмежень у `evals/unified/README.md`. JSON syntax перевірено; незалежну JSON Schema validation не виконано: `jsonschema` відсутній у наявному venv. Контракти не заморожені.

- Системний Python має jsonschema 4.10.3: обидві схеми пройшли `Draft202012Validator.check_schema`. Шість unit tests синтетичного validator пройшли; він перевіряє лише задокументовані структурні/шляхові властивості, не гарантує відсутності semantic oracle leakage. Manifest example validation і fixture freeze ще потрібні.

- 2026-11-18: вибірковий pytest для memory isolation, agent loop, purge та snapshot із фільтром `isolation or consent or duplicate_call or approval or cancel or purge or snapshot or restart`: 21 passed, 71 deselected, 3.35s. Результат не охоплює deselected тести і не є повним suite. Тести використовували тестові fixtures, а не реальну модель.
- Додано [частковий environment manifest](baseline/environment-2026-11-18.json), перевірений за draft schema. Статус NOT_EXECUTED означає, що модельний benchmark не виконувався; цей manifest не є записом pytest прогону. GPU, фактична модель, runtime version і power mode залишаються невідомими.

- Створено початковий генератор синтетичного SQLite через реальний MemoryStore та ізольованого actor: 3 tests passed. 8 tests валідатора включають перевірки однакових input/oracle bytes і hard link. Це не повний runtime snapshot, і клонування/перевірка цілісності ще потрібні.

- Розпочато U1: in-memory projection TurnEvent, без тексту та аргументів; 2 unit tests. Справжній evaluation harness та причинний trace з policy/evidence/verifier ще не підключені.

- U1 trace перевірено у реальному agent loop з тимчасовим state, scripted Ollama і локальним file_read; 1 integration test passed. Collector не приймає події іншого turn (unit test); оновлення не доводить completeness policy/evidence/verifier.

- Підготовлено чернетки U2 historical brevity reproduction і U3 memory baseline protocol у `reports/unified/`. Точні arms E1/E2, frozen fixtures, scoring і margins ще не затверджені; жодних нових модельних результатів немає.

- Повний baseline існуючого suite, без нових `tests/unified`: **771 passed, 8 skipped, 1 failed (153.04s)**. [Зафіксований підсумок і команда](baseline/pytest-2026-11-18.txt); повний stdout не збережено. Failure `tests/e2e/test_cli.py::test_desktop_command_is_optional_and_server_owned`: очікував `owner_token_missing`, отримав `desktop_extra_missing`; `PySide6` відсутній у цьому venv. Наявний CLI імпортує desktop перед перевіркою token. Це baseline failure, а не підтверджене виправлення; повтор із desktop extra не проводився.

- Окремий повтор цього тесту дав ту саму помилку (1 failed, 0.06s). Потрібно відокремити середовище з desktop extra від дефекту тесту/пріоритету помилок у CLI; production fix не включено до U0.

- Додано hash-verified клонування закритого synthetic MemoryStore: джерело з WAL чи зміненим hash відхиляється, існуючий файл не перезаписується. 7 tests passed, зокрема читання клону реальним MemoryStore і actor scope. Це не multi-store snapshot і не доводить цілісності всього runtime.

- Trace отримав експорт JSONL з повторною перевіркою полів і забороною перезапису. Це export adapter, а не повний event contract U1.

- Додано попередню класифікацію tool activity за зовнішньою expectation; результат completed явно позначається unverified. Наявність callback-подій не доводить їх повноту або правильність oracle; це не завершення U1.

- Класифікація tool use тепер вимагає повну послідовність callback подій і парні call start/result; пропуск або незавершений call не рахується успіхом. Тестові підтвердження не є verifier зовнішніх ефектів.

- Початковий U1 trace підключено до існуючого RuntimeTurnExecutor через opt-in observer. Інтеграційний тест двох actor turns використовує реальний runtime та scripted loopback model; окремі ізольовані traces не містять synthetic private marker. Повний harness з provenance/policy/verifier лишається відкритим; старий ScenarioRunner записує власні потенційно чутливі артефакти.

- З локальним системним `jsonschema` через `site.addsitedir` виконано unified + runtime executor tests: 32 passed. Додано 6 перевірок manifest schema (валидний baseline і негативні поля). Offline `uv lock` не мав jsonschema у кеші; залежності та lock не змінені. Наявна schema не забезпечує повноту параметрів для COMPLETED і не є gate.

- Створено перевірку наявності metadata і локальних raw results для reproducibility readiness. Порожні/невідомі поля та небезпечні шляхи блокують readiness; структурно валідний неповний запис залишається допустимим. 35 unified/runtime-executor tests passed. Значення та hashes незалежно не перевіряються; U0 gate відкритий.

- Draft manifest оновлено: кожен raw result має path і SHA-256; readiness validator перевіряє локальний файл і відхиляє невідповідність hash або вихід за artifact root. Тести з missing/tampered/escape пройшли. Hashes модельних assets і зміст результатів ним не перевіряються.

- Додано незалежний synthetic file verifier (SHA-256, відмова від symlink/виходу за root). Інтеграційний тест перевіряє file_write через реальний runtime із scripted model, потім виявляє зміну файла. Ця вузька перевірка не є загальним verifier completion чи authorization.

- Додано runtime-executor regression: synthetic oracle marker із ground_truth не з’являється в двох model requests у перевіреному deterministic scenario; 1 passed. Це не доводить відсутність leakage в інших executors, judges чи fixtures.

- Synthetic multi-store snapshot створюється через open_runtime, містить actor/session, memory і goal; пофайловий SHA-256 перевіряється на source і clone, посилання та SQLite journals відхиляються. 3 tests passed; тест відновлює actor, memory і goal через runtime. Це не snapshot production або live state і не доказ model swap.

- Повтор із locked desktop+tui+voice extras: 870 passed, 4 skipped, 158.47s. [Повний log](baseline/pytest-full-2026-11-18.log), SHA-256 `826b97ec0b4cfd349523036d6d26d40228057835c77594c4c3d9d765b760f558`. Новий runtime snapshot test написано після старту цього прогону; 43 цільові unified/executor перевірки пройшли окремо. Три real-model і один Docker opt-in тести повторно окремо підтвердили skip. Це не проходження real-model/hardware/longitudinal acceptance.

- Opt-in Docker broker test — 1 passed із network=none. Окремо `test_real_ollama.py` — 1 passed, 15 синтетичних реальних Bolt запитів, всі boundary та token counts правильні; [summary і raw файли](baseline/bolt-calibration-2026-11-18/summary.json). Tool execution не проводився. Інші два opt-in e2e тести лишаються відкритими; не вважати suite з 4 skips повністю прийнятим.

- Real Bolt bounded autonomy/reflection test: **1 passed, 3 synthetic repetitions**, each goal reached `achieved` with independent file check, no unchecked achieved, reflection recorded 3/3. [Raw synthetic summary](baseline/bolt-autonomy-2026-11-18/summary.json). Executed against a clean shallow checkout at commit 36d557d83ce2f44f694cea5d19939031c630a471, not the uncommitted research changes; filesystem sandbox hides HOME and uses temporary test state; grants limited to filesystem.read/write and time.read. The host network was shared for Ollama, so this is not a network-isolation test. Scope is one short task, not evidence of long-running or general autonomous initiative. First attempt failed before inference due to inaccessible Git metadata and is excluded as a sandbox setup failure.

- Opt-in real Bolt tools test: 1 pytest passed with no protocol failure in 12 runs, but five recorded behavioral misses. `shell_exec` oracle is obsolete because runtime hides that schema; the model used `run_command` three times. Two of three shell runs selected the parent directory and omitted the expected listing. Details in [MVP ledger](MVP_ACCEPTANCE_LEDGER.md), raw files and SHA256 in `baseline/bolt-tools-2026-11-18/`. Isolated Docker network=none, limited broker to local Ollama; clean HEAD, synthetic state. This does not establish all tasks passed.

- 2026-11-18: corrected the shell listing oracle after checking `ToolRegistry.schemas()`: the model sees `run_command`, not the hidden `shell_exec`. In a new networkless real-Bolt run, 11/12 tool-task repetitions met their behavior checks; the natural-language `ls` case passed 2/3 and the new pytest behavior gate correctly failed the run. A separate explicit-`cwd` prompt arm passed 0/3; a temporary schema-description arm passed 1/3 and was reverted. The issue is an incorrect model `cwd` argument, while the runtime executes that argument successfully. Raw evidence, hashes, conditions and limits: [MVP ledger](MVP_ACCEPTANCE_LEDGER.md#повтор-із-перевіреним-oracle-для-шляху-ls--18112026). This is diagnostic evidence, not U0 closure or MVP acceptance.

- Final deterministic suite after runtime CLI guard: **879 passed, 4 skipped in 175.83s**. [Raw log](baseline/pytest-full-mvp-final2-2026-11-18.log), SHA-256 `5b4e7aaddd6ae4a269393153c00fcb3b067d0e3d41d69db5f16202df254d245e`. Added regression coverage for `runner.py --runtime-dir` refusing an invocation without `B12_EVAL_SANDBOX=1`; the guard is an accidental-run check, while bubblewrap remains the OS isolation boundary. Targeted Ruff and format checks pass for all changed Python files. Repository-wide Ruff still reports 53 diagnostics outside the changed-file clean set.
- Harness audit found the previous single-scenario runtime CLI path lacked the guard that existed in `run_runtime_suite.py`; now guarded before scenario loading. README documents that the unguarded ordinary runner path is model-call-only and does not prove full B-12 runtime behavior.
- U0 remains open: 92 historical scenarios are not retested; the corrected live Bolt `cwd` behavior remains 2/3; four opt-in tests are skipped by the default deterministic suite. No claim of full MVP or plan completion follows from 879 passing tests.
- Follow-up on REL-08 at the initial oracle checkpoint: direct deterministic handler run on disposable synthetic state returned 1 literal event-log criterion failure and 2 passes for snapshot-state equality and deletion non-resurrection. [Raw result and code hash](baseline/rel08-oracle-check-2026-11-18.json), SHA-256 `ac699e09d06e809f616426f9b57993f31978a890fc33601da535a15605fd9bb0`. This was an evaluation-contract mismatch, not a model or runtime failure. The current status was subsequently updated after versioned oracle v2; see the addendum below.

## Networkless runtime-evaluation transport — 2026-11-18

- Extended the eval-only model broker to an exact multi-model allowlist and added a worker entry point that starts `SocketBridge` only after checking the sandbox marker, mounted socket, and loopback URL.
- `sandboxed_suite.sh` now starts the broker on the host, mounts only its private UDS directory, masks `/run`, `/tmp`, and `/var/tmp`, uses a fresh `/proc`, and runs bubblewrap with `--unshare-net`; it no longer relies on shared host networking or a host `/proc` escape hatch. The worker's Ollama URL is fixed to its in-namespace loopback bridge. The actual wrapper transport check was repeated after the additional tmpfs hardening.
- Targeted transport/entrypoint tests: **27 passed, 1 skipped** (Docker opt-in). A real wrapper `--transport-check` queried only `/api/tags` and confirmed the configured Bolt and Gemma 12B records. It did not load model weights, execute inference, or produce a scenario verdict. [Transport evidence](baseline/networkless-transport-check-2026-11-18.json).
- Before the smoke check the RTX 4060 reported 1,292 MiB used and 35% utilization, with a Steam game process using approximately 1,105 MiB; `ollama ps` was empty. Runtime-backed model scenarios were therefore deferred. This check closes only the transport setup subtask; the earlier real-Bolt autonomy experiment used shared host networking and must not be relabeled network-isolated.
- A first full-suite collection attempt with the project `.venv` alone failed because `jsonschema` is installed in system Python but absent from that venv; it is preserved as [collection-failure log](baseline/pytest-full-mvp-networkless-venv-collection-fail-2026-11-18.log), SHA-256 `e5b97ff7a2850bfa44612c239e6f55b03f1158772852cd74dd3e7b32969e26af`. The established `site.addsitedir("/usr/lib/python3/dist-packages")` workaround completed the full suite: **886 passed, 4 skipped in 176.02s**, [raw log](baseline/pytest-full-mvp-networkless-2026-11-18.log), SHA-256 `6e11950c9ec21a0b7dfa42dc278f4f5759b3f931d31f98f186a0091c4014d7d7`. This supersedes the earlier 879-test checkpoint above.
- Then the final shell-hardened diff was rerun with the safe Docker opt-in enabled: **887 passed, 3 skipped in 179.17s**, [final raw log](baseline/pytest-full-mvp-networkless-final-2026-11-18.log), SHA-256 `55ecea6b8a55a6ac08c8ada8fc77001e0e9bb8d772b0db071fa09e3c560fc0be`. The Docker fake-upstream test is included and passed; three remaining skips are real-model inference tests. No model inference was run in this batch because a Steam game held 1,105 MiB of GPU memory (40% utilization at final check).


## Новий execution evidence — MEM-01 / REL-08 — 18.11.2026

- `MEM-01` фактичний Bolt runtime ретест проведено тричі в networkless bubblewrap wrapper. Seeded memory Evidence, зміст, дата, кирилиця й заборонені дії — 3/3; oracle v3 навмисно не дозволяє загальному PASS, якщо TTFT >1,500 ms. Усі три запуски перевищили межу: 6,701 ms cold, 1,742/1,784 ms warm. Максимальний memory budget із YAML не виміряно. [Raw report set](baseline/mem01-rel08-oracle-retests-2026-11-18.json).
- `REL-08` oracle v2 без зміни production runtime перевірив snapshot restore, replay deletion state, відсутність tested forgotten bytes та цілісність audit chain: 2/2 pass; попередній content-event oracle заархівований як superseded, а historical statuses не переписані.
- Після додавання latency assertion та оновлення тестової фікстури повний набір із Docker opt-in завершився **888 passed, 3 skipped, 153.43 s**. [Raw stdout](baseline/pytest-full-mvp-mem01-rel08-final2-2026-11-18.log), SHA-256 `a4bfa6fad462b30c115ab939d931884d299897bcf0aa3f7b07eac632962ae2b6`. Попередній suite з одним fail був діагностичним: stale тестова фікстура очікувала прямий `memory_search` і не подавала runtime evidence.
- Поточний acceptance: 90/92 сценаріїв не retested, MEM-01 fail latency, REL-08 pass under oracle v2. U0 залишається відкритим; цей вузький результат не доводить загальну готовність MVP.

## Додатковий контракт маніфестів — 2026-11-18

- **Перевірений факт:** v1 залишено для backward compatibility; v2 додано окремим файлом і типами `software_suite` та `model_evaluation`. Це прибирає хибну вимогу називати LLM для детермінованого pytest і зберігає строгі model/profile/tokenizer/chat-template вимоги для inference benchmark.
- **Перевірений факт:** v2 manifest для повного pytest вказує 894 passed, 3 skipped, 0 failed / 156,55 с і зв'язаний із raw log та structured record їхніми SHA-256. Checkout був dirty, hash source tree записаний, але архів точного дерева не входить у пакет; manifest не стверджує відтворення запуску з поточного стану.
- **Перевірений факт:** raw artifact validator тепер відхиляє traversal і symlink components, включно з symlink усередині root, та читає лише regular files. Ця перевірка захищає шлях артефакту; не перевіряє достовірність його змісту.
- **Перевірений факт (локальні тести):** `tests/unified/test_manifest_schema.py` — 12 passed; v2 software manifest проходить readiness, а модельний manifest без обов'язкової provenance не проходить schema validation. U0 залишається відкритим: v2 ще не заморожено, fixtures/oracle не пройшли незалежний review, а model evaluation incompleteness лишається.

## Повний suite після manifest v2 — 2026-11-18

- **Перевірений факт:** після змін evaluator contracts повний `B12_DOCKER_TEST=1 .venv/bin/pytest -q` завершився **897 passed, 3 skipped, 0 failed за 157,86 с**. Три opt-in реальні model tests не є acceptance pass. [Raw log](baseline/pytest-full-manifest-v2-2026-11-18.log), SHA-256 `28a6e70ec7092ca01b4bbb357d581afd66a1a08fce546f6fdcf370daa3444495`; [software-suite manifest](baseline/software-suite-manifest-v2-2026-11-18.json).
- **Перевірений факт:** для запуску записаний hash дерева `src/`, `tests/`, `evals/`, `pyproject.toml`, `uv.lock` за deterministic path/hash recipe; SHA-256 `a8422801d8ada692227b0def1e6ba9488da18b39e246917fb0086828a80c5864` (569 файлів). Точний dirty snapshot не архівований, тому replay з цього manifest не заявляється.
- **Статус:** regression suite зелений, але U0 не закрито: runtime corpus має 86 непротестованих сценаріїв; resource, voice, hardware, model portability та longitudinal gates залишаються окремими.

## Контракт fixture v2 — 2026-11-18

- **Перевірений факт:** `scenarios-v2.schema.json` фіксує SHA-256 input та oracle для кожного сценарію. `validate_scenarios.py` підтримує legacy v1 і v2; v2 перевіряє точні hashes, split одного family, symlink-free root-relative paths, regular files, hardlinks та однаковий вміст між input/oracle. Це не доводить семантичну незалежність ground truth.
- **Перевірений факт (тести):** `tests/unified/test_validate_scenarios.py` — 11 passed. Є перевірки fixture mutation після freeze, missing hashes та внутрішнього symlink. Набір scenario families ще не згенерований; незалежний review і status FROZEN не заявляються.

## U1 telemetry — partial implementation — 2026-11-18

- **Перевірений факт:** `TurnEvent` доповнено `policy_decision`. `ToolRegistry` віддає observed рішення `allowed`/`approval_required`/`denied` із control/admission phase; agent-internal preflight окремо позначається. Observer не змінює авторизацію: помилка телеметрії не може дозволити або зупинити tool execution. Непередбачений шлях без події зберігається як `policy_unobserved`.
- **Перевірений факт:** `trace.py` + `trace.schema.json` серіалізують tool call, policy, status, error codes, per-tool evidence references, runtime outcome і незалежний evaluator verdict. Секретні тексти/аргументи/шляхи не потрапляють до JSONL; UUID замінюються aliases, файл створюється з mode 0600 і без перезапису. Approval wait зберігається як очікуваний не-terminal control state, а не як невдалий завершений tool.
- **Перевірений факт:** `RuntimeTurnExecutor` збирає result, `ScenarioRunner` додає deterministic/judge verdict після оцінювання. Unit і runtime integration coverage: 22 цільові trace tests passed; 107 тестів разом із `test_agent_loop.py` пройшли перед останнім доказовим fixture-тестом.
- **Обмеження U1:** classification/decision target із frozen scenario ще не додається; final claim зберігається тільки як `response_present` (текст claim не зберігається й семантично не розбирається); aliases не корелюють між різними traces або resumed approvals; output існуючого ScenarioRunner все ще може зберігати текст і private data. Отже U1 частково реалізований і exit criteria ще не виконані.

## Повний suite після U1 policy/evidence trace — 2026-11-18

- **Перевірений факт:** повний `B12_DOCKER_TEST=1 .venv/bin/pytest -q` завершився **904 passed, 3 skipped, 0 failed за 157,40 с**. Три skip-и — real-model opt-in, не acceptance pass. [Raw stdout](baseline/pytest-full-u1-trace-2026-11-18.log), SHA-256 `5fccfbf4a71c682047337d264bc48c3ae48e26f87e239b90c09143d742df1733`; [schema v2 manifest](baseline/software-suite-u1-trace-2026-11-18.json).
- **Перевірений факт:** digest source set (571 файлів) — `3ca98eb6fb5fc55a2bbd87995ca46de1bf09652a8c0513d3ea0d9aaf189df0be`; scope/algorithm і відсутність точного source archive описані в manifest. Це відтворюваний ідентифікатор вибраного дерева, не його архів.
- **Статус U0/U1:** schema contracts і детермінований regression перевірені; scenario corpus ще не frozen, semantic oracle review не виконаний, U1 causality має відкриті gaps, 86 runtime scenarios не повторені. Етапи далі лишаються відкритими.
