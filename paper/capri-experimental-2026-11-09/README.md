# Capri: bounded Gemma and context-ablation follow-up

This edition applies the author's existing A4/CMU preprint style to the scientific manuscript. See `formatting-spec.md` for exact requirements and `formatting-report.md` for the comparison and acceptance results. This edition adds bounded Gemma inference pilots and a scripted CPU prefix-size ablation. No audio or physical experiment was run. The recorded 118-pass/1-failure result belongs to the preceding scientific revision.

Open `manuscript.tex` in Scribe. From this directory:

```sh
python build.py
```

Tectonic, Python 3 and the Tectonic TeX bundle are required. CMU OTF fonts, TikZ, PGFPlots, natbib and other dependencies are resolved through that bundle; the first build may need a network download. Python figure generation uses only its standard library and bundled historical aggregate counts. Compilation does not require private traces, GitHub access or matplotlib.

The editable artifact is `manuscript.tex` plus `preamble.tex`, `references.bib` and generated `figures/*.tex`. The inherited audit artifacts, evidence matrix, revision report and research gaps preserve the scientific evidence. `validate_artifacts.py` is the earlier local verification and requires original private paths; `validate_layout.py` checks the portable formatting package. Both preceding scientific and academic edition directories are preserved unchanged. New raw evidence and reproduction scripts are in `experiments/gemma12b-stage-2026-11-09`; `followup.tex` is an insertion source already incorporated in manuscript.tex. Run `python validate_followup.py` to verify the new arithmetic without rerunning inference.

The house style is explicit; no journal has been selected, so compliance with a specific publisher's submission template is not asserted. Authorship and the manuscript's existing academic affiliation are preserved.

The build helper prefers the isolated cached Tectonic 0.17.0 used for this revision. On another machine set `TECTONIC=/path/to/tectonic` if needed; otherwise the executable on PATH is used. Compiler version and first-build network requirements should be checked before archival reproduction.
