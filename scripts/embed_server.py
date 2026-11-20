"""TCP embedding server for a GPU host: the embed_bridge.py protocol over one connection per
runtime, with the model loaded once. Listens on 127.0.0.1 only; reached through an SSH tunnel.

    python embed_server.py --backend st_embedder:Embedder --port 11436
"""

import argparse
import importlib
import json
import socketserver
import threading


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--backend", default="st_embedder:Embedder")
    parser.add_argument("--port", type=int, default=11436)
    args = parser.parse_args()
    module_name, _, class_name = args.backend.partition(":")
    embedder = getattr(importlib.import_module(module_name), class_name)()
    embedder.documents(["warm-up"])  # load the model before the first client
    lock = threading.Lock()

    class Handler(socketserver.StreamRequestHandler):
        def handle(self):
            for line in self.rfile:
                if not line.strip():
                    continue
                request = json.loads(line)
                try:
                    with lock:
                        if request["op"] == "info":
                            reply = {
                                "info": {
                                    "model_id": embedder.model_id,
                                    "package": "b12-st-embedder",
                                }
                            }
                        elif request["op"] == "documents":
                            reply = {"vectors": embedder.documents(request["texts"]).tolist()}
                        elif request["op"] == "query":
                            reply = {"vectors": [embedder.query(request["text"]).tolist()]}
                        else:
                            reply = {"error": "unknown_op"}
                except Exception as exc:  # the type only; texts may be private
                    reply = {"error": type(exc).__name__}
                self.wfile.write((json.dumps({"id": request.get("id"), **reply}) + "\n").encode())
                self.wfile.flush()

    class Server(socketserver.ThreadingTCPServer):
        allow_reuse_address = True
        daemon_threads = True

    with Server(("127.0.0.1", args.port), Handler) as server:
        server.serve_forever()


if __name__ == "__main__":
    main()
