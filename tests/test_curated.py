from medrag.ingest.curated import CURATED, curated_titles


def test_no_duplicates_and_languages_match():
    assert len(curated_titles("tr")) == len(curated_titles("en")) == len(CURATED)
    for lang in ("tr", "en"):
        titles = curated_titles(lang)
        assert len(set(titles)) == len(titles)
