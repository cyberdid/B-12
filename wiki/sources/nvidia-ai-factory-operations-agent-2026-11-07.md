---
type: source
updated: 2026-11-07
status: checked
sources: [raw/source-manifest.json]
tags: [nvidia, agentic-ops, security]
---
# NVIDIA AI Factory Operations Agent

## Походження та межі огляду

URL надано власником: [NVIDIA/AI-Factory-Operations-Agent](https://github.com/NVIDIA/AI-Factory-Operations-Agent/). Огляд виконано 2026-11-07 для commit [`307afa7e485a334389b4f2c8c68128fbf84ff007`](https://github.com/NVIDIA/AI-Factory-Operations-Agent/tree/307afa7e485a334389b4f2c8c68128fbf84ff007), зафіксованого 2026-11-05. Локальний snapshot до `raw/` не зберігався; тимчасова копія коду в `/tmp` використовувалася лише для читання.

Прочитано README, `docs/security_model.md`, `docs/multitenancy.md`, `docs/installation.md`, chart values і Kubernetes/automation-guard policy, RBAC/secrets templates та mutation ledger. Це вибірковий аналіз статичних матеріалів: Helm chart не встановлювався, deployment і тести не запускалися, повний threat model та всі модулі не аудіювалися. Межі внесені до [`raw/source-manifest.json`](../../raw/source-manifest.json).

## Перевірені факти

- README позиціонує проєкт як експериментальний NVIDIA blueprint для операцій AI Factory: Kubernetes, Prometheus/VictoriaMetrics, Grafana, Slurm, опційний Base Command Manager (BCM) і sandboxed command execution. Це розгортання Helm/Kubernetes із NemoClaw/OpenClaw та OpenShell, а не легка Python/TS agent library. README також описує HTTP, CLI та MCP bridge. [README](https://github.com/NVIDIA/AI-Factory-Operations-Agent/blob/307afa7e485a334389b4f2c8c68128fbf84ff007/README.md)
- У README вказано experimental release та обмеження раннього доступу: опубліковані chart і images потребують запрошення до приватного NGC registry. Відкритий GitHub-код сам по собі не означає, що всі артефакти можна встановити без цього доступу. [README](https://github.com/NVIDIA/AI-Factory-Operations-Agent/blob/307afa7e485a334389b4f2c8c68128fbf84ff007/README.md), [SUPPORT](https://github.com/NVIDIA/AI-Factory-Operations-Agent/blob/307afa7e485a334389b4f2c8c68128fbf84ff007/SUPPORT.md)
- Chart default вмикає UI, execution, Kubernetes, observability, Grafana, BCM і Slurm; `modules.edit.enabled` вимкнено. Отже «edit вимкнено» не означає, що немає доступу до кластерних даних: read-only модулі активні. [values.yaml](https://github.com/NVIDIA/AI-Factory-Operations-Agent/blob/307afa7e485a334389b4f2c8c68128fbf84ff007/helm/mosaic-stack/values.yaml)
- Документована модель розділяє View/Edit/Auto. Edit вимкнений за замовчуванням; інтерактивні сесії стартують у View; автоматизовані сесії залишаються read-only. Edit вимагає operation approval за `hitl=true`; Auto обходить підтвердження після попередження, але RBAC і серверні validators продовжують діяти. [Security model](https://github.com/NVIDIA/AI-Factory-Operations-Agent/blob/307afa7e485a334389b4f2c8c68128fbf84ff007/docs/security_model.md)
- Код відокремлює `run_kubectl` від `run_kubectl_admin`: перший дозволяє обмежений набір read-команд і блокує Secrets, shell syntax та підміну credentials; другий додається лише при ввімкненому edit. RBAC для читання в chart охоплює кластерні ресурси з `get/list/watch`; документ прямо попереджає, що цей reader за замовчуванням cluster-wide. Для tenant-релізу його слід вимкнути й передати окрему scoped identity. [Kubernetes policy](https://github.com/NVIDIA/AI-Factory-Operations-Agent/blob/307afa7e485a334389b4f2c8c68128fbf84ff007/helm/mosaic-stack/files/openclaw-seed/extensions/kubernetes/policy.ts), [RBAC](https://github.com/NVIDIA/AI-Factory-Operations-Agent/blob/307afa7e485a334389b4f2c8c68128fbf84ff007/helm/mosaic-stack/templates/rbac.yaml), [multitenancy](https://github.com/NVIDIA/AI-Factory-Operations-Agent/blob/307afa7e485a334389b4f2c8c68128fbf84ff007/docs/multitenancy.md)
- Документація прямо зазначає, що read-only не є межею конфіденційності: вміст, дозволений ідентичності, доступний сесії. Загальні локальні команди ізолюються OpenShell; віддалений SSH має конфігуровані aliases та argv policy, але рівень читання визначають права самої SSH identity. [Security model](https://github.com/NVIDIA/AI-Factory-Operations-Agent/blob/307afa7e485a334389b4f2c8c68128fbf84ff007/docs/security_model.md)

## Code-review спостереження

**Перевірений факт:** `mutation-ledger.ts` має стани `running/completed/failed`; stale `running` після перезапуску перетворюється на `failed`. Kubernetes runner трактує exit code 0 як `completed`, будь-який інший як `failed`; повторний tool-call ID не запускається вдруге. [Mutation ledger](https://github.com/NVIDIA/AI-Factory-Operations-Agent/blob/307afa7e485a334389b4f2c8c68128fbf84ff007/helm/mosaic-stack/files/openclaw-seed/extensions/mutation-ledger.ts), [Kubernetes plugin](https://github.com/NVIDIA/AI-Factory-Operations-Agent/blob/307afa7e485a334389b4f2c8c68128fbf84ff007/helm/mosaic-stack/files/openclaw-seed/extensions/kubernetes/index.ts)

**Потребує перевірки — висновок зі статичного читання:** `failed` не розрізняє відмову до ефекту та часткову зміну, після якої команда повернула помилку або процес перезапустився. Це варто перевірити на мутаціях, що охоплюють кілька Kubernetes-ресурсів, перш ніж переймати цей lifecycle для B-12. У B-12 вже передбачено окремий `unknown` для можливо часткового ефекту; див. [контроль інструментів](../topics/tool-control.md).

## Висновок для B-12

**Пропозиція:** не переносити цей stack у B-12 і не вважати його заміною NeMo Agent Toolkit. Це окремий deployment blueprint для кластерних операторів, тоді як B-12 — local-first компаньйон із контрольованими host tools та фізичною/голосовою дорожньою картою.

Корисні для зіставлення інженерні прийоми: розділені read/write tools та credentials, server-side policy до виконання, approval точного виклику, ізоляція загальних команд і аудит. Для можливого майбутнього запиту до зовнішнього Kubernetes/Slurm-кластера розглядати лише окрему optional read-only інтеграцію через чинний B-12 control path; спочатку визначити use case, data scope, credential boundary та перевірки. Це огляд і пропозиція, не рішення про інтеграцію. Детальніше — [аналіз придатності](../topics/nvidia-ai-factory-operations-agent.md).
