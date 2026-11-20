"""Pick (or create) the profile file for the model revision a remote Ollama serves.

A served digest equal to a calibrated profile's uses that profile. A new digest of the same tag
gets a copy of the tag's profile with that digest, only if the chat template is identical
(checked by the runtime at the first request). Prints the profile file name.
"""

import json
import sys
from pathlib import Path

BASE = {
    "gemma4:12b": "gemma4-12b-ollama-0.33.3.json",
    "gemma4:26b": "gemma4-26b-ollama-0.33.3.json",
    "gemma4:31b": "gemma4-31b-ollama-0.33.3.json",
}
PROFILES = Path.home() / ".local/share/b12/profiles"


def main():
    model, tags = sys.argv[1], json.loads(Path(sys.argv[2]).read_text())
    digest = next(m["digest"] for m in tags["models"] if m["name"] == model)
    for path in sorted(PROFILES.glob("*.json")):
        spec = json.loads(path.read_text())
        if spec.get("model") == model and spec.get("manifest_digest") == digest:
            print(path.name)
            return
    spec = json.loads((PROFILES / BASE[model]).read_text())
    spec["manifest_digest"] = digest
    name = (
        f"{BASE[model].removesuffix('-ollama-0.33.3.json')}-remote-{digest[:8]}-ollama-0.33.3.json"
    )
    (PROFILES / name).write_text(json.dumps(spec, indent=2))
    print(name)


if __name__ == "__main__":
    main()
