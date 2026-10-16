import io
import json
import logging
import threading
import urllib.error

import pytest

from medrag import rerank as rerank_mod
from medrag.rerank import (
    QWEN3_PREFIX,
    QWEN3_SUFFIX,
    ApiReranker,
    RerankError,
    apply_template,
    format_document,
    parse_scores,
    truncate,
)

CHUNKS = [
    {"title": f"Başlık{i}", "section": "Bölüm" if i % 2 else "", "text": f"metin {i} " * 5}
    for i in range(45)
]


def doc_index(doc: str) -> int:
    """Sahte servis: dokümandaki 'metin N' sayısından N'yi çıkarır (şablon sarmalayıcıları dahil)."""
    return int(doc.split("metin ")[1].split()[0])


def make(post=None, **kw):
    return ApiReranker("http://x/v1/", "KEY", post=post, **kw)


def fake_scores(payload):
    """Her doküman için puan = N / 100 (büyük N daha alakalı); index grup içi sıradır."""
    return {
        "results": [
            {"index": i, "relevance_score": doc_index(d) / 100}
            for i, d in enumerate(payload["documents"])
        ]
    }


# --- Ayrıştırma ---
def test_parse_relevance_score_and_score_keys():
    assert parse_scores({"results": [{"index": 1, "relevance_score": 0.2}, {"index": 0, "score": 0.9}]}, 2) == [
        0.9,
        0.2,
    ]


def test_parse_zero_score_is_kept():
    # 0.0 geçerli bir puandır ("falsy" diye atılmamalı)
    assert parse_scores({"results": [{"index": 0, "relevance_score": 0.0, "score": 0.7}]}, 1) == [0.0]


def test_parse_missing_indices_stay_none():
    out = parse_scores({"results": [{"index": 2, "relevance_score": 0.5}]}, 3)
    assert out == [None, None, 0.5]


def test_parse_ignores_out_of_range_duplicates_and_garbage():
    data = {
        "results": [
            {"index": 7, "relevance_score": 1.0},  # aralık dışı
            {"index": -1, "relevance_score": 1.0},
            "bozuk",
            {"index": 0, "relevance_score": float("nan")},
            {"index": 1, "relevance_score": True},  # bool puan değildir
            {"index": 1, "relevance_score": "0.5"},  # metin puan kabul edilmez
            {"index": 2, "relevance_score": 3},
        ]
    }
    assert parse_scores(data, 3) == [None, None, 3.0]


def test_parse_without_index_uses_position_when_complete():
    data = {"results": [{"relevance_score": 0.1}, {"relevance_score": 0.8}]}
    assert parse_scores(data, 2) == [0.1, 0.8]
    with pytest.raises(RerankError):  # index yok, sayı uyuşmuyor: puan eşlenemez
        parse_scores({"results": [{"relevance_score": 0.1}]}, 2)


def test_parse_accepts_data_key_and_bare_list():
    assert parse_scores({"data": [{"index": 0, "score": 0.3}]}, 1) == [0.3]
    assert parse_scores([{"index": 0, "relevance_score": 0.4}], 1) == [0.4]


@pytest.mark.parametrize("bad", [None, "x", {}, {"results": []}, {"results": "x"}, {"error": "boom"}])
def test_parse_raises_without_any_valid_score(bad):
    with pytest.raises(RerankError):
        parse_scores(bad, 2)


# --- Metin hazırlama ---
def test_truncate_cuts_at_word_boundary():
    text = "kelime " * 100
    out = truncate(text, 50)
    assert out.endswith("…") and len(out) <= 52
    assert "kelim " not in out  # kelime ortadan bölünmedi
    assert truncate("kısa", 50) == "kısa"


def test_format_document_has_title_section_and_limited_text():
    doc = format_document({"title": "Diyabet", "section": "Belirtiler", "text": "x " * 2000}, 300)
    assert doc.startswith("Diyabet - Belirtiler\n")
    assert len(doc) < 330
    assert format_document({"title": "T", "section": "", "text": "gövde"}, 300) == "T\ngövde"


def test_template_none_is_raw_and_qwen3_wraps_query_and_docs():
    q, docs = apply_template("soru", ["a", "b"], "none", "talimat")
    assert q == "soru" and docs == ["a", "b"]
    q, docs = apply_template("soru", ["a", "b"], "qwen3", "talimat")
    assert q.startswith(QWEN3_PREFIX) and "<Instruct>: talimat" in q and "<Query>: soru" in q
    assert docs[0] == f"<Document>: a{QWEN3_SUFFIX}"
    with pytest.raises(ValueError):
        apply_template("soru", ["a"], "yok", "")
    with pytest.raises(ValueError):
        make(template="yok")


# --- Yeniden sıralama, gruplama ---
def test_payload_shape_and_url():
    seen = []

    def post(payload):
        seen.append(payload)
        return fake_scores(payload)

    r = make(post, model="qwen3-reranker-8b", template="none")
    assert r.url == "http://x/v1/rerank"
    r.rerank("soru", CHUNKS[:2])
    payload = seen[0]
    assert set(payload) == {"model", "query", "documents"}
    assert payload["model"] == "qwen3-reranker-8b" and payload["query"] == "soru"
    assert payload["documents"][0].startswith("Başlık0\nmetin 0")


def test_large_pool_is_split_into_batches_in_order():
    sizes, lock = [], threading.Lock()

    def post(payload):
        with lock:
            sizes.append(len(payload["documents"]))
        return fake_scores(payload)

    r = make(post, batch_size=20, template="none")
    scores = r.rerank("soru", CHUNKS)
    assert sorted(sizes) == [5, 20, 20]
    assert scores == [i / 100 for i in range(45)]  # sıra korundu


def test_batches_run_in_parallel():
    barrier = threading.Barrier(3, timeout=5)  # 3 grup aynı anda içeride olmalı

    def post(payload):
        barrier.wait()
        return fake_scores(payload)

    r = make(post, batch_size=20, template="none", workers=8)
    assert len(r.rerank("soru", CHUNKS)) == 45


def test_missing_scores_in_response_become_none():
    def post(payload):
        return {"results": [{"index": 0, "relevance_score": 0.5}]}

    assert make(post, template="none").rerank("s", CHUNKS[:3]) == [0.5, None, None]


def test_empty_candidates_make_no_request():
    def post(payload):
        raise AssertionError("istek atılmamalı")

    assert make(post).rerank("s", []) == []


# --- Hata durumunda geri düşüş ---
def test_failure_returns_none_and_logs_once(caplog):
    def post(payload):
        raise RerankError("HTTP 500")

    r = make(post, template="none")
    with caplog.at_level(logging.WARNING, logger="medrag.rerank"):
        assert r.rerank("s", CHUNKS[:3]) is None
        assert r.rerank("s", CHUNKS[:3]) is None
    warnings = [m for m in caplog.records if m.levelno == logging.WARNING]
    assert len(warnings) == 1 and "vektör sırası" in warnings[0].getMessage()
    assert "KEY" not in warnings[0].getMessage()
    assert r.failures == 2 and r.calls == 2 and "HTTP 500" in r.last_error


def test_logs_again_after_recovery(caplog):
    state = {"fail": True}

    def post(payload):
        if state["fail"]:
            raise RerankError("kesinti")
        return fake_scores(payload)

    r = make(post, template="none")
    with caplog.at_level(logging.WARNING, logger="medrag.rerank"):
        assert r.rerank("s", CHUNKS[:2]) is None
        state["fail"] = False
        assert r.rerank("s", CHUNKS[:2]) is not None
        state["fail"] = True
        assert r.rerank("s", CHUNKS[:2]) is None
    assert len([m for m in caplog.records if m.levelno == logging.WARNING]) == 2


def test_one_failed_batch_fails_whole_rerank():
    calls = []

    def post(payload):
        calls.append(1)
        if len(calls) == 2:
            raise RerankError("tek grup düştü")
        return fake_scores(payload)

    assert make(post, batch_size=20, template="none", workers=1).rerank("s", CHUNKS) is None


def test_unparseable_response_returns_none():
    assert make(lambda p: {"foo": 1}).rerank("s", CHUNKS[:2]) is None


def test_slow_service_times_out_and_returns_none():
    release = threading.Event()

    def post(payload):
        release.wait(5)
        return fake_scores(payload)

    r = make(post, timeout=0.2, template="none")
    try:
        assert r.rerank("s", CHUNKS[:2]) is None
        assert "zaman aşımı" in r.last_error
    finally:
        release.set()


# --- HTTP katmanı (urlopen sahte) ---
class FakeResponse:
    def __init__(self, body):
        self.body = body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def read(self):
        return json.dumps(self.body).encode()


def http_error(code, body="hata ayrıntısı"):
    return urllib.error.HTTPError("http://x", code, "msg", {}, io.BytesIO(body.encode()))


def patch_urlopen(monkeypatch, outcomes, requests=None):
    outcomes = list(outcomes)

    def fake_urlopen(req, timeout):
        if requests is not None:
            requests.append((req, timeout))
        out = outcomes.pop(0)
        if isinstance(out, Exception):
            raise out
        return FakeResponse(out)

    monkeypatch.setattr(rerank_mod.urllib.request, "urlopen", fake_urlopen)


def make_http(**kw):
    sleeps = []
    return make(sleep=sleeps.append, template="none", **kw), sleeps


def test_http_retries_on_429_and_5xx_then_succeeds(monkeypatch):
    requests = []
    ok = {"results": [{"index": 0, "relevance_score": 0.9}]}
    patch_urlopen(monkeypatch, [http_error(429), http_error(503), ok], requests)
    r, sleeps = make_http()
    assert r.rerank("soru", CHUNKS[:1]) == [0.9]
    assert len(requests) == 3 and len(sleeps) == 2
    req, timeout = requests[0]
    assert req.get_header("Authorization") == "Bearer KEY"
    assert req.full_url == "http://x/v1/rerank"
    assert 0 < timeout <= 20


def test_http_retries_on_network_errors(monkeypatch):
    ok = {"results": [{"index": 0, "score": 0.1}]}
    patch_urlopen(monkeypatch, [urllib.error.URLError("bağlantı"), TimeoutError(), ok])
    r, _ = make_http()
    assert r.rerank("soru", CHUNKS[:1]) == [0.1]


def test_http_4xx_is_not_retried_and_error_never_leaks_key(monkeypatch):
    requests = []
    patch_urlopen(monkeypatch, [http_error(400, "context length exceeded")], requests)
    r, sleeps = make_http()
    assert r.rerank("soru", CHUNKS[:1]) is None
    assert len(requests) == 1 and not sleeps
    assert "HTTP 400" in r.last_error and "context length" in r.last_error
    assert "KEY" not in r.last_error


def test_http_gives_up_after_max_attempts(monkeypatch):
    requests = []
    patch_urlopen(monkeypatch, [http_error(500)] * 10, requests)
    r, sleeps = make_http()
    assert r.rerank("soru", CHUNKS[:1]) is None
    assert len(requests) == rerank_mod.MAX_ATTEMPTS
    assert len(sleeps) == rerank_mod.MAX_ATTEMPTS - 1


def test_http_respects_total_deadline(monkeypatch):
    now = {"t": 0.0}
    patch_urlopen(monkeypatch, [http_error(503)] * 10)
    r = ApiReranker(
        "http://x/v1", "KEY", timeout=10.0, template="none",
        clock=lambda: now["t"], sleep=lambda s: now.__setitem__("t", now["t"] + 6.0),
    )  # fmt: skip
    assert r.rerank("soru", CHUNKS[:1]) is None
    assert "zaman aşımı" in r.last_error


def test_request_raw_returns_unparsed_response():
    r = make(lambda p: {"results": [], "extra": 1})
    assert r.request_raw("s", ["a"]) == {"results": [], "extra": 1}
