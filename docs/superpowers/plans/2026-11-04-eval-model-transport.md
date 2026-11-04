# Isolated Eval Model Transport Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans for this already authorized Task 14 follow-up, with verification at each checkpoint.

**Goal:** Дати network-isolated eval доступ до pinned Ollama через private Unix socket із streaming і cancellation, не відкриваючи host network контейнеру.

**Tech Stack:** Existing Python 3.12/3.13 core dependencies: FastAPI, uvicorn, httpx; stdlib sockets; opt-in Docker integration test.

**Spec:** [Full system design](../specs/2026-10-24-b12-system-design.md), Task 14 [implementation plan](2026-10-24-b12-full-system.md), зокрема вимога справжніх test effects поза файлами власника.

**Scope:** Уточнення Task 14 авторизованого full-system plan. Host tools усередині майбутнього контейнера зберігають реальні ефекти. Цей checkpoint реалізує transport; Docker image/supervisor і real-Bolt eval — наступні gates, не результат цього checkpoint.

**Architecture:** `evals/ollama_broker.py` створює ASGI app і private Unix listener. Upstream URL фіксується supervisor, не HTTP-запитом. GET дозволені тільки `/api/version`, `/api/tags`, `/api/ps`; списки моделей фільтруються за pinned alias. POST `/api/show` і `/api/chat` вимагають pinned `model`; `/api/generate` допускає лише unload (`model`, `keep_alive=0`, `stream=false`). Query strings, інші routes/methods/models, надмірне чи некоректне JSON body відхиляються до upstream. Upstream redirect не виконується. Response передається потоком, client disconnect скасовує upstream як до headers, так і під час body. Payload не логується.

`evals/socket_bridge.py` запускається всередині контейнера і передає loopback TCP bytes у фіксований Unix socket; runtime B-12 використовує свій незмінений HTTP adapter. Namespace і mounts забезпечить Docker supervisor; сам bridge не є OS sandbox.

**Constraints:** Не виконувати inference або unload на host під час deterministic tests; локальний HTTP fixture замінює зовнішню модель. Не змінювати production state, model weights, original benchmark artifacts або відкладену runtime security policy. Unix listener 0600 у private directory, bounded requests/response і bounded shutdown. Невідомий чи недоступний upstream повертає fixed error без exception text.

### Task 1: Broker і Unix listener

Files: create `evals/ollama_broker.py`, `tests/integration/test_eval_model_transport.py`.

- [x] RED: real HTTP fixture та Unix transport перевіряють metadata filtering, pinned show, denial без upstream effect, body bound, streaming first chunk та disconnect before headers/during body. Перший запуск — 1 failure / 13 setup errors через відсутній broker module.
- [x] Implement `ModelBroker(path: Path, upstream_url: str, model: str)` context manager з FastAPI/uvicorn/httpx; Unix socket має private permissions і видаляється при close. Використати explicit upstream URL loopback-only та `trust_env=False`, `follow_redirects=False`.
- [x] GREEN: focused suite з Docker gate — 21 passed на Python 3.12 і 3.13.

### Task 2: Container-side TCP bridge

Files: create `evals/socket_bridge.py`; extend same integration tests.

- [x] RED: `SocketBridge(uds: Path, host='127.0.0.1', port=0)` передає справжній HTTP запит у broker; upstream stream і закриття з'єднання зберігаються. Тест був у початковому RED suite.
- [x] Implement bidirectional socket relay без HTTP rewrite, payload logs або вибору destination із запиту. Close зупиняє listener і active relays.
- [ ] GREEN: focused transport tests, `ruff check src tests evals`, full deterministic suite, diff check.

### Task 3: Evidence checkpoint

- [ ] Зберегти RED/GREEN, результат full suite і точні межі у wiki/log та eval topic; перевірити local links/index coverage.
- [ ] Commit transport/test changes окремо від documentation. Позначити Docker integrated runner і real-model run незавершеними.
