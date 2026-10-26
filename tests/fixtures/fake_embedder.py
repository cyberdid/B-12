"""Deterministic hashed bag-of-words embedder with the archive-index Embedder interface."""

import hashlib
import re

import numpy as np


class HashEmbedder:
    model_id = "test/hash-embedder"

    def _vector(self, text):
        vector = np.zeros(64, dtype=np.float32)
        for word in re.findall(r"[^\W_]+", text.lower()):
            vector[int(hashlib.sha256(word.encode()).hexdigest(), 16) % 64] += 1.0
        norm = np.linalg.norm(vector)
        return vector / norm if norm else vector

    def documents(self, texts):
        return np.stack([self._vector(t) for t in texts])

    def query(self, text):
        return self._vector(text)
