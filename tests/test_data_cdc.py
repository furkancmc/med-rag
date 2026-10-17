"""CDC kaynağı: arama süzgeci, syndication HTML ayrıştırma, indirme ve parça meta verisi; ağ yok."""

import json

from medrag.ingest.build import build_chunk_dicts
from medrag.ingest.cdc import (
    download_cdc,
    html_to_sections,
    normalize_url,
    page_ok,
    select_pages,
)
from medrag.ingest.parse import parse_cdc_page
from medrag.ingest.rawstore import read_jsonl

TODAY = "2026-10-17"
BODY = "Flu is a contagious respiratory illness. " + "Rest and fluids help. " * 30
CONTENT = (
    '<div class="syndicate"><h1>About Influenza</h1></div>'
    "<div><h2>Key points</h2><ul><li>Flu spreads easily.</li><li>Vaccines help.</li></ul>"
    f"<h2>Overview</h2><p>{BODY}</p><script>var x=1;</script>"
    "<h2>Related pages</h2><p>Other stuff to drop.</p></div>"
)


def item(i: int, url: str, name: str = "About Influenza") -> dict:
    return {
        "id": i, "name": name, "sourceUrl": url,
        "dateContentUpdated": "2026-02-26T05:00:00Z", "dateContentReviewed": "2026-01-10T05:00:00Z",
    }


def test_page_filter_keeps_consumer_pages_only():
    assert page_ok(item(1, "https://www.cdc.gov/flu/about/index.html"), "/flu/")
    assert not page_ok(item(2, "https://www.cdc.gov/mmwr/volumes/75/wr/x.htm"), "/flu/")
    assert not page_ok(item(3, "https://www.cdc.gov/flu/hcp/clinical.html"), "/flu/")
    assert not page_ok(item(4, "https://www.cdc.gov/measles/about/index.html"), "/flu/")
    assert not page_ok(item(5, "https://www.cdc.gov/flu/a.html", "Flu Infographic"), "/flu/")
    assert normalize_url("http://www.cdc.gov/flu/about/?x=1#top") == "https://www.cdc.gov/flu/about"


def test_select_pages_dedupes_and_ranks():
    results = [
        item(1, "https://www.cdc.gov/flu/a/b/c/other.html", "Other"),
        item(2, "https://www.cdc.gov/flu/signs-symptoms/index.html", "Symptoms"),
        item(3, "https://www.cdc.gov/flu/signs-symptoms/index.html", "Symptoms dup"),
        item(4, "https://www.cdc.gov/flu/about/index.html", "About"),
    ]
    chosen = select_pages(results, "/flu/", 2)
    assert sorted(c["id"] for c in chosen) == [2, 4]


def test_fallback_matches_by_name_outside_prefix(tmp_path):
    def get(url: str) -> bytes:
        if "syndicate" in url:
            return json.dumps({"results": {"sourceUrl": "https://www.cdc.gov/hepatitis/about/a.html",
                                           "name": "Hepatitis A", "content": CONTENT}}).encode()
        return json.dumps({"results": [
            item(1, "https://www.cdc.gov/hepatitis/about/a.html", "Hepatitis A"),
            item(2, "https://www.cdc.gov/tsunamis/about/x.html", "Tsunamis"),
        ]}).encode()

    rep = download_cdc(tmp_path, [("Hepatit A", "hepatitis A", "/hepatitis-a/")], get=get, today=TODAY)
    assert rep.ok and rep.fetched == 1


def test_html_to_sections_drops_boilerplate():
    title, sections = html_to_sections(CONTENT)
    assert title == "About Influenza"
    assert [h for h, _ in sections] == ["Key points", "Overview"]
    assert "- Flu spreads easily." in sections[0][1]
    assert "var x" not in sections[1][1]


def test_footer_and_on_this_page_removed():
    html = (
        "<h1>T</h1><h2>Symptoms</h2><p>Fever and cough.</p>"
        "<h2>On This Page</h2><ul><li>Symptoms</li></ul>"
        "<h2>Last</h2><p>Real text.</p><p>Aug. 26, 2024 Sources Print Share Facebook</p>"
        "<p>Content provided and maintained by the US CDC.</p>"
    )
    _, sections = html_to_sections(html)
    assert [h for h, _ in sections] == ["Symptoms", "Last"]
    assert sections[1][1] == "Real text."


def make_get(urls: list[str]):
    def get(url: str) -> bytes:
        urls.append(url)
        if "syndicate" in url:
            return json.dumps({"results": {
                "sourceUrl": "https://www.cdc.gov/flu/about/index.html",
                "name": "About Influenza", "content": CONTENT}}).encode()
        return json.dumps({"results": [
            item(10, "https://www.cdc.gov/flu/about/index.html"),
            item(11, "https://www.cdc.gov/mmwr/volumes/1/a.htm", "MMWR"),
        ]}).encode()

    return get


def test_download_cdc_idempotent_and_metadata(tmp_path):
    get = make_get([])
    topics = [("Grip", "flu", "/flu/"), ("Grip 2", "influenza", "/flu/")]
    rep = download_cdc(tmp_path, topics, get=get, today=TODAY)
    assert rep.ok and rep.fetched == 2
    rows = read_jsonl(tmp_path / "cdc" / "pages.jsonl")
    assert len(rows) == 1 and rows[0]["retrieved_at"] == TODAY
    assert rows[0]["published"] == "2026-01-10"
    rep2 = download_cdc(tmp_path, topics, get=get, today="2027-01-01")
    assert rep2.stats and not rep2.stats.written
    assert read_jsonl(tmp_path / "cdc" / "pages.jsonl")[0]["retrieved_at"] == TODAY

    doc = parse_cdc_page(rows[0])
    assert doc and doc.source == "cdc" and "Public domain" in doc.license
    assert doc.published == "2026-01-10" and doc.retrieved_at == TODAY
    chunks, _ = build_chunk_dicts([doc])
    assert chunks and all(c["source"] == "cdc" and c["retrieved_at"] == TODAY for c in chunks)


def test_download_cdc_failure_is_reported(tmp_path):
    def get(url: str) -> bytes:
        raise OSError("boom")

    rep = download_cdc(tmp_path, [("Grip", "flu", "/flu/")], get=get, today=TODAY)
    assert not rep.ok and rep.failed and rep.fatal
