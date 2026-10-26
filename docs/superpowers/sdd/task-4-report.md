# Task 4 — model streaming/context admission/cancellation

Статус: DONE. Implementation, deterministic verification та фінальний post-commit marked run завершені. Sole implementer, subagents/reviewers не запускалися. Base `88459dae996d9fdb8fd39fc1dbee5db5d2087ead`, branch `feat/b12-runtime`.

## Scope/API

- `ContextBuilder(settings).build(system, messages, evidence=(), tools=()) -> AdmittedRequest`, навмисне замінює скорочений list-return contract за binding spec §15.5. Context snapshot deeply immutable навіть при dataclass replacement; `payload()` повертає від’єднану копію.
- Snapshot: messages/tools, num_ctx, output_reserve, input_tokens, input_upper_bound, model, model_revision(manifest), template_revision(SHA), profile_identity, dropped_ids, fingerprint. Fingerprint охоплює повний payload плюс identity/budgets; точний count включає rendered system/evidence/history/tools/generation prompt. Output reserved до відправлення; explicit margin 16 у Bolt profile.
- Old user turns oldest-first evicted атомарно; latest user turn та всі його tool rounds обов’язкові. Required system/evidence/tools не обрізаються. Incomplete/ambiguous/orphan results відхиляються. Message IDs metadata не передаються provider; native call IDs збережені.
- Evidence contract `{id, text}`; caller/resolver відповідає за authorization/current visibility. Немає майбутнього tool/agent loop або нового control-plane implementation.
- `await OllamaModel(settings).chat(request, *, on_delta=None, cancel=None, deadline=None) -> ModelReply`; late messages/tools/options API відсутній. `on_delta: Callable[[str], None | Awaitable[None]]`, callbacks sequential. `cancel: asyncio.Event | None`; `deadline: float | None` absolute monotonic. `Settings.model_timeout_s=120` також обмежує весь operation. Cancellation covers deployment requests, header/read waits і callbacks; direct task cancellation propagates `CancelledError`. Transport закривається у finally до повернення; filesystem/tokenizer worker може закінчити чисте локальне обчислення після cancellation без HTTP/callback side effects.
- `ModelError.code`: `profile_invalid`, `profile_mismatch`, `invalid_request`, `context_overflow`, `admission_invalid`, `cancelled`, `deadline_exceeded`, `http_error`, `transport_timeout`, `transport_error`, `provider_error`, `malformed_ndjson`, `invalid_terminal`, `missing_done`, `invalid_tool_call`, `unterminated_reasoning`, `callback_error`, `context_mismatch`, `output_limit`.

## Profile/config/dependencies

`Settings.model_profile` / `tokenizer_dir` explicit absolute paths, env `B12_MODEL_PROFILE`/`B12_TOKENIZER_DIR`; no production Downloads paths/downloads. `profiles/bolt-e4b-ollama-0.33.3.json` pins known deployment and three tokenizer assets. Missing/unknown/hash-mismatched renderer fails closed; no uncalibrated byte heuristic. New Jinja2/tokenizers deps locked/synced via existing Downloads/B-12-runtime/uv-cache and .venv symlink.

`hf-jinja-v1` uses immutable sandbox Jinja, pinned tokenizer with saved truncation/padding disabled; bos/eos from pinned config; thinking/conversational mode off, generation prompt on. Before every chat, reload/hash profile, recalculate count/fingerprint, check settings budgets, server version/model manifest/native template. Default alias remains2048; actual admitted request explicitly 4096/output reserve 128 in calibration. Sampling defaults fixed in fingerprinted payload: temp 0 / seed 42 / draft_num_predict 0. Unknown/replaced model requires separately calibrated explicit profile; not hardcoded as Bolt renderer universally.

Native `message.thinking` ignored; optional supported inline `<think>…</think>` state parser handles split tags before callbacks. No hidden reasoning persisted in artifacts. Unterminated tag/block fails closed. This does not classify arbitrary prose/tags as trusted control. Public callback output is provisional until terminal success: late failure cannot retract streamed text. Metrics whitelist numeric provider fields plus TTFT/elapsed; no content/reasoning copies. TTFT includes local profile reload/hash + deployment checks, tool-only replies have `ttft_s=None`.

Native tool calls accumulate object arguments by `function.index`/opaque ID; malformed/nonobject/string JSON args and conflicting fields fail closed. Missing ID assigned response-local nonce+ordinal. Actual native generated call confirmed in real test; no tool effect executed. Resource bounds: public output tokenizer limit before callback; terminal `eval_count<=output_reserve`; 1 MiB NDJSON line and 8 MiB total response; deadline. Native prompt count must exactly equal admitted count, not merely be below input budget.

## RED/GREEN/self-review

Observed RED context scaffold: 10 failing tests (missing admission behavior), then GREEN 58 including existing 48 config tests. Observed RED transport scaffold: 22 failed, then GREEN 32 focused context/transport. Later targeted RED caught mutable replacement, unvalidated history tool type, missing public token cap, unstructured malformed tokenizer/Jinja failures, and revision identity accepted with recomputed fingerprint. Each fixed and rerun GREEN. A boundary-test literal was corrected from 34 to 33 after independent byte count of `system:S[];user:hi[];[]assistant:`; this was a test-expectation correction, not evidence of a production bug.

Final focused 47 tests pass. Real socket fixture exercises actual httpx/JSONL parser, not mocked adapter. Cancellation event/deadline/task tests wait for server-side socket EOF while client is blocked on next chunk. Added UTF-8/TCP fragmentation, sync/async callbacks, malformed JSONL, HTTP/provider errors, terminal count/shape, giant frame/unbounded hidden stream caps, tool arguments and identity change cases.

Final ordinary suite run once after code stable: `uv run --no-sync pytest -q` → **179 passed, 1 skipped in 2.14s**. Explicit real-model test skipped by default; no model/GPU used by ordinary suite. `ruff check src tests` clean; `git diff --check` clean. Self-review covered signature/spec §15.5, nested immutability, alias/profile invalidation, old vs active atomic groups, hidden-text path, cancellation cleanup, protocol parsing, resource bounds, fixed sampling snapshot, dependencies and no Task 5 implementation.

## Real calibration, immutable local evidence

Existing `artifacts/runtime-preflight-2026-10-24` and `artifacts/model-profile-preflight-2026-10-25` read/reused; unchanged. No alias/global service changes, downloads or rewriting raw originals. New independent run directories, each SHA256 manifest covers metadata, requests/public replies and summary (not manifest itself):

- `artifacts/task4-calibration-2026-10-25-run1`: 12/12 successful (4 scenarios × 3), first boundary 3228 tokens. Test passed 27.28 s. Base commit+dirty diff recorded, but untracked new code not fully represented by that dirty-diff hash; do not treat run1 as exact committed-code provenance.
- `artifacts/task4-calibration-2026-10-25-run2`: 15/15 successful (5 scenarios × 3), near-boundary 3928 tokens plus generated native tool calls; test passed 24.22 s. Same pre-commit provenance limitation, addressed by final post-commit run.

Run2 cases: UA/emoji 51 tokens → ГОТОВО;12 schemas, 968 tokens → ПЕРЕВІРЕНО;2 tool rounds, 183 tokens → 782; boundary 3928 → СОНЦЕ МІСЯЦЬ; generated native tool 108 →calculate_product(a=17, b=23). All counts exactly match native prompt_eval_count; independently checked outputs all pass. Boundary 3928 + 16 margin + 128 reserve = 4072 ≤ 4096. Run2 P50/P95 nearest-rank TTFT seconds: UA 0.661/0.799, schemas 0.673/0.824, multi-round 0.709/0.714, boundary 0.675/1.085. Tool-only TTFT null. N=3 per case is calibration, not a statistically strong benchmark; cache not cleared, mixed warm/prefix state reported. Run1 first UA cold-ish TTFT 8.486 s remains in evidence, not discarded.

Host `cyberdid-Crosshair`, Linux 7.0.0-38-generic/glibc2.39, Python 3.12.3, RTX 4060 Laptop 8188 MiB, power mode performance; Ollama 0.33.3, Q4_K_M. Run2 residency 3323010743 bytes all GPU, context_length 4096; nvidia-smi 3397 MiB after. Runtime profile revision 49843eed8db1f1c616c47af75cfd36e07aec0667; tokenizer cc8d3a0c…; config b3da1b72…; Jinja 35b7d064…; native template b507b9c2…; alias manifest 7eaa0c05…. Full hashes in profile/metadata. Source GGUF/imported blob hashes carried from existing verified provenance, not rehashed multi-GB weights in every calibration. Pinned assets and native alias manifest checked fresh for every chat. Existing 4096/8192 fit evidence retained; no default context change made here, no unnecessary 8192 rerun.

## Residual limits / downstream handoff

- No per-actor provider KV reset/erase guarantee. Adapter holds no conversation/HTTP cache; transport close does not prove server KV erasure. Task 7 provider-context hook must remain pending unless separate coordinated reset is evidenced. Model-wide unload can affect shared callers and needs bounded lifecycle coordination; not implemented here.
- External model alias mutation between preflight and POST is not atomically preventable by native API; deployment manager must serialize alias updates. Terminal exact count detects many mismatches but cannot prove semantic identity in every external race.
- Other model/templates, multimodal messages, alternate inline reasoning tags, stringified tool-argument fragments are unsupported until explicit profile/protocol work. Unknown message fields fail closed. Model-generated tool requests still require future control/grant validation.
- Profile files are trusted operator config; matching supplied hashes alone is not an independent model certification. Real tests establish this pinned deployment/corpus only. Exact counter+boundary checks improve confidence; no universal absence-of-truncation claim.
- Asset reload/hash/reparse each request adds TTFT overhead (~0.5–0.7s in warm samples including server checks), deliberately visible. Future safe cache can optimize with correct invalidation; not hidden in these numbers.
- Wiki page/index/log updated; central project status/implementation ledger delegated back to coordinator.

## Final committed verification

Implementation commit: `4e3cc06c68819fb665980bd16f3d3afe4108b42d` — `feat(model): add pinned context admission and cancellable Ollama streaming`.

Final marked command:

```bash
B12_REAL_MODEL=1 B12_TOKENIZER_DIR=/home/cyberdid/Downloads/B-12-runtime/tokenizer B12_CALIBRATION_DIR=/home/cyberdid/Projects/B-12/.worktrees/runtime/artifacts/task4-calibration-2026-10-25-run3 uv run --no-sync pytest -q -s tests/e2e/test_real_ollama.py
```

Result: **1 passed in 24.90 s; 15/15 calibration requests successful**. Five scenarios × three repetitions, same counts 51 / 968 / 183 / 3928 / 108, all exact prompt counts and independent text/tool assertions pass. Alias parameters unchanged; no model/tool downloads or tool effects.

Final evidence: `artifacts/task4-calibration-2026-10-25-run3/{metadata.json,summary.json,SHA256.json,*-0.json,*-1.json,*-2.json}`. Metadata HEAD is the implementation commit; dirty diff SHA is the empty-diff SHA (`e3b0c442…`), and code SHA-256 covers every src/b12 Python module, test script, pyproject and uv.lock. After run, every artifact hash and code hash verified against current files. Run1/2/3 finished directories and earlier preflight remain unchanged. SHA256.json hash: `c883896584e2e512473885415dd34f8b2dd2045d076f5917808e09deab716f67`.

Final calibration TTFT P50/P95 nearest-rank (seconds; n=3 each):

- ua_emoji: 0.622 / 2.995
- schema_heavy: 0.555 / 0.864
- multi_round: 0.647 / 0.682
- boundary: 0.583 / 1.728
- native_tool: no public text; TTFT null.

Final wiki lint: 26 pages, 214 local links, complete required frontmatter/source paths/index coverage; master brief SHA-256 `e2b0c4c33054082a4df48fed2785c834a95cfb7fb8f6a6e9198b6de53bd8e37a` unchanged. Docs-only commit: `b673212` — final committed calibration evidence. No source/test modifications after final marked run; tracked worktree clean.


## Fix round 1 — 2026-10-26

Base `b673212f03aa072ce24b3f594d587b4d283965e9`. Review source: `task-4-review.md`, three Important findings. Цей запис замінює попередні claims про повну structural admission та підтримку sync callbacks; історію й finished run1–3 не переписано. Subagents/reviewers не запускалися.

**Finding 1:** реальні regressions підтвердили, що reconstructed request із recomputed fingerprint/count міг додати `images`, orphan/incomplete tools, пропустити system/user або передати неправильну schema. Structural validation винесено в спільний `_validate_structure`, який викликають builder та `AdmittedRequest.validate` перед render/send. Shared `_message_groups` зберігає atomic-group перевірки. Leading text system, user history, roles/fields, complete tool groups і supported native function envelope перевіряються повторно; function schema має name/string description/object parameters, properties dict та required list із наявними properties. `ModelError(admission_invalid)` для неправильного snapshot, `invalid_request` для builder input. Fingerprint не є дозволом обійти protocol checks. Легальні snapshots залишилися сумісними.

**Finding 2:** public callback API тепер `DeltaCallback = Callable[[str], Awaitable[None]]`: лише async function/callable. Sync callback відхиляється з `invalid_callback` до profile load/HTTP і без execution; thread offload немає. Callbacks sequential/cooperative/nonblocking, мають propagate cancellation. Event/deadline перевіряються перед callbacks, кожним buffered frame, terminal response і повторно перед public successful return після cleanup. Cooperative callback task скасовується й await-иться до завершення `chat`; subsequent buffered callback не стартує після cancel. Самовільний blocking async callback порушує контракт: Python не гарантує його примусового preemption, але late SUCCESS після elapsed deadline відхиляється. Wiki й module docs узгоджені. E2E тепер використовує async callback і перевіряє, що public deltas точно утворюють sanitized `ModelReply.content`.

**Finding 3:** перед membership terminal reason перевіряється `type(reason) is str`; list/object/bool завжди дають `ModelError(invalid_terminal)` замість raw TypeError. Socket fixture підтверджує EOF/transport close.

RED/GREEN команди й результати:

1. `uv run --no-sync pytest -q tests/unit/test_context.py tests/integration/test_ollama_transport.py -k 'reconstructed_snapshot or forged_snapshot'` → RED **8 failed, 47 deselected** (усі malformed snapshots були прийняті). Після shared validation focused pair → **55 passed in 0.89 s**. Один проміжний refactor run виявив перенесений `data["tools"]` замість локального `tools` (NameError); помилку локалізовано single-test traceback і виправлено до GREEN.
2. `uv run --no-sync pytest -q tests/integration/test_ollama_transport.py -k 'sync_callback or cooperative_async or deadline_is_rechecked or callback_cancellation'` → RED **3 failed, 3 passed, 32 deselected**: sync callback виконався; noncooperative async callback повернув late success; second buffered callback стартував після event. Після fix transport → **38 passed in 1.33 s**.
3. `uv run --no-sync pytest -q tests/integration/test_ollama_transport.py -k malformed_terminal_reason` → RED **2 failed, 1 passed, 38 deselected** (list/dict raw TypeError); GREEN **3 passed, 38 deselected in 0.12 s**.
4. `uv run --no-sync pytest -q tests/unit/test_context.py -k tool_schema_validation_is_shared` → RED **12 failed, 23 deselected** для builder і reconstructed snapshot з unsupported function field, non-string description, non-object parameter root, invalid properties/required. Після fix final focused pair: `uv run --no-sync pytest -q tests/unit/test_context.py tests/integration/test_ollama_transport.py` → **76 passed in 1.57 s**.
5. Full ordinary suite один раз після стабілізації production: `uv run --no-sync pytest -q` → **208 passed, 1 skipped in 2.70 s**. Real test opt-in, ordinary suite без моделей/GPU. `uv run --no-sync ruff check src tests` → **All checks passed** після локального E2E closure-binding correction; production після full suite не змінювався. `git diff --check` clean. E2E callback closure binding перевіриться marked run4.

Self-review: перевірено shared-validator call sites, no unbudgeted POST, async-only preflight, awaited cooperative cleanup, event/deadline guards між buffered frames та перед return, malformed terminal handling. Немає нової provider-cache erase guarantee чи змін Task 5 scope. Raw, profile/model assets, alias/global service та finished calibration artifacts незмінні.

Fix commit: `46b374ccff433a2e3829c631802b635689d7e4ea` — `fix(model): enforce snapshot schemas and cooperative async callbacks`. Post-commit run4 завершено, новий immutable directory `artifacts/task4-calibration-2026-10-26-run4`.

Marked command:

```bash
B12_REAL_MODEL=1 B12_TOKENIZER_DIR=/home/cyberdid/Downloads/B-12-runtime/tokenizer B12_CALIBRATION_DIR=/home/cyberdid/Projects/B-12/.worktrees/runtime/artifacts/task4-calibration-2026-10-26-run4 uv run --no-sync pytest -q -s tests/e2e/test_real_ollama.py
```

Result: **1 passed in 26.37 s, 15/15 requests successful**. Five synthetic scenarios × three repeats: UA/emoji → ГОТОВО (51 input tokens), 12 function schemas → ПЕРЕВІРЕНО (968), two tool rounds → 782 (183), near-boundary → СОНЦЕ МІСЯЦЬ (3928), native generated tool → calculate_product(a=17,b=23) (108). Actual native counts match exact admitted counts, independent response assertions pass, async public deltas equal sanitized reply content in all 15 cases. Boundary 3928 + margin 16 + output reserve 128 = 4072 ≤ 4096. No tool executed.

Metadata includes current implementation HEAD above, empty tracked dirty-diff SHA-256, full file hashes for production modules, E2E test, pyproject and uv.lock; all 14 code hashes verified after run. All 17 artifact hashes verified; 15 response JSON records independently checked. Full pinned model/tokenizer/template/server identities and request inputs are in metadata/individual case files. SHA-256 of run4 `SHA256.json`: `aa2350234631b4301f447a48fac4a28d22f288ef7d45e2b8b0b082ed70ae4cd7`.

Production changed files at run4:

- `src/b12/context.py`: `fc3bb51867e9e6b828165d636a4f2257a9cf6b5ef6871dba3cb467add6c69704`.
- `src/b12/model.py`: `837776ee8964022f6ea398108741e0a3005b87c912fdb12c977e35cb9526222d`.
- `tests/e2e/test_real_ollama.py`: `3fbe675bf745f25d72ffc10d8d6e9549694216a9c4c32332a621423b05521f26`.

Host/runtime/profile and sampling remain pinned as recorded earlier: actual fresh metadata records host/OS/GPU/power, Ollama version/manifest, tokenizer assets, context 4096/output 128/temp 0/seed 42/draft 0. Model alias parameters unchanged; raw and finished run1–3 unchanged. No global service/model file edits. Mixed warm/prefix cache, n=3 per case; this is calibration, not a general latency benchmark. New P50/P95 nearest-rank TTFT seconds:

- ua_emoji: 0.614 / 2.865
- schema_heavy: 0.627 / 0.888
- multi_round: 0.611 / 0.637
- boundary: 0.559 / 1.69
- native_tool: no public text; TTFT null.

Fix round 1 status: implementation and verification DONE; separate coordinator re-review gate remains external to this implementer. Only evidence/wiki documentation changes follow this marked run; runtime/test source hashes stay equal to the committed calibration hashes.


Final docs-only commit/current HEAD: `f3dee60f9cd625fc70eaa1db376eb7f7986e957d`. Final wiki lint: 26 pages / 217 local links; frontmatter/source paths/index valid. Tracked worktree clean. Run4 code identity remains fix commit `46b374c`; later commit changes documentation only.

## Coordinator review completion — 2026-10-26

Independent scoped re-review [task-4-rereview.md](task-4-rereview.md), FIX_BASE `b673212`, HEAD `46b374c`: all three Important findings ADDRESSED; no Critical/Important breakage. Exact HEAD full suite was independently rerun: 208 passed, 1 skipped in 3.39s; Ruff clean. Run4's 17 artifact SHA256 entries, 14 listed runtime/test/dependency hashes, 15 saved reply/count/budget assertions and manifest hash independently verified by coordinator. Task 4 gate is complete; the other R01–R17 requirements remain in progress.
