import re

from .models import Chunk, Document

HEADING = re.compile(r"^(={2,})\s*(.+?)\s*\1\s*$")


# Vikipedi'de bilgi taşımayan bölümler (alt başlıklarıyla birlikte atılır)
BOILERPLATE = frozenset(
    {
        "see also", "references", "external links", "further reading", "notes", "bibliography",
        "footnotes", "sources", "citations", "ayrıca bakınız", "kaynakça", "dış bağlantılar",
        "notlar", "daha fazla okuma", "ek okumalar", "kaynaklar", "dipnotlar",
        "konuyla ilgili yayınlar", "notlar ve kaynaklar", "bu da ilginizi çekebilir",
    }
)
MIN_CHUNK_WORDS = 10  # bundan kısa parçalar aramaya katkı yapmaz


def drop_boilerplate(text: str) -> str:
    """'Kaynakça', 'See also' gibi bölümleri (ve alt bölümlerini) metinden çıkarır."""
    out: list[str] = []
    skip_level = 0
    for line in text.splitlines():
        m = HEADING.match(line.strip())
        if m:
            level = len(m.group(1))
            if skip_level and level <= skip_level:
                skip_level = 0
            if not skip_level and m.group(2).strip().casefold() in BOILERPLATE:
                skip_level = level
        if not skip_level:
            out.append(line)
    return "\n".join(out)


def split_sections(text: str) -> list[tuple[str, str]]:
    """Metni başlıklara göre böler. Başlık yoksa tek parça döner.

    Vikipedi düz metnindeki '== Başlık ==' satırlarını başlık sayar.
    """
    sections: list[tuple[str, list[str]]] = [("", [])]
    for line in text.splitlines():
        m = HEADING.match(line.strip())
        if m:
            sections.append((m.group(2), []))
        else:
            sections[-1][1].append(line)
    out = []
    for name, lines in sections:
        body = "\n".join(lines).strip()
        if body:
            out.append((name, body))
    return out


def split_words(text: str, max_words: int, overlap: int) -> list[str]:
    words = text.split()
    if len(words) <= max_words:
        return [" ".join(words)] if words else []
    step = max_words - overlap
    pieces = []
    for start in range(0, len(words), step):
        pieces.append(" ".join(words[start : start + max_words]))
        if start + max_words >= len(words):
            break
    return pieces


def chunk_document(doc: Document, max_words: int = 200, overlap: int = 30) -> list[Chunk]:
    if overlap >= max_words:
        raise ValueError("overlap, max_words'ten küçük olmalı")
    chunks = []
    n = 0  # kararlı kimlik: elenen parçalar da sayılır
    text = drop_boilerplate(doc.text) if doc.source == "wikipedia" else doc.text
    for section, body in split_sections(text):
        for piece in split_words(body, max_words, overlap):
            n += 1
            if len(piece.split()) < MIN_CHUNK_WORDS:
                continue
            chunks.append(
                Chunk(
                    id=f"{doc.id}#{n - 1}",
                    doc_id=doc.id,
                    title=doc.title,
                    section=section,
                    text=piece,
                    source=doc.source,
                    url=doc.url,
                    lang=doc.lang,
                    license=doc.license,
                    published=doc.published,
                    retrieved_at=doc.retrieved_at,
                    citation=doc.citation,
                )
            )
    return chunks
