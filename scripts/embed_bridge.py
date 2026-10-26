"""Stdio embedding bridge, run by the interpreter of an existing embedding app.

  /path/to/app/venv/bin/python scripts/embed_bridge.py [--backend module:Class]
Default backend: archive_index.embed:Embedder (the owner's archive-index install,
EmbeddingGemma 2). The backend is imported from that interpreter; no code is copied.
Protocol: one JSON object per line. Requests {"id", "op": "info"|"documents"|"query",
"texts"/"text"}; responses {"id", "info"} | {"id", "vectors"} | {"id", "error"}.
"""

import argparse
import importlib
import importlib.metadata
import json
import sys


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--backend", default="archive_index.embed:Embedder")
    args = parser.parse_args()
    module_name, _, class_name = args.backend.partition(":")
    embedder = getattr(importlib.import_module(module_name), class_name)()
    package = module_name.split(".")[0]
    try:
        version = importlib.metadata.version(package)
    except importlib.metadata.PackageNotFoundError:
        version = "unknown"
    for line in sys.stdin:
        if not line.strip():
            continue
        request = json.loads(line)
        try:
            if request["op"] == "info":
                reply = {
                    "info": {"model_id": embedder.model_id, "package": f"{package}=={version}"}
                }
            elif request["op"] == "documents":
                reply = {"vectors": embedder.documents(request["texts"]).tolist()}
            elif request["op"] == "query":
                reply = {"vectors": [embedder.query(request["text"]).tolist()]}
            else:
                reply = {"error": "unknown_op"}
        except Exception as exc:  # report the type only; texts may be private
            reply = {"error": type(exc).__name__}
        sys.stdout.write(json.dumps({"id": request.get("id"), **reply}) + "\n")
        sys.stdout.flush()


if __name__ == "__main__":
    main()
