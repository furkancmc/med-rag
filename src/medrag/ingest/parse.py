import re
import xml.etree.ElementTree as ET
from html.parser import HTMLParser
from pathlib import Path

from .models import Document

LANG_CODES = {"English": "en", "Spanish": "es"}
BLOCK_TAGS = {"p", "li", "br", "h1", "h2", "h3", "h4", "div", "ul", "ol"}


class _TextExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag == "li":
            self.parts.append("\n- ")
        elif tag in BLOCK_TAGS:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in BLOCK_TAGS and tag != "li":
            self.parts.append("\n")

    def handle_data(self, data):
        self.parts.append(data)


def html_to_text(html: str) -> str:
    p = _TextExtractor()
    p.feed(html)
    text = "".join(p.parts)
    text = re.sub(r"[ \t\xa0]+", " ", text)
    text = re.sub(r"\n\s*\n+", "\n\n", text)
    return "\n".join(line.strip() for line in text.splitlines()).strip()


def parse_medlineplus(xml_text: str) -> list[Document]:
    """MedlinePlus 'health topics' XML dosyasını okur.

    Özet alanı (full-summary) XML içinde kaçışlı HTML olarak gelir.
    """
    root = ET.fromstring(xml_text)
    docs = []
    for topic in root.iter("health-topic"):
        summary = topic.findtext("full-summary") or ""
        text = html_to_text(summary)
        if not text:
            continue
        lang = LANG_CODES.get(topic.get("language", ""), "en")
        docs.append(
            Document(
                id=f"medlineplus-{lang}-{topic.get('id')}",
                title=topic.get("title", ""),
                text=text,
                source="medlineplus",
                url=topic.get("url", ""),
                lang=lang,
                license="Public domain (NLM MedlinePlus)",
            )
        )
    return docs


def parse_wikipedia_extract(page: dict, lang: str) -> Document | None:
    """MediaWiki API'nin 'extracts' çıktısındaki bir sayfayı Document'a çevirir."""
    text = (page.get("extract") or "").strip()
    if not text or "missing" in page:
        return None
    title = page["title"]
    return Document(
        id=f"wikipedia-{lang}-{page['pageid']}",
        title=title,
        text=text,
        source="wikipedia",
        url=f"https://{lang}.wikipedia.org/wiki/{title.replace(' ', '_')}",
        lang=lang,
        license="CC BY-SA 4.0 (Wikipedia katkıcıları)",
    )


def parse_local_file(path: Path) -> Document | None:
    """data/local altındaki .txt ve .md dosyalarını okur (PDF sonra)."""
    if path.suffix.lower() not in {".txt", ".md"}:
        return None
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        return None
    return Document(
        id=f"local-{path.stem}",
        title=path.stem,
        text=text,
        source="local",
        url=str(path),
        lang="tr",
        license="Kullanıcı dosyası",
    )
