import json
import os
import sys

import numpy as np
import pytest

from medrag.config import ConfigError, Settings, active_embedding
from medrag.index.embed import ApiEmbedder, passage_text
from medrag.index.local_embed import LocalEmbedder, is_oom_error
from medrag.index.store import embed_incremental, load_vectors, save_vectors
from medrag.retrieve import load_retriever, make_embedder, make_reranker

DIM = 8


def fake_vec(text: str) -> np.ndarray:
    v = np.zeros(DIM, dtype=np.float32)
    v[len(text) % DIM] = 1.0
    v[(len(text) * 3 + 1) % DIM] += 0.5
    return v


def fake_batch(texts):
    return np.stack([fake_vec(t) for t in texts]) * 3.0  # normalize edilmemiş gelir


CHUNKS = [
    {"id": f"d#{i}", "title": "Başlık", "section": "", "text": "x" * (i * 7 + 3)} for i in range(10)
]


def local(**kw) -> LocalEmbedder:
    return LocalEmbedder("fake/model", DIM, encode_batch=fake_batch, **kw)


# --- arka uç seçimi ---
def test_backend_selection_local_is_lazy(monkeypatch):
    monkeypatch.delitem(sys.modules, "torch", raising=False)
    emb = make_embedder(Settings(embed_backend="local", local_embed_batch=4))
    assert isinstance(emb, LocalEmbedder) and emb.batch_size == 4
    assert emb._model is None  # model yalnız ilk kodlamada yüklenir
    assert "torch" not in sys.modules


def test_backend_selection_api_and_errors():
    assert isinstance(make_embedder(Settings(embed_backend="api"), "k"), ApiEmbedder)
    with pytest.raises(ConfigError):
        make_embedder(Settings(embed_backend="api"), None)
    with pytest.raises(ConfigError):
        make_embedder(Settings(embed_backend="nope"), "k")
    with pytest.raises(ConfigError):
        active_embedding(Settings(embed_backend="nope"))


def test_active_embedding_dirs_are_separate():
    api = active_embedding(Settings(embed_backend="api"))
    loc = active_embedding(Settings(embed_backend="local"))
    assert api[2].name == "index_qwen3" and loc[2].name == "index_bge_m3"
    assert loc[0] == "BAAI/bge-m3" and loc[1] == 1024


def test_reranker_backend_default_off_and_local_lazy():
    assert Settings().rerank_enabled is False
    assert make_reranker(Settings(rerank_backend="api"), None) is None
    from medrag.rerank_local import LocalReranker

    assert isinstance(make_reranker(Settings(rerank_backend="local"), None), LocalReranker)


# --- kodlama ---
def test_encode_sorted_by_length_keeps_input_order_and_normalizes():
    seen = []

    def batch(texts):
        seen.append([len(t) for t in texts])
        return fake_batch(texts)

    emb = LocalEmbedder("m", DIM, batch_size=3, encode_batch=batch)
    texts = ["a" * n for n in (5, 1, 9, 3, 7, 2, 8)]
    out = emb.encode_passages(texts)
    assert np.allclose(np.linalg.norm(out, axis=1), 1.0)
    for t, row in zip(texts, out, strict=True):
        v = fake_vec(t)
        assert np.allclose(row, v / np.linalg.norm(v))
    flat = [n for b in seen for n in b]
    assert flat == sorted(flat, reverse=True)  # uzundan kısaya gruplanır
    assert max(len(b) for b in seen) <= 3


def test_oom_shrinks_batch_and_retries():
    calls = []

    def batch(texts):
        calls.append(len(texts))
        if len(texts) > 2:
            raise RuntimeError("CUDA out of memory. Tried to allocate 2.00 GiB")
        return fake_batch(texts)

    emb = LocalEmbedder("m", DIM, batch_size=8, encode_batch=batch)
    texts = ["t" * n for n in range(1, 12)]
    out = emb.encode_passages(texts)
    assert out.shape == (11, DIM)
    assert emb.batch_size == 2 and emb.oom_retries == 2  # 8 -> 4 -> 2
    assert calls[:3] == [8, 4, 2]
    assert np.allclose(out[3], fake_vec(texts[3]) / np.linalg.norm(fake_vec(texts[3])))


def test_oom_at_batch_one_and_other_errors_propagate():
    def always_oom(texts):
        raise RuntimeError("out of memory")

    with pytest.raises(RuntimeError):
        LocalEmbedder("m", DIM, batch_size=1, encode_batch=always_oom).encode_passages(["a"])

    def broken(texts):
        raise ValueError("bozuk")

    with pytest.raises(ValueError):
        LocalEmbedder("m", DIM, batch_size=4, encode_batch=broken).encode_passages(["a"])
    assert is_oom_error(RuntimeError("CUDA out of memory")) and not is_oom_error(ValueError("x"))


def test_query_cache_and_empty():
    calls = []

    def batch(texts):
        calls.append(list(texts))
        return fake_batch(texts)

    emb = LocalEmbedder("m", DIM, encode_batch=batch)
    emb.encode_queries(["soru", "soru", "baska"])
    emb.encode_queries(["soru"])
    assert len(calls) == 1 and sorted(calls[0]) == ["baska", "soru"]  # ikinci çağrı önbellekten
    assert emb.encode_passages([]).shape == (0, DIM)


# --- indeks meta uyuşmazlığı ---
def test_index_meta_mismatch_rejected(tmp_path):
    vecs = local().encode_passages([passage_text(c) for c in CHUNKS])
    ids = [c["id"] for c in CHUNKS]
    save_vectors(tmp_path, ids, vecs, {"model": "qwen3-embedding-8b", "dimensions": DIM})
    with pytest.raises(ValueError, match="qwen3-embedding-8b"):
        load_vectors(tmp_path, CHUNKS, "BAAI/bge-m3", DIM)
    with pytest.raises(ValueError):
        load_vectors(tmp_path, CHUNKS, "qwen3-embedding-8b", DIM * 2)
    assert load_vectors(tmp_path, CHUNKS, "qwen3-embedding-8b", DIM).shape == (10, DIM)


def test_index_without_meta_rejected_when_model_checked(tmp_path):
    vecs = local().encode_passages([passage_text(c) for c in CHUNKS])
    (tmp_path).mkdir(exist_ok=True)
    save_vectors(tmp_path, [c["id"] for c in CHUNKS], vecs)
    meta = json.loads((tmp_path / "meta.json").read_text(encoding="utf-8"))
    assert "model" not in meta
    with pytest.raises(ValueError):
        load_vectors(tmp_path, CHUNKS, "BAAI/bge-m3", DIM)


# --- artımlı önbellek ---
def test_incremental_cache_with_local_embedder(tmp_path):
    emb = local(batch_size=4)
    v1, h1, s1 = embed_incremental(CHUNKS, emb, tmp_path, "fake/model", DIM, batch=4)
    assert s1.computed == 10 and s1.reused == 0
    save_vectors(
        tmp_path, [c["id"] for c in CHUNKS], v1, {"model": "fake/model", "dimensions": DIM}, h1
    )
    changed = [dict(c) for c in CHUNKS]
    changed[0]["text"] = "degisti"
    v2, _, s2 = embed_incremental(changed, local(), tmp_path, "fake/model", DIM, batch=4)
    assert (s2.computed, s2.reused) == (1, 9)
    assert np.allclose(v2[1:], v1[1:], atol=1e-3)
    # model değişirse önbellek kullanılmaz
    _, _, s3 = embed_incremental(CHUNKS, local(), tmp_path, "baska/model", DIM, batch=4)
    assert s3.computed == 10 and s3.reused == 0


# --- sunucu: anahtarsız yerel arka uç ---
def test_load_retriever_local_backend_without_api_key(tmp_path, monkeypatch):
    monkeypatch.delenv("EVREN_API_KEY", raising=False)
    data = tmp_path / "data"
    data.mkdir()
    chunks = [
        {"id": c["id"], "doc_id": "d", "title": "Grip", "section": "", "text": f"ateş öksürük {i}",
         "source": "x", "lang": "tr", "url": ""}
        for i, c in enumerate(CHUNKS)
    ]  # fmt: skip
    (data / "chunks.jsonl").write_text(
        "\n".join(json.dumps(c, ensure_ascii=False) for c in chunks), encoding="utf-8"
    )
    index = tmp_path / "idx"
    vecs = local().encode_passages([passage_text(c) for c in chunks])
    save_vectors(index, [c["id"] for c in chunks], vecs,
                 {"model": "BAAI/bge-m3", "dimensions": DIM})  # fmt: skip
    settings = Settings(
        data_dir=data, embed_backend="local", local_index_dir=index, local_embed_dimensions=DIM
    )
    retriever = load_retriever(settings)
    assert isinstance(retriever.embedder, LocalEmbedder) and retriever.embedder._model is None
    assert retriever.search("ateş", k=2, mode="bm25")  # model yüklenmeden BM25 çalışır
    with pytest.raises(ValueError):  # api indeksi/farklı model yanlışlıkla yüklenmez
        load_retriever(settings.model_copy(update={"local_embed_model": "baska/model"}))


@pytest.mark.gpu
@pytest.mark.skipif(os.environ.get("MEDRAG_GPU_TEST") != "1", reason="MEDRAG_GPU_TEST=1 gerekir")
def test_real_bge_m3_on_gpu():
    emb = LocalEmbedder("BAAI/bge-m3", 1024, batch_size=8)
    q = emb.encode_queries(["diyabet belirtileri nelerdir"])[0]
    docs = emb.encode_passages(
        ["Diyabette sık idrara çıkma ve susama görülür.", "Kırık kemik alçıyla tedavi edilir."]
    )
    assert q.shape == (1024,) and np.isclose(np.linalg.norm(q), 1.0, atol=1e-3)
    assert float(docs[0] @ q) > float(docs[1] @ q)
