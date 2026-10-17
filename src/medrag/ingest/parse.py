import re
from html.parser import HTMLParser
from pathlib import Path

from .cdc import LICENSE as CDC_LICENSE
from .europepmc import article_url, clean_abstract
from .models import Document
from .nihods import LICENSE as NIHODS_LICENSE
from .nihods import page_url as nihods_page_url
from .openfda import LICENSE as OPENFDA_LICENSE
from .openfda import build_sections, label_url
from .textutil import iso_date, slugify

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


def parse_medlineplus_topic(row: dict) -> Document | None:
    """topics.jsonl satırını Document'a çevirir. Özet kaçışlı HTML olarak gelir."""
    text = html_to_text(row.get("summary_html") or "")
    if not text:
        return None
    lang = LANG_CODES.get(row.get("language", ""), "en")
    return Document(
        id=f"medlineplus-{lang}-{row['id']}",
        title=row.get("title", ""),
        text=text,
        source="medlineplus",
        url=row.get("url", ""),
        lang=lang,
        license="Public domain (NLM MedlinePlus)",
        published=iso_date(row.get("published", "")),
        retrieved_at=row.get("retrieved_at", ""),
    )


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
        published=iso_date(page.get("published", "")),
        retrieved_at=page.get("retrieved_at", ""),
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


def parse_europepmc_article(row: dict) -> Document | None:
    """Europe PMC makale satırını (derleme özeti) Document'a çevirir."""
    text = clean_abstract(row.get("abstract_html") or "")
    if not text or not row.get("title"):
        return None
    cite = ". ".join(
        p
        for p in (
            row.get("authors", ""),
            f"{row.get('journal', '')}, {row.get('year', '')}".strip(", "),
            f"doi:{row['doi']}" if row.get("doi") else "",
        )
        if p
    )
    return Document(
        id="europepmc-" + str(row["key"]).replace(":", "-"),
        title=row["title"],
        text=text,
        source="europepmc",
        url=article_url(row),
        lang="en",
        license=f"{row.get('license', 'CC BY')} (Europe PMC)",
        published=iso_date(row.get("published", "")) or str(row.get("year", "")),
        retrieved_at=row.get("retrieved_at", ""),
        citation=cite,
    )


def drug_title(row: dict) -> str:
    name = row.get("term", "").title()
    tr = row.get("name_tr", "")
    alias = f" ({tr})" if tr and tr.casefold() != name.casefold() else ""
    return f"{name}{alias} – ilaç prospektüsü bilgisi"


def parse_openfda_label(row: dict) -> Document | None:
    """openFDA etiket satırını Document'a çevirir; bölümler '== Başlık ==' ile ayrılır."""
    raw = row.get("sections") or {}
    sections = build_sections(raw) if isinstance(raw, dict) else [tuple(x) for x in raw]
    if not sections:
        return None
    brands = ", ".join(row.get("brands") or [])
    intro = (
        "Bu bilgi ABD FDA onaylı ilaç prospektüsünden alınmıştır; Türkiye'deki ürünün "
        "kullanma talimatı farklı olabilir."
        + (f" Türkiye'de bilinen markalar: {brands}." if brands else "")
    )
    parts = [intro] + [f"== {title} ==\n{text}" for title, text in sections]
    return Document(
        id=f"openfda-{row.get('slug') or slugify(row.get('term', ''))}",
        title=drug_title(row),
        text="\n\n".join(parts),
        source="openfda",
        url=label_url(row),
        lang="en",
        license=OPENFDA_LICENSE,
        published=iso_date(row.get("published", "")),
        retrieved_at=row.get("retrieved_at", ""),
        citation=f"FDA etiketi: {row.get('label_name', '')}".strip(": "),
    )


def parse_nihods_factsheet(row: dict) -> Document | None:
    sections = row.get("sections") or []
    if not sections:
        return None
    parts = [f"== {head} ==\n{text}" for head, text in sections]
    name_tr = row.get("name_tr", "")
    title = row.get("title") or row.get("resource", "")
    return Document(
        id=f"nihods-{row.get('slug') or slugify(row.get('resource', ''))}",
        title=f"{title} ({name_tr}) – besin takviyesi bilgi sayfası" if name_tr else title,
        text="\n\n".join(parts),
        source="nihods",
        url=nihods_page_url(row),
        lang="en",
        license=NIHODS_LICENSE,
        published=iso_date(row.get("published", "")),
        retrieved_at=row.get("retrieved_at", ""),
    )


def parse_cdc_page(row: dict) -> Document | None:
    """CDC sayfa satırını Document'a çevirir; bölümler '== Başlık ==' ile ayrılır."""
    sections = row.get("sections") or []
    if not sections or not row.get("title"):
        return None
    parts = [f"== {head} ==\n{text}" for head, text in sections]
    name_tr = row.get("name_tr", "")
    suffix = f" – {name_tr} (CDC)" if name_tr else " (CDC)"
    return Document(
        id=f"cdc-{row.get('slug') or slugify(row['title'])}",
        title=f"{row['title']}{suffix}",
        text="\n\n".join(parts),
        source="cdc",
        url=row.get("url", ""),
        lang="en",
        license=CDC_LICENSE,
        published=iso_date(row.get("published", "")),
        retrieved_at=row.get("retrieved_at", ""),
    )
