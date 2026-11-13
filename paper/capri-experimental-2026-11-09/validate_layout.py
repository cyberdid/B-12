"""Check the explicit preprint house style without private experiment data."""
from collections import Counter
from pathlib import Path
import csv
import hashlib
import json
import re
import subprocess
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parent
ART = ROOT / "artifacts"
source = (ROOT / "manuscript.tex").read_text()
preamble = (ROOT / "preamble.tex").read_text()
assert r"\documentclass[11pt,a4paper]{article}" in source
for setting in (
    "a4paper,margin=25mm", "cmunrm.otf", "cmuntb.otf", "cmunti.otf",
    "font=small,labelfont=bf", "numbers,sort&compress", "{4pt}", "{1.12}",
):
    assert setting in preamble, setting
assert r"\bibliographystyle{unsrtnat}" in source
assert "Oleksandr Pylypenko" in source
assert "State University of Trade and Economics, Kyiv, Ukraine" in source

tables = re.findall(r"\\begin\{table\}.*?\\end\{table\}", source, re.S)
figures = re.findall(r"\\begin\{figure\}.*?\\end\{figure\}", source, re.S)
assert len(tables) == 6 and len(figures) == 4
for block in tables:
    assert block.index(r"\caption") < block.index(r"\begin{tabular")
    assert "\\hline" not in block
for block in figures:
    assert block.index(r"\input{figures/") < block.index(r"\caption")
    name = re.search(r"\\input\{([^}]+)\}", block)[1]
    assert (ROOT / name).is_file()
for label in re.findall(r"\\label\{((?:fig|tab):[^}]+)\}", source):
    assert r"\ref{" + label + "}" in source

bib = (ROOT / "references.bib").read_text()
keys = set(re.findall(r"@\w+\{([^,]+),", bib))
cited = {key for group in re.findall(r"\\cite\{([^}]+)\}", source) for key in group.split(",")}
assert keys == cited and len(cited) == 18
for line in bib.splitlines():
    if line.startswith("@"):
        assert "url={" in line

log = (ART / "latex-build.txt").read_text()
for defect in ("Overfull", "undefined", "Missing character", "LaTeX Error", "error:"):
    assert defect not in log, defect

def run(*arguments):
    return subprocess.check_output(arguments, text=True)

fonts = run("pdffonts", str(ROOT / "manuscript.pdf"))
assert "CMUSerif" in fonts and "DejaVu" not in fonts and "Type 3" not in fonts
for line in fonts.splitlines()[2:]:
    assert re.search(r"\s+yes\s+(?:yes|no)\s+(?:yes|no)\s+\d+\s+\d+\s*$", line), line
(ART / "fonts.txt").write_text(fonts)

bbox = run("pdftotext", "-bbox", str(ROOT / "manuscript.pdf"), "-")
(ART / "layout-bbox.html").write_text(bbox)
ns = {"x": "http://www.w3.org/1999/xhtml"}
pages = ET.fromstring(bbox).findall(".//x:page", ns)
for page in pages:
    assert abs(float(page.attrib["width"]) - 595.28) < .2
    assert abs(float(page.attrib["height"]) - 841.89) < .2
    for word in page.findall("x:word", ns):
        # Three points allow optical character protrusion at a 25 mm text margin.
        assert float(word.attrib["xMin"]) >= 70.866 - 3, word.text
        assert float(word.attrib["xMax"]) <= 524.41 + 3, word.text
        assert float(word.attrib["yMin"]) >= 70.866 - 3, word.text
        assert float(word.attrib["yMax"]) <= 810, word.text

text = run("pdftotext", "-layout", str(ROOT / "manuscript.pdf"), "-")
assert "??" not in text
(ART / "manuscript-text.txt").write_text(text)
reference_page = next(
    i + 1 for i, page in enumerate(text.split("\f"))
    if re.search(r"^\s*References\s*$", page, re.M)
)

outcomes = [json.loads(line) for line in (ART / "normalized-outcomes.jsonl").read_text().splitlines()]
counts = {}
for context, expected_runs, expected_passes in ((4096, 541, 496), (8192, 109, 102)):
    selected = [row for row in outcomes if row["num_ctx"] == context]
    assert len(selected) == expected_runs and sum(row["passed"] for row in selected) == expected_passes
    counts[str(context)] = {"runs": len(selected), "passed": sum(row["passed"] for row in selected)}
assert len(list(csv.DictReader((ROOT / "evidence-matrix.csv").open()))) == 29

previous = ROOT.parent / "capri-scientific-2026-11-09"
inherited_match = "previous edition not present in portable package"
if previous.is_dir():
    for relative in (
        
        "artifacts/normalized-outcomes.jsonl", "artifacts/focused-tests.xml",
        "artifacts/repeat-test.xml", "artifacts/metadata-ctx4096.json",
        "artifacts/metadata-ctx8192.json",
    ):
        digest = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
        assert digest(ROOT / relative) == digest(previous / relative), relative
    old_source = (previous / "manuscript.tex").read_text()
    def empirical_numbers(document):
        section = document.split(r"\section{Methods and evidence}", 1)[1]
        section = section.split(r"\section{Autonomy, Evidence State and Audio Boundaries}", 1)[0]
        return Counter(re.findall(r"\d+(?:[.,]\d+)*", section))
    assert empirical_numbers(old_source) == empirical_numbers(source)
    inherited_match = True

report = {
    "pages": len(pages), "reference_section_begins_page": reference_page,
    "a4_all_pages": True, "house_style_source_checks": True,
    "fonts_embedded": True, "no_type3_fonts": True,
    "bounding_boxes_within_text_width_including_optical_protrusion": True,
    "tables_caption_above": len(tables), "figures_caption_below": len(figures),
    "cited_references": len(cited), "evidence_claims": 29,
    "historical_aggregates": counts,
    "new_experiments_in_layout_revision": True,
    "inherited_evidence_and_empirical_numbers_unchanged": inherited_match,
    "visual_review": "Recorded separately in formatting-report.md; automation does not substitute for visual inspection.",
}
(ART / "layout-validation.json").write_text(json.dumps(report, indent=2) + "\n")
print(json.dumps(report, indent=2))
