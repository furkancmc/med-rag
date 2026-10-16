import numpy as np
import pytest

from medrag.index.embed import passage_text
from medrag.index.store import build_vectors, load_vectors, save_vectors


class FakeEmbedder:
    def encode_passages(self, texts):
        return np.array([[len(t), 1.0] for t in texts], dtype=np.float32)

    def encode_queries(self, texts):
        return self.encode_passages(texts)


CHUNKS = [
    {"id": "a#0", "title": "Grip", "section": "", "text": "ateş"},
    {"id": "b#0", "title": "Astım", "section": "Belirtiler", "text": "nefes darlığı"},
]


def test_passage_text_includes_title_and_section():
    assert passage_text(CHUNKS[1]) == "Astım - Belirtiler\nnefes darlığı"
    assert passage_text(CHUNKS[0]) == "Grip\nateş"


def test_build_in_batches_keeps_order():
    vecs = build_vectors(CHUNKS, FakeEmbedder(), batch=1)
    assert vecs.shape == (2, 2)
    assert vecs[0][0] == len(passage_text(CHUNKS[0]))


def test_roundtrip_and_mismatch(tmp_path):
    vecs = build_vectors(CHUNKS, FakeEmbedder())
    save_vectors(tmp_path, [c["id"] for c in CHUNKS], vecs)
    loaded = load_vectors(tmp_path, CHUNKS)
    assert np.allclose(np.linalg.norm(loaded, axis=1), 1.0, atol=1e-3)  # L2-normalize döner
    assert np.allclose(loaded, vecs / np.linalg.norm(vecs, axis=1, keepdims=True), atol=1e-2)
    with pytest.raises(ValueError):
        load_vectors(tmp_path, CHUNKS[:1])
