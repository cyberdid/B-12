---
type: source-review
updated: 2026-11-08
status: reviewed
sources: [raw/source-manifest.json, paper/capri-preprint/article-en.tex, paper/capri-preprint/article-uk.tex, wiki/topics/evals.md, wiki/topics/model-transport.md]
tags: [scribe, preprint, provenance]
---
# Scribe та двомовний препринт Capri

**Джерело:** [Scribe-IDE/Scribe](https://github.com/Scribe-IDE/Scribe), сторінку README й release переглянуто 08.11.2026; HEAD main на час перевірки — 08168f3208c32609ae5404016e9306c185f69f37, завантажена release v1.2.3. Scribe — локальний LaTeX editor; перевірено опис проєктних тек, Tectonic і Linux AppImage. Повний код не аудиторувався. Вебзнімок або архів джерела до raw не зберігався.

**Доручення власника:** використати Scribe й написати статтю англійською та українською. У paper/capri-preprint створено окремі XeTeX-сумісні джерела й PDF; AppImage Scribe запущено, а PDF складено наявним Tectonic. Саме редагування та компіляцію через UI Scribe не перевіряли.

**Межі:** статті є робочими рукописами, не опублікованими препринтами. Реальні модельні результати стосуються історичних commit; повний корпусний JSONL і metadata залишаються в локальному runtime worktree. Публічний пакет відтворення, перевірка авторських метаданих, зовнішніх посилань і незалежний науковий review ще потрібні. Персона Capri та ModelManager не були оцінені історичним експериментом.
