"""Container-side loopback bridge to a fixed mounted Unix socket; no payload logs."""

import select
import socket
import socketserver
import threading
from pathlib import Path


class SocketBridge:
    def __init__(self, uds: Path, *, host="127.0.0.1", port=11434):
        if host != "127.0.0.1":
            raise ValueError("bridge must bind container loopback")
        self._active = set()
        self._lock = threading.Lock()
        self._closing = threading.Event()
        owner = self

        class Handler(socketserver.BaseRequestHandler):
            def handle(self):
                upstream = socket.socket(socket.AF_UNIX)
                downstream = self.request
                with owner._lock:
                    owner._active.update((upstream, downstream))
                try:
                    upstream.settimeout(1)
                    downstream.settimeout(1)
                    upstream.connect(str(uds))
                    while not owner._closing.is_set():
                        ready, _, _ = select.select([upstream, downstream], [], [], 0.1)
                        for source in ready:
                            data = source.recv(65536)
                            if not data:
                                return
                            target = downstream if source is upstream else upstream
                            target.sendall(data)
                except (OSError, ValueError):
                    pass
                finally:
                    with owner._lock:
                        owner._active.difference_update((upstream, downstream))
                    upstream.close()

        class Server(socketserver.ThreadingTCPServer):
            allow_reuse_address = True
            daemon_threads = True

        self.server = Server((host, port), Handler)
        self.port = self.server.server_address[1]

    def __enter__(self):
        self.thread = threading.Thread(
            target=self.server.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True
        )
        self.thread.start()
        return self

    def __exit__(self, *_):
        self._closing.set()
        self.server.shutdown()
        self.server.server_close()
        with self._lock:
            for connection in list(self._active):
                try:
                    connection.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass
                connection.close()
        self.thread.join(2)
