"""Build and validate the paper; never call an inference service."""
from pathlib import Path
import os
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parent
cached = Path.home() / ".cache/capri-paper-tools/tectonic-0.17.0/tectonic"
engine = os.environ.get("TECTONIC") or (str(cached) if cached.is_file() else shutil.which("tectonic"))
if not engine:
    raise SystemExit("Install Tectonic (tested with 0.17.0) or set TECTONIC to its executable.")
subprocess.run([sys.executable, "render_figures.py"], cwd=ROOT, check=True)
print(subprocess.check_output([engine, "--version"], text=True).strip(), flush=True)
with (ROOT / "artifacts/latex-build.txt").open("w") as output:
    result = subprocess.run(
        [engine, "--keep-logs", "--keep-intermediates", "manuscript.tex"],
        cwd=ROOT, stdout=output, stderr=subprocess.STDOUT,
    )
if result.returncode:
    raise SystemExit("Compilation failed; inspect artifacts/latex-build.txt.")
subprocess.run([sys.executable, "validate_layout.py"], cwd=ROOT, check=True)
