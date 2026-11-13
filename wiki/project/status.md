---
type: status
updated: 2026-11-13
status: active
sources: [wiki/sources/master-brief.md, wiki/project/analysis.md, wiki/topics/operations.md, wiki/topics/evals.md, wiki/project/requirements-audit.md, wiki/sources/capri-desktop-companions-2026-11-07.md, wiki/sources/agent-hooks-2026-11-08.md, wiki/sources/gemma12b-desktop-launch-2026-11-09.md, wiki/sources/gemma12b-followup-2026-11-09.md, wiki/sources/capri-academic-formatting-2026-11-09.md, wiki/sources/capri-scientific-revision-2026-11-09.md, src/b12/agent.py, src/b12/persona.py, src/b12/api.py, src/b12/reflection.py, src/b12/tools/network.py, wiki/sources/nvidia-agent-frameworks-2026-11-06.md, wiki/sources/claude-password-policy-baseline-2026-11-04.md, wiki/project/desktop-companion-plan.md, wiki/topics/desktop-companion.md, wiki/sources/capri-personality-review-2026-11-08.md, wiki/sources/scribe-paper-2026-11-08.md, wiki/project/decisions.md, docs/superpowers/specs/2026-11-08-b12-capri-compact-actions-design.md, docs/superpowers/specs/2026-11-08-b12-capri-feature-parity-design.md, docs/superpowers/plans/2026-11-08-b12-capri-feature-parity.md, docs/superpowers/specs/2026-11-08-capri-persona-brand-design.md, docs/superpowers/plans/2026-11-08-capri-persona-brand.md, src/b12/desktop/actions.py, src/b12/desktop/activity.py, src/b12/desktop/hooks.py, src/b12/desktop/integrations.py, src/b12/desktop/local_features.py, src/b12/desktop/profile.py, src/b12/desktop/presentation.py, src/b12/desktop/client.py, src/b12/desktop/app.py, src/b12/desktop/chat.py, src/b12/desktop/cat.py, wiki/sources/nvidia-ai-factory-operations-agent-2026-11-07.md, wiki/topics/nvidia-ai-factory-operations-agent.md]
tags: [progress, next]
---
# Стан проєкту

На початку імпорту 24.10.2026 `/home/cyberdid/Projects/B-12` була порожньою текою без Git. Дослідницький baseline збережено commit `78daaef`. На початок аудиту 04.11 `main`, `feat/b12-runtime` та обидва remote refs збігалися на `fbe9e223`; `feat/b12-access` був предком на 8 комітів позаду. Подальший локальний fix `baed10d` виправляє pytest entrypoint. Датовані зрізи внизу сторінки зберігають історію.

## Поточний стан (2026-11-04)

- **Перевірений факт:** на точному `HEAD fbe9e223` повний suite через `uv run --no-sync python -m pytest -q` дав 592 passed / 3 skipped; `uv run --no-sync ruff check src tests` пройшов.
- **Перевірений факт:** R17 7-day checkpoint пройдено. `b12-daily-check.service` завершив перевірку 04.11.2026 11:46 EET на віці 8,091 дня: `ok=true`, SQLite та snapshots цілісні, забутий маркер відсутній у пошуку й байтах, pending purges — 0, перевірено 80 audit events. Доказ і межі — у [operations](../topics/operations.md#довгий-горизонт-task-19).
- **Перевірений факт:** кодова частина голосу, live full-duplex та AEC synchronization є; фізична акустична перевірка лишається відкритою. Реального Reachy/Jetson acceptance немає. 30-day checkpoint R17 очікується 26.11.2026.
- **Перевірений факт:** CLI використовує один runtime через `RuntimeLock`; global purge має hooks для керованих stores; документальні докази проходять через schema v2. Подальші зміни та їхні обмеження — у [журналі](../log.md) від 03.11.
- **Потребує перевірки:** останній повний Bolt eval у wiki — на `60a4c0b` від 27.10, не на поточному `HEAD`. Локальний 43-run artifact у старому worktree прив'язаний до `c294aff` і не є свідченням якості поточного коду; див. [evals](../topics/evals.md#актуальність-станом-на-2026-11-04).
- **Відкрито:** власник окремо відклав security findings A-01, A-07, A-08, A-18, A-19, A-22 та F-03; їх не слід трактувати як виправлені. Також лишаються безперервний 8-hour soak із перевіркою RSS, людська UA/EN оцінка, фізичний R15 soak і R16 hardware acceptance.
- **Перевірений факт:** fix `baed10d` додає корінь репозиторію до pytest `pythonpath`. Console entrypoint `uv run --no-sync pytest -q` тепер проходить: 592 passed / 3 skipped за 193,99 с; початкові два collection errors більше не відтворюються.
- **Перевірений факт:** `f61f9ba` синхронізує voice extra у lockfile; `069bbd5` виправляє corpus checks для актуальних command tools. Чисті locked environments з `dev+tui+voice` пройшли 598 passed / 3 skipped: Python 3.12.3 — 188,52 с; Python 3.13.14 — 189,80 с. Corpus v4 та Docker probe описані в [evals](../topics/evals.md#корпус-v4-та-відтворюване-середовище-2026-11-04); інтегрований ізольований runner ще потрібний.

## Оновлення 08.11.2026 — TUI Companion Upgrade

**Вимога власника:** реалізовувати ідеї Capri-подібних компаньйонів у наявному TUI; лишити Кіберкота стандартним і зробити зовнішній Capri skin опційним. Інша desktop UI не входить у scope.

**Поточна робота:** реалізацію зафіксовано у commits `0947f2e` та `cb5db3c` на branch `feat/b12-cybercat-tui` і локально інтегровано в `main` merge commit `72a06d6`; remote не оновлювався. Є local activity SQLite і provider hook adapter, TUI timeline/reports, явні PTT/mute/TTS контроли та зовнішній manifest skin loader. Hook приклади — лише project-local templates; вони не внесені в жодні налаштування, не активовані. Static review defects (Escape у paused approval, скасування mute preflight, fallback зі зниклого skin та гонка скасування approval) виправлено.

**Межі доказу:** зміни локально злиті в основну гілку, але не опубліковані. У цій сесії не запускаються tests, TUI/server, мікрофон, гучномовець або модель. Проводиться статична перевірка конфігів, Python/shell синтаксису, diff та wiki-посилань. Доступні локальні `uv` і audio executables, тому залежності не встановлювалися. Оригінальний Capri artwork не додається: огляд джерел не підтвердив права на ці зображення; потрібен власний/ліцензований pack, див. [Q19](open-questions.md) і [формат skin](../../src/b12/tui/assets/skins/README.md).

Детальний scope, інтерфейси та межі приймання: [специфікація](../../docs/superpowers/specs/2026-11-08-b12-tui-companion-upgrade-design.md), [план](../../docs/superpowers/plans/2026-11-08-b12-tui-companion-upgrade.md), [тема TUI](../topics/cyberpunk-tui.md).

## Наявне

- Незмінений [master brief](../../raw/B-12_Master_Project_2026-10-24.md), SHA-256 і маніфест 116 зовнішніх URL.
- [Тематична wiki](../index.md), [аналіз](analysis.md), [кандидати рішень](decisions.md), [питання](open-questions.md), [дорожня карта](roadmap.md).
- [Постійні правила агента](../../AGENTS.md) за запитаним LLM Wiki workflow.
- Вибіркова [незалежна перевірка](../sources/external-checks.md) NVIDIA Research та README; решта матеріалів мають явну межу достовірності.
- [Аудит локальної системи](../sources/system-audit-2026-10-24.md): RTX 4060 Laptop 8GB, i9-14900HX, 32GB RAM; CUDA й Ollama server 0.33.3 доступні. Є окремий store з Gemma E2B/E4B, ще не інтегрованими в B-12.
- [Перший smoke test Bolt](bolt-first-test.md): SHA-256 перевірено; alias `b12-bolt-e4b:q4km`, context 2048; 26 запитів, з них 3 overflow timing observations виключені. Warm decode ~62–64 tok/s; є поведінкові недоліки. Пізніше truncation risk закрито лише для pinned profile, див. наступний пункт; модель лишається кандидатом.
- [Review archive-index-public](../sources/archive-index-public.md): 16 source files за pinned commit, 17 core tests passed; synthetic lexical/provenance і cache-refresh probe виконані без production DB/embedding load. Pinned lexical modules тепер інтегровані через actor-scoped derived index; приватний production archive не імпортовано.
- [Model transport](../topics/model-transport.md): Task 4 reviewed; run4 — 15/15 реальних запитів до локального Bolt alias із exact prompt counts на сценаріях до 3928 токенів. Це перевірка pinned профілю, не універсального truncation proof чи голосового SLO. Model profile залишається explicit, alias default context — 2048.
- [Agent loop](../topics/agent-loop.md): Task 7 model→tools→results, events, sessions/provenance, PurgeCoordinator; real Bolt run2/run3 без protocol failures.
- [Tool control](../topics/tool-control.md): Tasks 5–6 перевірені; API authentication і global purge реалізовані. Security межі та відкладені знахідки описані в [самоогляді](security-self-review.md) й аудитах.

## Не підтверджено

Старий SQLite kernel і його попередні latency results не знайдені; це не стосується нового Task 2 MemoryStore. Потрібні фізичне R15 випробування з мікрофоном/динаміком, R16 наявне обладнання, оцінювання української якості людиною, поточний великий model/tool eval і тривала безперервна автономна перевірка. Окремі ранні дослідження voice з brief не мають оригіналів у `raw/`.

## Історичний snapshot: 2026-10-26

**Доручення власника:** реалізувати повноцінну систему з великим планом, звичайними/великими тестами, tools і повним host access. [Implementation/spec/ledger](implementation.md) задають поточний execution path; повторний дозвіл на старт не потрібний. **Перевірений факт:** Tasks 1–7 реалізовані; Task 7 `740629a`, full suite 350 passed / 2 skipped, Ruff clean; реальний Bolt виконує file write/read, system_info і memory recall після restart (3/3 у run2/run3). Task 8 owner CLI `964709b` (361 passed / 2 skipped; живий запуск із реальним Bolt). Task 9 API/auth `9632cdc` (382 passed / 2 skipped). Task 10 Web UI `6610f85` (headless Chrome acceptance 20/20, реальний Bolt). Task 11 автономність `6032a15`. **Пауза 26.10.2026 ~15:35 UTC за рішенням власника.** Tasks 12 (MCP і semantic через archive-index власника) і 13 (snapshots, deletion replay, restore, user unit — встановлює власник) завершено. Task 14: ctx4096 541 прогін, 81%, 0 протокольних помилок (до виправлень мови й морфології); ctx8192 частковий. Task 15: soak лише 1 год 19 хв (НЕ 8 год); виправлено дві лінійні деградації; ріст RSS ще відкритий. Tasks 16–17 відкладено власником. Task 18 — лише протокол на симуляторі; Task 19 — лише драйвер. Порядок продовження й деталі — у [звіті паузи](../../docs/superpowers/sdd/task-12-15-18-19-report.md). Full suite 450 passed / 3 skipped. Global purge hooks, API authentication, voice, robotics і тривалі acceptance також попереду. Власник відновив роботу 25.10 після явної паузи. Ціль active і не обмежена попередніми smoke tests. Наступні абзаци зберігають дослідницький baseline.

**M0 — частково:** versioned contracts, canonical memory/revocation primitives, server-owned owner/guest control та grant/approval lifecycle є. System heartbeat і retention/global-purge coordinators ще потрібні. Для M1 є memory, lexical retrieval, pinned Bolt transport і strict tool policy/registry, реальні host handlers; agent/session loop, idle reflection та A/B ще немає. M2–M6 не початі.

**Початковий Bolt smoke test:** зберігається як історичний baseline у [своєму звіті](bolt-first-test.md); його truncation на 2048 був підставою створити явний admission adapter. Новий run4 вимірює інший pinned renderer і чітко вказаний context 4096. Модель іще кандидат: Ukrainian quality corpus, tool performance, A/B і голосовий SLO залишаються відкритими.

**Уточнення після наданого репозиторію:** pinned lexical adapter в окремих actor stores ідентифікує evidence UUID/revisions, а context adapter admission-check-ить його. [Поточний код і межі](../topics/archive-retrieval.md). Cross-store resolver та purge coordinator ще потребують agent/control integration; приватний архів не імпортовано.

Походження старого kernel залишається відкритим. Його пошук та Event/Memory/Consent contracts можна продовжити після першого model test. Q15 про характеристики host закрито в межах read-only аудиту; див. [питання](open-questions.md).

**Стан на 27.10.2026 20:40 EET (злитий код `60a4c0b`, `main` == `feat/b12-runtime`):** Tasks 1–15 виконано, 16–17 відкладено рішенням власника, 18 — лише протокол на симуляторі, 19 — день 0 записано 27.10 о 09:34, 20 — [аудит](requirements-audit.md) складено. Виконано R01–R08, R11, R14 (10 із 17; R14 з межами), частково R09, R10, R12, R13, відкрито R15–R17. **Перевірений факт:** 467 тестів пройшло (3 пропущено — реальна модель вмикається явно); eval 91,7 % (ctx 4096) і 93,6 % (ctx 8192), див. [evals](../topics/evals.md); soak 8,007 год активного часу, не безперервно, див. [operations](../topics/operations.md). Відкриті рішення власника: мережевий allowlist `http_fetch`, sudoers для `sudo_exec`, установка systemd-сервісу й щоденного таймера, ліцензія. Незалежного рецензента для Tasks 7–19 не буде (рішення власника 27.10.2026).

**Стан на 31.10.2026 (функціональне підсилення ядра та перевірка R17):**
- **Перевірений факт:** у `src/b12/` посилено функціональність режиму «Не зупинятися» (`persist`): покриття `_track_files` тепер враховує файли й підкаталоги, опрацьовані через `run_command`, `shell_exec` та `file_search`; детектор текстових псевдо-викликів охоплює всі 15 вбудованих інструментів; відновлення ходу через `Agent.resume()` зберігає 30-хвилинний дедлайн для `persist`-ходів (так само в CLI та TUI); `run_command` автоматично підставляє дефолтні `cwd` і `declared_effects`, якщо мала модель їх пропускає; `file_search` підтримує передачу шляху до окремого файла (не лише каталогу) і читає до 256 КіБ на файл; у `MemoryStore.search` та `Agent._recall` збережено українські апострофи при токенізації/морфології (`ім'я` ↔ `імені`, `комп'ютер` ↔ `комп'ютера`) і додано фільтрацію розмовних стоп-слів для запитів природною мовою; у `BridgeEmbedder.close()` закрито витік транспорту subprocess (`0 warnings` у `pytest`).
- **Перевірений факт (R17 і сервіс):** виконано `scripts/daily_check.py check --out ~/.local/state/b12/long_horizon` на 4,389 доби після закладання якоря (поріг 1 дня пройдено): усі 3 якорі знаходяться, забутий якір відсутній у пошуку й у кожному байті `state_dir`, цілісність усіх SQLite та знімків `ok: true`, перевірено 80 подій аудиту. Встановлено юніти `b12.service`, `b12-daily-check.service` та увімкнено щоденний таймер `b12-daily-check.timer` (`systemctl --user enable --now b12-daily-check.timer`, перевірено `status=0/SUCCESS`). Додано кореневий файл `LICENSE` (Apache-2.0). Попереду точки 7 і 30 днів.
- **Перевірений факт (тести):** повний набір `554 passed, 3 skipped, 0 warnings`.
- **Перевірений факт (голос, Tasks 16–17 / R15 та рев'ю 02.11.2026):** реалізовано та модернізовано повний локальний голосовий шар у `src/b12/audio/` (`capture.py`, `endpoint.py`, `asr.py`, `tts.py`, `aec.py`, `speaker.py`, `pipeline.py`, `duplex.py`), підключено CLI (`b12 voice {status,mute,unmute,say,listen}`), HTTP API (`/api/voice/{status,mute,tts,asr,speaker/*}`) та Web UI (`🎙 Голос`, `Mute мікр.`, `Озвучувати`). Усунено всі функціональні дефекти з рев'ю `B-12_Voice_Stack_Review_2026-11-01.md` (`V-001`..`V-011`) та інтегровано найкращі інженерні практики з `NVIDIA-AI-IOT/reachy-mini-jetson-assistant`: конкурентні `asyncio.Task` у `DuplexSession.speak_response()` без дедлоку черги й із негайним стартом першої фрази (`V-001`), одноразовий AEC-прохід зі збереженням `BargeInResult.cleaned_audio` (`V-002`), усунення подвійного виклику Whisper ASR у дуплексі (`V-003`), 3-ступеневий конвеєр стрімінгу `LLM → extract_stream_clauses → TTS → AudioPlayer` (`V-004`), ізольоване скасування лише активного голосового ходу при barge-in (`V-005`), збереження стану LSTM у `SileroVad` без пофреймового `reset()` та без штучного RMS-бустингу в продакшені (`V-006`, `V-007`), справжній 128-таповий FIR NLMS AEC із FFT-вирівнюванням затримки, детекцією double-talk та системним `PulseAudioWebRtcAec` (`V-008`, `V-009`), почанковий неблокуючий запис у `AudioPlayer` із хуками руху `on_playback_start`/`on_playback_end` (`V-010`), збереження коротких 1–2-слівних відповідей у `is_tts_echo_text` (`V-011`) та перехід на espeak-модель `uk_UA-mykyta-high.onnx` за замовчуванням. У `evals/voice/report.json` отримано **нульовий WER (`uk_mean_wer: 0.0`, `en_mean_wer: 0.0`)** по всіх 8 UA/EN/code-switching фразах, endpoint P50 `320,0 мс`, ASR CPU int8 P50 `2173,58 мс`; у `evals/voice/duplex/report.json` — AEC ERLE `30,41 дБ` на багатопроменевому RIR із шумом, barge-in `time_to_stop` P50 `0,025 мс` / P95 `0,036 мс` на реальному TTS через ONNX Silero VAD, speaker FAR/FRR `0,0 / 0,0`, exact-replay атака блокується. Відкритою межею для повного закриття R15 лишається 8-годинний фізичний акустичний soak у кімнаті з ТБ/шумом.

При наступній сесії починати з цього стану, оновлювати його лише за новими доказами та дописувати [журнал](../log.md).

## Оновлення 10.11.2026 — комплексна оцінка Capri

- **Перевірений факт:** програма оцінки (92 сценарії, групи A–K) виконана. Підсумок після повного прогону, live-перевірок F/I і Track 1 для LT-02/JOURNEY-04: 27 пройдено, 53 провалено, 12 заблоковано обладнанням, 0 — часом; пасовий показник 33,8% (27/80, 95% ДІ 24,3–44,6%). Попередні 29/49 (37,2%) знято. Деталі: [capri-comprehensive-evaluation.md](capri-comprehensive-evaluation.md).
- **Перевірений факт:** виправлено порожній PASS у раннері (сценарій без ходів тепер FAIL), тести писали в реальні `artifacts/`, RQ2 і розділи A1–A4 звіту приведено у відповідність до артефактів. Тести: 135/135.
- **Перевірений факт:** LT-02 і JOURNEY-04 виконано за Track 1 (синтетичне зміщення часу, `b12-bolt-e4b:q4km`, 3 запуски): LT-02 PASS 3/3 (повтор на вільному GPU); JOURNEY-04 FAIL — Neovim 0/3, близькість 0,680 нижче семантичного порогу 0,7 (зміна порогу — рішення власника). LT-02 у реальному часі: якір 10.11 21:14 UTC, екзамен з 17.11. Track 2 (реальні дні) веде таймер R17; День 30 — 26.11.2026.
- **Перевірений факт:** таймер `b12-daily-check` полагоджено 10.11.2026 з дозволу власника: `~/.config/b12/env` узгоджено з `config.toml` (gemma4:12b), копія `env.before-gemma-align-20261110`; запуск через systemd — 14,54 дня, `ok=true`.
- **Відкрито:** голос і робот — `BLOCKED_HARDWARE`.
- **Відкрито:** розбіжність RE-01 (базовий прогін PASS, A4 FULL FAIL) не пояснена.
- **Перевірений факт:** `tests/test_m3_gate_challenger2.py` (28/28) включено в коміт `010beb5`.

## Оновлення 11.11.2026 — звіт про роботу

- **Перевірений факт:** таймер `b12-daily-check` після виправлення відпрацював сам: запуск 00:03 11.11 за Києвом, `ok=true`.
- **Спростовано/замінено:** запис вище про непояснену розбіжність RE-01 застарів. Старий PASS не відтворився: п'ять повторних запусків дали FAIL, і його знято в повному перезапуску.
- Підсумок робіт 10–11.11: [work-report-2026-11-11.md](work-report-2026-11-11.md).

## Оновлення 12.11.2026 — оцінка через рантайм Capri

- **Спростовано/замінено:** підсумок 27/80 (33,8%) і «витік MEM-05» — артефакт стенда, який обходив рантайм. Через `Agent.turn` у пісочниці: 39 пройдено, 41 провалено, 12 заблоковано; 48,8% (39/80, 95% ДІ 38,1–59,5%). Деталі: [capri-comprehensive-evaluation.md](capri-comprehensive-evaluation.md).
- **Перевірений факт:** виправлено в B-12 — роль співрозмовника в системному промпті та жодного шляху домашньої теки для гостя; чистий вихід `b12 serve` за SIGTERM; зупинка власника скасовує фоновий хід; резерв `min_free_mb` для записів пам'яті. Тести: репозиторій і оцінка проходять повністю.
- **Перевірений факт:** `scripts/setup-bolt.sh` готує модель і токенізатор за закріпленими ревізіями зі звіркою SHA-256; `--verify-only` на наявному розгортанні пройшов. Свіжий клон: `uv sync`, `b12 doctor`, `b12 init`, хід розмови — працюють.
- **Відкрито:** JOURNEY-04 (пошук), AUT-09 і REL-08 (рішення власника), H і J (обладнання).

## Оновлення 12.11.2026 (друга хвиля) — виправлення за розміткою провалів

- **Перевірений факт:** фінальний прогін через рантайм — 47 пройдено, 33 провалено, 12 заблоковано; 58,8% (47/80). Робоча конфігурація (gemma4:12b із семантичним пошуком) — теж 47/80. Попередній підсумок 39/80 замінено.
- **Перевірений факт:** знайдено й виправлено дірку безпеки: у режимі повного доступу `run_command` надсилав дані `curl` без підтвердження в обхід `network_allow`. Тепер мережеві команди чекають підтвердження власника; `sudo`/`su`/`doas`/`pkexec` поза `sudo_exec` заборонено.
- **Перевірений факт:** реалізовано пріоритети цілей (AUT-09), відносні шляхи для читання, виконання виклику, написаного як уся відповідь, вподобання в контексті. Тести: 719 passed, 4 skipped; оцінка 135 passed.
- **Відкрито:** JOURNEY-04, багатоденні сценарії, заміна фактів, H і J (обладнання). PR #2 оновлюється злиттям `main`.

## Поточний запит власника (2026-11-08) — повна Capri-функціональність

- **Перевірений факт:** актуальний `mochiiwuff/capri-desktop` main лишається на `cb33e87dfaee79cec8b4b0f737ca89e07b87ba4b`; повний README/code audit показав, що попередня B-12 зміна реалізувала лише компактний чат, ручні нагадування, prompt/site shortcuts, launchers і chat handoff. Детальна capability matrix — у [джерельній картці](../sources/capri-desktop-companions-2026-11-07.md).
- **Вимога власника:** «з цього репозиторію все забрати». За [ADR-012](decisions.md#adr-012--функціональна-сумісність-capri-desktop) треба пройти весь feature inventory і впровадити сумісні можливості у native Qt B-12, а не називати попередній subset повним портом.
- **Поточний стан:** у worktree `feat/b12-desktop-companion` додано opt-in hooks/activity journal для трьох coding agents, звіти, profile/interaction settings, UA/EN нагадування з підтвердженням, local file/system/media panel, guide/autostart, auto-sleep і необов’язкове слідування між дисплеями. Це незалежна реалізація частини сумісних можливостей, не весь Capri Desktop. Ruff, format, compileall, JSON і whitespace static checks пройшли; automated tests та Qt smoke не запускали.
- **Не виконували:** не встановлювали hooks у реальні конфіги, не запускали host-команди/програми, Qt-клієнт, API/model, voice/audio або GPU; функції, що потребують цих дій, іще не мають host acceptance.
- **Межі:** переноситься поведінка власним кодом, не upstream files/art. На Linux/X11 немає Windows-only window APIs; B-12 текстовий chat поки не має image input. Hooks, PC telemetry і capture мають бути opt-in; capture вимагає vision-capable transport; системні команди лишаються за B-12 grants/approval. Feature без коду або host evidence не позначати реалізованою.
- **Вимога власника:** перейменувати видимого компаньйона на Capri та додати придатні стильові/поведінкові складники з досліджених проєктів. **Код додано локально:** базова оригінальна persona підключена до спільного Agent; локальний desktop profile іде як обмежений style-only context через `/api/chat`; desktop/TUI/Web/CLI/API title узгоджені. Reflection prompt також називає Capri.
- **Сумісність:** назви Python package, `b12` CLI/API path, env/state paths, hook markers і `QSettings("B-12", "NeonCompanion")` лишилися внутрішніми контрактами; це зафіксовано в [ADR-013](decisions.md#adr-013--ідентичність-capri-та-сумісність-runtime). Upstream prompt/діалоги не копіювалися.
- **Приватність і перевірка:** desktop profile поля передаються вибраному model provider у prompt; із локальною моделлю лишаються локально, із хмарною — надсилаються provider. Не потрапляють у transcript/long-term memory/activity log. Код і docs оновлено; далі виконуються лише статичні перевірки, persona human eval та host acceptance не проводились.
- **Оновлення особистості Capri (08.11.2026):** власник затвердив повне самоназвання Capri та самостійно сформульований характер: допитливий, дотепний, пустотливий, з іронією, власними поглядами й уважною турботою. Спільний prompt оновлено; Ruff, format, compileall, JSON, whitespace та нові локальні посилання перевірені; загальний scan виявив одну історичну відсутню artifact-ціль у попередньому записі журналу. Людська оцінка на цільовій моделі ще не проводилась. Evidence й фанатські межі — у [картці persona review](../sources/capri-personality-review-2026-11-08.md), рішення — в [ADR-014](decisions.md#adr-014--імерсивне-самосприйняття-capri-та-чесність-про-межі).
- **Перезапуск після оновлення persona:** API та Qt-клієнт підняті з /home/cyberdid/.codex/worktrees/cb2c/B-12. API health=true, active turns=0, pending approvals=0; X11 показує вікно Capri · CAPRI 300×410. Ollama/model, voice/audio та GPU не запускалися.
- **Уточнення власника за скриншотом (2026-11-08):** compact chat повертав `HTTP 422`, бо desktop передавав локальне `history_opt_in` у строгий API `companion_profile`. Клієнт тепер відправляє тільки дозволені поля стилю. Capri animations переведені з повторення одного atlas loop/статичних поз на окремий presentation controller з chat reactions, ручним меню жестів і процедурними Qt FX. Перевірено статично, відрендерено representative actions і перезапущено лише Qt-клієнт; X11 показує overlay 300×410, API health — `true`. Живий model turn для повторної перевірки 422 не надсилали.

## Поточний стан (2026-11-08)

- **Перевірений факт:** desktop-функцію реалізовано у `feat/b12-desktop-companion`, що наразі стоїть поверх `feat/b12-runtime` на `3e7fb07`; merge-base обох із `main` — `5f6ba90`. Runtime зміни вже входять у відкритий PR #1, тому desktop PR потрібно базувати на `feat/b12-runtime` до злиття PR #1. README, desktop guide і план описують окрему optional Qt оболонку: Capri як початковий вигляд за наявності локального паку, а вбудований Кіберкіт — як опційний вигляд; також tray, sessions/chat/history, streamed turns, exact approval, memory/consent і voice mute/status.
- **Перевірений факт:** [Desktop PR #2](https://github.com/cyberdid/B-12/pull/2) відкритий, mergeable і базується на `feat/b12-runtime`; після злиття PR #1 його слід retarget на `main`. PR #2 не злитий.
- **Перевірений факт:** після втрати потоку відомого turn клієнт зберігає lock, пропонує cancel і звіряє точний стан через owner-scoped `GET /api/turns/{id}/status`. Запит має перевірку власника; тільки `active=false` розблоковує composer і запускає reload історії. Подробиці — у [темі](../topics/desktop-companion.md) та [архітектурному огляді API](../topics/cli-server-mode.md).
- **Перевірений факт:** після recovery/visual regression fixes повний locked suite — 742 passed / 4 skipped за 151,69 с. Фінальні Ruff, lock check, `git diff --check`, sdist/wheel build і склад wheel наведені у фінальному записі [журналу](../log.md).
- **Перевірений факт:** окремий host smoke запустив лише desktop-клієнт на X11 з ізольованими `XDG_CONFIG_HOME`/`B12_STATE_DIR`, фіктивним токеном і тестовою адресою без API listener. X.Org 21.1.11 відобразив вікно 244×272 у 32-bit TrueColor visual; Qt повернув `QSystemTrayIcon.isSystemTrayAvailable() == true`. Клієнт зупинився за timeout; звичайний user config лишився відсутнім/незмінним. Живі server, model, microphone, audio playback і GPU workload не запускались; уже наявний Ollama не змінювався.
- **Перевірений факт:** offscreen Qt preview виявив і відтворив білий порожній approval surface (`#efefef`); stylesheet fix має pixel-level regression test на темний `#0a1020` фон. CUA native app inventory у цій сесії порожній, тому screenshot фактичного compositor/tray і mouse interaction не підтверджені.
- **Потребує перевірки:** взаємодія з tray і window manager на реальному desktop, Wayland, чисте системне пакування та тривалий живий model stream. Сам факт X11 window map і доступності tray API не підтверджує повний native UX.

### Capri appearance update (2026-11-08)

- **Вимога власника:** окреме графічне Qt-вікно має починатися з Capri, а Кіберкіт є опційною альтернативою. Це не доручення змінювати або запускати TUI.
- **Перевірений факт:** додано validated local atlas renderer, збереження вигляду в `QSettings`, перемикач у контекстному меню і tray; desktop завантажує `b12.skins` без Textual/TUI modules. `scripts/import-capri-skin.py` зібрав 60 анімаційних кадрів і три пози з pinned `nic0dvornikov/capricorn-linux` у приватний pack `~/.local/share/b12/skins/capri`. RGBA atlas: 8×8 клітинок, 249×380 кожна, 676,721 bytes; art поза Git.
- **Перевірений факт:** X11 на `DISPLAY=:1` (2560×1600) показав viewable вікно `B-12 · CAPRI` 300×410. Context menu вручну перемкнув Capri → Кіберкіт → Capri; після перезапуску клієнта Capri лишилася вибраною. Loopback API health — HTTP 200.
- **Перевірений факт:** уточнення власника стосується тільки графічного Qt-компаньйона; TUI не є цільовим інтерфейсом цієї зміни. Відгалуження лишається на desktop commit `c4a93a3` без злиття локального `main`; нові Capri-зміни поки локальні й не опубліковані. `src/b12/tui/` у цьому diff не змінювався.
- **Межі:** upstream assistant code не запускався; чат, model inference, microphone capture, speaker playback і GPU не використовувалися. LICENSE виключає Capri/Cyberpunk artwork, тому локальне доручення не є правом на поширення; див. [Q20](open-questions.md). Automated tests не запускалися; статичні перевірки зафіксовані в [журналі](../log.md).

### Compact chat та додаткові функції (2026-11-08)

- **Вимога власника:** чат з Capri має відкриватися компактно біля персонажа; відсутні корисні функції з наданих репозиторіїв додавати. Уточнення: програми й системні команди також потрібні в компаньйоні.
- **Перевірений факт у локальному коді:** click відкриває компактний frameless chat, ×/Escape його ховають, ⤢ повертає повне вікно. Bubble прив’язаний до pet і перебудовує позицію після drag. Він використовує той самий ChatWindow state/control для поточної session, history, streaming, cancel та approval.
- **Перевірений факт у локальному коді:** додано QSettings reminders із date/time, due notice, snooze/dismiss; prompt shortcuts only-prefill; HTTP(S) site shortcuts із перевіркою URL; app launchers з absolute executable+argv і confirmation; shell command composer передає текст у B-12 chat/tool flow. ADR-011 документує запит і межі.
- **Перевірка:** Ruff, `py_compile`, JSON та `git diff --check` проходять. Offscreen Qt smoke створив `DesktopShell`, перемкнув compact/full, побудував dialogs; API endpoint був навмисно не запущений. Жодних automated tests, server/model/audio/GPU чи реальних програм не запускали.
- **Потребує перевірки:** видимий X11 компоновочний smoke з реальним Capri pack, drag/resize geometry, live model stream/approval через bubble, persistence через restart, reminder notification backend і Wayland. Поточна локальна зміна в worktree `feat/b12-desktop-companion` ще не опублікована.

## Поточний стан (2026-11-07)

- **Перевірений факт:** досліджено чотири надані репозиторії та офіційні Qt сторінки; pins, межі ліцензій і висновки — у [джерельному огляді](../sources/capri-desktop-companions-2026-11-07.md). Три desktop-референси дали UX-приклади; `CHNFTQ/Capricorn` — genomics diffusion-проєкт.
- **Перевірений факт:** підготовлено дизайн і покроковий план desktop-функції. Деталі — у [плані](desktop-companion-plan.md); тестовий baseline до змін — 22 TUI integration tests passed.

## Поточний стан (2026-11-06)

- **Перевірений факт:** зміни реалізації та перевірки виконані у worktree `.worktrees/runtime`, гілка `feat/b12-runtime`, від бази `5f6ba90`. На GitHub відкрито [PR #1 до `main`](https://github.com/cyberdid/B-12/pull/1); він ще не злитий.
- **Перевірений факт:** додано `web_search` з DuckDuckGo Lite та Bing RSS fallback; обидва шляхи проходять через `network.http` і `network_allow`. Ізольований live-запит реальним `b12-bolt-e4b:q4km` повернув офіційну сторінку NVIDIA Nemotron. Це один запит, не гарантія сталої якості пошуку.
- **Перевірений факт:** у persist-аналізі фіксуються неповні byte ranges, повна пагінація `file_list` і непрочитані файли; сторінки поза очікуваним offset не закривають теку. Фінальний маркер не завершує хід при прогалинах; є обмежене продовження до 60 додаткових раундів.
- **Перевірений факт із межами:** read-only review зовнішньої теки shell-скриптів завершився `failed/incomplete_coverage` у v3 і v4. У v4 EOF підтверджено для 10 з 11 скриптів; один залишився частково прочитаним. Фінальна відповідь Bolt була інвентарем файлів, а не доказовим аудитом. Claude baseline у wiki має статус неперевіреного звіту, не ground truth. Деталі та умови — у [evals](../topics/evals.md#live-bolt-перевірки-інтернету-та-кодового-review-2026-11-06).
- **Перевірений факт:** після змін перезапущено B-12 server на 8712 із `.worktrees/runtime`; Kitty TUI знову підключено до цього API. `web_search` видно в live tool registry. GPU не перезапускався і сторонні GPU-процеси не чіпалися.
- **Перевірений факт:** повний suite після pagination fix — 665 passed, 4 skipped; `ruff check src tests evals` і `git diff --check` пройшли. Wiki lint: 41 сторінка, 340 локальних посилань, 0 битих посилань/якорів, 0 відсутніх source paths та 0 неіндексованих сторінок. SHA-256 незмінного master brief збігається з маніфестом: `e2b0c4c33054082a4df48fed2785c834a95cfb7fb8f6a6e9198b6de53bd8e37a`.
- **Потребує перевірки:** живий Bolt multi-file audit поки не дає доказового звіту; див. [evals](../topics/evals.md#live-bolt-перевірки-інтернету-та-кодового-review-2026-11-06). GPU лишався спільним з іншим процесом; сторонні процеси не зупинялися.

## Наявне

- Незмінений [master brief](../../raw/B-12_Master_Project_2026-10-24.md), SHA-256 і маніфест 128 зовнішніх джерел.
- [Тематична wiki](../index.md), [аналіз](analysis.md), [кандидати рішень](decisions.md), [питання](open-questions.md), [дорожня карта](roadmap.md).
- [Постійні правила агента](../../AGENTS.md) за запитаним LLM Wiki workflow.
- Вибіркова [незалежна перевірка](../sources/external-checks.md) NVIDIA Research та README; решта матеріалів мають явну межу достовірності.
- [Аудит локальної системи](../sources/system-audit-2026-10-24.md): RTX 4060 Laptop 8GB, i9-14900HX, 32GB RAM; CUDA й Ollama server 0.33.3 доступні. Є окремий store з Gemma E2B/E4B, ще не інтегрованими в B-12.
- [Перший smoke test Bolt](bolt-first-test.md): SHA-256 перевірено; alias `b12-bolt-e4b:q4km`, context 2048; 26 запитів, з них 3 overflow timing observations виключені. Warm decode ~62–64 tok/s; є поведінкові недоліки. Пізніше truncation risk закрито лише для pinned profile, див. наступний пункт; модель лишається кандидатом.
- [Review archive-index-public](../sources/archive-index-public.md): 16 source files за pinned commit, 17 core tests passed; synthetic lexical/provenance і cache-refresh probe виконані без production DB/embedding load. Pinned lexical modules тепер інтегровані через actor-scoped derived index; приватний production archive не імпортовано.
- [Model transport](../topics/model-transport.md): Task 4 reviewed; run4 — 15/15 реальних запитів до локального Bolt alias із exact prompt counts на сценаріях до 3928 токенів. Це перевірка pinned профілю, не універсального truncation proof чи голосового SLO. Model profile залишається explicit, alias default context — 2048.
- [Agent loop](../topics/agent-loop.md): Task 7 model→tools→results, events, sessions/provenance, PurgeCoordinator; real Bolt run2/run3 без protocol failures.
- [Tool control](../topics/tool-control.md): Tasks 5–6 перевірені; API authentication і global purge реалізовані. Security межі та відкладені знахідки описані в [самоогляді](security-self-review.md) й аудитах.

## Поточний стан (2026-11-07)

- **Перевірений факт:** виконано вибірковий аналіз NVIDIA AI Factory Operations Agent на pinned commit `307afa7e485a334389b4f2c8c68128fbf84ff007`. Це experimental Helm/Kubernetes кластерний blueprint, не B-12 runtime library. Default edit вимкнений, але read-only кластерні інтеграції активні; для tenant deployment потрібна окрема scoped identity. Деталі, кодові спостереження та межі аудиту — у [картці джерела](../sources/nvidia-ai-factory-operations-agent-2026-11-07.md) і [аналізі придатності](../topics/nvidia-ai-factory-operations-agent.md).
- **Пропозиція:** не інтегрувати stack у B-12 без конкретної кластерної потреби. Нового архітектурного рішення не ухвалено; код і runtime не змінювалися.

## Наявне

- Незмінений [master brief](../../raw/B-12_Master_Project_2026-10-24.md), SHA-256 і маніфест 120 зовнішніх джерел.
- [Тематична wiki](../index.md), [аналіз](analysis.md), [кандидати рішень](decisions.md), [питання](open-questions.md), [дорожня карта](roadmap.md).
- [Постійні правила агента](../../AGENTS.md) за запитаним LLM Wiki workflow.
- Вибіркова [незалежна перевірка](../sources/external-checks.md) NVIDIA Research та README; решта матеріалів мають явну межу достовірності.
- [Аудит локальної системи](../sources/system-audit-2026-10-24.md): RTX 4060 Laptop 8GB, i9-14900HX, 32GB RAM; CUDA й Ollama server 0.33.3 доступні. Є окремий store з Gemma E2B/E4B, ще не інтегрованими в B-12.
- [Перший smoke test Bolt](bolt-first-test.md): SHA-256 перевірено; alias `b12-bolt-e4b:q4km`, context 2048; 26 запитів, з них 3 overflow timing observations виключені. Warm decode ~62–64 tok/s; є поведінкові недоліки. Пізніше truncation risk закрито лише для pinned profile, див. наступний пункт; модель лишається кандидатом.
- [Review archive-index-public](../sources/archive-index-public.md): 16 source files за pinned commit, 17 core tests passed; synthetic lexical/provenance і cache-refresh probe виконані без production DB/embedding load. Pinned lexical modules тепер інтегровані через actor-scoped derived index; приватний production archive не імпортовано.
- [Model transport](../topics/model-transport.md): Task 4 reviewed; run4 — 15/15 реальних запитів до локального Bolt alias із exact prompt counts на сценаріях до 3928 токенів. Це перевірка pinned профілю, не універсального truncation proof чи голосового SLO. Model profile залишається explicit, alias default context — 2048.
- [Agent loop](../topics/agent-loop.md): Task 7 model→tools→results, events, sessions/provenance, PurgeCoordinator; real Bolt run2/run3 без protocol failures.
- [Tool control](../topics/tool-control.md): Tasks 5–6 перевірені; API authentication і global purge реалізовані. Security межі та відкладені знахідки описані в [самоогляді](security-self-review.md) й аудитах.

## Оновлення 12.11.2026 (фінал) — заміна фактів і остаточні числа

- **Перевірений факт:** фінальний прогін — 46/34/12, 57,5% (46/80); робоча конфігурація gemma4:12b — 44/36/12, 55,0%. Проміжні 47/80 замінено; різниця — розкид формулювань.
- **Перевірений факт:** реалізовано заміну фактів (`memory_store` з `supersedes`); тести 721 passed, 4 skipped. Моделі механізмом поки не користуються.
- **Перевірений факт:** у власному venv гілки desktop з `--extra desktop` проходять обидва e2e-тести, що падали в спільному venv, і 74 тести desktop-клієнта.
- **Перевірений факт:** `main` проходить на Python 3.13 (721 passed); виправлено виявлення циклу символьних посилань у пісочниці оцінки. Гілка desktop на 3.13 з усіма extras — 811 passed. PR #1 і PR #2 — `MERGEABLE`.
- **Перевірений факт (останній прогін):** основний 46/80 (той самий список провалів), gemma 47/80. Додано `memory_supersede` і схожі записи в результаті `memory_store`. Злиття PR заблоковане захистом як злиття без рецензії — за власником. Нестабільний e2e-тест `test_abrupt_kill_recovers_integrity_and_marks_started_unknown`: 1 провал з 11 запусків.

## Оновлення 13.11.2026 — збагачення пам'яті, ембедер на CPU

- **Перевірений факт:** фонове збагачення пам'яті категоріями закрило JOURNEY-04 (3/3 на обох моделях). Остаточно: основний 47/33/12 (58,8%), gemma 48/32/12 (60,0%).
- **Перевірений факт:** міст EmbeddingGemma на GPU спричиняв `CUDA out of memory` в Ollama поруч із gemma4:12b; тепер він типово на CPU (`embedding_device`). Тести: 725 passed, 4 skipped.
- **Відкрито:** MEM-07 (моделі не користуються `memory_supersede`), багатосесійні сценарії, злиття PR (за власником), 7/30-денні тести (17.11, 26.11), голос і робот.
