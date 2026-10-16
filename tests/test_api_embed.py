import numpy as np

from medrag.index.embed import QUERY_TASK, ApiEmbedder


def make(calls):
    def post(inputs):
        calls.append(list(inputs))
        return [[3.0, 4.0, 12.0, 0.0] for _ in inputs]

    return ApiEmbedder("http://x/v1/", "KEY", "m", dimensions=2, batch_size=2, post=post)


def test_batches_truncates_and_normalizes():
    calls = []
    vecs = make(calls).encode_passages(["a", "b", "c"])
    assert [len(c) for c in calls] == [2, 1]
    assert vecs.shape == (3, 2)
    assert np.allclose(np.linalg.norm(vecs, axis=1), 1.0)
    assert np.allclose(vecs[0], [0.6, 0.8])  # (3, 4) kesilip normalize edildi


def test_query_gets_instruction_prefix_but_passage_does_not():
    calls = []
    emb = make(calls)
    emb.encode_passages(["pasaj"])
    emb.encode_queries(["soru"])
    assert calls[0] == ["pasaj"]
    assert calls[1] == [f"Instruct: {QUERY_TASK}\nQuery:soru"]


def test_url():
    assert make([]).url == "http://x/v1/embeddings"


def test_parallel_batches_keep_order():
    def post(inputs):
        return [[float(t), 1.0] for t in inputs]

    emb = ApiEmbedder("http://x/v1", "K", "m", dimensions=2, batch_size=2, workers=4, post=post)
    vecs = emb.encode_passages([str(i + 1) for i in range(9)])
    order = np.argsort(vecs[:, 0] / vecs[:, 1])  # normalize oran 1..9 ile artıyor
    assert order.tolist() == list(range(9))
