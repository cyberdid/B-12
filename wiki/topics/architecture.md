---
type: topic
updated: 2026-10-24
status: proposed
sources: [raw/B-12_Master_Project_2026-10-24.md]
tags: [architecture, runtime]
---
# Архітектура runtime

**Пропозиція з brief §4; реалізації тут немає.**

```text
Audio / Camera / Tools / Control
             ↓ typed observations
       Event bus / World state
           ↙             ↘
 System 1               System 2 ← Memory / Goals
 audio, interrupt,      LLM interpretation,
 motor limits           planning, reflection
           ↘             ↙ proposals
        Deterministic action policy
                 ↓
         Motion writer / TTS / Tools
                 ↓ outcomes
        Policy-filtered durable memory
```

System 1 виконує barge-in, mute, обмеження приводів і короткі реакції без очікування LLM. System 2 запускається на змістовних подіях та активних цілях. Повільне міркування не повинне затримувати interrupt або створювати другий writer рухів.

**Контракти до реалізації:**

| Контракт | Що треба визначити |
|---|---|
| Event | ID, UTC, тип, походження, schema version, evidence IDs |
| Observation | Сенсорний зміст, впевненість, TTL та допустимий строк зберігання |
| Action | Намір, аргументи, ціль, строк дії, cancellation ID |
| Memory | Зміст, джерела, підстави збереження, видимість і життєвий цикл |
| Consent | Суб’єкт, область дозволу, контрольне джерело, строк, відкликання |
| Tool | Типізовані входи/виходи, права, timeout, обмеження, результат |
| Identity | Сесійний чи постійний ID, confidence; окремо від прав доступу |

Додаткові поля таблиці — пропозиції цього аналізу для M0, не готові схеми. Перевірка прав відбувається перед ефектом; текст моделі не змінює consent. Сенсорний потік і довготривале сховище мають різні політики, див. [пам’ять](memory.md).

Модель, транспорт і корпус змінюються через адаптери. Вибір процесів/IPC/фреймворку ще відкритий: для першого PoC не потрібні всі каталоги зі структури §13 brief. [Голос](voice.md), [автономність](autonomy.md) і [обладнання](hardware.md) описують окремі обмеження. Статуси принципів — у [реєстрі рішень](../project/decisions.md).

Для retrieval реалізовано [pinned actor-scoped lexical adapter](archive-retrieval.md); context builder рахує повний запит до pinned Bolt profile. Це не підключає приватний глобальний архів, semantic embedding або MCP.

Server-owned grant/control і typed tool outcome реалізовані окремим етапом; межі approval, unknown outcome та Task6 host-tool контракт зібрані у [сторінці tool control](tool-control.md). API authentication і реальні host handlers лишаються наступними етапами.
