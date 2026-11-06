---
type: source
updated: 2026-11-06
status: checked
sources: [raw/source-manifest.json]
tags: [nvidia, agent-evaluation, migration]
---
# NVIDIA agent frameworks: NeMo Agent Toolkit і Helix

## Походження та межі читання

Офіційні сторінки NVIDIA відкрито 2026-11-06. Локальну копію вебсторінок не збережено. Прочитано міграційну сторінку NeMo Agent Toolkit 1.9 (повідомлення про завершення підтримки й перелік наступників), документацію Helix Agent Evaluation (модель tasks/runners/trials/metrics, локальний запуск та оцінювання траєкторій), quickstart і огляд agentic metrics. Інші розділи продуктів не перевірялися.

- [NeMo Agent Toolkit migration guide](https://docs.nvidia.com/nemo/agent-toolkit/1.9/resources/migration-guide.html)
- [NeMo Helix Agent Evaluation](https://docs.nvidia.com/nemo-helix/documentation/evaluate-models/agent-eval/)
- [NeMo Helix Agent Evaluation Quickstart](https://docs.nvidia.com/nemo-helix/documentation/evaluate-models/agent-eval/quickstart/)
- [NeMo Helix Agentic Evaluation Metrics](https://docs.nvidia.com/nemo-helix/documentation/evaluate-models/metrics/agentic-metrics/)

## Перевірені зовнішні факти

**Перевірений факт:** міграційний посібник NVIDIA повідомляє, що NeMo Agent Toolkit deprecated з жовтня 2026 року та має досягти EOL до кінця 2026 року. Серед наступників NVIDIA називає Relay для observability/middleware/governance, Fabric для запуску agent harnesses і Helix для оцінювання, оптимізації та hardening.

**Перевірений факт:** Helix Agent Evaluation описує task-oriented модель `Task → Runner → Trial → Metrics → Result`. `Trial` може містити кінцеву відповідь, статус, докази траєкторії (ATIF чи OTLP), файловий стан, логи й metadata. Метрики можуть оцінювати як кінцеву відповідь, так і проміжні дії та вибір інструментів. Документація передбачає локальний in-process SDK запуск без Helix services.

## Висновок для B-12

**Пропозиція:** не додавати deprecated `nvidia-nat` до runtime B-12. Також не робити Helix SDK обов’язковою залежністю: B-12 — local-first і вже має task corpus, model runner, server-side tool журнал, model metrics та ізольований eval transport. Корисні властивості Helix — відокремлення task від runner і оцінювання траєкторії окремо від відповіді — застосовуються як критерії B-12 eval. Підключення Helix або Relay лишається окремою optional інтеграцією після перевірки сумісності та ліцензії.

Прочитання документації не доводить, що будь-який NVIDIA пакет встановлений, сумісний із B-12 або обраний для впровадження.
