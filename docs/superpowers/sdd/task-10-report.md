# Task 10 — Web UI

Coordinator/implementer: Claude Code (Claude Opus 5.5), 26.10.2026. BASE `9ce4c9d`, commit `6610f85`.

Files: `src/b12/web/{index.html,app.js,style.css}`; API additions `/` + `/static/{app.js,style.css}` (CSP `default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'`, nosniff, no-referrer), `GET /api/me`, `GET /api/sessions`.

Rulings: token у sessionStorage (лише ця вкладка), тільки заголовок; поточна сесія в localStorage. Увесь текст моделі/tools — textContent (тест забороняє innerHTML/insertAdjacentHTML/eval). Quiet mode та goals не показуються — з’являться разом із Task 11 (без фейкових контролів).

Evidence:
- pytest: 3 web tests (CSP/assets, /api/me + sessions, static safety scan). Full 385 passed / 2 skipped; Ruff clean.
- Claude-in-Chrome розширення не було підключене → headless Chrome 153 через CDP (`scripts/web_acceptance.mjs`, Node 22). Живий `b12 serve` + реальний Bolt, temp state. run1: 18/19 — єдиний FAIL був дефектом перевірки (картка з історії без статусу), а також помічено UI-ваду: результат після resume не прив’язувався до картки tool → виправлено (мапа карток за call_id на рівні сторінки). run2: 20/20 PASS: login gate, wrong token, token not in URL, 13 tools, health, реальний file_write/file_read (байти на диску «Вебтест 55»), streamed reply, history після reload, memory remember/search/forget → «Забуто повністю», approval у черзі → Дозволити → resume → memory видалена, resumed result на тій самій картці, cancel → «Скасовано.», consent toggle змінює стан сервера, 390px без горизонтального overflow, 0 console errors. Скриншоти (світла, темна, mobile) переглянуті вручну.
- Artifacts: `artifacts/task10-web-acceptance-2026-10-26/` (8 PNG, report.json, run1-report.json, SHA256SUMS).
Limits: немає SSE-reconnect після обриву мережі (показується стан «З’єднання завершилося без результату»); людська UX-оцінка не проводилась; одна вкладка = один токен.
