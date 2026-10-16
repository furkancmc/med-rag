"""openFDA ilaç prospektüsleri (https://api.fda.gov/drug/label.json, kamu malı).

Her ilaç için tek istek yapılır (`generic_name` araması, en yeni 25 etiket); aralarından jenerik adı
tam eşleşen ve en çok bölümü olan en yeni etiket seçilir. Yalnızca endikasyon, uyarı, yan etki,
etkileşim ve özel grup bölümleri saklanır; DOZ içeren bölümler (dosage_and_administration,
dosage_forms_and_strengths, overdosage, clinical_pharmacology...) hiç alınmaz.

Sınırlar: anahtarsız 240 istek/dk ve 1000 istek/gün. Hız sınırlayıcı ve günlük bütçe sayacı vardır;
`OPENFDA_API_KEY` ortam değişkeni verilirse limitler yükselir (anahtar günlüğe yazılmaz).
"""

import re
import threading
import time
import urllib.parse
from collections.abc import Callable
from pathlib import Path

from .drugs import DRUGS
from .net import (
    RateLimiter,
    describe_error,
    get_json_or_none,
    http_get,
    limited,
    run_parallel,
)
from .rawstore import save_merged
from .report import SourceReport
from .textutil import (
    clean_whitespace,
    iso_date,
    slugify,
    text_hash,
    today_iso,
    truncate_words,
)

SOURCE = "openfda"
API_URL = "https://api.fda.gov/drug/label.json"
DAILYMED_URL = "https://dailymed.nlm.nih.gov/dailymed/lookup.cfm?setid={set_id}"
LICENSE = "Public domain (FDA openFDA)"
RATE = 3.0  # saniyede istek (sınır 4/sn = 240/dk; geri çekilme payı bırakılır)
WORKERS = 4
CANDIDATES = 25
NO_KEY_DAILY_BUDGET = 900  # 1000/gün sınırının altında kalmak için
KEY_DAILY_BUDGET = 100_000

# Alınan bölümler: (openFDA alanı, Türkçe başlık, en fazla kelime). DOZ bölümleri bilerek yok.
SECTIONS: list[tuple[str, str, int]] = [
    ("indications_and_usage", "Endikasyonlar (ne için kullanılır)", 250),
    ("purpose", "Kullanım amacı", 80),
    ("boxed_warning", "Kutulu uyarı (en ciddi risk uyarısı)", 250),
    ("contraindications", "Kontrendikasyonlar (kullanılmaması gerekenler)", 200),
    ("warnings_and_cautions", "Uyarılar ve önlemler", 450),
    ("warnings", "Uyarılar", 450),
    ("precautions", "Önlemler", 350),
    ("do_not_use", "Şu durumlarda kullanmayın", 120),
    ("ask_doctor", "Kullanmadan önce doktora danışın", 150),
    ("ask_doctor_or_pharmacist", "Doktor veya eczacıya danışın", 150),
    ("when_using", "Kullanırken dikkat", 100),
    ("stop_use", "Şu durumlarda kullanmayı bırakın", 120),
    ("pregnancy_or_breast_feeding", "Gebelik ve emzirme", 120),
    ("adverse_reactions", "Yan etkiler", 350),
    ("drug_interactions", "İlaç etkileşimleri", 350),
    ("use_in_specific_populations", "Özel gruplarda kullanım", 350),
    ("pregnancy", "Gebelik", 250),
    ("nursing_mothers", "Emzirme", 150),
    ("lactation", "Emzirme", 150),
    ("pediatric_use", "Çocuklarda kullanım", 150),
    ("geriatric_use", "Yaşlılarda kullanım", 120),
    ("mechanism_of_action", "Etki mekanizması", 150),
    ("information_for_patients", "Hasta bilgilendirmesi", 250),
]
SECTION_FIELDS = [f for f, _, _ in SECTIONS]
SPECIFIC_POPULATION_FIELDS = ("pregnancy", "nursing_mothers", "lactation", "pediatric_use", "geriatric_use")
# 'warnings_and_cautions' varsa eski biçimli 'warnings'/'precautions' alınmaz (aynı içerik)
EXCLUSIVE = {"warnings": "warnings_and_cautions", "precautions": "warnings_and_cautions"}
SHORT_ONLY = {"information_for_patients": 250}  # uzunsa alınmaz

SALT_WORDS = frozenset(
    {
        "hydrochloride", "hcl", "sodium", "potassium", "calcium", "magnesium", "sulfate", "sulphate",
        "tartrate", "succinate", "besylate", "maleate", "mesylate", "acetate", "citrate", "phosphate",
        "anhydrous", "monohydrate", "dihydrate", "trihydrate", "hydrate", "bromide", "hydrobromide",
        "fumarate", "dipropionate", "nitrate", "oxalate", "lactate", "gluconate", "pamoate",
        "disoproxil", "tromethamine", "xinafoate", "medoxomil", "axetil", "base",
    }
)  # fmt: skip
CATIONS = frozenset({"sodium", "potassium", "calcium", "magnesium"})


class BudgetExceeded(RuntimeError):
    """Günlük istek bütçesi doldu."""


class RequestBudget:
    def __init__(self, limit: int):
        self.limit = limit
        self.used = 0
        self._lock = threading.Lock()

    def take(self) -> None:
        with self._lock:
            if self.used >= self.limit:
                raise BudgetExceeded(f"günlük istek bütçesi doldu ({self.limit})")
            self.used += 1


def norm_generic(name: str) -> str:
    """Karşılaştırma için jenerik adı sadeleştirir ('INSULIN GLARGINE-YFGN' -> 'insulin glargine')."""
    s = re.sub(r"-[a-z]{4}\b", "", name.lower())
    return " ".join(re.findall(r"[a-z0-9]+", s))


def strip_salts(norm: str) -> str:
    return " ".join(t for t in norm.split() if t not in SALT_WORDS)


def name_matches(label_name: str, term: str) -> bool:
    """Etiketin jenerik adı arama terimiyle aynı etken madde mi? (kombinasyonlar elenir)"""
    label_n, term_n = norm_generic(label_name), norm_generic(term)
    if label_n == term_n:
        return True
    stripped_term = strip_salts(term_n)
    if not stripped_term or (CATIONS & set(term_n.split()) and len(stripped_term.split()) <= 1):
        return False  # örn. 'potassium chloride' yalnızca tam eşleşir ('sodium chloride' ≠)
    return strip_salts(label_n) == stripped_term


def label_names(label: dict) -> list[str]:
    openfda = label.get("openfda") or {}
    return list(openfda.get("generic_name") or [])


def clean_label_text(text: str) -> str:
    """Etiket metnindeki numaralı başlıkları, çapraz atıfları ve boşlukları sadeleştirir."""
    text = re.sub(r"\[\s*see [^\]]*\]", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"\(\s*\d{1,2}(?:\.\d{1,2})*(?:\s*[,;]\s*\d{1,2}(?:\.\d{1,2})*)*\s*\)", " ", text)
    # başta "1 INDICATIONS AND USAGE" ya da "WARNINGS" gibi bölüm başlığı
    text = re.sub(r"^\s*(?:\d{1,2}(?:\.\d{1,2})*\s+)?[A-Z][A-Z &,/()'-]{4,}(?=\s+[A-Z][a-z])", "", text)
    # satır içi alt başlık numaraları ("5.1 Hepatotoxicity") yeni satıra
    text = re.sub(r"\s(\d{1,2}\.\d{1,2})\s+(?=[A-Z])", "\n", text)
    text = re.sub(r"[ \t]+", " ", text)
    return clean_whitespace(text)


def section_text(value: object) -> str:
    """openFDA alan değeri (metin listesi ya da metin) -> tek metin."""
    if isinstance(value, list):
        return "\n".join(str(v) for v in value if str(v).strip())
    return str(value or "")


def extract_sections(label: dict) -> dict[str, str]:
    """Etiketten izin verilen, boş olmayan bölümleri (ham metin, 3x kelime sınırıyla) alır."""
    out: dict[str, str] = {}
    for field, _title, cap in SECTIONS:
        text = section_text(label.get(field)).strip()
        if text:
            out[field] = truncate_words(text, cap * 3)
    return out


def score_label(label: dict, sections: dict[str, str]) -> tuple:
    has_safety = any(f in sections for f in ("warnings_and_cautions", "warnings", "contraindications"))
    return (
        "indications_and_usage" in sections,
        has_safety,
        len(sections),
        iso_date(label.get("effective_time")),
    )


def choose_label(results: list[dict], terms: list[str]) -> tuple[dict | None, dict[str, str]]:
    best, best_sections, best_score = None, {}, None
    for label in results:
        if not any(name_matches(n, t) for n in label_names(label) for t in terms):
            continue
        sections = extract_sections(label)
        if "indications_and_usage" not in sections:
            continue
        score = score_label(label, sections)
        if best_score is None or score > best_score:
            best, best_sections, best_score = label, sections, score
    return best, best_sections


def build_sections(sections: dict[str, str]) -> list[tuple[str, str]]:
    """Ham bölümlerden (alan -> metin) belgeye girecek (Türkçe başlık, temiz metin) listesini üretir.

    Kurallar: 'warnings_and_cautions' varsa eski 'warnings'/'precautions' atlanır; ayrı gebelik/
    emzirme/çocuk/yaşlı bölümleri varsa toplu 'özel gruplar' bölümü atlanır; hasta bilgilendirmesi
    uzunsa atlanır; aynı metin ikinci kez eklenmez.
    """
    out: list[tuple[str, str]] = []
    seen: set[str] = set()
    for field, title, cap in SECTIONS:
        raw = sections.get(field)
        if not raw:
            continue
        if field in EXCLUSIVE and EXCLUSIVE[field] in sections:
            continue
        if field == "use_in_specific_populations" and any(
            f in sections for f in SPECIFIC_POPULATION_FIELDS
        ):
            continue
        text = clean_label_text(raw)
        if field in SHORT_ONLY and len(text.split()) > SHORT_ONLY[field]:
            continue
        text = truncate_words(text, cap)
        key = text_hash(text)
        if len(text.split()) < 3 or key in seen:
            continue
        seen.add(key)
        out.append((title, text))
    return out


def search_url(term: str, api_key: str = "", limit: int = CANDIDATES) -> str:
    params = {
        "search": f'openfda.generic_name:"{term}"',
        "sort": "effective_time:desc",
        "limit": str(limit),
    }
    if api_key:
        params["api_key"] = api_key
    return f"{API_URL}?{urllib.parse.urlencode(params, quote_via=urllib.parse.quote_plus)}"


def fetch_drug(
    entry: tuple[str, str, tuple[str, ...]],
    get: Callable[[str], bytes],
    api_key: str = "",
) -> dict | None:
    """Bir ilaç için en uygun etiketi seçip ham satıra çevirir; bulunamazsa None."""
    term, name_tr, brands = entry
    terms = [t.strip() for t in term.split("|")]
    label, sections = None, {}
    for t in terms:
        data = get_json_or_none(get, search_url(t, api_key))  # 404 = sonuç yok
        results = (data or {}).get("results") or []
        label, sections = choose_label(results, terms)
        if label:
            break
    if not label:
        return None
    published = iso_date(label.get("effective_time"))
    return {
        "slug": slugify(terms[0]),
        "term": terms[0],
        "name_tr": name_tr,
        "brands": list(brands),
        "label_name": (label_names(label) or [""])[0],
        "set_id": label.get("set_id", ""),
        "version": str(label.get("version", "")),
        "published": published,
        "sections": sections,
    }


def download_openfda(
    raw_dir: Path,
    drugs: list[tuple[str, str, tuple[str, ...]]] | None = None,
    get: Callable[[str], bytes] | None = None,
    limit: int | None = None,
    workers: int = WORKERS,
    today: str | None = None,
    api_key: str = "",
    rate: float = RATE,
) -> SourceReport:
    start = time.time()
    today = today or today_iso()
    entries = list(drugs if drugs is not None else DRUGS)
    if limit:
        entries = entries[:limit]
    budget = RequestBudget(KEY_DAILY_BUDGET if api_key else NO_KEY_DAILY_BUDGET)
    base = get or http_get
    limiter = RateLimiter(rate if get is None else 0)

    paced = limited(base, limiter)

    def counted(url: str) -> bytes:
        budget.take()
        return paced(url)

    report = SourceReport(SOURCE, requested=len(entries))
    rows: list[dict] = []
    for out in run_parallel(
        lambda e: fetch_drug(e, counted, api_key), entries, workers, label=SOURCE, every=25
    ):
        term = out.item[0]
        if out.error:
            report.failed.append((term, describe_error(out.error)))
        elif out.value is None:
            report.missing.append(term)
        else:
            rows.append(out.value)
    report.fetched = len(rows)
    report.notes.append(f"API istekleri: {budget.used} (günlük bütçe {budget.limit})")
    if rows:
        path = raw_dir / SOURCE / "labels.jsonl"
        report.stats = save_merged(
            path,
            rows,
            key="slug",
            content_keys=("sections", "set_id", "version", "name_tr", "brands"),
            today=today,
        )
        report.path = path
        s = report.stats
        report.documents = s.added + s.updated + s.unchanged + s.kept
    report.samples = [f"{r['label_name']} ({r['published']})" for r in rows[:6]]
    report.seconds = time.time() - start
    if not rows:
        report.fatal = "hiç etiket alınamadı (ağ, sorgu sözdizimi ya da günlük bütçe?)"
    return report


def label_url(row: dict) -> str:
    if row.get("set_id"):
        return DAILYMED_URL.format(set_id=row["set_id"])
    return f"https://open.fda.gov/apis/drug/label/?q={urllib.parse.quote(row['term'])}"
