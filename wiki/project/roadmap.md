---
type: roadmap
updated: 2026-11-04
status: in_progress
sources: [raw/B-12_Master_Project_2026-10-24.md, wiki/project/analysis.md, wiki/project/status.md, wiki/topics/operations.md, evals/voice/report.json, evals/voice/duplex/report.json, docs/audits/2026-11-02-b12-spec-compliance-audit.md]
tags: [milestones, acceptance]
---
# Дорожня карта й критерії переходу

Етапи M0–M6 походять з brief §12; критерії нижче конкретизовані в цьому аналізі. Стан оновлено 04.11 за Git, аудитами та наявними artifacts. Наявність коду і проходження програмних тестів не закривають фізичні gates. [Поточний стан](status.md), [execution path](implementation.md).

| Етап | Робота | Доказ завершення | Залежності / стан |
|---|---|---|---|
| M0 — специфікація | Походження коду; Event/Observation/Action/Memory/Consent/Tool/Identity; permission/retention; telemetry/heartbeat | Узгоджені versioned contracts, негативні сценарії policy, відтворюваний software-only запуск, інструкція й логи | Contracts, control/grants, purge hooks і telemetry є; Observation та audit schema розриви F-06/F-09 ще відкриті |
| M1 — текстове ядро | SQLite, retrieval, змінний LLM adapter, один tool, малий event loop та idle reflection | Дозволена подія згадується з evidence після restart; заборонена не зберігається; tool проходить policy; результати model A/B | Реалізовані agent, memory/retrieval, tools, CLI/API/Web/TUI та reflection; поточний великий eval, model A/B і людська оцінка ще потрібні |
| M2 — голос desktop | PTT, UA/EN ASR, streaming TTS, speaker verification baseline | Версійований corpus, WER, TTS оцінка, latency traces P50/P95 та повтори | Програмний стек є. Report 02.11 — synthetic TTS→ASR smoke, n=8: TTS TTFA P50 1634,61 / P95 2441,51 мс; ASR P50 2173,58 мс. Попередні 258,6 мс застаріли; фізичний end-to-end SLO ще не виміряно |
| M3 — full-duplex | AEC render reference, endpoint, barge-in, consent/mute | 8h soak з ТБ/шумом/GPU load; виміряний time-to-stop; немає self-trigger loops; policy tests | Live duplex і AEC synchronization є. Report 02.11: ERLE mean 30,41 дБ на simulated RIR (n=5), internal software stop P95 0,036 мс (n=10). Попередні 156,3 дБ замінено; ці метрики не вимірюють фізичне стихання динаміка. Фізичний soak відкритий |
| M4 — робот | Вибір платформи; Wireless transport proof за потреби; один writer рухів; reconnect | Media proof без LLM; bounded motion, stop/mute, контрольна згода; recovery при Wi-Fi loss | Motion controller і simulator є; speed/lease findings A-16/A-23 та фізичний transport ще відкриті |
| M5 — Jetson | Окремі й спільні model workloads, audio under load, degraded mode | Manifest конфігурації й raw traces unified memory/swap/TTFT/thermal/dropout; немає OOM або swap stalls у прийнятому сценарії | Персональний Jetson; частина profiling може передувати M4; не почато |
| M6 — тривала експлуатація | Recall, self-model, доречна ініціатива, review/forget, recovery | Recall через реальні 1/7/30 днів; 24–72h operation; quiet-mode та deletion evidence; журнал збоїв/виправлень | Перевірки реального state пройшли 1-day і 7-day рубежі; timer активний. 30-day gate 26.11, тривала автономність і безперервний soak відкриті |

## Перший вертикальний зріз — пропозиція

Текстова симуляція без робота: контрольний сигнал дозволяє записати тестову подію; після перезапуску система пригадує її з ID доказу, пропонує продовження та виконує один дозволений інструмент. Той самий сценарій без згоди не залишає персонального durable payload. Кожний крок має результат і коротке пояснення.

Цей зріз перевіряє [архітектуру](../topics/architecture.md) та [пам’ять](../topics/memory.md) до витрат на акустику й механіку. Він не доводить природність голосу або довготривалі спогади.

## Як приймати результати

Для latency окремо звітувати фізичне завершення мовлення, endpoint decision, перші корисні токени й meaningful audio. Уточнити перцентиль цілі <1,5 с перед порівнянням; earcon не зараховується. Для кожного прогону вказувати host, revision, налаштування й обсяг вибірки. Mock доводить контракт, а не hardware performance. Прискорений replay не закриває реальний 30-day retention.

Рішення після етапу дописати до [реєстру](decisions.md), невирішені розриви — до [питань](open-questions.md), нові артефакти — до [індексу](../index.md) та [журналу](../log.md).
