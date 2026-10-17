"""Yalnızca BM25 ile arama yapan hafif arama (embedding/rerank çağrısı yok).

Uçtan uca senaryo testlerinde maliyetli embedding çağrılarına gerek kalmadan kaynaklı akışı denemek içindir.
`Retriever.search(query, k)` imzasıyla uyumludur.
"""

from pathlib import Path

from medrag.index.bm25 import BM25
from medrag.index.store import load_chunks
from medrag.index.tokenize import tokenize
from medrag.retrieve import Hit, bm25_text


class Bm25OnlyRetriever:
    def __init__(self, chunks: list[dict]):
        self.chunks = chunks
        self.bm25 = BM25([tokenize(bm25_text(c)) for c in chunks])

    def search(self, query: str, k: int = 5, **_ignored) -> list[Hit]:
        return [Hit(self.chunks[i], float(s)) for i, s in self.bm25.search(tokenize(query), k)]


def load_bm25_retriever(data_dir: Path) -> Bm25OnlyRetriever:
    """data_dir/chunks.jsonl yoksa ham veriden üretir (ağ gerekmez)."""
    if not (data_dir / "chunks.jsonl").exists():
        from medrag.ingest.build import build_chunks

        build_chunks(data_dir)
    return Bm25OnlyRetriever(load_chunks(data_dir))
