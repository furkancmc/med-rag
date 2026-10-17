import numpy as np

from medrag.eval.metrics import evaluate, first_relevant_rank, format_table
from medrag.eval.queries import clean_question, generate_queries, sample_chunks
from medrag.index.embed import CachingEmbedder


def chunk(i, source="wikipedia", lang="tr", words=80):
    return {"id": f"d{i}#0", "doc_id": f"d{i}", "title": f"T{i}", "source": source,
            "lang": lang, "text": " ".join(["kelime"] * words)}


def test_sample_respects_quotas_and_min_words_and_unique_docs():
    chunks = [chunk(i) for i in range(30)]
    chunks += [chunk(100 + i, "medlineplus", "en") for i in range(30)]
    chunks += [chunk(200 + i, "wikipedia", "en") for i in range(30)]
    chunks.append(chunk(999, words=5))  # çok kısa, seçilmemeli
    picked = sample_chunks(chunks, 10)
    assert len(picked) == 10
    assert all(c["doc_id"] != "d999" for c in picked)
    assert len({c["doc_id"] for c in picked}) == 10
    assert sample_chunks(chunks, 10) == picked  # deterministik


def test_build_queries_keeps_existing_and_balances_groups():
    from medrag.eval.queries import build_queries

    chunks = [chunk(i) for i in range(40)] + [chunk(100 + i, "medlineplus", "en") for i in range(40)]
    old = [{"query": "Eski soru bir mi?", "chunk_id": "d0#0", "doc_id": "d0"},
           {"query": "Eski soru iki mi?", "chunk_id": "d100#0", "doc_id": "d100"}]
    counter = iter(range(1000))
    rows = build_queries(chunks, 20, lambda p: f"Tamamen farklı {next(counter)} numaralı soru nedir?",
                         workers=1, existing=old)
    assert rows[0]["query"] == "Eski soru bir mi?" and rows[1]["doc_id"] == "d100"
    assert rows[0]["source"] == "wikipedia"  # eski satıra kaynak eklendi
    assert len(rows) == 20 and len({r["doc_id"] for r in rows}) == 20  # eski dokümanlar tekrar seçilmez
    wiki = sum(r["source"] == "wikipedia" for r in rows)
    assert abs(wiki - (20 - wiki)) <= 2


def test_dedupe_protects_existing_rows():
    from medrag.eval.queries import dedupe_queries

    rows = [{"query": "Grip nedir bilgi ver"}, {"query": "Grip nedir bilgi ver"},
            {"query": "Grip nedir bilgi ver?"}]
    assert len(dedupe_queries(rows, protected=2)) == 2
    assert len(dedupe_queries(rows)) == 1


def test_clean_question():
    assert clean_question('\n  "Şeker hastalığı neden olur?"\nAçıklama') == "Şeker hastalığı neden olur?"


def test_generate_skips_failures_and_short_outputs():
    chunks = [chunk(1), chunk(2), chunk(3)]

    def complete(prompt):
        if "T1" in prompt:
            raise RuntimeError("hata")
        return "x" if "T2" in prompt else "Grip belirtileri nelerdir?"

    rows = generate_queries(chunks, complete, workers=1)
    assert [r["doc_id"] for r in rows] == ["d3"]


def test_metrics():
    assert first_relevant_rank(["a", "b", "c"], "c") == 3
    assert first_relevant_rank(["a"], "z") is None
    queries = [{"query": "q1", "doc_id": "a"}, {"query": "q2", "doc_id": "b"}]
    ranking = {"q1": [{"doc_id": "a"}], "q2": [{"doc_id": "x"}, {"doc_id": "b"}]}
    r = evaluate(queries, lambda q: ranking[q])
    assert r["recall@1"] == 0.5 and r["recall@3"] == 1.0
    assert abs(r["mrr@10"] - 0.75) < 1e-9
    assert "| bm25 |" in format_table({"bm25": r})


def test_caching_embedder_calls_inner_once():
    calls = []

    class Inner:
        def encode_queries(self, texts):
            calls.append(list(texts))
            return np.array([[float(len(t))] for t in texts])

    emb = CachingEmbedder(Inner())
    emb.encode_queries(["ab", "abc"])
    out = emb.encode_queries(["abc", "ab"])
    assert calls == [["ab", "abc"]]
    assert out.tolist() == [[3.0], [2.0]]
