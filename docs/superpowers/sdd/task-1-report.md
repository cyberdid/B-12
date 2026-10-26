# Task 1 — package, contracts та config

Статус: **DONE** (independent review завершений; єдиний P3 finding виправлено з RED/GREEN evidence нижче).

- Дата: 2026-10-24.
- Worktree: `/home/cyberdid/Projects/B-12/.worktrees/runtime`.
- Branch: `feat/b12-runtime`.
- BASE: `78daaef799befd67f8c1ec515d28596061eacc2e`.
- Початковий commit: `4cf5e7940146bb613ef7645f177fc02704e42871` — `feat: establish validated B-12 runtime contracts`.
- HEAD/fix commit: `4c455b578499182b8f59f9cab38fcf2fa72916d2` — `fix: reject empty URL query and fragment delimiters`.
- Scope: тільки `.gitignore`, `pyproject.toml`, `uv.lock`, `config.example.toml`, `src/b12/{__init__,contracts,config}.py`, `tests/unit/test_{contracts,config}.py`.
- Не редагувалися wiki, raw, benchmark artifacts або файли інших task. Незакомічена зміна plan належить координатору й не включена до commit.

## RED evidence

Спочатку створено packaging, порожній package initializer та поведінкові тести. Production contracts/config ще не існували.

У всіх командах uv використовувалися:

```bash
UV_PROJECT_ENVIRONMENT=/home/cyberdid/Downloads/B-12-runtime/.venv
UV_CACHE_DIR=/home/cyberdid/Downloads/B-12-runtime/uv-cache
```

Початковий запуск:

```bash
uv run pytest tests/unit/test_contracts.py tests/unit/test_config.py -q
```

Exit 2, очікувані missing imports:

```text
ModuleNotFoundError: No module named 'b12.contracts'
ModuleNotFoundError: No module named 'b12.config'
2 errors in 0.08s
```

Після початкового GREEN (85 passed) додано окремі boundary regressions до наступних production змін. Повтор тієї самої команди дав exit 1:

```text
FAILED ...test_actor_rejects_invalid_identity[guest\x7f]
FAILED ...test_memory_rejects_invalid_provenance[changes9]
FAILED ...test_invalid_ollama_endpoint_is_rejected[http://localhost:]
FAILED ...test_state_path_may_not_have_a_file_as_parent
4 failed, 87 passed in 0.13s
```

Кожне падіння — `DID NOT RAISE ValidationError`: DEL у identity, UTC offset без двокрапки, порожній explicit port і файл серед батьків state path. Після цього реалізовано відповідні перевірки. Тести не читають source code і не підміняють поведінку mocked success.

## GREEN evidence

Фінальне середовище: Ubuntu host, CPython **3.12.3** (`/usr/bin/python3.12`), uv **0.12.1**. Початковий uv auto-selection використав 3.13.14 (дозволений requires-python); фінальне середовище відтворено на baseline 3.12.3.

```bash
uv sync --extra dev --locked --python /usr/bin/python3.12
```

Exit 0: `Resolved 32 packages in 0.72ms`, `Installed 31 packages in 15ms`. Lock містить hashes й dependency metadata, Python constraint `>=3.12,<3.14`. Без Torch, GPU/audio dependencies або model downloads. Runtime dependencies: httpx, pydantic, FastAPI, uvicorn, NumPy, pymorphy3 та uk/ru dictionaries; dev extra: pytest, pytest-asyncio, Ruff.

```bash
uv run pytest tests/unit/test_contracts.py tests/unit/test_config.py -q
```

Exit 0:

```text
........................................................................ [ 79%]
...................                                                      [100%]
91 passed in 0.14s
```

```bash
uv run ruff check src/b12 tests/unit/test_contracts.py tests/unit/test_config.py
git diff --check
git diff --cached --check
```

Exit 0, `All checks passed!`, whitespace checks без output.

```bash
uv build --out-dir /home/cyberdid/Downloads/B-12-runtime/dist
```

Exit 0, успішно створено `b12_runtime-0.1.0.tar.gz` і `b12_runtime-0.1.0-py3-none-any.whl` поза root partition.

Окремий Python import probe імпортував `b12`, усі п’ять contracts і `Settings`, перевірив відсутність `torch` та `numpy` в `sys.modules`. Exit 0: `3.12.3 0.1.0 CPU-only import OK`.

## Public interfaces

- `b12.__version__ = '0.1.0'`; src layout, distribution `b12-runtime`.
- Усі DTO в `b12.contracts`: Pydantic strict validation, unknown fields forbidden, `schema_version: Literal[1] = 1`, JSON roundtrip через стандартні Pydantic methods. Версія має бути саме integer 1.
- `Actor(id: str, owner: bool=False, consent: bool=False)` — frozen; ID 1..128, не порожній, без surrounding whitespace/control characters; string/numeric booleans rejected. Actor є DTO довіреного control path; transport authentication буде реалізовано downstream.
- `MemoryRecord(id, owner_id, kind, text, source, created_at, evidence_ids=())`: persistent `id` та кожний evidence ID перевіряються як UUID; `owner_id` — opaque actor namespace, `source` — довільний nonblank provenance locator. Text nonblank. `created_at` — ISO8601 UTC string, suffix `Z` або `+00:00`, без naive/local time.
- `ToolCall(id, name, arguments, turn_id=None, task_id=None)`: model call ID opaque 1..128, origins якщо задані — application UUID. Arguments — finite JSON values зі string object keys; не довільні Python objects.
- `ToolResult(call_id, name, status, content, duration_ms=0, error_code=None, truncated=False, side_effects=(), outcome_unknown=False)`: finite nonnegative duration; content/side effects JSON; immutable empty tuple defaults. `status` і `error_code` відкриті для downstream error codes, nonblank.
- `ModelReply(content='', tool_calls=(), metrics=default_factory(dict), finish_reason='stop')`: cross-instance metrics isolation, finite JSON metrics.
- `Settings(state_dir: Path, model='b12-bolt-e4b:q4km', ollama_url='http://127.0.0.1:11434', num_ctx=4096, output_tokens=512, max_rounds=8, max_tool_calls=16, tool_timeout_s=30, host_access='full')`: positive strict integer limits, finite positive timeout, output reserve strictly below context. `host_access` accepts `full`, `read_only`, `none`.
- State path: absolute або `~`-prefixed, normalized resolved Path; reject empty/NUL/relative/root/file та file ancestors. Parsing не створює directories/files і не перевіряє hardware/resource availability.
- Ollama endpoint: HTTP(S), valid hostname/port; loopback default, explicit remote endpoints і path prefix дозволені; credentials/query/fragment/whitespace/backslash rejected. Parsing не виконує network I/O.
- `Settings.from_env(environ: Mapping[str,str] | None=None)`: explicit mapping ізольований від ambient `B12_*`; None читає process env. `B12_STATE_DIR`, `B12_MODEL`, `B12_OLLAMA_URL`, `B12_NUM_CTX`, `B12_OUTPUT_TOKENS`, `B12_MAX_ROUNDS`, `B12_MAX_TOOL_CALLS`, `B12_TOOL_TIMEOUT_S`, `B12_HOST_ACCESS`. Default state location `$XDG_STATE_HOME/b12` або `~/.local/state/b12`. Invalid env values raise validation/value errors; parsing без запису.
- `config.example.toml` можна завантажити через `Settings(**tomllib.loads(...))`. Standalone file loader не додано: його не вимагав Task 1.

## Review та межі

- Враховано coordinator ruling щодо opaque model IDs, UUID persistent IDs, UTC, schema version, call origins та uncertain side effects.
- `num_ctx=4096` — кандидат config default, не доказ deployment resource fit. Реальний inference/token/context benchmark залишається Task 4.
- Frozen Actor не є authentication boundary сам по собі; downstream server має створювати його з authenticated session, а не довіряти model/request body.
- Config parsing читає metadata state path для валідації, але не пише runtime state. Permissions/bootstrap/migrations — downstream task.
- `.venv` — symlink на Downloads partition, правило ignore доповнене для самого symlink; cache/build artifacts також у Downloads.
- Потреби в approval, іншому контексті або зовнішньому доступі для Task 1 немає. Загальна системна ціль залишається active.

## Review fix — empty URL delimiters (P3)

Independent review у `task-1-review.md`: quality pass, sole minor spec deviation — `urlsplit` повертає порожні query/fragment для URL із bare `?` або `#`, тому truthiness check пропускав literal delimiter.

Спочатку додано обидва invalid URL cases та позитивний case `https://inference.example.org/ollama%3F%23` для збереження легітимного percent-encoded path. RED на Python 3.12.3:

```bash
uv run pytest tests/unit/test_config.py -q
```

Exit 1:

```text
FAILED ...test_invalid_ollama_endpoint_is_rejected[http://localhost:11434?]
FAILED ...test_invalid_ollama_endpoint_is_rejected[http://localhost:11434#]
2 failed, 46 passed in 0.08s
```

Обидва падіння — `DID NOT RAISE ValidationError`. Після RED замінено лише `parsed.query`/`parsed.fragment` на перевірки literal `?`/`#` у вихідному endpoint. Percent-encoded `%3F`/`%23` залишаються дозволеними.

GREEN:

```bash
uv run pytest tests/unit/test_contracts.py tests/unit/test_config.py -q
uv run ruff check src/b12/config.py tests/unit/test_config.py
git diff --check
git diff --cached --check
```

Exit 0: **94 passed in 0.09s**, `All checks passed!`, whitespace checks без output. Окремий focused probe підтвердив, що `http://@localhost:11434` і `http://:@localhost:11434` уже відхиляються поточною перевіркою `parsed.username is not None`; додаткової production зміни для empty userinfo не знадобилося. Probe не виконував network I/O або state writes.

Fix commit `4c455b578499182b8f59f9cab38fcf2fa72916d2` містить тільки `src/b12/config.py` і `tests/unit/test_config.py` (4 insertions, 2 deletions). Нових concerns немає.
