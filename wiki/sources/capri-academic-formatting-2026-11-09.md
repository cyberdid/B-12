---
type: source-review
updated: 2026-11-09
status: compiled
sources: [raw/author-layout-references-2026-11-09/wow.pdf, raw/author-layout-references-2026-11-09/minecraft.pdf, raw/author-layout-references-2026-11-09/archive.pdf, raw/author-layout-references-2026-11-09/fft.pdf, paper/capri-academic-2026-11-09/formatting-spec.md, paper/capri-academic-2026-11-09/artifacts/layout-reference-manifest.json]
tags: [paper, formatting, reproducibility, correction]
---
# Узгодження оформлення Capri з авторськими препринтами

**Вимога власника:** переглянути локальні PDF його статей; застосувати чітко прописане академічне оформлення. **Уточнення власника:** конкретного журналу немає.

**Перевірений факт:** локальні WoW, Minecraft, archive-index і FFT використовують A4, поля 25 мм, клас article 11 pt, Computer Modern Unicode та числовий natbib. Повністю прочитані чотири преамбули; візуально переглянуті титули та вибрані внутрішні сторінки. Це аналіз верстки, не повторна перевірка наукових результатів інших робіт. Оригінали й преамбули збережені без змін у raw; локальне походження й SHA-256 наведені у manifest артефактів.

**Спростовано/замінено:** попередній Capri PDF на Letter із DejaVu Serif не відповідав наявному авторському шаблону. Самі ці параметри не є універсально забороненими для науки; помилкою було неврахування конкретного авторського оформлення. Єдиного універсального формату для всіх видавництв не заявлено.

**Реалізовано:** окрема редакція у paper/capri-academic-2026-11-09 з авторською преамбулою, назвами таблиць зверху, підписами рисунків знизу, native TikZ/PGFPlots, бібліографією за порядком цитування та canonical DOI/URL. [Норми](../../paper/capri-academic-2026-11-09/formatting-spec.md), [звіт](../../paper/capri-academic-2026-11-09/formatting-report.md), [перевірка](../../paper/capri-academic-2026-11-09/artifacts/layout-validation.json).

**Межі:** авторство й наявна афіліація збережені; інші статуси/контакти не додавалися. Нових model/voice/GPU/CPU експериментів немає; 118 passed / 1 failed успадковано з попередньої наукової ревізії. Попередня 19-сторінкова редакція та 9-сторінкові оригінали зберігаються окремо. Production-код не змінювався. Відповідність конкретному журналу потребує його вибору й окремої перевірки.
