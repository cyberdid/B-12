# Scientific revision, 2026-11-09

Open manuscript.tex in Scribe. Build with tectonic manuscript.tex. Original English/Ukrainian manuscripts and root PDFs are preserved. references.bib contains verified primary-source metadata. build_revision.py regenerates the manuscript and figures from the original and local historical artifacts; it requires the original source tree and local metadata paths. Building the existing LaTeX/PDF does not require raw experiment traces.

Artifacts include the source inventory, Git/PR snapshot, environment, historical aggregate data and hashes, scoped pytest JUnit/text outputs. See evidence-matrix.csv, revision-report.md and research-gaps.md. Python plotting requires matplotlib; compilation requires Tectonic and DejaVu Serif. No publication action is performed.

Rebuild: python build_revision.py, then python finalize_manuscript.py, then tectonic manuscript.tex. Regeneration requires the source tree, read-only GitHub CLI access and historical local metadata; the existing manuscript and vector PDFs compile independently. New tests include a reproducible failing assertion, not an all-tests-passed release.

Portable PDF build (from this directory):

```bash
python render_figures.py  # optional; matplotlib required; no private traces/network
tectonic manuscript.tex
```

The packaged manuscript, bibliography and figures are the authoritative editable edition. `build_revision.py` is the original audit/assembly workflow, not required for routine editing; rerunning it refreshes evidence snapshots and overwrites editorial reports. `validate_artifacts.py` checks the local private originals as well as bundled cross-references. `artifacts/package-checksums.json` lists the final packaged file hashes. `scoring-method.tex` is retained as an editable insertion source; its content is already included in manuscript.tex.

Final edition: 19 pages including references (which start on page 17); 4 figures, 6 tables, 17 references, 26 evidence claims. For editorial changes, edit manuscript.tex directly; runtime-detail.tex and scoring-method.tex are retained insertion sources already incorporated in that file.
