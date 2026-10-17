import numpy as np

from medrag.eval.search_cli import build_report, parse_methods, run_methods
from medrag.llm import EvrenLLM
from medrag.multiquery import QueryExpander, parse_expansions, trim_truncated
from medrag.retrieve import Retriever, expansion_completer

CHUNKS = [
    {"id": "d1#0", "doc_id": "d1", "title": "Diyabet", "section": "", "text": "kan şekeri yükselir",
     "source": "wikipedia", "lang": "tr"},
    {"id": "d2#0", "doc_id": "d2", "title": "Grip", "section": "", "text": "ateş ve öksürük olur",
     "source": "medlineplus", "lang": "en"},
]
VECS = np.array([[1.0, 0.0], [0.0, 1.0]], dtype=np.float32)


class FakeEmbedder:
    """'flu' içeren sorguyu Grip'e, diğerlerini Diyabet'e yaklaştırır."""

    def encode_queries(self, texts):
        return np.array([[0.0, 1.0] if "flu" in t else [1.0, 0.1] for t in texts], dtype=np.float32)

    def clear_cache(self):
        pass


class FakeReranker:
    def __init__(self, scores):
        self.scores, self.calls, self.failures, self.last_error = scores, 0, 0, ""

    def rerank(self, query, chunks):
        self.calls += 1
        return self.scores


def length_post(content, reasoning="düşünüyorum", finish="length"):
    return lambda payload: {
        "choices": [{"message": {"content": content, "reasoning_content": reasoning},
                     "finish_reason": finish}]
    }


def test_trim_truncated_drops_last_partial_line():
    assert trim_truncated("a bir\nb iki\nyarım ka") == "a bir\nb iki"
    assert trim_truncated("tek satır") == "tek satır"
    assert trim_truncated("") == ""


def test_completer_trims_when_length():
    llm = EvrenLLM("http://x", "m", "k", post=length_post("English version\nTürkçe yazım\nyarım"))
    assert expansion_completer(llm)("p") == "English version\nTürkçe yazım"
    llm = EvrenLLM("http://x", "m", "k", post=length_post("English version\nTürkçe yazım", finish="stop"))
    assert expansion_completer(llm)("p") == "English version\nTürkçe yazım"


def test_completer_doubles_max_tokens_on_empty_length():
    seen = []

    def post(payload):
        seen.append(payload["max_tokens"])
        content = "" if len(seen) < 2 else "flu symptoms\nGrip belirtileri"
        return {"choices": [{"message": {"content": content, "reasoning_content": "..."},
                             "finish_reason": "length" if not content else "stop"}]}

    llm = EvrenLLM("http://x", "m", "k", post=post)
    assert expansion_completer(llm, 1000)("p") == "flu symptoms\nGrip belirtileri"
    assert seen == [1000, 2000]


def test_expander_falls_back_on_empty_reply():
    llm = EvrenLLM("http://x", "m", "k", post=length_post("", finish="length"))
    exp = QueryExpander(expansion_completer(llm, 100))
    assert exp.expand("grip belirtileri nelerdir") == []  # hata fırlatmaz, sadece orijinal sorgu
    assert exp.failures == 1 and "boş cevap" in exp.last_error


def test_parse_expansions_dedupes_original():
    out = parse_expansions("1. flu symptoms\nGrip belirtileri nelerdir\n- grip belirtileri nelerdir?",
                           "Grip belirtileri nelerdir")
    assert out == ["flu symptoms"]


def make_retriever(expander=None, reranker=None):
    return Retriever(CHUNKS, VECS, FakeEmbedder(), expander=expander, reranker=reranker)


def test_multiquery_fusion_brings_translation_hit():
    r = make_retriever(QueryExpander(lambda p: "flu symptoms\nsoğuk algınlığı yakınmaları"))
    plain = r.search("şeker", k=1, multiquery=False)
    assert [h.chunk["id"] for h in plain] == ["d1#0"]
    fused = r.search("şeker", k=2, multiquery=True)
    assert {h.chunk["id"] for h in fused} == {"d1#0", "d2#0"}


def test_multiquery_expander_error_uses_original_only():
    def boom(prompt):
        raise RuntimeError("LLM yok")

    r = make_retriever(QueryExpander(boom))
    hits = r.search("şeker", k=2, multiquery=True)
    assert hits[0].chunk["id"] == "d1#0"
    assert r.diagnostics()["multiquery"]["failures"] == 1


def test_rerank_failure_keeps_vector_order():
    r = make_retriever(reranker=FakeReranker(None))
    assert [h.chunk["id"] for h in r.search("şeker", k=2, rerank=True)] == ["d1#0", "d2#0"]


def test_parse_methods_all_and_dedupe():
    names = [m.name for m in parse_methods("all,vector")]
    assert names[:3] == ["bm25", "vector", "rerank20"] and names.count("vector") == 1
    assert "mq-rerank" in names


def test_run_methods_and_report_have_quality_and_latency():
    r = make_retriever(QueryExpander(lambda p: "flu symptoms\nGrip yakınmaları"),
                       FakeReranker([0.1, 0.9]))
    queries = [{"query": "şeker", "doc_id": "d1", "chunk_id": "d1#0", "source": "wikipedia", "lang": "tr"},
               {"query": "flu nedir", "doc_id": "d2", "chunk_id": "d2#0", "source": "medlineplus",
                "lang": "en"}]
    methods = parse_methods("vector,rerank20,mq-vector,mq-rerank")
    res = run_methods(r, queries, methods, workers=2, latency_n=2, log=lambda *_: None)
    assert list(res) == ["vector", "rerank20", "mq-vector", "mq-rerank"]
    assert res["vector"]["metrics"]["recall@1"] == 1.0
    assert res["rerank20"]["metrics"]["recall@1"] == 0.0  # sahte reranker adayların sırasını tersine çevirir
    assert res["rerank20"]["diagnostics"]["rerank"]["calls"] >= 2
    assert all(e["latency"]["mean"] >= 0 and e["latency"]["p95"] >= 0 for e in res.values())
    info = {"workers": 2, "latency_n": 2, "rerank_model": "m", "rerank_template": "qwen3",
            "rerank_doc_chars": 1500, "rerank_timeout": 60.0, "multiquery_model": "x",
            "multiquery_original_weight": 1.0}
    md, report = build_report(res, 2, info)
    assert "vector" in md and "mq-rerank" in report["methods"] and report["queries"] == 2
