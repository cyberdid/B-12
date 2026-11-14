# Measuring a Local AI Companion Through Its Own Runtime (2026-11-14)

Follow-up to `paper/capri-experimental-2026-11-09`. Same house style (A4, 25 mm margins,
`article` 11 pt, Computer Modern Unicode, `natbib`/`unsrtnat`, `booktabs`, TikZ/PGFPlots,
Tectonic 0.17.0); see `paper/capri-academic-2026-11-09/formatting-spec.md`.

## Build

    ../../.venv/bin/python build.py

`collect_data.py` computes every number in the paper from repository artifacts into
`artifacts/data.json`; `render_figures.py` draws the figures from that file only;
`validate_layout.py` checks the house style and that the numbers quoted in the text equal
the computed ones. No step calls a model.

## Data

- Repeated runs: `evals/capri_comprehensive/reports/repeats/` (runs 1-6, `deployed-26b/`, `deployed-31b/`).
- Prompt-cache measurement: `evals/capri_comprehensive/reports/experiments/evidence-after-user-2026-11-14/`.
- Brevity A/B: `experiments/brevity_ab.py` (run inside the bubblewrap sandbox like the suite,
  3 repeats x 2 arms x 17 scenarios, primary model on an idle RTX 4060) and its rows in
  `experiments/brevity_ab_rows.json`; the owner's home directory is replaced with `~`.

## Review

Every page was rendered (`pdftoppm`) and inspected; legend overlaps in Figures 2-4, a wrapped
label in Figure 1 and lower-cased arXiv titles were fixed before the final build. Automated
checks do not replace scientific review; the evaluation was run by the same agent that wrote
the paper, and there is no independent replication.
