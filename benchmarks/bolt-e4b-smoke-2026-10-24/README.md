# Перший локальний smoke test Bolt E4B

**Виконано 24.10.2026.** [Людинозрозумілий звіт](../../wiki/project/bolt-first-test.md) і [report.json](report.json) містять результати, ручну оцінку та обмеження.

Офіційний NVIDIA GGUF Q4_K_M без projector/drafter, Ollama 0.33.3, RTX 4060 Laptop 8GB. [Початковий аудит](../../wiki/project/model-test-readiness.md) містить exact revision, очікуваний SHA-256 і характеристики host.

`Modelfile` задає окремий локальний alias `b12-bolt-e4b:q4km`, контекст 2048 і верхню межу output 192 tokens. Вбудований template береться з моделі/runtime. Sampling за замовчуванням Modelfile відповідає NVIDIA temperature 1.0 / top_p 0.95; smoke harness явно використовує temperature 0 і seed 42 для відтворюваної короткої перевірки. Це різні режими, їхні результати не змішуються.

Після перевірки ваг:

```bash
/usr/local/bin/ollama create b12-bolt-e4b:q4km \
  -f benchmarks/bolt-e4b-smoke-2026-10-24/Modelfile
python3 benchmarks/bolt-e4b-smoke-2026-10-24/run_smoke.py --initial-only
python3 benchmarks/bolt-e4b-smoke-2026-10-24/run_smoke.py
```

Кожний запуск створює окремий `run-<UTC>/` з manifest, фактичними запитами/відповідями, streaming arrival timestamps, GPU snapshots і summary. Скрипт не виконує запропоновані tools; усі події й дані синтетичні. Reasoning field видаляється перед збереженням; зберігається лише його довжина. Model output оцінюється як відповідь моделі, а не дозвіл на дію.

Набір: українське знайомство; п’ять повторів ідентичного prompt; точний JSON без grammar constraints; пригадування з наданим evidence; невідома подія; code-switch; quiet mode; consent boundary; виклик тестової функції. JSON і tool-call перевіряються машинно; інші відповіді потребують окремого перегляду. Узгоджена відповідь про policy не доводить наявність runtime policy enforcement.

`ttft_content_s` — час від HTTP request до першого непорожнього content або tool call; це client-observed arrival, не внутрішній GPU TTFT. Cold load враховується окремим полем server metrics. Однакові warm prompts можуть використовувати prefix cache. P50/P95 на п’яти повторах описують лише цей малий тест і не підтверджують SLO. `decode_tok_s` обчислюється з server eval_count/eval_duration. Жодна метрика тут не вимірює голос, довготривалу пам’ять або продуктивність Jetson.

Окремі prefill probes з унікальним system prefix дали zero-cache результати для ~440/1160/1700 токенів. [Початковий probe](prefill-20261024T174508Z/runner.py) включав 120-line overflow case; три його вимірювання з цієї групи виключені, див. [review](prefill-20261024T174508Z/review.json). [run_prefill.py](run_prefill.py) відтворює bounded follow-up на 90 lines і перевіряє expected response / zero cached tokens.

[gguf-import-verification.json](gguf-import-verification.json) підтверджує однакові 720 tensors і payload після перепакування контейнера Ollama. [verify_gguf_import.py](verify_gguf_import.py) описує перевірку; шляхи в ньому прив’язані до цього host. Source GGUF, Ollama layer і alias мають різні digests; кожен зафіксовано окремо.
