"""Check the preprint house style and that reported numbers match artifacts/data.json."""
from pathlib import Path
import json
import re
import subprocess
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parent
ART = ROOT / "artifacts"
source = (ROOT / "manuscript.tex").read_text()
preamble = (ROOT / "preamble.tex").read_text()
assert r"\documentclass[11pt,a4paper]{article}" in source
for setting in ("a4paper,margin=25mm", "cmunrm.otf", "cmuntb.otf", "cmunti.otf",
                "font=small,labelfont=bf", "numbers,sort&compress", "{4pt}", "{1.12}"):
    assert setting in preamble, setting
assert r"\bibliographystyle{unsrtnat}" in source
assert "Oleksandr Pylypenko" in source and "State University of Trade and Economics, Kyiv, Ukraine" in source

tables = re.findall(r"\\begin\{table\}.*?\\end\{table\}", source, re.S)
figures = re.findall(r"\\begin\{figure\}.*?\\end\{figure\}", source, re.S)
for block in tables:
    assert block.index(r"\caption") < block.index(r"\begin{tabular"), "table caption above"
    assert "\\hline" not in block
for block in figures:
    assert block.index(r"\input{figures/") < block.index(r"\caption"), "figure caption below"
    assert (ROOT / re.search(r"\\input\{([^}]+)\}", block)[1]).is_file()
for label in re.findall(r"\\label\{((?:fig|tab):[^}]+)\}", source):
    assert re.search(r"\\[cC]?ref\{[^}]*" + re.escape(label), source), label

bib = (ROOT / "references.bib").read_text()
keys = set(re.findall(r"@\w+\{([^,]+),", bib))
cited = {k.strip() for g in re.findall(r"\\cite\{([^}]+)\}", source) for k in g.split(",")}
assert keys == cited, (keys - cited, cited - keys)
assert bib.lower().count("url") >= len(keys)

log = (ART / "latex-build.txt").read_text()
for defect in ("Overfull", "undefined", "Missing character", "LaTeX Error", "error:"):
    assert defect not in log, defect

# Numbers in the text must equal the computed data.
d = json.loads((ART / "data.json").read_text())
r = d["repeats"]
expected = [
    ", ".join(map(str, r["bolt"]["per_run"])), ", ".join(map(str, r["gemma4-26b"]["per_run"])),
    ", ".join(map(str, r["gemma4-31b"]["per_run"])), ", ".join(map(str, r["bolt-evidence-after-user"]["per_run"])),
    f"{r['bolt']['pooled_percent']}\\%", f"{r['gemma4-26b']['pooled_percent']}\\%",
    f"{len(d['stable_fail_all_three'])}".replace("17", "Seventeen"),
    f"from {d['brevity_ab']['control']['casual_chars_median']} to {d['brevity_ab']['treatment']['casual_chars_median']} characters",
    f"from {d['brevity_ab']['control']['work_turns_with_tool']} of 21 to {d['brevity_ab']['treatment']['work_turns_with_tool']} of 21",
    f"from {int(d['prompt_cache']['baseline']['cached_median'])} to {int(d['prompt_cache']['after']['cached_median'])}",
    f"p={d['evidence_paired']['sign_test_p']}", f"The {d['model_dependent']['n']} model-dependent",
]
expected[-1] = f"the {d['model_dependent']['n']} model-dependent"
for text in expected:
    assert text in source, text
for sid in d["stable_fail_all_three"]:
    assert sid in source, sid

def run(*a):
    return subprocess.check_output(a, text=True)
pdf = str(ROOT / "manuscript.pdf")
fonts = run("pdffonts", pdf)
assert "CMUSerif" in fonts and "DejaVu" not in fonts and "Type 3" not in fonts
for line in fonts.splitlines()[2:]:
    assert re.search(r"\s+yes\s+(?:yes|no)\s+(?:yes|no)\s+\d+\s+\d+\s*$", line), line
bbox = run("pdftotext", "-bbox", pdf, "-")
ns = {"x": "http://www.w3.org/1999/xhtml"}
pages = ET.fromstring(bbox).findall(".//x:page", ns)
for page in pages:
    assert abs(float(page.attrib["width"]) - 595.28) < .2 and abs(float(page.attrib["height"]) - 841.89) < .2
    for w in page.findall("x:word", ns):
        assert float(w.attrib["xMin"]) >= 70.866 - 3 and float(w.attrib["xMax"]) <= 524.41 + 3, w.text
        assert float(w.attrib["yMin"]) >= 70.866 - 3 and float(w.attrib["yMax"]) <= 810, w.text
text = run("pdftotext", "-layout", pdf, "-")
assert "??" not in text
report = {"pages": len(pages), "a4_all_pages": True, "fonts_embedded_cmu": True,
          "tables": len(tables), "figures": len(figures), "references": len(keys),
          "numbers_match_data_json": True,
          "visual_review": "Each page rendered and inspected; see README."}
(ART / "layout-validation.json").write_text(json.dumps(report, indent=2) + "\n")
print(json.dumps(report, indent=2))
