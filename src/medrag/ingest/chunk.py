import re

from .models import Chunk, Document

HEADING = re.compile(r"^(={2,})\s*(.+?)\s*\1\s*$")


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
    for section, body in split_sections(doc.text):
        for piece in split_words(body, max_words, overlap):
            chunks.append(
                Chunk(
                    id=f"{doc.id}#{len(chunks)}",
                    doc_id=doc.id,
                    title=doc.title,
                    section=section,
                    text=piece,
                    source=doc.source,
                    url=doc.url,
                    lang=doc.lang,
                    license=doc.license,
                )
            )
    return chunks
