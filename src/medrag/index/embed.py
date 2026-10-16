from typing import Protocol

import numpy as np


class Embedder(Protocol):
    def encode_passages(self, texts: list[str]) -> np.ndarray: ...

    def encode_queries(self, texts: list[str]) -> np.ndarray: ...


def passage_text(chunk: dict) -> str:
    """Embedding'e giden metin: başlık ve bölüm adı bağlam verir."""
    head = chunk["title"] + (f" - {chunk['section']}" if chunk["section"] else "")
    return f"{head}\n{chunk['text']}"


class E5Embedder:
    """multilingual-e5-small (CPU'da çalışır). e5 modelleri 'query: ' / 'passage: ' ön eki ister."""

    def __init__(self, model_name: str = "intfloat/multilingual-e5-small"):
        from sentence_transformers import SentenceTransformer  # opsiyonel bağımlılık

        self.model = SentenceTransformer(model_name, device="cpu")

    def _encode(self, texts: list[str], prefix: str) -> np.ndarray:
        vecs = self.model.encode(
            [prefix + t for t in texts],
            batch_size=32,
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        return np.asarray(vecs, dtype=np.float32)

    def encode_passages(self, texts: list[str]) -> np.ndarray:
        return self._encode(texts, "passage: ")

    def encode_queries(self, texts: list[str]) -> np.ndarray:
        return self._encode(texts, "query: ")
