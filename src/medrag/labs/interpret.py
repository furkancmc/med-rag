"""Kural tabanlı tahlil yorumlayıcı: ad eşleştirme, sayı/birim ayrıştırma, sınıflandırma.

Sınıflandırma tamamen kuraldır (LLM karışmaz). Birim tanınmazsa ya da belirtilmemişse tahmin yürütülmez;
sonuç "unknown" olur.
"""

import re
import unicodedata
from dataclasses import dataclass, field

from .reference import SEXES, TESTS, LabTest

# --- Ad eşleştirme ---

_TR = str.maketrans({"ı": "i", "İ": "i", "I": "i", "ş": "s", "Ş": "s", "ğ": "g", "Ğ": "g",
                     "ü": "u", "Ü": "u", "ö": "o", "Ö": "o", "ç": "c", "Ç": "c"})


def fold(text: str) -> str:
    """Küçük harf, Türkçe karakterleri sadeleştir, noktalama yerine boşluk koy."""
    text = unicodedata.normalize("NFKD", text.translate(_TR).lower())
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = re.sub(r"[^a-z0-9+\-]+", " ", text).replace(" - ", " ")
    return re.sub(r"\s+", " ", text).strip()


# Bu sözcükler varsa ad başka bir testi (ör. "direkt bilirubin", "kreatinin klirensi") ifade eder.
_EXCLUDE = {"direkt", "indirekt", "direct", "indirect", "klirens", "klirensi", "klerens", "clearance",
            "egfr", "gfr", "idrar", "urine", "oran", "orani", "ratio", "baglama", "kapasitesi",
            "kapasite", "tibc", "uibc", "mikroalbumin", "spot", "gunluk"}
_PRIORITY = ("ldl", "hdl", "hba1c", "ft4")


def _build_index() -> tuple[dict[str, LabTest], list[tuple[str, LabTest]]]:
    exact: dict[str, LabTest] = {}
    for t in TESTS:
        for name in (t.id, t.name, *t.aliases):
            exact.setdefault(fold(name), t)
    contained = sorted(((k, t) for k, t in exact.items() if len(k) >= 3), key=lambda kt: -len(kt[0]))
    return exact, contained


_EXACT, _CONTAINED = _build_index()


def match_test(name: str) -> LabTest | None:
    """Rapordaki test adını katalogdaki teste eşler; emin değilse None döner."""
    if not name or not name.strip():
        return None
    key = fold(name)
    if not key:
        return None
    if key in _EXACT:
        return _EXACT[key]
    words = set(key.split())
    if words & _EXCLUDE:
        return None
    padded = f" {key} "
    for pid in _PRIORITY:
        for alias, t in _CONTAINED:
            if t.id == pid and f" {alias} " in padded:
                return t
    hits = {t.id: t for alias, t in _CONTAINED if f" {alias} " in padded}
    if len(hits) == 1:
        return next(iter(hits.values()))
    if hits:
        # birden çok aday: en uzun eşleşen takma ad kazanır
        for alias, t in _CONTAINED:
            if f" {alias} " in padded:
                return t
    return None


# --- Sayı ve aralık ayrıştırma ---

_QUAL = re.compile(r"^\s*(<=|>=|≤|≥|<|>)?\s*(.*)$")
_NUM = r"\d+(?:[.,]\d+)*"


def _to_float(raw: str) -> float:
    s = raw.replace(" ", "")
    if "," in s and "." in s:
        dec = "," if s.rfind(",") > s.rfind(".") else "."
        thou = "." if dec == "," else ","
        s = s.replace(thou, "").replace(dec, ".")
    elif "," in s:
        s = s.replace(",", "") if re.fullmatch(r"\d{1,3}(,\d{3}){2,}", s) else s.replace(",", ".")
    elif s.count(".") > 1:
        s = s.replace(".", "")
    return float(s)


def parse_value(raw: str | float) -> tuple[float, str]:
    """'5,4' -> (5.4, ''), '<0.5' -> (0.5, '<'). Geçersizse ValueError."""
    if isinstance(raw, bool):
        raw = str(raw)  # True/False sayı sayılmaz; aşağıda ValueError olur
    if not isinstance(raw, str):
        return float(raw), ""
    m = _QUAL.match(str(raw))
    qual = (m.group(1) or "") if m else ""
    qual = {"≤": "<=", "≥": ">="}.get(qual, qual)
    body = (m.group(2) if m else "").strip()
    if not re.fullmatch(_NUM, body.replace(" ", "")):
        raise ValueError(f"sayı okunamadı: {raw!r}")
    return _to_float(body), qual


def parse_range(text: str | None) -> tuple[float | None, float | None] | None:
    """'3.5-5.0' -> (3.5, 5.0); '<5' -> (None, 5.0); '>4' -> (4.0, None). Okunamazsa None."""
    if not text:
        return None
    s = str(text).strip().replace("–", "-").replace("—", "-").replace("~", "-")
    m = re.fullmatch(rf"\s*({_NUM})\s*(?:-|/|ile|to)\s*({_NUM})\s*(?:[^\d\s].*)?", s)
    if m:
        low, high = _to_float(m.group(1)), _to_float(m.group(2))
        return (low, high) if low <= high else None
    m = re.match(rf"\s*(<=|<|≤)\s*({_NUM})", s)
    if m:
        return None, _to_float(m.group(2))
    m = re.match(rf"\s*(>=|>|≥)\s*({_NUM})", s)
    if m:
        return _to_float(m.group(2)), None
    return None


# --- Birim ---

_UNIT_ALIAS = {
    "k/ul": "103/ul", "bin/ul": "103/ul", "103/mm3": "103/ul",
    "m/ul": "106/ul", "milyon/ul": "106/ul", "mil/ul": "106/ul", "106/mm3": "106/ul",
    "iu/l": "u/l", "mcg/dl": "ug/dl", "mcg/l": "ug/l", "mcg/ml": "ug/ml", "mu/l": "miu/l",
}
_SUP = str.maketrans({"µ": "u", "μ": "u", "³": "3", "⁶": "6", "⁹": "9", "×": "x", "%": "pct", "²": "2"})


def norm_unit(unit: str) -> str:
    s = unit.translate(_TR).lower().translate(_SUP)
    s = re.sub(r"[\s^*]+", "", s).replace("¹²", "12").replace("10e", "10").removeprefix("x")
    return _UNIT_ALIAS.get(s, s)


def unit_table(test: LabTest) -> dict[str, tuple[float, float]]:
    """Normalize birim -> (çarpan, ofset); kanonik = değer*çarpan + ofset."""
    table = {norm_unit(test.unit): (1.0, 0.0)}
    for u, conv in test.units.items():
        table[norm_unit(u)] = conv
    return table


def convert(test: LabTest, value: float, unit: str | None) -> float | None:
    """Değeri kanonik birime çevirir; birim yoksa/tanınmıyorsa None."""
    table = unit_table(test)
    if not unit or not unit.strip():
        return value if len(table) == 1 else None
    conv = table.get(norm_unit(unit))
    if conv is None:
        return None
    return value * conv[0] + conv[1]


def _from_canonical(test: LabTest, value: float, unit: str | None) -> float:
    if not unit:
        return value
    conv = unit_table(test).get(norm_unit(unit))
    if conv is None or conv[0] == 0:
        return value
    return (value - conv[1]) / conv[0]


# --- Sınıflandırma ---

STATUS_TR = {"low": "düşük", "high": "yüksek", "normal": "normal", "critical": "kritik", "unknown": "belirsiz"}


@dataclass
class Result:
    test_id: str | None
    name: str
    value: float | None
    unit: str
    status: str = "unknown"
    direction: str | None = None  # kritik/düşük/yüksek yönü: "low" | "high"
    range: dict | None = None
    note: str = ""
    qualifier: str = ""
    canonical_value: float | None = None
    canonical_unit: str | None = None
    notes: list[str] = field(default_factory=list, repr=False)

    def to_dict(self) -> dict:
        return {
            "test_id": self.test_id,
            "name": self.name,
            "value": self.value,
            "qualifier": self.qualifier,
            "unit": self.unit,
            "status": self.status,
            "direction": self.direction,
            "range": self.range,
            "note": self.note,
            "canonical_value": self.canonical_value,
            "canonical_unit": self.canonical_unit,
        }


def _round(x: float | None) -> float | None:
    return None if x is None else round(x, 3)


def pick_reference(test: LabTest, sex: str | None) -> tuple[tuple[float | None, float | None], str]:
    """Referans aralığı ve kısa not. Cinsiyete özgü test için cinsiyet yoksa geniş aralık."""
    if "all" in test.ranges:
        return test.ranges["all"], ""
    if sex in SEXES:
        return test.ranges[sex], ""
    lows = [r[0] for r in test.ranges.values()]
    highs = [r[1] for r in test.ranges.values()]
    low = None if any(x is None for x in lows) else min(lows)  # type: ignore[type-var]
    high = None if any(x is None for x in highs) else max(highs)  # type: ignore[type-var]
    return (low, high), "Cinsiyet belirtilmediği için kadın ve erkek aralıklarını kapsayan geniş aralık kullanıldı."


def _classify(v: float, qual: str, low: float | None, high: float | None) -> tuple[str, str]:
    """(durum, ek not). Nitelikli değerlerde ("<0.5") yalnızca kesin olan söylenir."""
    if not qual:
        if low is not None and v < low:
            return "low", ""
        if high is not None and v > high:
            return "high", ""
        return "normal", ""
    if qual in ("<", "<="):  # gerçek değer v'den küçük
        if low is not None and v <= low:
            return "low", ""
        return "unknown", "Değer bir eşiğin altında bildirilmiş; kesin sınıflandırılamadı."
    if high is not None and v >= high:  # ">" ya da ">="
        return "high", ""
    return "unknown", "Değer bir eşiğin üstünde bildirilmiş; kesin sınıflandırılamadı."


# Raporda referans aralığı yazıyorsa o esas alınır; yoksa genel aralık kullanılır ve hekime yönlendirilir.
BUILTIN_RANGE_NOTE = (
    "Raporunuzda referans aralığı girilmediği için genel yetişkin aralığı kullanıldı; aralıklar "
    "laboratuvara göre değişir. Kesin değerlendirme için raporunuzdaki aralığa bakın ve hekiminize danışın."
)
CRITICAL_NOTE = (
    "Kritik eşik genel bir klinik eşiktir (laboratuvarınızın uyarı değerleri farklı olabilir); "
    "bu değeri bir hekimle değerlendirin."
)


def interpret_value(
    test_name: str,
    value: str | float,
    unit: str | None = None,
    ref_low: float | str | None = None,
    ref_high: float | str | None = None,
    sex: str | None = None,
    age: int | None = None,
) -> Result:
    test = match_test(test_name)
    unit_s = (unit or "").strip()
    if test is None:
        return Result(None, test_name.strip(), None, unit_s,
                      note="Bu test listemizde yok; yorumlanamadı. Raporunuzdaki referans aralığına bakın.")
    try:
        v, qual = parse_value(value)
    except ValueError:
        return Result(test.id, test.name, None, unit_s, note="Değer sayı olarak okunamadı.")
    res = Result(test.id, test.name, v, unit_s or test.unit, qualifier=qual)
    if v < 0:
        res.note = "Negatif değer geçersiz."
        return res
    canon = convert(test, v, unit_s or None)
    if canon is None:
        res.note = (
            f"Birim belirtilmedi; sınıflandırma için birim gerekli (beklenen: {test.unit})."
            if not unit_s
            else f"Birim '{unit_s}' tanınmadı (beklenen: {', '.join([test.unit, *test.units])}); sınıflandırılamadı."
        )
        return res
    res.canonical_value, res.canonical_unit = _round(canon), test.unit
    shown_unit = unit_s or test.unit

    user_low = user_high = None
    try:
        if ref_low not in (None, ""):
            user_low = parse_value(ref_low)[0]
        if ref_high not in (None, ""):
            user_high = parse_value(ref_high)[0]
    except ValueError:
        user_low = user_high = None

    notes: list[str] = []
    if user_low is not None or user_high is not None:
        status, extra = _classify(v, qual, user_low, user_high)  # rapor aralığı, girilen birimde
        res.range = {"low": user_low, "high": user_high, "unit": shown_unit, "source": "Raporunuzdaki aralık",
                     "basis": "report"}
    else:
        (rl, rh), sex_note = pick_reference(test, sex)
        status, extra = _classify(canon, qual, rl, rh)
        res.range = {
            "low": _round(None if rl is None else _from_canonical(test, rl, unit_s or None)),
            "high": _round(None if rh is None else _from_canonical(test, rh, unit_s or None)),
            "unit": shown_unit,
            "source": test.ref_source,
            "basis": "builtin",
        }
        notes.append(BUILTIN_RANGE_NOTE)
        if sex_note:
            notes.append(sex_note)
        if age is not None and age < 18:
            notes.append("Bu aralıklar yetişkinler içindir; çocuk ve ergenlerde farklıdır.")
    if extra:
        notes.append(extra)

    # Kritik eşikler her zaman uygulanır (rapor aralığı verilmiş olsa bile)
    if test.crit_low is not None and canon <= test.crit_low and qual in ("", "<", "<="):
        status, res.direction = "critical", "low"
    elif test.crit_high is not None and canon >= test.crit_high and qual in ("", ">", ">="):
        status, res.direction = "critical", "high"
    if status in ("low", "high"):
        res.direction = status
    res.status = status
    if status == "critical":
        notes.insert(0, "Kritik düzeyde " + ("düşük" if res.direction == "low" else "yüksek")
                     + " değer: en kısa sürede bir sağlık kuruluşuyla görüşün.")
        notes.append(CRITICAL_NOTE)
    elif status in ("low", "high"):
        notes.insert(0, f"Referans aralığının {'altında' if status == 'low' else 'üzerinde'}.")
    res.note = " ".join(notes)
    return res


def catalog() -> list[dict]:
    return [t.to_catalog() for t in TESTS]
