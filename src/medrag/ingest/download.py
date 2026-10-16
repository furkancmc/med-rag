"""MedlinePlus ve Vikipedi indirmeleri (yeni kaynaklar kendi modüllerinde: europepmc, openfda, nihods)."""

import json
import re
import time
import urllib.parse
import xml.etree.ElementTree as ET
from collections.abc import Callable
from pathlib import Path

from .net import USER_AGENT, RateLimiter, describe_error, http_get, run_parallel
from .rawstore import MergeStats, save_merged
from .report import SourceReport
from .textutil import iso_date, today_iso

WIKI_WORKERS = 4  # paralel bağlantı sayısı
WIKI_RATE = 8.0  # saniyede en fazla bu kadar istek (tüm bağlantılar toplamı)
MEDLINE_INDEX = "https://medlineplus.gov/xml.html"
MEDLINE_TOPICS = re.compile(r'href="([^"]*mplus_topics_(\d{4}-\d{2}-\d{2})\.xml)"')

# Varsayılan Vikipedi kategorileri (adlar GitHub Actions'ta arama ile doğrulandı)
DEFAULT_CATEGORIES = {
    "tr": ["Kategori:Hastalıklar ve bozukluklar", "Kategori:Semptom ve belirtiler"],
    "en": ["Category:Diseases and disorders"],
}

_wiki_limiter = RateLimiter(WIKI_RATE)


def wiki_get(url: str) -> bytes:
    _wiki_limiter.wait()
    return http_get(url)


# --- MedlinePlus ---


def find_medlineplus_urls(index_html: str) -> list[str]:
    urls = []
    for href, _date in MEDLINE_TOPICS.findall(index_html):
        full = urllib.parse.urljoin(MEDLINE_INDEX, href)
        if full not in urls:
            urls.append(full)
    return urls


def medlineplus_topics_from_xml(xml_bytes: bytes, languages: tuple[str, ...]) -> list[dict]:
    """XML'den sadece istenen dillerdeki konuları sade bir sözlük listesine çevirir."""
    root = ET.fromstring(xml_bytes)
    rows = []
    for topic in root.iter("health-topic"):
        if topic.get("language") not in languages:
            continue
        rows.append(
            {
                "id": topic.get("id"),
                "language": topic.get("language"),
                "title": topic.get("title", ""),
                "url": topic.get("url", ""),
                "summary_html": topic.findtext("full-summary") or "",
            }
        )
    return rows


def download_medlineplus_report(
    raw_dir: Path,
    get: Callable[[str], bytes] = http_get,
    languages: tuple[str, ...] = ("English",),
    today: str | None = None,
    limit: int | None = None,
) -> SourceReport:
    """Sayfadaki en güncel 'health topics' XML dosyasını indirip topics.jsonl'a birleştirir."""
    start = time.time()
    today = today or today_iso()
    index = get(MEDLINE_INDEX).decode("utf-8", errors="replace")
    urls = find_medlineplus_urls(index)
    if not urls:
        raise RuntimeError("MedlinePlus sayfasında topics XML bağlantısı bulunamadı")
    latest = max(urls)  # dosya adlarındaki tarih ISO biçiminde, sıralama doğru çalışır
    version = iso_date(latest.rsplit("_", 1)[-1].removesuffix(".xml"))
    rows = medlineplus_topics_from_xml(get(latest), languages)
    if not rows:
        raise RuntimeError(f"{latest} içinde {languages} dilinde konu bulunamadı")
    if limit:
        rows = rows[:limit]
    for row in rows:
        row["published"] = version  # konu metninin bu sürümde yayımlandığı tarih
    path = raw_dir / "medlineplus" / "topics.jsonl"
    stats = save_merged(
        path,
        rows,
        key=lambda r: f"{r['language']}-{r['id']}",
        content_keys=("title", "url", "summary_html"),
        today=today,
    )
    report = SourceReport(
        "medlineplus",
        path=path,
        requested=len(rows),
        fetched=len(rows),
        documents=stats.added + stats.updated + stats.unchanged + stats.kept,
        stats=stats,
        samples=[r["title"] for r in rows[:8]],
        notes=[f"kaynak dosya: {latest.rsplit('/', 1)[-1]}"],
        seconds=time.time() - start,
    )
    return report


def download_medlineplus(
    raw_dir: Path,
    get: Callable[[str], bytes] = http_get,
    languages: tuple[str, ...] = ("English",),
    today: str | None = None,
) -> Path:
    report = download_medlineplus_report(raw_dir, get, languages, today)
    print(report.render())
    return report.path or raw_dir


# --- Vikipedi ---


def wiki_api(lang: str, params: dict) -> str:
    q = urllib.parse.urlencode({**params, "format": "json", "formatversion": "2"})
    return f"https://{lang}.wikipedia.org/w/api.php?{q}"


def category_titles(
    lang: str,
    category: str,
    get: Callable[[str], bytes] = wiki_get,
    depth: int = 1,
    limit: int = 500,
) -> list[str]:
    """Kategorideki makale başlıklarını toplar, alt kategorilere 'depth' kadar iner."""
    titles: list[str] = []
    seen_cats = {category}
    queue = [(category, 0)]
    while queue and len(titles) < limit:
        cat, level = queue.pop(0)
        cont = None
        while True:
            params = {
                "action": "query",
                "list": "categorymembers",
                "cmtitle": cat,
                "cmlimit": "500",
                "cmtype": "page|subcat",
            }
            if cont:
                params["cmcontinue"] = cont
            data = json.loads(get(wiki_api(lang, params)))
            for m in data.get("query", {}).get("categorymembers", []):
                if m["ns"] == 0:
                    titles.append(m["title"])
                elif m["ns"] == 14 and level < depth and m["title"] not in seen_cats:
                    seen_cats.add(m["title"])
                    queue.append((m["title"], level + 1))
            cont = data.get("continue", {}).get("cmcontinue")
            if not cont:
                break
    return list(dict.fromkeys(titles))[:limit]


def _page_row(page: dict) -> dict:
    """API sayfasını ham satıra çevirir; son düzenleme zamanı `published` olur."""
    revisions = page.get("revisions") or [{}]
    return {
        "pageid": page.get("pageid"),
        "ns": page.get("ns", 0),
        "title": page.get("title", ""),
        "extract": page.get("extract") or "",
        "published": iso_date(revisions[0].get("timestamp", "")),
    }


def fetch_extracts_detailed(
    lang: str,
    titles: list[str],
    get: Callable[[str], bytes] = wiki_get,
    workers: int = WIKI_WORKERS,
) -> tuple[list[dict], list[tuple[str, str]]]:
    """Başlık başına tek istek (tam metin için Vikipedi sayfa başına tek istek kabul ediyor).

    Bir başlığın hatası diğerlerini durdurmaz. Döner: (sayfalar, [(başlık, hata])).
    """

    def fetch_one(title: str) -> list[dict]:
        params = {
            "action": "query",
            "prop": "extracts|revisions",
            "explaintext": "1",
            "rvprop": "timestamp",
            "redirects": "1",
            "titles": title,
        }
        data = json.loads(get(wiki_api(lang, params)))
        return data.get("query", {}).get("pages", [])

    pages, failed = [], []
    for out in run_parallel(fetch_one, titles, workers, label=f"vikipedi-{lang}"):
        if out.error:
            failed.append((out.item, describe_error(out.error)))
        else:
            pages.extend(out.value)
    return pages, failed


def fetch_extracts(
    lang: str, titles: list[str], get: Callable[[str], bytes] = wiki_get
) -> list[dict]:
    pages, failed = fetch_extracts_detailed(lang, titles, get)
    if failed and not pages:
        raise RuntimeError(f"hiçbir başlık alınamadı; ilk hata: {failed[0][1]}")
    return pages


def search_categories(lang: str, query: str, get: Callable[[str], bytes] = wiki_get) -> list[str]:
    """Doğru kategori adını bulmak için kategori sayfalarında arama yapar."""
    params = {
        "action": "query",
        "list": "search",
        "srsearch": query,
        "srnamespace": "14",
        "srlimit": "30",
    }
    data = json.loads(get(wiki_api(lang, params)))
    return [r["title"] for r in data.get("query", {}).get("search", [])]


def download_wikipedia_report(
    raw_dir: Path,
    lang: str,
    categories: list[str] | None = None,
    limit: int | None = 500,
    depth: int = 1,
    get: Callable[[str], bytes] = wiki_get,
    titles: list[str] | None = None,
    today: str | None = None,
    prune: bool = False,
    workers: int = WIKI_WORKERS,
) -> SourceReport:
    """Verilen başlıkları ya da kategorilerdeki makaleleri indirip `<lang>.jsonl`'a birleştirir.

    `prune=True` (yalnız tam çalışmada): bu çalışmada alınmayan eski satırlar silinir.
    """
    start = time.time()
    today = today or today_iso()
    if titles is None:
        titles = []
        for cat in categories or []:
            titles += category_titles(lang, cat, get=get, depth=depth, limit=limit or 500)
        titles = list(dict.fromkeys(titles))[: limit or 500]
    elif limit:
        titles = titles[:limit]
    if not titles:
        raise RuntimeError(f"{lang} için indirilecek makale bulunamadı: {categories}")
    print(f"{lang}: {len(titles)} başlık isteniyor", flush=True)
    pages, failed = fetch_extracts_detailed(lang, titles, get=get, workers=workers)

    kept, seen, missing = [], set(), []
    for page in pages:
        if "missing" in page or not (page.get("extract") or "").strip():
            missing.append(page.get("title", "?"))
        elif page["pageid"] not in seen:  # iki başlık aynı sayfaya yönlenebilir
            seen.add(page["pageid"])
            kept.append(_page_row(page))
    if not kept:
        detail = failed[0][1] if failed else "tüm sayfalar boş/bulunamadı"
        raise RuntimeError(f"{lang}: hiç makale alınamadı ({detail})")

    path = raw_dir / "wikipedia" / f"{lang}.jsonl"
    stats: MergeStats = save_merged(
        path,
        kept,
        key="pageid",
        content_keys=("title", "extract"),
        today=today,
        drop_old=(lambda _row: True) if prune else None,
    )
    return SourceReport(
        f"wikipedia-{lang}",
        path=path,
        requested=len(titles),
        fetched=len(kept),
        documents=stats.added + stats.updated + stats.unchanged + stats.kept,
        missing=missing,
        failed=failed,
        stats=stats,
        samples=[r["title"] for r in kept[:8]],
        seconds=time.time() - start,
    )


def download_wikipedia(
    raw_dir: Path,
    lang: str,
    categories: list[str] | None = None,
    limit: int = 500,
    depth: int = 1,
    get: Callable[[str], bytes] = wiki_get,
    titles: list[str] | None = None,
) -> Path:
    """Geriye uyumlu sarmalayıcı: raporu yazdırır, ham dosyanın yolunu döner."""
    report = download_wikipedia_report(
        raw_dir, lang, categories, None if titles is not None else limit, depth, get, titles
    )
    print(report.render())
    return report.path or raw_dir


__all__ = [
    "DEFAULT_CATEGORIES",
    "USER_AGENT",
    "category_titles",
    "download_medlineplus",
    "download_medlineplus_report",
    "download_wikipedia",
    "download_wikipedia_report",
    "fetch_extracts",
    "fetch_extracts_detailed",
    "find_medlineplus_urls",
    "http_get",
    "medlineplus_topics_from_xml",
    "search_categories",
    "wiki_api",
    "wiki_get",
]
