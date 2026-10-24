---
type: roadmap
updated: 2026-10-24
status: proposed
sources: [raw/B-12_Master_Project_2026-10-24.md, wiki/project/analysis.md]
tags: [milestones, acceptance]
---
# Дорожня карта й критерії переходу

Етапи M0–M6 походять з brief §12; критерії нижче конкретизовані в цьому аналізі. Календарні строки не призначені: немає перевіреного коду, host profile та обладнання. [Поточний стан](status.md).

| Етап | Робота | Доказ завершення | Залежності / стан |
|---|---|---|---|
| M0 — специфікація | Походження коду; Event/Observation/Action/Memory/Consent/Tool/Identity; permission/retention; telemetry/heartbeat | Узгоджені versioned contracts, негативні сценарії policy, відтворюваний software-only запуск, інструкція й логи | Документація частково; runtime не початий |
| M1 — текстове ядро | SQLite, retrieval, змінний LLM adapter, один tool, малий event loop та idle reflection | Дозволена подія згадується з evidence після restart; заборонена не зберігається; tool проходить policy; результати model A/B | [Перший Bolt smoke test](bolt-first-test.md) виконано; A/B та runtime ще не реалізовані; залежать від контрактів M0 |
| M2 — голос desktop | PTT, UA/EN ASR, streaming TTS, speaker verification baseline | Версійований corpus, WER, TTS оцінка, latency traces P50/P95 та повтори | Текстовий шлях M1; не почато |
| M3 — full-duplex | AEC render reference, endpoint, barge-in, consent/mute | 8h soak з ТБ/шумом/GPU load; виміряний time-to-stop; немає self-trigger loops; policy tests | M2; не почато |
| M4 — робот | Вибір платформи; Wireless transport proof за потреби; один writer рухів; reconnect | Media proof без LLM; bounded motion, stop/mute, контрольна згода; recovery при Wi-Fi loss | Доступне обладнання й стабільне аудіо; не почато |
| M5 — Jetson | Окремі й спільні model workloads, audio under load, degraded mode | Manifest конфігурації й raw traces unified memory/swap/TTFT/thermal/dropout; немає OOM або swap stalls у прийнятому сценарії | Персональний Jetson; частина profiling може передувати M4; не почато |
| M6 — тривала експлуатація | Recall, self-model, доречна ініціатива, review/forget, recovery | Recall через реальні 1/7/30 днів; 24–72h operation; quiet-mode та deletion evidence; журнал збоїв/виправлень | Попередні перевірки; не почато |

## Перший вертикальний зріз — пропозиція

Текстова симуляція без робота: контрольний сигнал дозволяє записати тестову подію; після перезапуску система пригадує її з ID доказу, пропонує продовження та виконує один дозволений інструмент. Той самий сценарій без згоди не залишає персонального durable payload. Кожний крок має результат і коротке пояснення.

Цей зріз перевіряє [архітектуру](../topics/architecture.md) та [пам’ять](../topics/memory.md) до витрат на акустику й механіку. Він не доводить природність голосу або довготривалі спогади.

## Як приймати результати

Для latency окремо звітувати фізичне завершення мовлення, endpoint decision, перші корисні токени й meaningful audio. Уточнити перцентиль цілі <1,5 с перед порівнянням; earcon не зараховується. Для кожного прогону вказувати host, revision, налаштування й обсяг вибірки. Mock доводить контракт, а не hardware performance. Прискорений replay не закриває реальний 30-day retention.

Рішення після етапу дописати до [реєстру](decisions.md), невирішені розриви — до [питань](open-questions.md), нові артефакти — до [індексу](../index.md) та [журналу](../log.md).
