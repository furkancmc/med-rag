import json
import re
import time
import urllib.parse
import urllib.request
from collections.abc import Callable
from pathlib import Path

USER_AGENT = "medrag/0.1 (egitim amacli RAG projesi)"
MEDLINE_INDEX = "https://medlineplus.gov/xml.html"
MEDLINE_TOPICS = re.compile(r'href="([^"]*mplus_topics_\d{4}-\d{2}-\d{2}\.xml)"')

# Varsayılan Vikipedi kategorileri (ağ açılınca doğrulanacak, CLI'dan değiştirilebilir)
DEFAULT_CATEGORIES = {
    "tr": ["Kategori:Hastalıklar"],
    "en": ["Category:Diseases and disorders"],
}


def http_get(url: str, retries: int = 3) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                return resp.read()
        except OSError:
            if attempt == retries - 1:
                raise
            time.sleep(2**attempt)
    raise RuntimeError("ulaşılamaz")


def find_medlineplus_urls(index_html: str) -> list[str]:
    urls = []
    for href in MEDLINE_TOPICS.findall(index_html):
        full = urllib.parse.urljoin(MEDLINE_INDEX, href)
        if full not in urls:
            urls.append(full)
    return urls


def download_medlineplus(raw_dir: Path, get: Callable[[str], bytes] = http_get) -> list[Path]:
    """xml.html sayfasındaki güncel 'health topics' XML dosyalarını indirir."""
    index = get(MEDLINE_INDEX).decode("utf-8", errors="replace")
    urls = find_medlineplus_urls(index)
    if not urls:
        raise RuntimeError("MedlinePlus sayfasında topics XML bağlantısı bulunamadı")
    out_dir = raw_dir / "medlineplus"
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    for url in urls:
        path = out_dir / url.rsplit("/", 1)[-1]
        path.write_bytes(get(url))
        paths.append(path)
    return paths


def wiki_api(lang: str, params: dict) -> str:
    q = urllib.parse.urlencode({**params, "format": "json", "formatversion": "2"})
    return f"https://{lang}.wikipedia.org/w/api.php?{q}"


def category_titles(
    lang: str,
    category: str,
    get: Callable[[str], bytes] = http_get,
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
    lang: str, titles: list[str], get: Callable[[str], bytes] = http_get
) -> list[dict]:
    """Başlıkların düz metin içeriğini 20'şerli gruplar halinde çeker."""
    pages = []
    for i in range(0, len(titles), 20):
        params = {
            "action": "query",
            "prop": "extracts",
            "explaintext": "1",
            "exlimit": "max",
            "redirects": "1",
            "titles": "|".join(titles[i : i + 20]),
        }
        data = json.loads(get(wiki_api(lang, params)))
        pages.extend(data.get("query", {}).get("pages", []))
    return pages


def download_wikipedia(
    raw_dir: Path,
    lang: str,
    categories: list[str],
    limit: int = 500,
    depth: int = 1,
    get: Callable[[str], bytes] = http_get,
) -> Path:
    titles: list[str] = []
    for cat in categories:
        titles += category_titles(lang, cat, get=get, depth=depth, limit=limit)
    titles = list(dict.fromkeys(titles))[:limit]
    pages = fetch_extracts(lang, titles, get=get)
    out_dir = raw_dir / "wikipedia"
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{lang}.jsonl"
    with path.open("w", encoding="utf-8") as f:
        for page in pages:
            f.write(json.dumps(page, ensure_ascii=False) + "\n")
    return path
