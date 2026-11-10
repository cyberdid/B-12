---
type: source-review
updated: 2026-11-09
status: compiled
sources: [paper/capri-scientific-2026-11-09/manuscript.tex, paper/capri-scientific-2026-11-09/evidence-matrix.csv, paper/capri-scientific-2026-11-09/artifacts/validation.json, paper/capri-scientific-2026-11-09/artifacts/git-pr-snapshot.json]
tags: [paper, evidence, reproducibility, audit]
---
# Наукова редакція B-12 / Capri

**Вимога власника:** окрема поглиблена англомовна systems research редакція зі збереженням оригіналу.

**Перевірено:** історичні 650 рядків результатів повторно агреговані за полями recorded passed; 496/541, 102/109, 117/150 та outbound fetch 0/5 збігаються із summary. Нове вибіркове CPU-тестування — 118 passed / 1 failed; окремий повтор — та сама невдала перевірка. Це fixed-character-budget assertion 11364 проти <10000; причина не встановлена, реального model overflow ця перевірка не доводить. Production-код і тести не змінювалися.

**Артефакти:** [нова стаття](../../paper/capri-scientific-2026-11-09/manuscript.tex), [матриця](../../paper/capri-scientific-2026-11-09/evidence-matrix.md), [звіт](../../paper/capri-scientific-2026-11-09/revision-report.md), [прогалини](../../paper/capri-scientific-2026-11-09/research-gaps.md). Git/PR snapshot відрізняє remote main, відкриті PR і dirty feature-tree; історичний benchmark не приписаний поточному HEAD.

**Література:** первинні arXiv abstracts і метадані перевірено для Generative Agents, MemGPT, Reflexion, Voyager, Character-LLM, AgentBench, InjecAgent, HELM, AWQ і SWE-agent; раніші ReAct/RAG/Lost in the Middle перевірено у попередньому огляді. URLs, назви, автори й arXiv DOI містяться в references.bib і bibliography-verification.json. Повні статті не репліковані; це тематичний огляд, не систематичний literature review. Вебзнімків у raw немає.

**Межі:** жоден висновок не названо independently verified; автоматизовані тести написані проєктом. Усі запитані каталоги інвентаризовані, кодові твердження перевірено за вибраними файлами й тестами; інвентар не є доказом повного незалежного посторінкового аудиту кожного історичного документа. Сирі історичні траси залишаються локальними; normalized outcomes не дозволяють перевірити кожен семантичний check. Нових GPU, голосових або фізичних тестів немає.

**Фінальна перевірка:** PDF 19 сторінок із бібліографією від сторінки 17, 4 рисунки, 6 таблиць, 17 джерел, 26 claims. Компіляція, cross-references, авторство та незмінність оригіналу перевірені; докази у artifacts/final-review.json і validation.json.
