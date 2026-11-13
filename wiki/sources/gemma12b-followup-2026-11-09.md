---
type: source-review
updated: 2026-11-09
status: compiled
sources: [raw/gemma12b-followup-2026-11-09/owner-excerpt.md, raw/gemma12b-followup-2026-11-09/receipts.json, paper/experiments/gemma12b-stage-2026-11-09/protocol.md, paper/experiments/gemma12b-stage-2026-11-09/stage-summary.json, paper/capri-experimental-2026-11-09/manuscript.tex]
tags: [paper, gemma, calibration, experiment, context]
---
# Gemma 12B та контрольований експериментальний етап

**Вимога власника:** власні експериментальні результати; уточнення моделі — Gemma 12B. Надана оцінка стосувалася старішої 19-сторінкової редакції; рейтинги не є незалежним рецензуванням. Excerpt у raw явно неповний.

**Перевірений факт:** локально наявний gemma4:12b, Q4_K_M, manifest 4eb23ef187e2c5462566d6a1d3bbbc2f1346d0b4327cbb66d58fffbcc9b2b05c; Ollama 0.33.3. Тестові tokenizer assets pinned до Google IT revision 43c9d014b231474fa7212dbb48a762566c2b255d. Local GGUF metadata посилається на base repo; тотожність саме IT вагам не встановлена. Готовий production profile не активувався.

**Нові вимірювання:** 8/8 exact input-count matches для чотирьох конфігурацій; 12/12 виконань трьох вибраних поточних eval-сценаріїв на контекстах 4096/8192, 16 user turns. Параметри, обмеження, корпус і raw checks — у [звітi](../../paper/experiments/gemma12b-stage-2026-11-09/results-report.md). Це вузький пілот, не повний корпус і не модельний рейтинг.

**Контрольований CPU-висновок:** чотири prefix arms × три повтори. Поточна persona: 11344 символи, HEAD: 10598, без prefix: 9886, neutral matched: 11344. Non-system counts збігаються на всіх 37 раундах. Префікс змінює символьний результат, а не доводить покращення поведінки. HEAD теж не проходить; остання зміна не є єдиною причиною. Старі 11364 з іншого temporary path не підмінено новим числом. Production persona й тест не змінювалися.

**Артефакт:** [нова редакція](../../paper/capri-experimental-2026-11-09/manuscript.tex), 17 сторінок A4/CMU, 6 таблиць, 4 рисунки з відсотками категорій, 18 джерел, 29 claims. Історичний Bolt score лишається історичним. Нові експерименти не доводять переваги над Bolt чи збереження характеру між моделями. Попередні редакції збережено.

**Межі джерел:** прочитано вступ офіційної Google model card, metadata API й tokenizer/config/template assets для профілю; повний model report та ваги не перевірялися. Офіційні URLs і SHA-256 — у receipts. Assets збережені в окремому локальному кеші, не в raw; вебсторінок-знімків у raw немає. Ваги не завантажувалися. Гостьових/приватних даних, аудіо чи біометрії у випробуваннях немає.

**Після перевірки:** model unload підтверджено для обох пілотів; GPU повернувся до початкових 15 MiB. Live Capri config/пам'ять/процеси не змінювали. Full 109-case rerun, matched current-code cross-model test і blinded persona evaluation залишаються наступними дослідами.
