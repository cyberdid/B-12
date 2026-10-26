"""Optional semantic recall over canonical memory; lexical search stays the fallback.

Vectors are a derived, rebuildable projection keyed by (actor, memory ID, embedding
model digest) in a private SQLite file. Liveness is re-checked against the canonical
store on every query, so a forgotten memory is never returned even before the purge
hook deletes its vector; a model digest change invalidates every stored vector.
"""

import asyncio
import json
import os
import sqlite3
from pathlib import Path

import numpy as np

_SCHEMA = """
CREATE TABLE IF NOT EXISTS vectors(actor_id TEXT NOT NULL, memory_id TEXT NOT NULL,
 digest TEXT NOT NULL, vector BLOB NOT NULL, PRIMARY KEY(actor_id, memory_id));
"""


class EmbeddingUnavailable(Exception):
    pass


class BridgeEmbedder:
    """Talks to scripts/embed_bridge.py running under an existing embedding app's venv."""

    def __init__(self, python: str, *, backend: str, env=None, timeout_s: float = 120):
        self.python, self.backend, self.timeout_s = python, backend, timeout_s
        # Offline: the owner's app loads its model from the local cache, never the network.
        self.env = {**os.environ, "HF_HUB_OFFLINE": "1", **(env or {})}
        self.process = None
        self.digest: str | None = None
        self._lock = asyncio.Lock()
        self._next = 0

    async def _start(self):
        script = Path(__file__).resolve().parents[2] / "scripts" / "embed_bridge.py"
        from b12.tools.process import _die_with_parent

        self.process = await asyncio.create_subprocess_exec(
            self.python,
            str(script),
            "--backend",
            self.backend,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
            env=self.env,
            preexec_fn=_die_with_parent,
            limit=64 * 1024 * 1024,
        )

    async def _call(self, request: dict) -> dict:
        async with self._lock:
            try:
                if self.process is None or self.process.returncode is not None:
                    await self._start()
                self._next += 1
                request = {"id": self._next, **request}
                self.process.stdin.write(json.dumps(request).encode() + b"\n")
                await self.process.stdin.drain()
                line = await asyncio.wait_for(self.process.stdout.readline(), self.timeout_s)
            except (OSError, TimeoutError, ValueError) as exc:
                self.close()
                raise EmbeddingUnavailable(type(exc).__name__) from exc
            if not line:
                self.close()
                raise EmbeddingUnavailable("bridge_exited")
            reply = json.loads(line)
            if reply.get("id") != request["id"] or "error" in reply:
                raise EmbeddingUnavailable(str(reply.get("error", "protocol")))
            return reply

    async def resolve_digest(self) -> str:
        info = (await self._call({"op": "info"}))["info"]
        self.digest = f"{info['model_id']}@{info['package']}"
        return self.digest

    async def documents(self, texts: list[str]) -> np.ndarray:
        return self._matrix(
            (await self._call({"op": "documents", "texts": texts}))["vectors"], texts
        )

    async def query(self, text: str) -> np.ndarray:
        return self._matrix((await self._call({"op": "query", "text": text}))["vectors"], [text])[0]

    @staticmethod
    def _matrix(vectors, texts) -> np.ndarray:
        matrix = np.asarray(vectors, dtype=np.float32)
        if matrix.ndim != 2 or len(matrix) != len(texts):
            raise EmbeddingUnavailable("malformed embeddings")
        norms = np.linalg.norm(matrix, axis=1, keepdims=True)
        return matrix / np.where(norms == 0, 1, norms)

    def close(self):
        if self.process is not None and self.process.returncode is None:
            self.process.kill()
        self.process = None

    async def aclose(self):
        process, self.process = self.process, None
        if process is not None and process.returncode is None:
            process.kill()
            await process.wait()


class SemanticIndex:
    # EmbeddingGemma 2 (measured 26.10.2026): relevant ~0.79-0.85, unrelated ~0.60-0.69.
    def __init__(
        self, path: Path, embedder: BridgeEmbedder, memory, *, batch: int = 32, min_score=0.7
    ):
        self.min_score = min_score
        self.path = Path(path)
        self.path.mkdir(mode=0o700, parents=True, exist_ok=True)
        db = self.path / "vectors.sqlite3"
        fd = os.open(db, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        os.close(fd)
        self.db = sqlite3.connect(db, isolation_level=None)
        self.db.execute("PRAGMA secure_delete=ON")
        self.db.executescript(_SCHEMA)
        self.embedder, self.memory, self.batch = embedder, memory, batch

    def close(self):
        self.embedder.close()
        self.db.close()

    async def sync(self, actor, *, limit: int = 1000) -> int:
        """Embed live memories lacking a vector for the current model digest."""
        digest = self.embedder.digest or await self.embedder.resolve_digest()
        self.db.execute("DELETE FROM vectors WHERE actor_id=? AND digest!=?", (actor.id, digest))
        known = {
            row[0]
            for row in self.db.execute(
                "SELECT memory_id FROM vectors WHERE actor_id=?", (actor.id,)
            )
        }
        missing = [r for r in self.memory.recent(actor, limit=limit) if r.id not in known]
        for start in range(0, len(missing), self.batch):
            chunk = missing[start : start + self.batch]
            vectors = await self.embedder.documents([r.text for r in chunk])
            self.db.executemany(
                "INSERT OR REPLACE INTO vectors VALUES (?,?,?,?)",
                [
                    (actor.id, r.id, digest, v.tobytes())
                    for r, v in zip(chunk, vectors, strict=True)
                ],
            )
        return len(missing)

    async def warm_up(self) -> None:
        """Load the model before the first user turn (cold load measured ~16 s)."""
        await self.embedder.resolve_digest()
        await self.embedder.query("warm up")

    async def search(self, query: str, actor, *, k: int = 5, min_score: float | None = None):
        min_score = self.min_score if min_score is None else min_score
        await self.sync(actor)
        rows = self.db.execute(
            "SELECT memory_id, vector FROM vectors WHERE actor_id=?", (actor.id,)
        ).fetchall()
        if not rows:
            return []
        matrix = np.frombuffer(b"".join(r[1] for r in rows), dtype=np.float32).reshape(
            len(rows), -1
        )
        query_vector = await self.embedder.query(query)
        scores = matrix @ query_vector
        ranked = []
        for index in np.argsort(-scores):
            memory_id = rows[index][0]
            if scores[index] < min_score or len(ranked) >= k:
                break
            if self.memory.is_live(memory_id, actor):  # canonical liveness, every query
                ranked.append((memory_id, float(scores[index])))
        return ranked

    def purge(self, actor_id: str, memory_ids) -> None:
        self.db.executemany(
            "DELETE FROM vectors WHERE actor_id=? AND memory_id=?",
            [(actor_id, m) for m in memory_ids],
        )
