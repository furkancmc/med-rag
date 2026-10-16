"""Europe PMC: 2020 ve sonrası, CC BY / CC BY-SA lisanslı derleme makalelerinin özetleri.

API: https://europepmc.org/RestfulWebService (search, format=json, resultType=core).
Her curated İngilizce konu için en fazla `per_topic` makale alınır. Lisans sunucuda değil
istemcide süzülür (cc by, cc by-sa; NC/ND ve diğerleri atılır). Ham satırda özet HTML olarak
saklanır; etiket temizliği ayrıştırma aşamasındadır (`parse.parse_europepmc_article`).
"""

import re
import time
import urllib.parse
from collections.abc import Callable
from pathlib import Path

from .net import RateLimiter, describe_error, get_json, http_get, limited, run_parallel
from .rawstore import save_merged
from .report import SourceReport
from .textutil import SPACES, iso_date, strip_tags, today_iso

SOURCE = "europepmc"
SEARCH_URL = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"
ARTICLE_URL = "https://europepmc.org/article/{source}/{id}"
DEFAULT_PER_TOPIC = 3
MIN_YEAR = 2020
PAGE_SIZE = 50
CANDIDATES = 15  # lisans/özet süzgecinden geçen ilk bu kadar aday arasından seçilir
MIN_ABSTRACT_WORDS = 60
WORKERS = 4
RATE = 8.0  # saniyede istek
REVIEW_TYPES = ("Review", "Systematic Review", "Meta-Analysis", "Practice Guideline", "Guideline")
BAD_TYPES = ("retract", "erratum", "correction", "comment", "withdrawn")

# "cc by", "cc by-sa", "cc by 4.0", "CC-BY-SA" ... ; nc/nd/cc0/diğerleri eşleşmez
LICENSE_RE = re.compile(r"^cc[ -]by(?P<sa>[ -]sa)?(?:[ -]\d\.\d)?$", re.IGNORECASE)

# Yapılandırılmış özet etiketleri (HTML başlığı ya da "BACKGROUND:" biçiminde)
ABSTRACT_LABELS = (
    "background and aims?|background and objectives?|background and purpose|background|introduction|"
    "objectives?|aims?|purpose|importance|context|rationale|"
    "materials? and methods?|methods? and materials?|methods?|methodology|design|setting|"
    "participants|patients|study design|study selection|data sources?|data extraction|"
    "data synthesis|data collection|searches?|eligibility criteria|"
    "main outcomes? and measures?|main outcome measures?|measurements?|interventions?|exposures?|"
    "results?|findings|main results|key findings|"
    "conclusions?(?: and relevance)?|interpretation|discussion|summary|significance|"
    "implications|recent findings|purpose of review|"
    "clinical relevance|funding|trial registration|registration|limitations"
)
LABEL_LINE = re.compile(rf"^(?:{ABSTRACT_LABELS})\s*[:.\-–]?\s*$", re.IGNORECASE)
LABEL_PREFIX = re.compile(rf"^(?:{ABSTRACT_LABELS})\s*[:–-]\s+", re.IGNORECASE)
LABEL_INLINE = re.compile(rf"(?<=[.!?])\s+(?:{ABSTRACT_LABELS})\s*:\s+", re.IGNORECASE)
LABEL_CAPS = re.compile(rf"\b(?:{ABSTRACT_LABELS.upper()})\s*:\s*")  # "METHODS: ..." (büyük harf)
BLOCK = re.compile(r"</?(?:p|h[1-6]|div|br|li|ul|ol|sec|title|abstract)\b[^>]*>", re.IGNORECASE)


def license_label(value: str) -> str:
    """'cc by' -> 'CC BY', 'cc by-sa' -> 'CC BY-SA'; kabul edilmeyen lisans için ''."""
    m = LICENSE_RE.match((value or "").strip())
    if not m:
        return ""
    return "CC BY-SA" if m.group("sa") else "CC BY"


def clean_abstract(raw: str) -> str:
    """Özet HTML'ini sade metne çevirir; 'Background/Methods/Results...' etiketlerini atar.

    Paragraflar satır başı ile ayrılı kalır, etiketler çıkarılır (metin akışı bozulmaz).
    """
    text = BLOCK.sub("\n", raw or "")
    paragraphs = []
    for line in text.split("\n"):
        line = strip_tags(line)
        if not line or LABEL_LINE.match(line):
            continue
        line = LABEL_CAPS.sub(" ", LABEL_PREFIX.sub("", line))
        line = SPACES.sub(" ", LABEL_INLINE.sub(" ", line)).strip()
        if line:
            paragraphs.append(line)
    return "\n".join(paragraphs)


def build_query(term: str, today: str, year_from: int = MIN_YEAR, title_only: bool = True) -> str:
    phrase = term.replace('"', " ").strip()
    topic = f'TITLE:"{phrase}"' if title_only else f'(TITLE:"{phrase}" OR ABSTRACT:"{phrase}")'
    types = " OR ".join(f'PUB_TYPE:"{t}"' for t in REVIEW_TYPES)
    return (
        f"{topic} AND ({types}) AND HAS_ABSTRACT:y AND OPEN_ACCESS:y "
        f"AND FIRST_PDATE:[{year_from}-01-01 TO {today}]"
    )


def search_url(query: str, page_size: int = PAGE_SIZE) -> str:
    params = {
        "query": query,
        "format": "json",
        "resultType": "core",
        "pageSize": str(page_size),
    }
    return f"{SEARCH_URL}?{urllib.parse.urlencode(params)}"


def _pub_types(result: dict) -> list[str]:
    types = (result.get("pubTypeList") or {}).get("pubType") or []
    return [types] if isinstance(types, str) else list(types)


def _journal(result: dict) -> str:
    info = result.get("journalInfo") or {}
    return strip_tags((info.get("journal") or {}).get("title") or result.get("journalTitle") or "")


def result_to_row(result: dict, topic: str) -> tuple[dict | None, str]:
    """Bir API sonucunu ham satıra çevirir. Uygun değilse (None, neden) döner."""
    lic = license_label(result.get("license", ""))
    if not lic:
        return None, f"lisans uygun değil ({result.get('license') or 'yok'})"
    types = _pub_types(result)
    if any(b in t.lower() for t in types for b in BAD_TYPES):
        return None, "düzeltme/geri çekilmiş/yorum"
    if result.get("language") and result["language"].lower() not in ("eng", "en"):
        return None, f"dil {result['language']}"
    abstract = result.get("abstractText") or ""
    if len(clean_abstract(abstract).split()) < MIN_ABSTRACT_WORDS:
        return None, "özet kısa/yok"
    published = iso_date(result.get("firstPublicationDate")) or iso_date(result.get("pubYear"))
    year = int(published[:4]) if published else 0
    if year < MIN_YEAR:
        return None, f"eski ({published or 'tarih yok'})"
    src, rid = result.get("source", ""), result.get("id", "")
    if not (src and rid and result.get("title")):
        return None, "kimlik/başlık eksik"
    row = {
        "key": f"{src}:{rid}",
        "source": src,
        "id": rid,
        "pmid": result.get("pmid", ""),
        "pmcid": result.get("pmcid", ""),
        "doi": result.get("doi", ""),
        "title": strip_tags(result["title"]).rstrip("."),
        "abstract_html": abstract,
        "journal": _journal(result),
        "year": year,
        "published": published,
        "license": lic,
        "license_raw": result.get("license", ""),
        "authors": strip_tags(result.get("authorString", "")),
        "pub_types": types,
        "cited_by": int(result.get("citedByCount") or 0),
        "topics": [topic],
    }
    return row, ""


def pick_articles(
    results: list[dict], topic: str, per_topic: int
) -> tuple[list[dict], list[str]]:
    """Uygun adaylar arasından ilk CANDIDATES tanesini alıp atıf sayısına göre `per_topic` seçer.

    Sunucu sırası alaka sırasıdır; atıf sayısı eşitlikte alaka sırasını korur (kararlı sıralama).
    """
    candidates, skipped = [], []
    for r in results:
        row, why = result_to_row(r, topic)
        if row:
            candidates.append(row)
        else:
            skipped.append(f"{r.get('id', '?')}: {why}")
        if len(candidates) >= CANDIDATES:
            break
    ranked = sorted(candidates, key=lambda row: -row["cited_by"])
    return ranked[:per_topic], skipped


def fetch_topic(
    topic: str,
    get: Callable[[str], bytes],
    today: str,
    per_topic: int = DEFAULT_PER_TOPIC,
    search_term: str | None = None,
) -> tuple[list[dict], list[str]]:
    """Bir konu için en fazla iki sorgu: önce başlıkta eşleşme, yetmezse serbest ifade."""
    term = search_term or topic
    rows: list[dict] = []
    skipped: list[str] = []
    for title_only in (True, False):
        url = search_url(build_query(term, today, title_only=title_only))
        data = get_json(get, url)
        results = (data.get("resultList") or {}).get("result") or []
        picked, why = pick_articles(results, topic, per_topic)
        skipped += why
        seen = {r["key"] for r in rows}
        rows += [r for r in picked if r["key"] not in seen]
        rows = sorted(rows, key=lambda row: -row["cited_by"])[:per_topic]
        if len(rows) >= per_topic:
            break
    return rows, skipped


def merge_topic_rows(per_topic_rows: list[list[dict]]) -> list[dict]:
    """Aynı makale birden fazla konuda çıkarsa tek satırda birleştirir (konular birleşik)."""
    merged: dict[str, dict] = {}
    for rows in per_topic_rows:
        for row in rows:
            if row["key"] in merged:
                topics = merged[row["key"]]["topics"]
                merged[row["key"]]["topics"] = sorted(set(topics) | set(row["topics"]))
            else:
                merged[row["key"]] = dict(row)
    return list(merged.values())


def download_europepmc(
    raw_dir: Path,
    topics: list[str],
    get: Callable[[str], bytes] | None = None,
    per_topic: int = DEFAULT_PER_TOPIC,
    limit: int | None = None,
    workers: int = WORKERS,
    today: str | None = None,
    search_terms: dict[str, str] | None = None,
    rate: float = RATE,
) -> SourceReport:
    """Konular için derleme özetlerini çekip `europepmc/articles.jsonl` dosyasına birleştirir.

    Taze çalışmada sorgulanan konulara ait eski satırlardan bu kez dönmeyenler silinir
    (sıralama zamanla değişir); sorgulanmayan konuların satırları korunur.
    """
    start = time.time()
    today = today or today_iso()
    if limit:
        topics = topics[:limit]
    base = get or http_get
    fetch = limited(base, RateLimiter(rate)) if get is None else base
    terms = search_terms or {}

    def work(topic: str) -> tuple[list[dict], list[str]]:
        return fetch_topic(topic, fetch, today, per_topic, terms.get(topic))

    report = SourceReport(SOURCE, requested=len(topics))
    per_topic_rows: list[list[dict]] = []
    for out in run_parallel(work, topics, workers, label=SOURCE, every=25):
        if out.error:
            report.failed.append((out.item, describe_error(out.error)))
            continue
        rows, skipped = out.value
        per_topic_rows.append(rows)
        report.skipped += [f"{out.item}/{s}" for s in skipped]
        if rows:
            report.fetched += 1
        else:
            report.missing.append(out.item)
    fresh = merge_topic_rows(per_topic_rows)
    queried = {t for t in topics if t not in {x for x, _ in report.failed}}
    path = raw_dir / SOURCE / "articles.jsonl"
    if fresh or queried:
        report.stats = save_merged(
            path,
            fresh,
            key="key",
            content_keys=("title", "abstract_html", "license_raw", "doi"),
            today=today,
            drop_old=lambda old: set(old.get("topics", [])) <= queried,
        )
        report.path = path
        s = report.stats
        report.documents = s.added + s.updated + s.unchanged + s.kept
    report.samples = [f"{r['title']} ({r['journal']}, {r['year']})" for r in fresh[:6]]
    report.notes.append(
        f"konu başına en fazla {per_topic} makale; {len(fresh)} benzersiz makale; "
        f"lisanslar: {sorted({r['license'] for r in fresh})}"
    )
    report.seconds = time.time() - start
    if not fresh:
        report.fatal = "hiç makale alınamadı (sorgu sözdizimi/ağ?) - ilk hata/atlama ayrıntılarına bak"
    return report


def article_url(row: dict) -> str:
    return ARTICLE_URL.format(source=row["source"], id=row["id"])
