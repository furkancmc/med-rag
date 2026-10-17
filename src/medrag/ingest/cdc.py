"""CDC hastalık ve korunma sayfaları (ABD hükümet içeriği, kamu malı).

API: CDC Content Services (https://tools.cdc.gov/api/v2/resources/media). `www.cdc.gov` sayfalarının
kendisi bot koruması (403) verdiği için, sayfaların resmi "syndication" HTML'i kullanılır
(`/media/<id>/syndicate.json`). Her konu için arama yapılır, sonuçlar konunun URL önekine ve
tüketici sayfası olmasına göre süzülür (MMWR raporları, istatistik, hekim/`php`/`hcp` sayfaları,
infografik ve görsel sayfaları atılır), en uygun `per_topic` sayfa alınır.
"""

import re
import time
import urllib.parse
from collections.abc import Callable
from pathlib import Path

from .net import RateLimiter, describe_error, get_json, http_get, limited, run_parallel
from .rawstore import save_merged
from .report import SourceReport
from .textutil import clean_whitespace, iso_date, slugify, strip_tags, today_iso

SOURCE = "cdc"
SEARCH_URL = "https://tools.cdc.gov/api/v2/resources/media"
SYNDICATE_URL = "https://tools.cdc.gov/api/v2/resources/media/{id}/syndicate.json"
SITE = "https://www.cdc.gov"
LICENSE = "Public domain (US CDC; cdc.gov içeriği)"
DEFAULT_PER_TOPIC = 3
PAGE_SIZE = 50
MIN_WORDS = 80
WORKERS = 3
RATE = 3.0  # saniyede istek

# (Türkçe ad, arama sorgusu, cdc.gov URL öneki)
TOPICS: list[tuple[str, str, str]] = [
    ("Grip (influenza)", "flu", "/flu/"),
    ("Kızamık", "measles", "/measles/"),
    ("Kabakulak", "mumps", "/mumps/"),
    ("Kızamıkçık", "rubella", "/rubella/"),
    ("Suçiçeği", "chickenpox varicella", "/chickenpox/"),
    ("Zona", "shingles", "/shingles/"),
    ("Boğmaca", "whooping cough pertussis", "/pertussis/"),
    ("Tetanos", "tetanus", "/tetanus/"),
    ("Difteri", "diphtheria", "/diphtheria/"),
    ("Çocuk felci", "polio", "/polio/"),
    ("Hepatit A", "hepatitis A", "/hepatitis-a/"),
    ("Hepatit B", "hepatitis B", "/hepatitis-b/"),
    ("Hepatit C", "hepatitis C", "/hepatitis-c/"),
    ("HPV", "HPV human papillomavirus", "/hpv/"),
    ("HIV ve AIDS", "HIV", "/hiv/"),
    ("Tüberküloz", "tuberculosis", "/tb/"),
    ("COVID-19", "COVID-19", "/covid/"),
    ("RSV", "RSV respiratory syncytial virus", "/rsv/"),
    ("Pnömokok hastalığı", "pneumococcal", "/pneumococcal/"),
    ("Menenjit", "meningitis", "/meningitis/"),
    ("Menenjit aşısı (meningokok)", "meningococcal", "/meningococcal/"),
    ("Rotavirüs", "rotavirus", "/rotavirus/"),
    ("Norovirüs", "norovirus", "/norovirus/"),
    ("Gıda zehirlenmesi", "food safety food poisoning", "/food-safety/"),
    ("Salmonella", "salmonella", "/salmonella/"),
    ("E. coli", "E. coli", "/ecoli/"),
    ("Kolera", "cholera", "/cholera/"),
    ("Tifo", "typhoid fever", "/typhoid-fever/"),
    ("Sıtma", "malaria", "/malaria/"),
    ("Kuduz", "rabies", "/rabies/"),
    ("Lyme hastalığı", "lyme disease", "/lyme-disease/"),
    ("Kene ısırığı", "ticks", "/ticks/"),
    ("Sivrisinek kaynaklı hastalıklar", "mosquito bite prevention", "/mosquitoes/"),
    ("Cinsel yolla bulaşan enfeksiyonlar", "STI sexually transmitted infections", "/std/"),
    ("Klamidya", "chlamydia", "/std/chlamydia/"),
    ("Gonore", "gonorrhea", "/std/gonorrhea/"),
    ("Sifiliz", "syphilis", "/syphilis/"),
    ("El yıkama", "handwashing", "/clean-hands/"),
    ("Antibiyotik kullanımı ve direnç", "antibiotic use", "/antibiotic-use/"),
    ("Sepsis", "sepsis", "/sepsis/"),
    ("Diyabet", "diabetes", "/diabetes/"),
    ("Kalp hastalığı", "heart disease", "/heart-disease/"),
    ("Yüksek tansiyon", "high blood pressure", "/high-blood-pressure/"),
    ("Kolesterol", "cholesterol", "/cholesterol/"),
    ("İnme (felç)", "stroke", "/stroke/"),
    ("Kalp krizi", "heart attack", "/heart-disease/"),
    ("Astım", "asthma", "/asthma/"),
    ("KOAH", "COPD", "/copd/"),
    ("Kronik böbrek hastalığı", "chronic kidney disease", "/kidney-disease/"),
    ("Kanser", "cancer", "/cancer/"),
    ("Meme kanseri", "breast cancer", "/breast-cancer/"),
    ("Kolorektal kanser", "colorectal cancer", "/colorectal-cancer/"),
    ("Akciğer kanseri", "lung cancer", "/lung-cancer/"),
    ("Cilt kanseri ve güneşten korunma", "skin cancer", "/skin-cancer/"),
    ("Rahim ağzı kanseri", "cervical cancer", "/cervical-cancer/"),
    ("Prostat kanseri", "prostate cancer", "/prostate-cancer/"),
    ("Obezite ve sağlıklı kilo", "healthy weight obesity", "/healthy-weight-growth/"),
    ("Sağlıklı beslenme", "nutrition healthy eating", "/nutrition/"),
    ("Fiziksel aktivite", "physical activity", "/physical-activity-basics/"),
    ("Uyku", "sleep", "/sleep/"),
    ("Sigara ve tütün", "smoking tobacco", "/tobacco/"),
    ("Alkol", "alcohol", "/alcohol/"),
    ("Depresyon", "depression", "/depression/"),
    ("Anksiyete", "anxiety", "/anxiety/"),
    ("Ruh sağlığı", "mental health", "/mental-health/"),
    ("Alzheimer ve demans", "dementia alzheimer", "/alzheimers-dementia/"),
    ("Epilepsi", "epilepsy", "/epilepsy/"),
    ("Düşme ve yaşlılarda güvenlik", "older adult falls", "/falls/"),
    ("Hamilelik", "pregnancy", "/pregnancy/"),
    ("Gebelikte sağlıklı beslenme ve folik asit", "folic acid", "/folic-acid/"),
    ("Anne sütü ve emzirme", "breastfeeding", "/breastfeeding/"),
    ("Bebeklerde ani ölüm (SIDS) ve güvenli uyku", "safe sleep sudden infant death", "/sudden-infant-death/"),
    ("Çocuk aşıları", "child vaccines immunization schedule", "/vaccines/"),
    ("Çocuk gelişimi", "child development milestones", "/child-development/"),
    ("Otizm", "autism", "/autism/"),
    ("Dikkat eksikliği ve hiperaktivite (DEHB)", "ADHD", "/adhd/"),
    ("Kurşun zehirlenmesi", "lead poisoning", "/lead-prevention/"),
    ("Karbonmonoksit zehirlenmesi", "carbon monoxide poisoning", "/carbon-monoxide/"),
    ("Aşırı sıcak ve sıcak çarpması", "extreme heat", "/extreme-heat/"),
    ("Soğuk hava ve donma", "extreme cold", "/winter-weather/"),
    ("Yaralanma ve kazalardan korunma", "injury prevention", "/injury/"),
    ("Boğulma ve suda güvenlik", "drowning prevention", "/drowning/"),
    ("Kafa travması ve sarsıntı", "concussion", "/headinjury/"),
    ("Sağlıklı su ve hijyen", "healthy water", "/healthywater/"),
    ("Seyahat sağlığı", "travelers health", "/travel/"),
    ("Aşılar (yetişkin)", "adult vaccines", "/vaccines/"),
    ("Kronik yorgunluk sendromu", "ME/CFS chronic fatigue", "/me-cfs/"),
    ("Uzun COVID", "long COVID", "/covid/"),
    ("Orak hücre anemisi", "sickle cell disease", "/sickle-cell/"),
    ("Talasemi", "thalassemia", "/thalassemia/"),
    ("Hemofili", "hemophilia", "/hemophilia/"),
    ("Çölyak hastalığı", "celiac disease", "/celiac-disease/"),
    ("Alerjiler", "allergies", "/allergies/"),
    ("Gıda alerjisi", "food allergy", "/food-allergies/"),
    ("Işık ve görme sağlığı", "vision health", "/vision-health/"),
    ("İşitme kaybı", "hearing loss", "/hearing-loss/"),
    ("Ağız ve diş sağlığı", "oral health", "/oral-health/"),
]

# URL yolunda bunlardan biri varsa sayfa tüketiciye uygun değildir
BAD_PATH = (
    "/php/", "/hcp/", "/mmwr/", "/nchs/", "/data-research", "/communication-resources", "/resources/",
    "/health-equity", "/tv/", "/diabetes-tv", "/current-research", "/news", "/partners", "/funding",
    "/cdc-info", "/surveillance", "/laboratories", "/healthcare-providers", "/clinicians",
    "/clinical", "/data-reports", "/vitalsigns", "/campaign", "/pdf", "/social-media", "/infographic", "/dpk/", "/publications",
)
BAD_NAME = (
    "infographic", "photos", "social media", "video", "podcast", "toolkit", "statistics report",
    "campaign", "museum", "dashboard", "modules", "budget", "timeline", "amigas",
)
# Sayfa altlığı: "Aug. 26, 2024 Sources Print Share ..." ve atıf cümlesi
FOOTER = re.compile(
    r"(?:\n|^)\s*(?:[A-Z][a-z]{2,8}\.? \d{1,2}, \d{4}\s+Sources\b|Content Source:|"
    r"Content provided and maintained by)[\s\S]*$"
)
# Tüketici sayfası ipuçları: varsa sıralamada öne çıkar
GOOD_HINTS = (
    "about", "basics", "symptoms", "signs", "causes", "prevent", "treatment", "risk", "living-with",
    "testing", "vaccin", "spread", "complications", "facts",
)
BAD_SECTIONS = re.compile(
    r"^(on this page|related|more information|resources?|references?|sources?|languages?|other languages|"
    r"get email updates|contact|for more information|page last reviewed|links|"
    r"related topics|find help|share|print)\b",
    re.IGNORECASE,
)
H2 = re.compile(r"<h2\b[^>]*>(.*?)</h2>", re.IGNORECASE | re.DOTALL)
H1 = re.compile(r"<h1\b[^>]*>(.*?)</h1>", re.IGNORECASE | re.DOTALL)
DROP_BLOCKS = re.compile(
    r"<(script|style|nav|figure|noscript|svg|form|button)\b.*?</\1>", re.IGNORECASE | re.DOTALL
)


def search_url(query: str, page_size: int = PAGE_SIZE) -> str:
    params = {
        "q": query,
        "mediatype": "html",
        "language": "english",
        "max": str(page_size),
        "sort": "-datecontentupdated",
    }
    return f"{SEARCH_URL}?{urllib.parse.urlencode(params)}"


def normalize_url(url: str) -> str:
    return (url or "").split("#")[0].split("?")[0].replace("http://", "https://").rstrip("/")


def page_ok(item: dict, prefix: str, name_words: tuple[str, ...] = ()) -> bool:
    """Arama sonucu konunun URL önekinde, tüketici düzeyinde bir sayfa mı?

    `name_words` doluysa sayfa adı bunlardan en az birini içermelidir (önek dışı yedek eşleşme için).
    """
    url = normalize_url(item.get("sourceUrl") or "")
    if not url.startswith(SITE + prefix.rstrip("/")):
        return False
    path = url[len(SITE):] + "/"
    if any(b in path for b in BAD_PATH):
        return False
    name = (item.get("name") or "").lower()
    if any(b in name for b in BAD_NAME):
        return False
    return not name_words or any(w in name or w in path for w in name_words)


def _score(item: dict) -> tuple[int, str]:
    path = normalize_url(item.get("sourceUrl") or "").lower()
    hints = sum(1 for g in GOOD_HINTS if g in path)
    depth_bonus = 1 if path.count("/") <= 5 else 0  # köke yakın sayfalar genel bilgi taşır
    return hints + depth_bonus, item.get("dateContentUpdated") or ""


def select_pages(
    results: list[dict], prefix: str, per_topic: int, name_words: tuple[str, ...] = ()
) -> list[dict]:
    """Uygun sayfaları URL'ye göre tekilleştirip en iyi `per_topic` tanesini seçer."""
    unique: dict[str, dict] = {}
    for item in results:
        if not page_ok(item, prefix, name_words):
            continue
        unique.setdefault(normalize_url(item["sourceUrl"]), item)
    ranked = sorted(unique.values(), key=_score, reverse=True)
    return ranked[:per_topic]


def html_to_sections(html: str) -> tuple[str, list[tuple[str, str]]]:
    """Syndication HTML'ini (sayfa başlığı, [(bölüm başlığı, düz metin)]) çiftine çevirir."""
    html = DROP_BLOCKS.sub(" ", html or "")
    m = H1.search(html)
    title = strip_tags(m.group(1)) if m else ""
    html = H1.sub(" ", html)
    parts = H2.split(html)  # [giriş, başlık1, gövde1, başlık2, gövde2, ...]
    sections: list[tuple[str, str]] = []
    pairs = [("", parts[0])] + [(parts[i], parts[i + 1]) for i in range(1, len(parts) - 1, 2)]
    for head_html, body_html in pairs:
        head = strip_tags(head_html)
        if head and BAD_SECTIONS.match(head):
            continue
        body = re.sub(r"</(p|div|h[1-6]|ul|ol|tr)>|<br\s*/?>", "\n", body_html, flags=re.IGNORECASE)
        body = re.sub(r"<li\b[^>]*>", "\n- ", body, flags=re.IGNORECASE)
        body = H1.sub(" ", body)
        text = clean_whitespace(FOOTER.sub("", clean_whitespace(strip_tags_keep_lines(body))))
        if text:
            sections.append((head or "Özet", text))
    return title, sections


def strip_tags_keep_lines(text: str) -> str:
    """strip_tags satır sonlarını koruyarak (satır başına uygular)."""
    return "\n".join(strip_tags(line) for line in text.splitlines())


def fetch_page(item: dict, topic: str, name_tr: str, get: Callable[[str], bytes]) -> dict | None:
    data = get_json(get, SYNDICATE_URL.format(id=item["id"]))
    result = data.get("results") if isinstance(data, dict) else None
    if isinstance(result, list):
        result = result[0] if result else None
    if not isinstance(result, dict):
        return None
    title, sections = html_to_sections(result.get("content") or "")
    title = title or strip_tags(result.get("name") or item.get("name") or "")
    words = sum(len(t.split()) for _, t in sections)
    if not title or words < MIN_WORDS:
        return None
    url = normalize_url(result.get("sourceUrl") or item.get("sourceUrl") or "")
    published = iso_date(
        item.get("dateContentReviewed") or item.get("dateContentUpdated") or item.get("dateModified")
    )
    return {
        "slug": slugify(url[len(SITE):] or title),
        "media_id": item["id"],
        "title": title,
        "name_tr": name_tr,
        "topic": topic,
        "url": url,
        "published": published,
        "sections": [[h, t] for h, t in sections],
    }


def fetch_topic(
    entry: tuple[str, str, str], get: Callable[[str], bytes], per_topic: int
) -> tuple[list[dict], list[str]]:
    """Bir konu için (satırlar, süzme notları) döner."""
    name_tr, query, prefix = entry
    data = get_json(get, search_url(query))
    results = data.get("results") if isinstance(data, dict) else None
    results = results if isinstance(results, list) else []
    chosen = select_pages(results, prefix, per_topic)
    if not chosen:  # CDC'nin syndication kütüphanesi eksik olabilir: önek dışında ad eşleşmesi dene
        words = tuple(w for w in query.lower().split() if len(w) >= 4) or (query.lower(),)
        chosen = select_pages(results, "", per_topic, words)
    rows: list[dict] = []
    notes: list[str] = []
    if not chosen:
        notes.append("uygun sayfa yok")
    for item in chosen:
        row = fetch_page(item, query, name_tr, get)
        if row:
            rows.append(row)
        else:
            notes.append(f"kısa/boş sayfa ({item.get('name', '')})")
    return rows, notes


def download_cdc(
    raw_dir: Path,
    topics: list[tuple[str, str, str]] | None = None,
    get: Callable[[str], bytes] | None = None,
    per_topic: int = DEFAULT_PER_TOPIC,
    limit: int | None = None,
    workers: int = WORKERS,
    today: str | None = None,
    rate: float = RATE,
) -> SourceReport:
    """CDC sayfalarını çekip `cdc/pages.jsonl` dosyasına birleştirir (idempotent)."""
    start = time.time()
    today = today or today_iso()
    entries = list(topics if topics is not None else TOPICS)
    if limit:
        entries = entries[:limit]
    base = get or http_get
    fetch = limited(base, RateLimiter(rate)) if get is None else base
    report = SourceReport(SOURCE, requested=len(entries))
    by_slug: dict[str, dict] = {}
    for out in run_parallel(
        lambda e: fetch_topic(e, fetch, per_topic), entries, workers, label=SOURCE, every=20
    ):
        name = out.item[0]
        if out.error:
            report.failed.append((name, describe_error(out.error)))
            continue
        rows, notes = out.value
        report.skipped += [f"{name}/{n}" for n in notes]
        if rows:
            report.fetched += 1
        else:
            report.missing.append(name)
        for row in rows:
            by_slug.setdefault(row["slug"], row)  # aynı sayfa birden çok konuda gelebilir
    fresh = list(by_slug.values())
    if fresh:
        path = raw_dir / SOURCE / "pages.jsonl"
        report.stats = save_merged(
            path, fresh, key="slug", content_keys=("title", "sections", "published"), today=today
        )
        report.path = path
        s = report.stats
        report.documents = s.added + s.updated + s.unchanged + s.kept
    report.samples = [f"{r['title']} ({r['url']})" for r in fresh[:6]]
    report.notes.append(f"konu başına en fazla {per_topic} sayfa; {len(fresh)} benzersiz sayfa")
    report.seconds = time.time() - start
    if not fresh:
        report.fatal = "hiç CDC sayfası alınamadı (API/ağ?)"
    return report
