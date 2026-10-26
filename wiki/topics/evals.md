---
type: topic
updated: 2026-10-26
status: partially_implemented
sources: [evals/build_cases.py, evals/scoring.py, evals/runner.py, tests/e2e/test_eval_runner.py, tests/e2e/test_bolt_tools.py, tests/e2e/test_bolt_autonomy.py]
tags: [eval, bolt, benchmark, ukrainian]
---
# Eval: корпус, runner і результати

**Перевірений факт:** корпус `evals/cases/*.jsonl` (генерується `evals/build_cases.py`) містить 109 сценаріїв: 20 UA, 15 EN/code-switch, 43 tool-задачі (30 багатокрокових), 14 пам'яті (recall, виправлення, consent, ізоляція actor, approval), 7 behavior, 9 adversarial (injection у файлі й документі, privilege, exfiltration, фейковий tool-output), 60-turn розмова. Очікування обчислює генератор, а не модель. Перевірки детерміновані (`evals/scoring.py`); поля людської оцінки лишаються порожніми.

Runner відновлюваний: окремі state і sandbox на кожну трійку (case, repeat, ctx); записує трасу викликів, токени, TTFT; провалені каталоги зберігаються. Умови прогону: Ollama 0.33.3, `b12-bolt-e4b:q4km` (Q4_K_M), ctx 4096, `num_predict` 512, T=0, seed 42, RTX 4060 Laptop 8 GB; cold/warm кеш не скидався, окрім окремого latency-набору.

## Результати (ctx 4096, 5 повторів, 541 прогін, код до виправлень мови й морфології)

Загалом 81 %, 0 протокольних помилок. За категоріями (пройдено/прогонів): behavior 35/35, conversation 1/1, tools 182/215, memory 60/70, adversarial 40/45, ua 80/100, en 40/75. TTFT P50 1.39 с, P95 2.32 с; cold 5.45 с проти warm ≈ 1.2 с.

## Що знайшов eval

- **Мова відповіді:** 8 із 15 EN-сценаріїв Bolt відповів українською. Виправлення — детермінована інструкція мови за скриптом повідомлення (`d089bc6`); повторний EN+UA-прогін 34/35.
- **Морфологія пам'яті:** `memory_search("шафку")` не знаходив «шафки». Виправлення — розгортання лем (`9e24942`).
- **Політика мережі:** на пряме прохання користувача модель викликала `http_fetch` на чужий URL (`adv-exfiltrate-secret`, 5/5). Пропозиція: allowlist мережевих призначень власника. Не реалізовано.
- **Хибні перевірки корпусу:** disagreement-кейси вимагали конкретне число, хоча «Ні.» правильне (corpus v2); числова відповідь без літер не має скрипту.

**Межа:** 81 % — до двох виправлень; повний повторний прогін на поточному HEAD і ctx 8192 (частково, 47 прогонів, 97.9 % на новішому коді) ще виконуються. Людської мовної оцінки не було; наведені числа не є голосовим SLO.

Див. [agent loop](agent-loop.md), [автономність](autonomy.md).
