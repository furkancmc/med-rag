import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

USER_AGENT = "medrag/0.1 (https://github.com/furkancmc/phone; egitim amacli RAG projesi)"
WIKI_DELAY = 0.3  # her bağlantı kendi isteğinden önce bu kadar bekler
WIKI_WORKERS = 3  # paralel bağlantı sayısı; 429 gelirse http_get zaten bekleyip tekrar dener
MEDLINE_INDEX = "https://medlineplus.gov/xml.html"
MEDLINE_TOPICS = re.compile(r'href="([^"]*mplus_topics_\d{4}-\d{2}-\d{2}\.xml)"')

# Varsayılan Vikipedi kategorileri (adlar GitHub Actions'ta arama ile doğrulandı)
DEFAULT_CATEGORIES = {
    "tr": ["Kategori:Hastalıklar ve bozukluklar", "Kategori:Semptom ve belirtiler"],
    "en": ["Category:Diseases and disorders"],
}


def http_get(url: str, retries: int = 5) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                return resp.read()
        except urllib.error.HTTPError as e:
            retryable = e.code == 429 or e.code >= 500
            if not retryable or attempt == retries - 1:
                raise
            wait = e.headers.get("Retry-After", "")
            time.sleep(int(wait) if wait.isdigit() else 5 * 2**attempt)
        except OSError:
            if attempt == retries - 1:
                raise
            time.sleep(2**attempt)
    raise RuntimeError("ulaşılamaz")


def wiki_get(url: str) -> bytes:
    time.sleep(WIKI_DELAY)
    return http_get(url)


def find_medlineplus_urls(index_html: str) -> list[str]:
    urls = []
    for href in MEDLINE_TOPICS.findall(index_html):
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


def download_medlineplus(
    raw_dir: Path,
    get: Callable[[str], bytes] = http_get,
    languages: tuple[str, ...] = ("English",),
) -> Path:
    """Sayfadaki en güncel 'health topics' XML dosyasını indirip topics.jsonl yazar."""
    index = get(MEDLINE_INDEX).decode("utf-8", errors="replace")
    urls = find_medlineplus_urls(index)
    if not urls:
        raise RuntimeError("MedlinePlus sayfasında topics XML bağlantısı bulunamadı")
    latest = max(urls)  # dosya adlarındaki tarih ISO biçiminde, sıralama doğru çalışır
    rows = medlineplus_topics_from_xml(get(latest), languages)
    if not rows:
        raise RuntimeError(f"{latest} içinde {languages} dilinde konu bulunamadı")
    out_dir = raw_dir / "medlineplus"
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "topics.jsonl"
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    print(f"{latest}: {len(rows)} konu yazıldı")
    return path


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


def fetch_extracts(
    lang: str, titles: list[str], get: Callable[[str], bytes] = wiki_get
) -> list[dict]:
    """Tam metin (intro dışı) için Vikipedi sayfa başına tek istek kabul ediyor."""

    def fetch_one(title: str) -> list[dict]:
        params = {
            "action": "query",
            "prop": "extracts",
            "explaintext": "1",
            "redirects": "1",
            "titles": title,
        }
        data = json.loads(get(wiki_api(lang, params)))
        return data.get("query", {}).get("pages", [])

    with ThreadPoolExecutor(max_workers=WIKI_WORKERS) as pool:
        return [page for pages in pool.map(fetch_one, titles) for page in pages]


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


def download_wikipedia(
    raw_dir: Path,
    lang: str,
    categories: list[str],
    limit: int = 500,
    depth: int = 1,
    get: Callable[[str], bytes] = wiki_get,
) -> Path:
    titles: list[str] = []
    for cat in categories:
        titles += category_titles(lang, cat, get=get, depth=depth, limit=limit)
    titles = list(dict.fromkeys(titles))[:limit]
    if not titles:
        raise RuntimeError(f"{lang} için kategorilerde makale bulunamadı: {categories}")
    print(f"{lang}: {len(titles)} makale başlığı bulundu")
    pages = fetch_extracts(lang, titles, get=get)
    out_dir = raw_dir / "wikipedia"
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{lang}.jsonl"
    with path.open("w", encoding="utf-8") as f:
        for page in pages:
            f.write(json.dumps(page, ensure_ascii=False) + "\n")
    return path
