---
type: source-review
updated: 2026-11-08
status: reviewed
sources: [raw/source-manifest.json, paper/capri-preprint/article-en.tex, paper/capri-preprint/article-uk.tex, paper/capri-preprint/evidence.md]
tags: [preprint, sources, retrieval, agents]
---
# Джерела робочого препринту Capri

**Межа перевірки:** 08.11.2026 переглянуто abstracts і метадані, а не повні тексти статей. Вебзнімки у raw не збережено. Формулювання у рукописах обмежені цим оглядом; повне порівняння та незалежний огляд залишаються відкритими.

- [ReAct](https://arxiv.org/abs/2210.03629) — досліджує чергування модельного міркування та дій; це мотивація agent loop, а не перевірка B-12.
- [Retrieval-Augmented Generation](https://arxiv.org/abs/2005.11401) — досліджує поєднання параметричної генерації та зовнішньої пам'яті. B-12 не заявляє відтворення експериментів статті.
- [Lost in the Middle](https://arxiv.org/abs/2307.03172) — досліджує вплив позиції відомостей у довгому контексті. Наш truncation case є окремим спостереженням.
- [Beyond Search Scores](https://doi.org/10.5281/zenodo.23602155), [WoW companions](https://doi.org/10.5281/zenodo.23911809) і [Minecraft autonomy audit](https://doi.org/10.5281/zenodo.23910891) — попередні роботи власника, прочитані за metadata та abstracts Zenodo API. Їхні оцінки належать відповідним проєктам і не перенесені як вимірювання B-12.

Історичні локальні B-12 metadata та summary, їхні хеші й межі опублікованості наведено в [evidence.md](../../paper/capri-preprint/evidence.md). Це не публічний пакет сирих даних.
