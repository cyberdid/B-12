"""Fetch only the exact public tokenizer assets recorded in the experiment receipt."""
from pathlib import Path
import hashlib
import json
import urllib.request

OUT = Path(__file__).resolve().parent
receipt = json.loads((OUT / "gemma-assets-preflight.json").read_text())
cache = Path.home() / ".cache/b12-paper-models/gemma-4-12B-it" / receipt["revision"]
cache.mkdir(parents=True, exist_ok=True)
for name, record in receipt["assets"].items():
    target = cache / name
    if not target.is_file() or hashlib.sha256(target.read_bytes()).hexdigest() != record["sha256"]:
        with urllib.request.urlopen(record["url"], timeout=60) as response:
            data = response.read(100_000_001)
        assert len(data) < 100_000_001 and hashlib.sha256(data).hexdigest() == record["sha256"], name
        target.write_bytes(data)
    record["local_path"] = str(target)
(OUT / "gemma-assets-preflight.json").write_text(json.dumps(receipt, indent=2) + "\n")
print("Pinned tokenizer assets verified; no model weights downloaded.")
