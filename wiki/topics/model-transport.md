---
type: topic
updated: 2026-10-25
status: implemented_task4
sources: [src/b12/context.py, src/b12/model.py, src/b12/model_profile.py, profiles/bolt-e4b-ollama-0.33.3.json, tests/unit/test_context.py, tests/integration/test_ollama_transport.py, tests/e2e/test_real_ollama.py]
tags: [model, context, streaming, cancellation]
---
# Admission і model transport

**Перевірений факт:** Task 4 реалізує окремі context/transport primitives. Agent loop, tool execution, consent resolver та global purge сюди не входять. [Контракти майбутньої системи](../../docs/superpowers/specs/2026-10-24-b12-system-design.md), [стан реалізації](../project/implementation.md).

`ContextBuilder(settings).build(system, messages, evidence=(), tools=())` повертає `AdmittedRequest`. Усі вкладені messages/tools immutable; caller-owned dict/list не зберігаються. Snapshot містить context/output budgets, точний rendered token count із додатковим margin, model manifest/template/profile identity, fingerprint і dropped message IDs. `payload()` повертає окрему копію; зміни цієї копії не змінюють snapshot.

Останній user turn, усі його assistant/tool-call/result rounds, system text, evidence та tools — обов’язкові. Старі user turns можна видалити лише цілком, oldest first. Incomplete, orphan або ambiguous tool results відхиляються. Evidence входить як `{id, text}`; його авторизацію, актуальність і відповідність `EvidenceRef` перевіряє майбутній shared resolver. Текст evidence позначений як недовірені дані; це не механізм control permissions.

## Явний profile

`Settings.model_profile` і `Settings.tokenizer_dir` задають абсолютні локальні шляхи або відповідні `B12_MODEL_PROFILE` / `B12_TOKENIZER_DIR`. Default path користувача не зашито в production. Немає fallback на неперевірений byte heuristic або завантаження моделей. [Приклад configuration](../../config.example.toml), [pinned Bolt profile](../../profiles/bolt-e4b-ollama-0.33.3.json).

Підтриманий renderer `hf-jinja-v1`: локальний `tokenizers`, immutable sandbox Jinja, `add_generation_prompt=True`, `enable_thinking=False`, `conversational_mode=False`. Перед використанням перевіряються SHA-256 усіх трьох assets. Saved tokenizer truncation/padding вимикаються. Profile включає revision, renderer version, tokenizer/template hashes, alias manifest, server version та native template hash. Інша модель потребує явного відкаліброваного profile.

Перед кожним chat adapter повторно перевіряє локальні assets, snapshot/budgets, `/api/version`, `/api/tags`, `/api/show`. Alias defaults не змінює: кожен запит явно передає admitted `num_ctx`, `num_predict`, temperature 0, seed 42 і `draft_num_predict=0`. Terminal `prompt_eval_count` має точно збігатися з локальним rendered count; меншого count недостатньо для висновку «усе вмістилося». Зовнішнє перепризначення alias між profile check та POST неможливо атомарно заблокувати цим API; deployment manager має серіалізувати такі зміни.

## Streaming і shared cancellation

API: `await OllamaModel(settings).chat(request, on_delta=None, cancel=None, deadline=None) -> ModelReply`. Пізніх messages/tools/options параметрів немає. `on_delta` має контракт `(str) -> None | Awaitable[None]`; callbacks послідовні. `cancel` — shared `asyncio.Event`; `deadline` — абсолютний `time.monotonic()` timestamp. Діє також `model_timeout_s`. Event/deadline охоплюють connection, очікування chunks і callbacks; `Task.cancel()` зберігає `CancelledError`. Transport закривається перед завершенням. Тести перевіряють server-side socket EOF, а не лише факт встановлення event.

Native `message.thinking` відкидається. Профіль може дозволити лише підтриману пару inline delimiters `<think>` / `</think>`; parser тримає часткові delimiters між chunks і не передає прихований текст callbacks. Незавершений блок або неоднозначний частковий delimiter дає `unterminated_reasoning`. Інші довільні provider prose/tags не отримують статусу довіреного reasoning/control protocol.

Native tool-call `function.index` / opaque provider ID пов’язують object-argument chunks. Конфлікти відхиляються, stringified JSON arguments не є native object protocol. Відсутні IDs отримують стабільний у межах відповіді `call-<response nonce>-<ordinal>`; tool call сам по собі нічого не виконує. Terminal stop/length зберігається в `finish_reason`.

Wire обмежено 8 MiB загалом і 1 MiB на JSONL frame; public text token count перевіряється до callback, provider `eval_count` — на terminal event. Metrics містять лише whitelisted числові поля й timing, без копії content/reasoning. `ttft_s` включає повторне локальне profile loading/verification та deployment requests; для відповіді лише з tool calls він `None`.

**Межа:** callback text попередній до успішного `ModelReply`; пізня transport/context failure не може відкликати вже показаний текст. Consumer завершує turn відповідним terminal failure/cancel event. Тут немає власного conversation/HTTP cache. Закриття запиту **не доводить** видалення зовнішнього Ollama KV cache. Per-actor reset/erase API не реалізовано; майбутній purge coordinator має явно обліковувати provider cache як unresolved компонент, доки окремий керований reset не підтверджений.

## Перевірки

**Перевірений факт:** 47 focused context/transport tests, ordinary full suite 179 passed / 1 real-model test skipped; локальні socket fixtures не використовують моделі/GPU. Перевірені overflow, schema budget, atomic groups, exact boundary, nested immutability, profile invalidation, fragmented UTF-8/NDJSON, provider/HTTP/malformed/missing-done errors, output limits, callbacks, blocked-read cancellation і reasoning stripping.

Real run1: 12/12 запитів; run2: 15/15 при context 4096/output reserve 128. [Run2 metadata](../../artifacts/task4-calibration-2026-10-25-run2/metadata.json), [summary](../../artifacts/task4-calibration-2026-10-25-run2/summary.json), [hashes](../../artifacts/task4-calibration-2026-10-25-run2/SHA256.json). Повторів по 3; UA/emoji, 12 schemas, дві tool rounds, near-boundary і native generated tool call. Token counts відповідно 51/968/183/3928/108; усі збігаються з Ollama. Boundary 3928 + margin 16 + reserve 128 = 4072 ≤ 4096; обидва коди на початку/кінці контексту повернуто незалежно від count check. Жодного tool effect не виконано.

На `cyberdid-Crosshair`, Linux 7.0.0-38, RTX 4060 Laptop 8GB, performance mode, Ollama 0.33.3, Q4_K_M residency `size_vram=3323010743`, context_length 4096. Alias default залишився 2048. Run2 TTFT P50/P95 nearest-rank: UA 0.661/0.799 s, schemas 0.673/0.824 s, multi-round 0.709/0.714 s, boundary 0.675/1.085 s. Cache не очищувався; ці три повтори — calibration, не стабільний latency benchmark. Run1/2 виконані до implementation commit; metadata має base commit/dirty diff hash. Final run3 після commit `4e3cc06` також пройшов 15/15 запитів (1 marked test passed, 24.90 s), із чистим tracked tree та SHA-256 production/test/dependency files. [Final metadata](../../artifacts/task4-calibration-2026-10-25-run3/metadata.json), [summary](../../artifacts/task4-calibration-2026-10-25-run3/summary.json), [manifest](../../artifacts/task4-calibration-2026-10-25-run3/SHA256.json); докладний звіт — у [Task 4 report](../../.superpowers/sdd/2026-10-24-b12-full-system/task-4-report.md).

Попередні [4096/8192 preflight results](../../artifacts/runtime-preflight-2026-10-24/summary.json) не переписано. Модель залишається кандидатом; 4096 fit не підтверджує combined voice/VLM residency або повну відсутність truncation для будь-якого майбутнього profile. [Попередні model observations](../project/bolt-first-test.md), [transport source card](../sources/runtime-api-docs.md).
