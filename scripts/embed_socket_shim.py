#!/usr/bin/env python3
"""Stand-in for the embedding interpreter inside the eval sandbox: BridgeEmbedder runs
`<this> embed_bridge.py --backend …`; the arguments are ignored and stdin/stdout are relayed to
the Unix socket in B12_EVAL_EMBED_SOCKET (an embedding server reached by the orchestrator).
Stdlib only, so the sandbox's system Python can run it."""

import os
import socket
import sys
import threading


def main():
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock.connect(os.environ["B12_EVAL_EMBED_SOCKET"])

    def upstream():
        for line in sys.stdin.buffer:
            sock.sendall(line)
        sock.shutdown(socket.SHUT_WR)

    threading.Thread(target=upstream, daemon=True).start()
    reader = sock.makefile("rb")
    for line in reader:
        sys.stdout.buffer.write(line)
        sys.stdout.buffer.flush()


if __name__ == "__main__":
    main()
