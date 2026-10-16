from medrag.index.bm25 import BM25
from medrag.index.tokenize import normalize, tokenize


def test_normalize_turkish_chars():
    assert normalize("İSTANBUL Şeker Hastalığı ığ") == "istanbul seker hastaligi ig"


def test_tokenize_prefix_stemming_joins_suffixed_words():
    assert tokenize("diyabetin diyabette") == ["diyab", "diyab"]
    assert tokenize("Grip, ateş!") == ["grip", "ates"]


def test_bm25_ranks_relevant_doc_first():
    docs = [tokenize(t) for t in [
        "Astım solunum yollarının kronik hastalığıdır",
        "Diyabet kan şekerinin yükselmesidir",
        "Grip ateş ve öksürük yapar",
    ]]
    bm = BM25(docs)
    top = bm.search(tokenize("şeker yüksek"), k=2)
    assert top[0][0] == 1
    assert bm.search(tokenize("olmayan kelime")) == []


def test_bm25_empty_corpus():
    assert BM25([]).search(["a"]) == []
