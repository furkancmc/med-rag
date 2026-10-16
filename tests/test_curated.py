from medrag.ingest.curated import CURATED, curated_titles


def test_no_duplicates_and_no_empty_titles():
    for lang in ("tr", "en"):
        titles = curated_titles(lang)
        assert titles and all(titles)
        assert len(set(titles)) == len(titles)


def test_tr_skips_topics_without_turkish_page():
    assert len(curated_titles("tr")) == len(CURATED) - sum(1 for tr, _ in CURATED if tr is None)
    assert len(curated_titles("en")) == len(CURATED)
