import json

import pytest

from medrag.ingest.download import (
    category_titles,
    download_medlineplus,
    download_wikipedia,
    fetch_extracts,
    find_medlineplus_urls,
    search_categories,
)

INDEX = '<a href="/xml/mplus_topics_2026-10-15.xml">x</a> <a href="/xml/other.xml">y</a>'


def test_find_urls():
    assert find_medlineplus_urls(INDEX) == [
        "https://medlineplus.gov/xml/mplus_topics_2026-10-15.xml"
    ]


XML = b"""<health-topics>
<health-topic id="1" language="English" title="Flu" url="https://x/flu">
<full-summary>&lt;p&gt;Flu&lt;/p&gt;</full-summary></health-topic>
<health-topic id="2" language="Spanish" title="Gripe" url="https://x/gripe">
<full-summary>&lt;p&gt;Gripe&lt;/p&gt;</full-summary></health-topic>
</health-topics>"""

INDEX2 = (
    '<a href="/xml/mplus_topics_2026-10-14.xml">a</a> '
    '<a href="/xml/mplus_topics_2026-10-15.xml">b</a>'
)


def test_download_medlineplus_latest_english_only(tmp_path):
    asked = []

    def get(url):
        asked.append(url)
        return INDEX2.encode() if url.endswith("xml.html") else XML

    path = download_medlineplus(tmp_path, get=get)
    rows = [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines()]
    assert [r["title"] for r in rows] == ["Flu"]
    assert asked[-1].endswith("mplus_topics_2026-10-15.xml")


def fake_wiki(url):
    if "categorymembers" in url and "Alt" in url:
        return json.dumps({"query": {"categorymembers": [{"ns": 0, "title": "Verem"}]}}).encode()
    if "categorymembers" in url:
        return json.dumps(
            {
                "query": {
                    "categorymembers": [
                        {"ns": 0, "title": "Astım"},
                        {"ns": 14, "title": "Kategori:Alt"},
                    ]
                }
            }
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


def test_fetch_extracts_one_request_per_title():
    urls = []

    def get(url):
        urls.append(url)
        return json.dumps(
            {"query": {"pages": [{"pageid": 1, "title": "x", "extract": "m"}]}}
        ).encode()

    pages = fetch_extracts("tr", ["A", "B", "C"], get=get)
    assert len(urls) == 3 and len(pages) == 3


def test_search_categories():
    def get(url):
        assert "srnamespace=14" in url
        return json.dumps({"query": {"search": [{"title": "Kategori:Hastalıklar"}]}}).encode()

    assert search_categories("tr", "hastalık", get=get) == ["Kategori:Hastalıklar"]
