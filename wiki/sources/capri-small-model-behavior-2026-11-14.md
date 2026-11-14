---
type: source-review
updated: 2026-11-14
status: compiled
sources:
  - raw/deep-research-prompt-behavior-2026-11-14.md
  - research/capri-small-model-behavior-2026-11-14/report.md
  - profiles/bolt-e4b-ollama-0.33.3.json
  - src/b12/context.py
  - src/b12/runtime.py
  - evals/capri_comprehensive/reports/repeats/REPEATS_SUMMARY.md
tags: [research, behavior, small-models, memory, latency, continuity]
---
# Дослідження поведінки Capri на малих локальних моделях

## Походження

- Первинний prompt наданий власником локально: /home/cyberdid/Documents/B-12-deep-research-prompt-behavior.md.
- Незмінна копія: raw/deep-research-prompt-behavior-2026-11-14.md.
- SHA-256: 84ad1d1e5726acd0041fae07dd2b4f412effea0157e70379973527471164df2f.
- Дата ingest/access: 2026-11-14.
- Це інше джерело, ніж попередній raw/deep-research-behavior-2026-11-14.md з SHA 2f0c894f…04d9; ці два prompt-и не об’єднувати.
- Вебджерела перевірено через першоджерела (ACL Anthology, NeurIPS Proceedings, arXiv, Ollama/GitHub, NIST, PMC) 2026-11-14. Локальні HTML/PDF snapshots не збережено; звіт прямо позначає межу прочитаного та evidence level.

## Охоплення

Повний синтез міститься у [дослідницькому звіті](../../research/capri-small-model-behavior-2026-11-14/report.md); окремі поля та джерела зберігаються у research/capri-small-model-behavior-2026-11-14/results/.

- Стислі відповіді без втрати tool-use та української мови.
- TTFT, prefix/KV reuse, keep_alive, num_batch, Flash Attention/KV quantization, offload і speculative/MTP.
- Виявлення конфліктів між memory/document evidence.
- Selection і застосування вподобань, включно з контекстним over-application.
- Незакриті задачі, відбір ініціативи й момент повідомлення.
- Порівняння data/retrieval/behavioral continuity після зміни моделі; відповідь на запитання про AIBEVA.
- Парний A/B план для 80 сценаріїв з урахуванням фактичної run-to-run нестабільності.

## Межі достовірності

- Рецензовані paper results залишено прив’язаними до їхніх моделей та корпусів; числові ефекти не переносяться на Capri.
- MemPABench, PITCH і робота про model transition позначені як препринти станом на дату доступу, крім випадків окремо зазначеної acceptance інформації.
- TTFT та brevity pilot наведені як повідомлені власником результати; незалежного повтору в цьому research pass немає.
- У звіті виправлено плутанину між зміною загального числа PASS на 0–1 і кількістю попарно різних verdicts на 4/7/7.
- Bolt model-family label у наданому prompt суперечить локальній назві/provenance документації; перед новим експериментом потрібно звірити ваги, alias і manifest.
- Не запускали inference, GPU benchmark, Capri, клієнт чи тести; production код не змінювали, коментарі не публікували.

## Основні джерела

- [When Instructions Multiply](https://aclanthology.org/2025.findings-emnlp.896/) — peer-reviewed, EMNLP 2025.
- [CCTU](https://aclanthology.org/2026.findings-aacl.85/) — peer-reviewed, IJCNLP-AACL 2026.
- [RULER](https://aclanthology.org/2024.findings-emnlp.172/) та [DeCRIM](https://aclanthology.org/2024.findings-emnlp.458/) — peer-reviewed, EMNLP 2024.
- [ECON](https://aclanthology.org/2024.emnlp-main.447/) — peer-reviewed, EMNLP 2024; [WikiContradict](https://papers.nips.cc/paper_files/paper/2024/hash/c63819755591ea972f8570beffca6b1b-Abstract-Datasets_and_Benchmarks_Track.html) — NeurIPS 2024.
- [PrefEval](https://arxiv.org/abs/2502.09597), ICLR 2025; [MemPABench](https://arxiv.org/abs/2610.30485), preprint 2026; [BenchPreS](https://arxiv.org/abs/2603.16557), EMNLP 2026.
- [Generative Agents](https://arxiv.org/abs/2304.03442) і [MemGPT](https://arxiv.org/abs/2310.08560) — foundational work, 2023/2024.
- [Proactive Agent](https://arxiv.org/abs/2410.12361) — preprint 2024; [PITCH](https://arxiv.org/abs/2610.25896) — preprint 2026.
- [Model Transition study](https://arxiv.org/abs/2611.10628) — preprint 2026.
- [Ollama v0.33.3 release](https://github.com/ollama/ollama/releases/tag/v0.33.3), [versioned FAQ](https://github.com/ollama/ollama/blob/v0.33.3/docs/faq.mdx), [API types](https://github.com/ollama/ollama/blob/v0.33.3/api/types.go).
- [AIBEVA first-party page](https://www.aibfamily.cloud/) та [афілійована demo публікація](https://www.reddit.com/user/Anxious_Count_8728/comments/1xvzpi9/switched_the_model_kept_the_memory/).

## Пов’язане

- [Попередній deep research prompt review](deep-research-behavior-2026-11-14.md) — окремий вхідний документ, не ця стаття.
- [Оцінка Capri](../project/capri-comprehensive-evaluation.md).
- [Пам’ять](../topics/memory.md), [моделі](../topics/models.md), [автономність](../topics/autonomy.md).
