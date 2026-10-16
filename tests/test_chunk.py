import pytest

from medrag.ingest.chunk import chunk_document, split_sections
from medrag.ingest.models import Document


def make_doc(text):
    return Document("d1", "Başlık", text, "wikipedia", "http://x", "tr", "CC BY-SA 4.0")


def test_sections_split_on_headings():
    text = "Giriş cümlesi.\n== Belirtiler ==\nAteş ve öksürük.\n== Tedavi ==\nİstirahat."
    assert split_sections(text) == [
        ("", "Giriş cümlesi."),
        ("Belirtiler", "Ateş ve öksürük."),
        ("Tedavi", "İstirahat."),
    ]


def test_long_section_is_split_with_overlap():
    text = " ".join(f"k{i}" for i in range(50))
    chunks = chunk_document(make_doc(text), max_words=20, overlap=5)
    assert len(chunks) == 3
    assert chunks[0].text.split()[-5:] == chunks[1].text.split()[:5]
    assert all(len(c.text.split()) <= 20 for c in chunks)


def test_chunk_keeps_metadata_and_unique_ids():
    chunks = chunk_document(make_doc("a b c\n== Bölüm ==\nd e f"))
    assert [c.section for c in chunks] == ["", "Bölüm"]
    assert len({c.id for c in chunks}) == 2
    assert chunks[0].license == "CC BY-SA 4.0"


def test_bad_overlap():
    with pytest.raises(ValueError):
        chunk_document(make_doc("a b"), max_words=10, overlap=10)
