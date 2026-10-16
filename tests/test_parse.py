from medrag.ingest.parse import (
    html_to_text,
    parse_local_file,
    parse_medlineplus,
    parse_wikipedia_extract,
)

# Gerçek MedlinePlus dosyasının biçimini gösteren küçük kesit (sadece parse testi için)
MEDLINE_XML = """<?xml version="1.0"?>
<health-topics total="2">
  <health-topic id="7" language="English" title="Asthma" url="https://medlineplus.gov/asthma.html">
    <full-summary>&lt;p&gt;Asthma is a disease.&lt;/p&gt;&lt;ul&gt;&lt;li&gt;Cough&lt;/li&gt;&lt;li&gt;Wheeze&lt;/li&gt;&lt;/ul&gt;</full-summary>
  </health-topic>
  <health-topic id="8" language="Spanish" title="Asma" url="https://medlineplus.gov/spanish/asthma.html">
    <full-summary></full-summary>
  </health-topic>
</health-topics>"""


def test_html_to_text_keeps_lists():
    assert html_to_text("<p>Merhaba</p><ul><li>bir</li><li>iki</li></ul>") == "Merhaba\n\n- bir\n- iki"


def test_medlineplus_parse_skips_empty_summary():
    docs = parse_medlineplus(MEDLINE_XML)
    assert len(docs) == 1
    d = docs[0]
    assert d.id == "medlineplus-en-7" and d.lang == "en"
    assert "Asthma is a disease." in d.text and "- Wheeze" in d.text
    assert d.url == "https://medlineplus.gov/asthma.html"


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
