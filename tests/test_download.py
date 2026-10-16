import json

import pytest

from medrag.ingest.download import (
    category_titles,
    download_medlineplus,
    download_wikipedia,
    find_medlineplus_urls,
)

INDEX = '<a href="/xml/mplus_topics_2026-10-15.xml">x</a> <a href="/xml/other.xml">y</a>'


def test_find_urls():
    assert find_medlineplus_urls(INDEX) == ["https://medlineplus.gov/xml/mplus_topics_2026-10-15.xml"]


def test_download_medlineplus(tmp_path):
    def get(url):
        return INDEX.encode() if url.endswith("xml.html") else b"<health-topics/>"

    paths = download_medlineplus(tmp_path, get=get)
    assert paths[0].name == "mplus_topics_2026-10-15.xml"
    assert paths[0].read_bytes() == b"<health-topics/>"


def fake_wiki(url):
    if "categorymembers" in url and "Alt" in url:
        return json.dumps(
            {"query": {"categorymembers": [{"ns": 0, "title": "Verem"}]}}
        ).encode()
    if "categorymembers" in url:
        return json.dumps(
            {"query": {"categorymembers": [
                {"ns": 0, "title": "Astım"},
                {"ns": 14, "title": "Kategori:Alt"},
            ]}}
        ).encode()
    return json.dumps(
        {"query": {"pages": [{"pageid": 1, "title": "Astım", "extract": "metin"}]}}
    ).encode()


def test_category_follows_subcategories():
    assert category_titles("tr", "Kategori:Üst", get=fake_wiki, depth=1) == ["Astım", "Verem"]
    assert category_titles("tr", "Kategori:Üst", get=fake_wiki, depth=0) == ["Astım"]


def test_download_wikipedia_writes_jsonl(tmp_path):
    path = download_wikipedia(tmp_path, "tr", ["Kategori:Üst"], get=fake_wiki)
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    assert rows[0]["title"] == "Astım"


def test_empty_category_is_an_error(tmp_path):
    def empty(url):
        return json.dumps({"query": {"categorymembers": []}}).encode()

    with pytest.raises(RuntimeError):
        download_wikipedia(tmp_path, "tr", ["Kategori:Yok"], get=empty)
