# Measuring a Local AI Companion Through Its Own Runtime (2026-11-14, revised 2026-11-15)

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

## Revision 2026-11-15 (after an external review)

- Behaviour after moving Evidence is described as "no detected aggregate change in scenario
  success", not as unchanged behaviour; the injection robustness of the new placement is
  stated as untested.
- Model scale: every run rescored with latency/duration bounds ignored; paired by scenario,
  Bolt + 12B vs 26b and 31b differ by 15:13 and 14:12 scenarios (p = 0.85). The conclusion is
  narrowed to "larger models did not improve the outcome".
- Brevity A/B widened to 16 work scenarios (156 executions, `brevity_ab_rows_v2.json`); the
  7-scenario run is kept as the pilot.
- Second annotation of the 17 persistent failures (51 blinded items) by Codex (`gpt-6-luna`)
  and Antigravity (Gemini 4 Argon, medium), two passes each in opposite order, with the
  author's labels fixed beforehand (`labels_claude.json`); the owner adjudicated the 13
  disputed items (`labels_owner.json`; marks yes/+ normal, +- minor defect, - major defect).
  Fleiss' kappa 0.69. Run `experiments/judges/analyze.py` to recompute.
- The first paper's DOI (10.5281/zenodo.24079168) is cited; the data availability statement
  says exactly which reply texts are public.
