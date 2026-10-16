"""Kompakt saklama (int8), geriye uyumluluk ve artımlı embedding."""

import json

import numpy as np

from medrag.index.embed import passage_text
from medrag.index.store import (
    dequantize_int8,
    embed_incremental,
    load_vectors,
    passage_hash,
    quantize_int8,
    save_vectors,
)

DIM = 32


def chunk(i: int, text: str | None = None) -> dict:
    return {"id": f"d#{i}", "title": f"T{i}", "section": "", "text": text or f"metin {i}"}


class CountingEmbedder:
    """Metinden belirlenimci (hash tabanlı) vektör üretir; çağrılan metinleri sayar."""

    def __init__(self):
        self.calls: list[str] = []

    def encode_passages(self, texts):
        self.calls += texts
        out = []
        for t in texts:
            rng = np.random.default_rng(abs(hash(t)) % (2**32))
            out.append(rng.normal(size=DIM))
        v = np.asarray(out, dtype=np.float32)
        return v / np.linalg.norm(v, axis=1, keepdims=True)

    encode_queries = encode_passages


def random_unit(n: int, dim: int = 1024, seed: int = 0) -> np.ndarray:
    v = np.random.default_rng(seed).normal(size=(n, dim)).astype(np.float32)
    return v / np.linalg.norm(v, axis=1, keepdims=True)


def test_int8_roundtrip_cosine_error_tiny():
    v = random_unit(200)
    q, s = quantize_int8(v)
    assert q.dtype == np.int8
    back = dequantize_int8(q, s)
    back /= np.linalg.norm(back, axis=1, keepdims=True)
    cos = (v * back).sum(axis=1)
    assert cos.min() > 0.9995
    # sıralama korunur: sorgu benzerliklerinin en yükseği aynı kalır
    queries = random_unit(20, seed=1)
    assert (np.argmax(queries @ v.T, axis=1) == np.argmax(queries @ back.T, axis=1)).mean() >= 0.95


def test_save_picks_int8_when_large_and_loads_normalized(tmp_path):
    chunks = [chunk(i) for i in range(50)]
    v = random_unit(50, DIM)
    fmt = save_vectors(tmp_path, [c["id"] for c in chunks], v, {"model": "m"}, max_float16_mb=0)
    assert fmt == "int8"
    assert (tmp_path / "scales.npy").exists()
    assert json.loads((tmp_path / "meta.json").read_text())["format"] == "int8"
    loaded = load_vectors(tmp_path, chunks)
    assert loaded.dtype == np.float32
    assert np.allclose(np.linalg.norm(loaded, axis=1), 1.0, atol=1e-3)
    assert (loaded * v).sum(axis=1).min() > 0.999
    # küçük indeks float16 kalır ve eski scales dosyası temizlenir
    assert save_vectors(tmp_path, [c["id"] for c in chunks], v) == "float16"
    assert not (tmp_path / "scales.npy").exists()


def test_loads_legacy_float16_without_hashes_or_format(tmp_path):
    chunks = [chunk(0), chunk(1)]
    v = random_unit(2, DIM)
    np.save(tmp_path / "vectors.npy", v.astype(np.float16))  # eski biçim
    (tmp_path / "ids.json").write_text(json.dumps([c["id"] for c in chunks]))
    (tmp_path / "meta.json").write_text(json.dumps({"model": "m", "dimensions": DIM}))
    assert np.allclose(load_vectors(tmp_path, chunks), v, atol=1e-2)


def test_incremental_reuses_unchanged_chunks(tmp_path):
    chunks = [chunk(i) for i in range(5)]
    emb = CountingEmbedder()
    vecs, hashes, stats = embed_incremental(chunks, emb, tmp_path, "m", DIM)
    assert stats.computed == 5 and stats.reused == 0
    save_vectors(tmp_path, [c["id"] for c in chunks], vecs, {"model": "m", "dimensions": DIM}, hashes)

    # bir chunk değişti, biri eklendi, biri silindi
    new = [chunk(0), chunk(1, "değişti"), chunk(2), chunk(3), chunk(9)]
    emb2 = CountingEmbedder()
    vecs2, hashes2, stats2 = embed_incremental(new, emb2, tmp_path, "m", DIM)
    assert stats2.computed == 2 and stats2.reused == 3 and stats2.dropped == 2
    assert sorted(emb2.calls) == sorted([passage_text(new[1]), passage_text(new[4])])
    assert vecs2.shape == (5, DIM)
    assert np.allclose(vecs2[0], vecs[0], atol=1e-2)  # float16 turu sonrası aynı
    assert hashes2[0] == hashes[0] and hashes2[1] != hashes[1]


def test_incremental_invalidated_by_model_change(tmp_path):
    chunks = [chunk(i) for i in range(3)]
    vecs, hashes, _ = embed_incremental(chunks, CountingEmbedder(), tmp_path, "m", DIM)
    save_vectors(tmp_path, [c["id"] for c in chunks], vecs, {"model": "m", "dimensions": DIM}, hashes)
    emb = CountingEmbedder()
    _, _, stats = embed_incremental(chunks, emb, tmp_path, "baska-model", DIM)
    assert stats.computed == 3 and stats.reused == 0
    assert passage_hash(chunks[0], "m", DIM) != passage_hash(chunks[0], "baska-model", DIM)


def test_incremental_trust_legacy_and_dedup_within_run(tmp_path):
    chunks = [chunk(0), chunk(1), chunk(2, "metin 0")]  # 2 numara ile 0 aynı başlık? hayır: başlık farklı
    chunks[2]["title"] = chunks[0]["title"]  # aynı passage metni
    v = random_unit(2, DIM)
    np.save(tmp_path / "vectors.npy", v.astype(np.float16))
    (tmp_path / "ids.json").write_text(json.dumps(["d#0", "d#1"]))
    (tmp_path / "meta.json").write_text(json.dumps({"model": "m", "dimensions": DIM}))
    emb = CountingEmbedder()
    _, _, stats = embed_incremental(chunks, emb, tmp_path, "m", DIM)  # güvensiz: hepsi yeni
    assert stats.computed == 2  # d#0 ile d#2 aynı metin: tek istek
    emb2 = CountingEmbedder()
    _, _, stats2 = embed_incremental(chunks, emb2, tmp_path, "m", DIM, trust_legacy=True)
    assert stats2.computed == 0 and emb2.calls == []
