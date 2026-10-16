"""NIH Office of Dietary Supplements (ODS) bilgi sayfaları (kamu malı, tüketici düzeyi).

API: https://ods.od.nih.gov/api/?resourcename=<Ad>&readinglevel=Consumer&outputformat=JSON
Yanıt biçimi sürümler arasında değişebildiği için ayrıştırıcı toleranslıdır: iç içe yapıda
başlık + metin çiftlerini bulur. Not: ODS bazı ağlarda bot koruması (403) uygular; bu durum
kaynak raporunda "hata" olarak görünür, diğer kaynakları etkilemez.
"""

import json
import time
import urllib.parse
from collections.abc import Callable
from pathlib import Path

from .net import RateLimiter, describe_error, http_get, limited, run_parallel
from .rawstore import save_merged
from .report import SourceReport
from .textutil import clean_whitespace, iso_date, slugify, strip_tags, today_iso

SOURCE = "nihods"
API_URL = "https://ods.od.nih.gov/api/"
PAGE_URL = "https://ods.od.nih.gov/factsheets/{name}-Consumer/"
LICENSE = "Public domain (NIH Office of Dietary Supplements)"
RATE = 2.0
WORKERS = 3

# (ODS kaynak adı, Türkçe ad)
SUPPLEMENTS: list[tuple[str, str]] = [
    ("VitaminD", "D vitamini"),
    ("VitaminB12", "B12 vitamini"),
    ("VitaminC", "C vitamini"),
    ("VitaminA", "A vitamini"),
    ("VitaminE", "E vitamini"),
    ("VitaminK", "K vitamini"),
    ("VitaminB6", "B6 vitamini"),
    ("Folate", "Folat (folik asit)"),
    ("Thiamin", "B1 vitamini (tiamin)"),
    ("Riboflavin", "B2 vitamini (riboflavin)"),
    ("Niacin", "Niasin (B3 vitamini)"),
    ("Biotin", "Biyotin"),
    ("Choline", "Kolin"),
    ("Iron", "Demir"),
    ("Calcium", "Kalsiyum"),
    ("Magnesium", "Magnezyum"),
    ("Zinc", "Çinko"),
    ("Potassium", "Potasyum"),
    ("Selenium", "Selenyum"),
    ("Iodine", "İyot"),
    ("Copper", "Bakır"),
    ("Chromium", "Krom"),
    ("Phosphorus", "Fosfor"),
    ("Omega3FattyAcids", "Omega-3 yağ asitleri"),
    ("Probiotics", "Probiyotikler"),
    ("Melatonin", "Melatonin"),
    ("Ashwagandha", "Ashwagandha"),
    ("Echinacea", "Ekinezya"),
    ("Garlic", "Sarımsak takviyesi"),
    ("Ginger", "Zencefil"),
    ("Turmeric", "Zerdeçal"),
    ("Cranberry", "Kızılcık"),
    ("Ginkgo", "Ginkgo"),
    ("Coenzyme-Q10", "Koenzim Q10"),
    ("Creatine", "Kreatin"),
    ("Fiber", "Lif"),
    ("MultivitaminMineral", "Multivitamin/mineral takviyeleri"),
]

HEAD_KEYS = ("heading", "title", "sectiontitle", "name", "header")
TEXT_KEYS = ("text", "content", "body", "html", "description")
CHILD_KEYS = ("sections", "subsections", "children", "items", "content")


def _get(d: dict, keys: tuple[str, ...]):
    lowered = {k.lower(): v for k, v in d.items()}
    for k in keys:
        if k in lowered and lowered[k] not in (None, ""):
            return lowered[k]
    return None


def extract_sections(node: object, depth: int = 0) -> list[tuple[str, str]]:
    """Yanıt ağacından (başlık, düz metin) çiftleri çıkarır."""
    out: list[tuple[str, str]] = []
    if isinstance(node, list):
        for item in node:
            out += extract_sections(item, depth)
    elif isinstance(node, dict) and depth < 8:
        head = _get(node, HEAD_KEYS)
        text = _get(node, TEXT_KEYS)
        if isinstance(head, str) and isinstance(text, str):
            html = text.replace("</p>", "\n").replace("<li>", "\n- ")
            body = clean_whitespace(strip_tags(html))
            if body:
                out.append((strip_tags(head), body))
        for key, value in node.items():
            if key.lower() in CHILD_KEYS and isinstance(value, list | dict):
                out += extract_sections(value, depth + 1)
    return out


def api_url(resource: str) -> str:
    q = urllib.parse.urlencode(
        {"resourcename": resource, "readinglevel": "Consumer", "outputformat": "JSON"}
    )
    return f"{API_URL}?{q}"


def fetch_factsheet(entry: tuple[str, str], get: Callable[[str], bytes]) -> dict | None:
    resource, name_tr = entry
    data = json.loads(get(api_url(resource)))
    sections = extract_sections(data)
    if not sections:
        return None
    root = data[0] if isinstance(data, list) and data else data
    title = (_get(root, HEAD_KEYS) if isinstance(root, dict) else None) or resource
    published = ""
    if isinstance(root, dict):
        published = iso_date(_get(root, ("lastupdated", "last_updated", "updated", "date")) or "")
    return {
        "slug": slugify(resource),
        "resource": resource,
        "title": strip_tags(str(title)),
        "name_tr": name_tr,
        "published": published,
        "sections": [[h, t] for h, t in sections],
    }


def download_nihods(
    raw_dir: Path,
    supplements: list[tuple[str, str]] | None = None,
    get: Callable[[str], bytes] | None = None,
    limit: int | None = None,
    workers: int = WORKERS,
    today: str | None = None,
    rate: float = RATE,
) -> SourceReport:
    start = time.time()
    today = today or today_iso()
    entries = list(supplements if supplements is not None else SUPPLEMENTS)
    if limit:
        entries = entries[:limit]
    base = get or http_get
    fetch = limited(base, RateLimiter(rate)) if get is None else base
    report = SourceReport(SOURCE, requested=len(entries))
    rows: list[dict] = []
    for out in run_parallel(lambda e: fetch_factsheet(e, fetch), entries, workers, label=SOURCE):
        if out.error:
            report.failed.append((out.item[0], describe_error(out.error)))
        elif out.value is None:
            report.missing.append(out.item[0])
        else:
            rows.append(out.value)
    report.fetched = len(rows)
    if rows:
        path = raw_dir / SOURCE / "factsheets.jsonl"
        report.stats = save_merged(
            path, rows, key="slug", content_keys=("title", "sections", "name_tr"), today=today
        )
        report.path = path
        s = report.stats
        report.documents = s.added + s.updated + s.unchanged + s.kept
    report.samples = [r["title"] for r in rows[:6]]
    report.seconds = time.time() - start
    if not rows:
        report.fatal = "hiç bilgi sayfası alınamadı (ODS bot koruması/403 olabilir)"
    return report


def page_url(row: dict) -> str:
    return PAGE_URL.format(name=row["resource"])
