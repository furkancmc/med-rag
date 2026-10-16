import numpy as np
import pytest

from medrag.retrieve import Retriever

CHUNKS = [
    {"id": "d1#0", "doc_id": "d1", "title": "Diyabet", "section": "", "text": "kan şekeri yükselir"},
    {"id": "d2#0", "doc_id": "d2", "title": "Grip", "section": "", "text": "ateş ve öksürük olur"},
    {"id": "d3#0", "doc_id": "d3", "title": "Astım", "section": "", "text": "nefes darlığı yapar"},
]
# Sahte 2 boyutlu uzay: "glikoz düzeyi" sorgusu kelime olarak hiçbir chunk'la eşleşmez
# ama vektör olarak Diyabet'e yakındır.
VECS = np.array([[1.0, 0.0], [0.0, 1.0], [-1.0, 0.0]], dtype=np.float32)


class FakeEmbedder:
    def encode_queries(self, texts):
        return np.array([[1.0, 0.1] for _ in texts], dtype=np.float32)

    def encode_passages(self, texts):
        raise NotImplementedError


def make():
    return Retriever(CHUNKS, VECS, FakeEmbedder())


def test_bm25_misses_synonym_but_vector_finds_it():
    r = make()
    assert r.search("glikoz düzeyi", mode="bm25") == []
    assert r.search("glikoz düzeyi", k=1, mode="vector")[0].chunk["id"] == "d1#0"


def test_hybrid_combines_both_rankings():
    r = make()
    hits = r.search("ateş", k=3, mode="hybrid")
    ids = [h.chunk["id"] for h in hits]
    assert set(ids) == {"d1#0", "d2#0", "d3#0"} or ids[0] in {"d1#0", "d2#0"}
    assert "d2#0" in ids[:2]  # kelime eşleşmesi (BM25) yukarı taşır
    assert hits[0].score >= hits[-1].score


def test_unknown_mode():
    with pytest.raises(ValueError):
        make().search("x", mode="yok")
