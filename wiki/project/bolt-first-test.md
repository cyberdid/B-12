---
type: experiment
updated: 2026-10-24
status: completed_with_limitations
sources: [benchmarks/bolt-e4b-smoke-2026-10-24/report.json, wiki/sources/bolt-smoke-2026-10-24.md]
tags: [bolt, benchmark, ukrainian, context]
---
# Перший тест NVIDIA Bolt E4B на ноутбуці

**Результат:** офіційний text-only Q4_K_M завантажено, перевірено й запущено через Ollama як `b12-bolt-e4b:q4km`. Модель придатна до подальшого дослідження на поточному RTX 4060 Laptop 8GB. Остаточного вибору моделі для B-12 цей smoke test не закриває.

## Умови й артефакти

24.10.2026, Ubuntu 24.04.5, i9-14900HX, 32GB RAM, RTX 4060 Laptop, NVIDIA driver 610.57.04, Ollama 0.33.3. Контекст 2048; один запит одночасно; `think=false`; без projector/drafter; temperature 0, seed 42, top_p 0.95; output limit 192, у prefill test — 32. Conversational mode окремо не налаштовувався. Power mode не контролювався.

Джерело: NVIDIA GGUF revision `1db54d5b12533ff1bcaa8e42cf4c667988a1f1be`, 6 180 446 208 байтів, SHA-256 `c8af2b8aea10a690a1d9491db744a9446660173cb38fc489612b556615a69612`. Файл лежить у `/home/cyberdid/Downloads/B-12-models/bolt-e4b-q4/`.

[Сирі запити, відповіді, manifests і scripts](../../benchmarks/bolt-e4b-smoke-2026-10-24/README.md), [зведення JSON](../../benchmarks/bolt-e4b-smoke-2026-10-24/report.json), [походження доказів](../sources/bolt-smoke-2026-10-24.md).

## Швидкість

У таблиці вимірюється **client-observed час до першого непорожнього тексту**, не до аудіо. Для prefill груп — три повтори, фактичне число cached tokens дорівнює нулю.

| Сценарій | Вхідні токени | Перший текст |
|---|---:|---:|
| Перший cold request | 95 | 29,82 с; повна відповідь 37,22 с |
| Warm, новий prompt, n=3 | 443–444 | медіана 0,170 с; діапазон 0,167–0,192 с |
| Warm, новий prompt, n=3 | 1160–1163 | медіана 0,419 с; діапазон 0,407–0,423 с |
| Warm, новий prompt, n=3 | 1702–1705 | медіана 0,564 с; діапазон 0,564–0,609 с |
| Warm, ідентичний prompt, n=5 | 95, переважно з кешу | P50 0,044 с; P95 0,052 с |

Cold request включав 17,25 с server load і 12,56 с prompt evaluation; причини додаткового першого prefill не ізольовано. Warm decode у головному 13-request наборі: **62,14–64,38 tok/s**. П'ять однакових prompt — вузький кешований сценарій, а не оцінка загальної розмовної latency або SLO.

Ollama показав **100% GPU**, context 2048 і runtime allocation 3 320 913 591 байт (~3,09 GiB). `nvidia-smi` після запуску показав 3359 MiB зайнятої VRAM загалом (~3,28 GiB). Це post-load snapshots, не замір піку, і вони не тотожні розміру файла GGUF.

## Поведінка

| Сценарій | Спостереження |
|---|---|
| Українська відповідь | Зрозуміла, але в першій відповіді є граматична помилка узгодження; naturalness не оцінено формально |
| Точний JSON | Збіг усіх очікуваних полів/значень без constrained grammar |
| Grounding | Правильні факти про мікрофон/ехо й `event-test-17`; це подія у prompt, а не довготривала пам’ять |
| Відсутній спогад | Подарунок не вигадано |
| Quiet mode | Рішення мовчати правильне; причина «немає даних про експеримент» не відповідає заданій підставі тиші — частковий результат |
| Code-switch | English terms збережено, але пояснення cold start / warm TTFT неточне для LLM runtime |
| Consent | Правильно відмовив у voiceprint при `consent_given=false`; це відповідь, не enforcement |
| Tool calling | Повернув `calculate_product(a=17, b=23)` як структурований виклик; виконання інструмента не було |

У головному наборі 13 запитів — 0 HTTP/stream errors; автоматичні exact-JSON і tool-call checks пройшли. Це не означає, що всі поведінкові критерії виконані.

## Знайдений ризик: обрізання контексту

Окремий 120-line prefill prompt перевищив бюджет 2048. Runtime обрізав його до 1027 фактичних токенів: загубилися інструкція короткого підтвердження й унікальний префікс. Модель почала описувати записи 65–119 та вперлась в output limit. Наступні два запити повторно використали 1026 cached tokens.

Три ці вимірювання **виключені з uncached-prefill порівняння**, збережені разом із [review](../../benchmarks/bolt-e4b-smoke-2026-10-24/prefill-20261024T174508Z/review.json). Контрольний follow-up на 90 lines / ~1700 tokens пройшов з нульовим кешем і очікуваним словом «ГОТОВО».

**Наслідок для runtime — пропозиція:** до inference рахувати token budget для system/tools/memory/user/output, не допускати мовчазного видалення контрольних інструкцій; виносити дозволи у детерміністичний шар. У контекстному вікні 2048 не можна без перевірки подавати довгу історію. Див. [Q18](open-questions.md).

## Що далі

Модель залишити кандидатом. Наступний корисний крок — версійований UA/EN набір з quiet-mode reason checks, технічним grounding і multi-turn tools, а також контрольований тест context 4096/8192 з token-budget validation та VRAM snapshots. Це пропозиції, ще не виконані тести. Порівняння з Gemma, voice SLO, ASR/TTS, Jetson, robot і довготривала пам’ять залишаються відкритими.

Інтерактивний запуск на цьому комп’ютері:

```bash
/usr/local/bin/ollama run b12-bolt-e4b:q4km --think=false
```

Інтерактивний alias має temperature 1.0 за Modelfile, тому його відповіді можуть відрізнятись від deterministic-smoke режиму temperature 0. Повноцінної особистості чи пам’яті B-12 тут ще немає.
