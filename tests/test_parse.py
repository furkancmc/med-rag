from medrag.ingest.parse import (
    html_to_text,
    parse_local_file,
    parse_medlineplus_topic,
    parse_wikipedia_extract,
)


def test_html_to_text_keeps_lists():
    assert (
        html_to_text("<p>Merhaba</p><ul><li>bir</li><li>iki</li></ul>") == "Merhaba\n\n- bir\n- iki"
    )


def test_medlineplus_topic():
    row = {
        "id": "7",
        "language": "English",
        "title": "Asthma",
        "url": "https://medlineplus.gov/asthma.html",
        "summary_html": "<p>Asthma is a disease.</p><ul><li>Cough</li><li>Wheeze</li></ul>",
    }
    d = parse_medlineplus_topic(row)
    assert d.id == "medlineplus-en-7" and d.lang == "en"
    assert "Asthma is a disease." in d.text and "- Wheeze" in d.text
    assert parse_medlineplus_topic({**row, "summary_html": ""}) is None


def test_wikipedia_page():
    page = {"pageid": 5, "title": "Astım", "extract": "Astım bir hastalıktır."}
    d = parse_wikipedia_extract(page, "tr")
    assert d.url == "https://tr.wikipedia.org/wiki/Astım"
    assert d.license.startswith("CC BY-SA")
    assert parse_wikipedia_extract({"pageid": 6, "title": "X", "extract": ""}, "tr") is None


def test_local_file(tmp_path):
    f = tmp_path / "not.txt"
    f.write_text("Deneme metni", encoding="utf-8")
    assert parse_local_file(f).title == "not"
    assert parse_local_file(tmp_path / "a.pdf") is None
