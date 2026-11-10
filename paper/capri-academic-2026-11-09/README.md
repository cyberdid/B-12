# Capri: academic layout revision

This edition applies the author's existing A4/CMU preprint style to the scientific manuscript. See `formatting-spec.md` for exact requirements and `formatting-report.md` for the comparison and acceptance results. No new inference, audio or regression experiment was run for this layout revision. The recorded 118-pass/1-failure result belongs to the preceding scientific revision.

Open `manuscript.tex` in Scribe. From this directory:

```sh
python build.py
```

Tectonic, Python 3 and the Tectonic TeX bundle are required. CMU OTF fonts, TikZ, PGFPlots, natbib and other dependencies are resolved through that bundle; the first build may need a network download. Python figure generation uses only its standard library and bundled historical aggregate counts. Compilation does not require private traces, GitHub access or matplotlib.

The editable artifact is `manuscript.tex` plus `preamble.tex`, `references.bib` and generated `figures/*.tex`. The inherited audit artifacts, evidence matrix, revision report and research gaps preserve the scientific evidence. `validate_artifacts.py` is the earlier local verification and requires original private paths; `validate_layout.py` checks the portable formatting package. The previous `paper/capri-scientific-2026-11-09` directory is preserved unchanged.

The house style is explicit; no journal has been selected, so compliance with a specific publisher's submission template is not asserted. Authorship and the manuscript's existing academic affiliation are preserved.

The build helper prefers the isolated cached Tectonic 0.17.0 used for this revision. On another machine set `TECTONIC=/path/to/tectonic` if needed; otherwise the executable on PATH is used. Compiler version and first-build network requirements should be checked before archival reproduction.
