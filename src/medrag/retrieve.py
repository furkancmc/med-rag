import os
from dataclasses import dataclass

import numpy as np

from .config import Settings
from .index.bm25 import BM25
from .index.embed import ApiEmbedder, Embedder
from .index.store import load_chunks, load_vectors
from .index.tokenize import tokenize
from .ingest.build import build_chunks

RRF_K = 60  # sıralama birleştirmede standart sabit


@dataclass
class Hit:
    chunk: dict
    score: float


def bm25_text(chunk: dict) -> str:
    return f"{chunk['title']} {chunk['section']} {chunk['text']}"


class Retriever:
    def __init__(self, chunks: list[dict], vectors: np.ndarray, embedder: Embedder):
        self.chunks = chunks
        self.vectors = vectors
        self.embedder = embedder
        self.bm25 = BM25([tokenize(bm25_text(c)) for c in chunks])

    def _bm25_ranking(self, query: str, n: int) -> list[int]:
        return [i for i, _ in self.bm25.search(tokenize(query), n)]

    def _vector_ranking(self, query: str, n: int) -> list[int]:
        q = self.embedder.encode_queries([query])[0]
        scores = self.vectors @ q
        top = np.argpartition(-scores, min(n, len(scores) - 1))[:n]
        return [int(i) for i in top[np.argsort(-scores[top])]]

    def search(self, query: str, k: int = 5, mode: str = "hybrid", pool: int = 50) -> list[Hit]:
        if mode == "bm25":
            ranked = [(i, 1.0) for i in self._bm25_ranking(query, k)]
        elif mode == "vector":
            ranked = [(i, 1.0) for i in self._vector_ranking(query, k)]
        elif mode == "hybrid":
            fused: dict[int, float] = {}
            for ranking in (self._bm25_ranking(query, pool), self._vector_ranking(query, pool)):
                for rank, i in enumerate(ranking):
                    fused[i] = fused.get(i, 0.0) + 1.0 / (RRF_K + rank + 1)
            ranked = sorted(fused.items(), key=lambda x: x[1], reverse=True)[:k]
        else:
            raise ValueError(f"bilinmeyen mod: {mode}")
        return [Hit(self.chunks[i], score) for i, score in ranked]


def load_retriever(settings: Settings) -> Retriever:
    api_key = os.environ.get("EVREN_API_KEY")
    if not api_key:
        raise RuntimeError("EVREN_API_KEY ortam değişkeni tanımlı değil")
    if not (settings.data_dir / "chunks.jsonl").exists():
        build_chunks(settings.data_dir)  # data/raw'dan deterministik olarak üretilir
    chunks = load_chunks(settings.data_dir)
    vectors = load_vectors(settings.index_dir, chunks)
    embedder = ApiEmbedder(
        settings.embed_api_url, api_key, settings.embed_api_model, settings.embed_dimensions
    )
    return Retriever(chunks, vectors, embedder)
