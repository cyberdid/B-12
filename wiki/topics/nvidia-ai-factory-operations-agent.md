---
type: topic
updated: 2026-11-07
status: compiled
sources: [wiki/sources/nvidia-ai-factory-operations-agent-2026-11-07.md, wiki/topics/architecture.md, wiki/topics/tool-control.md]
tags: [nvidia, agent-evaluation, cluster-ops]
---
# NVIDIA AI Factory Operations Agent: придатність для B-12

## Що це за проєкт

**Перевірений факт:** AI Factory Operations Agent (AFOA) — експериментальний Helm/Kubernetes blueprint для діагностики та контрольованих операцій у датацентровому AI-кластері. Він об’єднує OpenClaw/NemoClaw, OpenShell, кластерні tools і MCP/HTTP/CLI інтерфейси. Це окрема система розгортання, не фреймворк, який B-12 може під’єднати як звичайну бібліотеку. Межі огляду й джерела — у [картці](../sources/nvidia-ai-factory-operations-agent-2026-11-07.md).

## Що варте уваги

- **Поділ читання і змін:** окремі інструменти та Kubernetes identities для read/edit, із серверною валідацією перед викликом.
- **Гранулярне підтвердження:** Edit має operation approval; окремий Auto режим явно дозволяє обходити запит підтвердження після попередження. Автоматичні перевірки залишаються read-only.
- **Ізоляція і межі credentials:** загальний `exec` віднесений до OpenShell; SSH destination та identity задає оператор; MCP/browser клієнтам credentials кластера не видаються.
- **Обережність щодо read-only:** chart default reader кластерний і має широку видимість дозволених ресурсів. Для tenant належить вимкнути його та налаштувати scoped identity; межі namespace самі собою не ізолюють різних tenant-ів.

Ці прийоми зіставляються з B-12 server-owned grants і результатами tools у [контролі інструментів](tool-control.md), а не переносяться автоматично.

## Рішення щодо B-12

**Пропозиція:** без змін у runtime та без нової архітектурної залежності. У B-12 уже є host tools, grants, approval і окремий `unknown` outcome; AFOA додає Kubernetes/Helm/OpenShell/NGC deployment surface, не потрібний для локального компаньйона, TUI, голосу чи pet.

Якщо з’явиться конкретна потреба аналізувати зовнішній GPU/Slurm кластер, оцінити малу optional read-only інтеграцію через існуючий control path: мінімальний tool scope, окремі credentials, жодного прямого керування приводами чи аудіо з LLM. До такого use case нічого не інтегрувати. Виявлена відмінність у lifecycle для часткової мутації позначена як питання перевірки в [картці джерела](../sources/nvidia-ai-factory-operations-agent-2026-11-07.md#code-review-спостереження).
