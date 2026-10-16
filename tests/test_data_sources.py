"""Yeni veri kaynakları (Europe PMC, openFDA, NIH ODS), ham depo ve ayrıştırma; ağ yok."""

import json

from medrag.ingest.build import build_chunk_dicts, build_chunks, load_documents
from medrag.ingest.chunk import chunk_document, drop_boilerplate
from medrag.ingest.curated import CURATED, curated_titles
from medrag.ingest.europepmc import clean_abstract, download_europepmc, license_label
from medrag.ingest.models import Document
from medrag.ingest.nihods import download_nihods, extract_sections
from medrag.ingest.openfda import download_openfda
from medrag.ingest.parse import (
    parse_europepmc_article,
    parse_nihods_factsheet,
    parse_openfda_label,
)
from medrag.ingest.rawstore import read_jsonl

TODAY = "2026-10-17"
ABSTRACT = (
    "<h4>Background</h4><p>Hypertension is a major risk factor. " + "Word " * 70 + "</p>"
    "<h4>Methods</h4><p>We reviewed trials. METHODS: more text here. " + "Data " * 10 + "</p>"
)


def epmc_result(i: int, lic: str = "cc by", year: str = "2023", cited: int = 5, abstract=ABSTRACT):
    return {
        "id": f"3{i}", "source": "MED", "pmid": f"3{i}", "doi": f"10.1/{i}",
        "title": f"Hypertension review {i}.", "abstractText": abstract, "license": lic,
        "firstPublicationDate": f"{year}-03-01", "pubYear": year, "language": "eng",
        "citedByCount": cited, "authorString": "Doe J, Roe R.",
        "pubTypeList": {"pubType": ["Review", "Journal Article"]},
        "journalInfo": {"journal": {"title": "Lancet"}},
    }


def test_license_label_accepts_cc_by_only():
    assert license_label("cc by") == "CC BY"
    assert license_label("CC BY-SA 4.0") == "CC BY-SA"
    assert license_label("cc by-nc") == ""
    assert license_label("cc by-nd") == ""
    assert license_label("") == ""


def test_clean_abstract_strips_labels():
    text = clean_abstract(ABSTRACT)
    assert "Background" not in text and "Methods" not in text.split("\n")[0]
    assert text.startswith("Hypertension is a major risk factor.")
    assert "METHODS:" not in text


def test_download_europepmc_filters_and_is_idempotent(tmp_path):
    results = [
        epmc_result(1, cited=1),
        epmc_result(2, lic="cc by-nc", cited=99),  # lisans uygun değil
        epmc_result(3, year="2018"),  # eski
        epmc_result(4, cited=50),
        epmc_result(5, abstract="short"),  # kısa özet
    ]
    urls = []

    def get(url: str) -> bytes:
        urls.append(url)
        return json.dumps({"resultList": {"result": results}}).encode()

    rep = download_europepmc(tmp_path, ["Hypertension"], get=get, per_topic=2, today=TODAY)
    assert rep.ok and rep.fetched == 1
    assert any("nc" in s or "eski" in s for s in rep.skipped)
    rows = read_jsonl(tmp_path / "europepmc" / "articles.jsonl")
    assert [r["id"] for r in rows] == ["34", "31"] or sorted(r["id"] for r in rows) == ["31", "34"]
    assert all(r["license"] in ("CC BY", "CC BY-SA") for r in rows)
    assert all("PUB_TYPE" in u or "pubType" in u or "query=" in u for u in urls)
    # ikinci çalışma: dosya değişmez, retrieved_at korunur
    rep2 = download_europepmc(tmp_path, ["Hypertension"], get=get, per_topic=2, today="2027-01-01")
    assert rep2.stats is not None and not rep2.stats.written
    assert {r["retrieved_at"] for r in read_jsonl(tmp_path / "europepmc" / "articles.jsonl")} == {TODAY}


def test_europepmc_document_metadata():
    row = {
        "key": "MED:34", "id": "34", "source": "MED", "doi": "10.1/4", "title": "Hypertension review",
        "abstract_html": ABSTRACT, "journal": "Lancet", "year": 2023, "published": "2023-03-01",
        "license": "CC BY", "authors": "Doe J", "retrieved_at": TODAY,
    }
    doc = parse_europepmc_article(row)
    assert doc and doc.id == "europepmc-MED-34"
    assert doc.url == "https://europepmc.org/article/MED/34"
    assert doc.published == "2023-03-01" and doc.retrieved_at == TODAY
    assert "Lancet" in doc.citation and "doi:10.1/4" in doc.citation


def fda_label(name="ACETAMINOPHEN", version="3"):
    return {
        "set_id": "abc-123", "version": version, "effective_time": "20240501",
        "openfda": {"generic_name": [name]},
        "indications_and_usage": ["1 INDICATIONS AND USAGE Acetaminophen reduces fever and relieves mild pain."],
        "warnings": ["Liver damage may occur if you take more than directed. Ask a doctor."],
        "contraindications": ["Hypersensitivity to acetaminophen or any component of the product."],
        "dosage_and_administration": ["Take 2 tablets every 6 hours. Do not exceed 8 tablets."],
        "overdosage": ["In case of overdose get medical help right away."],
        "dosage_forms_and_strengths": ["Tablets 500 mg"],
    }


def test_download_openfda_excludes_dose_sections(tmp_path):
    def get(url: str) -> bytes:
        return json.dumps({"results": [fda_label()]}).encode()

    drugs = [("acetaminophen", "parasetamol", ("Parol",))]
    rep = download_openfda(tmp_path, drugs=drugs, get=get, today=TODAY)
    assert rep.ok and rep.fetched == 1
    row = read_jsonl(tmp_path / "openfda" / "labels.jsonl")[0]
    blob = json.dumps(row["sections"])
    assert "Take 2 tablets" not in blob and "overdose" not in blob.lower() and "500 mg" not in blob
    assert "reduces fever" in blob
    assert row["published"] == "2024-05-01"
    doc = parse_openfda_label(row)
    assert doc and doc.title == "Acetaminophen (parasetamol) – ilaç prospektüsü bilgisi"
    assert "Parol" in doc.text and doc.license.startswith("Public domain")
    assert doc.url.startswith("https://dailymed.nlm.nih.gov")


def test_openfda_missing_drug_is_reported_not_fatal(tmp_path):
    def get(url: str) -> bytes:
        return json.dumps({"results": [fda_label("ACETAMINOPHEN")]}).encode()

    drugs = [("acetaminophen", "parasetamol", ()), ("foobarol", "foobarol", ())]
    rep = download_openfda(tmp_path, drugs=drugs, get=get, today=TODAY)
    assert rep.fetched == 1 and rep.missing == ["foobarol"] and rep.ok


NIH_JSON = {
    "Name": "Zinc",
    "LastUpdated": "2022-09-30",
    "Sections": [
        {"Heading": "What is zinc?", "Text": "<p>Zinc is a nutrient that people need to stay healthy.</p>"},
        {"Heading": "How much zinc do I need?", "Text": "<ul><li>Adults need 8-11 mg daily</li></ul>",
         "SubSections": [{"Heading": "Pregnancy", "Text": "<p>Pregnant women need more zinc.</p>"}]},
    ],
}


def test_nihods_extract_and_download(tmp_path):
    secs = extract_sections(NIH_JSON)
    assert [h for h, _ in secs] == ["What is zinc?", "How much zinc do I need?", "Pregnancy"]
    assert "<p>" not in secs[0][1]

    rep = download_nihods(
        tmp_path, [("Zinc", "Çinko")], get=lambda u: json.dumps(NIH_JSON).encode(), today=TODAY
    )
    assert rep.ok
    row = read_jsonl(tmp_path / "nihods" / "factsheets.jsonl")[0]
    doc = parse_nihods_factsheet(row)
    assert doc and "Çinko" in doc.title and doc.published == "2022-09-30"
    assert "== What is zinc? ==" in doc.text


def test_nihods_blocked_is_fatal_for_source_only(tmp_path):
    import urllib.error

    def get(url: str) -> bytes:
        raise urllib.error.HTTPError(url, 403, "Forbidden", {}, None)  # type: ignore[arg-type]

    rep = download_nihods(tmp_path, [("Zinc", "Çinko")], get=get, today=TODAY)
    assert not rep.ok and rep.failed and "403" in rep.failed[0][1]


def test_drop_boilerplate_with_subsections():
    text = "Giriş.\n== Belirtiler ==\nAteş.\n== Kaynakça ==\nBir kaynak.\n=== Alt ===\nDaha.\n== Tedavi ==\nİstirahat."
    out = drop_boilerplate(text)
    assert "Bir kaynak" not in out and "Daha" not in out and "Alt" not in out
    assert "Ateş" in out and "İstirahat" in out


def test_wikipedia_boilerplate_chunks_removed_and_ids_stable():
    body = " ".join(f"kelime{i}" for i in range(15))
    doc = Document(
        "wikipedia-tr-1", "Grip", f"{body}\n== See also ==\n{body}\n== Tedavi ==\n{body} x",
        "wikipedia", "u", "tr", "CC BY-SA", published="2024-01-01", retrieved_at=TODAY,
    )
    chunks = chunk_document(doc)
    assert [c.section for c in chunks] == ["", "Tedavi"]
    assert chunks[1].id == "wikipedia-tr-1#1"  # 'See also' elense de kimlikler kaymaz... (1 = ikinci parça)
    assert chunks[0].published == "2024-01-01" and chunks[0].retrieved_at == TODAY
    assert chunk_document(doc)[1].id == chunks[1].id  # tekrar çalıştırma aynı


def test_short_chunks_dropped():
    doc = Document("d", "T", "çok kısa metin", "medlineplus", "u", "en", "PD")
    assert chunk_document(doc) == []


def test_near_duplicate_chunks_removed():
    text = " ".join(f"w{i}" for i in range(20))
    a = Document("a", "A", text, "medlineplus", "u", "en", "PD")
    b = Document("b", "B", text.upper() + " !", "wikipedia", "u", "en", "PD")
    chunks, stats = build_chunk_dicts([a, b])
    assert len(chunks) == 1 and stats["duplicates"] == {"wikipedia": 1}


def test_build_with_all_sources(tmp_path):
    raw = tmp_path / "raw"
    (raw / "europepmc").mkdir(parents=True)
    row = {
        "key": "MED:34", "id": "34", "source": "MED", "title": "Hypertension review",
        "abstract_html": ABSTRACT, "journal": "Lancet", "year": 2023, "published": "2023-03-01",
        "license": "CC BY", "authors": "Doe J", "retrieved_at": TODAY,
    }
    (raw / "europepmc" / "articles.jsonl").write_text(json.dumps(row), encoding="utf-8")
    (raw / "openfda").mkdir()
    label = {
        "slug": "acetaminophen", "term": "acetaminophen", "name_tr": "parasetamol", "brands": ["Parol"],
        "label_name": "ACETAMINOPHEN", "set_id": "s", "published": "2024-05-01",
        "sections": {"indications_and_usage": "Acetaminophen reduces fever and relieves mild pain in adults and children."},
        "retrieved_at": TODAY,
    }
    (raw / "openfda" / "labels.jsonl").write_text(json.dumps(label), encoding="utf-8")
    assert len(load_documents(raw, tmp_path / "local")) == 2
    assert build_chunks(tmp_path) >= 2
    rows = read_jsonl(tmp_path / "chunks.jsonl")
    assert {r["source"] for r in rows} == {"europepmc", "openfda"}
    assert all(r["license"] and r["retrieved_at"] and r["published"] for r in rows)
    assert len({r["id"] for r in rows}) == len(rows)


def test_curated_list_is_large_and_clean():
    assert len(CURATED) >= 400
    for lang in ("tr", "en"):
        titles = curated_titles(lang)
        assert len({t.casefold() for t in titles}) == len(titles)
    assert "Kırım-Kongo kanamalı ateşi" in curated_titles("tr")
