"""EmbeddingGemma 2 backend for scripts/embed_bridge.py, written from the model card.

Same parameters as the owner's local install: documents as "title: none | text: …", queries
with the model's SearchQuery prompt, normalized vectors, bfloat16 on a GPU that supports it
(float16 degrades these embeddings per the model card). Used where the local install is not
available, e.g. on a Colab GPU behind the e2-micro orchestrator (19.11.2026).
"""

import numpy as np

MODEL_ID = "google/embeddinggemma-2"


class Embedder:
    def __init__(self, model_id: str = MODEL_ID) -> None:
        self.model_id = model_id
        self._model = None

    def _load(self):
        if self._model is None:
            import torch
            from sentence_transformers import SentenceTransformer

            device = "cuda" if torch.cuda.is_available() else "cpu"
            kwargs = {}
            if device == "cuda":
                kwargs["torch_dtype"] = (
                    torch.bfloat16 if torch.cuda.is_bf16_supported() else torch.float32
                )
            self._model = SentenceTransformer(self.model_id, device=device, model_kwargs=kwargs)
        return self._model

    def documents(self, texts):
        if not texts:
            return np.zeros((0, 0), dtype=np.float32)
        prefixed = [f"title: none | text: {text}" for text in texts]
        vectors = self._load().encode(
            prefixed, batch_size=16, normalize_embeddings=True, convert_to_numpy=True
        )
        return np.asarray(vectors, dtype=np.float32)

    def query(self, text):
        vector = self._load().encode(
            text, prompt_name="SearchQuery", normalize_embeddings=True, convert_to_numpy=True
        )
        return np.asarray(vector, dtype=np.float32)
