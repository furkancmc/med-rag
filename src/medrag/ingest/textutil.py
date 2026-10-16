"""Kaynaklar arasında ortak küçük metin yardımcıları."""

import hashlib
import html
import re
import unicodedata
from datetime import UTC, date, datetime

TAG = re.compile(r"<[^>]+>")
SPACES = re.compile("[ \\t\\xa0\\u2009\\u200b]+")


def today_iso() -> str:
    """Bugünün tarihi (UTC, ISO). Testlerde `today=` parametresiyle sabitlenir."""
    return datetime.now(UTC).date().isoformat()


def strip_tags(text: str) -> str:
    """HTML etiketlerini atar, varlıkları (&amp; vb.) çözer, boşlukları sadeleştirir."""
    return SPACES.sub(" ", html.unescape(TAG.sub(" ", text or ""))).strip()


def clean_whitespace(text: str) -> str:
    """Satır yapısını koruyarak fazla boşlukları ve boş satırları sadeleştirir."""
    lines = [SPACES.sub(" ", line).strip() for line in (text or "").splitlines()]
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()


def iso_date(value: object) -> str:
    """Çeşitli tarih biçimlerini ISO tarihe (YYYY-MM-DD) ya da yıla (YYYY) çevirir; tanınmazsa ''.

    Kabul edilenler: 2024-05-01, 20240501, 2024-05-01T10:00:00Z, 05/26/2003, 2021 (yalnız yıl).
    """
    s = str(value or "").strip()
    if not s:
        return ""
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})", s) or re.match(r"^(\d{4})(\d{2})(\d{2})$", s)
    if m:
        return _valid_date(*m.groups())
    m = re.match(r"^(\d{1,2})/(\d{1,2})/(\d{4})$", s)  # ABD biçimi: ay/gün/yıl
    if m:
        return _valid_date(m.group(3), m.group(1), m.group(2))
    if re.fullmatch(r"\d{4}", s):
        return s if 1800 <= int(s) <= 2200 else ""
    return ""


def _valid_date(year: str, month: str, day: str) -> str:
    try:
        return date(int(year), int(month), int(day)).isoformat()
    except ValueError:
        return ""


def normalize_for_hash(text: str) -> str:
    """Yinelenen metin tespiti için: küçük harf, aksansız, yalnız harf/rakam, tek boşluk."""
    text = text.replace("ı", "i").replace("İ", "i")
    text = unicodedata.normalize("NFKD", text.casefold())
    text = "".join(c for c in text if not unicodedata.combining(c))
    return " ".join(re.findall(r"[a-z0-9]+", text))


def text_hash(text: str) -> str:
    return hashlib.sha1(normalize_for_hash(text).encode("utf-8")).hexdigest()


def truncate_words(text: str, max_words: int) -> str:
    """En fazla `max_words` kelime bırakır; mümkünse cümle sonunda keser."""
    words = text.split()
    if len(words) <= max_words:
        return text
    cut = " ".join(words[:max_words])
    end = max(cut.rfind(". "), cut.rfind("? "), cut.rfind("! "))
    if end > len(cut) * 0.5:
        return cut[: end + 1]
    return cut.rstrip(",;:") + " …"


def slugify(text: str) -> str:
    """Kararlı, kimlik dostu ASCII ad: 'Amoxicillin/Clavulanate' -> 'amoxicillin-clavulanate'."""
    return "-".join(normalize_for_hash(text).split()) or "x"
