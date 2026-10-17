"""Görsel okuma: tahlil fotoğrafından değer çıkarma (OCR + LLM) ve ilaç kutusu tanıma.

Görseller yalnızca istek süresince bellekte tutulur; diske yazılmaz, loglanmaz.
Evren API: OCR için `POST /v1/ocr` {"model", "image": data-URI} -> {"text"};
görsel sohbet için `POST /v1/chat/completions` (OpenAI tarzı image_url içeriği).
"""

import base64
import html
import json
import os
import re
import urllib.error
import urllib.request
from collections.abc import Callable
from typing import Any

from medrag.labs.interpret import match_test, norm_unit, parse_range, parse_value, unit_table
from medrag.labs.reference import TESTS

ALLOWED_TYPES = ("image/jpeg", "image/png", "image/webp")


class VisionError(RuntimeError):
    """Kullanıcıya gösterilebilecek görsel okuma hatası."""


class ImageError(ValueError):
    def __init__(self, message: str, status: int = 422):
        super().__init__(message)
        self.status = status


def sniff_image(data: bytes) -> str | None:
    """Sihirli baytlardan MIME türünü bulur (istemcinin söylediğine güvenilmez)."""
    if data[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return None


def validate_image(data: bytes, max_bytes: int) -> str:
    if not data:
        raise ImageError("Dosya boş.")
    if len(data) > max_bytes:
        raise ImageError(f"Görsel çok büyük (en fazla {max_bytes // (1024 * 1024)} MB).", 413)
    mime = sniff_image(data)
    if mime is None:
        raise ImageError("Yalnızca JPEG, PNG veya WebP görsel yükleyebilirsiniz.", 415)
    return mime


def data_uri(data: bytes, mime: str) -> str:
    return f"data:{mime};base64,{base64.b64encode(data).decode()}"


# --- API istemcisi ---


class VisionClient:
    def __init__(
        self,
        base_url: str,
        api_key: str | None = None,
        post: Callable[[str, dict], dict] | None = None,
        timeout: int = 120,
    ):
        self.base = base_url.rstrip("/")
        self.api_key = api_key or os.environ.get("EVREN_API_KEY", "")
        self.timeout = timeout
        self._post = post or self._http_post

    def _http_post(self, path: str, payload: dict) -> dict:
        if not self.api_key:
            raise VisionError("EVREN_API_KEY tanımlı değil")
        req = urllib.request.Request(
            self.base + path,
            data=json.dumps(payload).encode(),
            headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                return json.loads(resp.read())
        except urllib.error.HTTPError as e:
            raise VisionError(f"görsel isteği başarısız: HTTP {e.code}") from e
        except (urllib.error.URLError, TimeoutError, ValueError) as e:
            raise VisionError(f"görsel isteği başarısız: {type(e).__name__}") from e

    def ocr(self, image: bytes, mime: str, model: str) -> str:
        data = self._post("/ocr", {"model": model, "image": data_uri(image, mime)})
        text = data.get("text") if isinstance(data, dict) else None
        if not isinstance(text, str) or not text.strip():
            raise VisionError(f"{model} boş OCR cevabı verdi")
        return text

    def chat(self, image: bytes, mime: str, model: str, prompt: str, max_tokens: int = 2000) -> str:
        payload = {
            "model": model,
            "temperature": 0,
            "max_tokens": max_tokens,
            "messages": [{"role": "user", "content": [
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {"url": data_uri(image, mime)}},
            ]}],
        }
        data = self._post("/chat/completions", payload)
        try:
            content = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as e:
            raise VisionError(f"{model} beklenmeyen cevap verdi") from e
        if not isinstance(content, str) or not content.strip():
            raise VisionError(f"{model} boş cevap verdi")
        return content.strip()


# --- OCR çıktısından değer çıkarma ---

TRANSCRIBE_PROMPT = (
    "Bu görseldeki tüm metni, özellikle tablo satırlarını (test adı, sonuç, birim, referans aralığı) "
    "olduğu gibi, satır satır yaz. Yorum ekleme, bilmediğini uydurma."
)

EXTRACT_PROMPT = """Aşağıda bir tahlil raporunun OCR metni var. Test sonuç satırlarını JSON listesi olarak \
çıkar. Her öğe: {{"test": "<rapordaki test adı>", "value": "<sonuç, rapordaki gibi>", "unit": "<birim ya da null>", \
"ref_low": "<referans alt sınır ya da null>", "ref_high": "<referans üst sınır ya da null>"}}.
Kurallar: Yalnızca metinde yazan sayıları kullan, hiçbir şeyi uydurma ya da hesaplama; okunamayanı null yaz. \
Hasta bilgisi, tarih, doktor adı gibi satırları ve sayısal sonucu olmayan satırları atla. Referans "12-16" ise \
ref_low 12, ref_high 16; "<5" ise ref_high 5. Sadece JSON listesi yaz, başka metin yazma.

OCR METNİ:
{text}"""

_FLAGS = {"h", "l", "y", "d", "n", "hh", "ll", "*", "+", "-", "high", "low", "yuksek", "dusuk", "normal"}
_ALL_UNITS = {norm_unit(u) for t in TESTS for u in (t.unit, *t.units)}
_ROW = re.compile(
    r"^(?P<name>[^\W\d_][^\d|<>]*?)\s+(?P<val>[<>]=?\s*\d+(?:[.,]\d+)?)\s*(?P<rest>.*)$"
)
_ROW2 = re.compile(r"^(?P<name>[^\W\d_][^\d|<>]*?)\s+(?P<val>\d+(?:[.,]\d+)?)\s*(?P<rest>.*)$")


def ocr_to_lines(text: str) -> list[list[str]]:
    """OCR metnini (markdown/HTML tablo ya da düz metin) hücre listelerine böler."""
    t = re.sub(r"</t[dh]\s*>", " | ", text, flags=re.IGNORECASE)
    t = re.sub(r"</tr\s*>|<br\s*/?>", "\n", t, flags=re.IGNORECASE)
    t = html.unescape(re.sub(r"<[^>]+>", "", t)).replace("**", "")
    rows = []
    for line in t.splitlines():
        line = line.strip()
        if not line or re.fullmatch(r"[\s|:\-]+", line):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")] if "|" in line else [line]
        rows.append([c for c in cells if c])
    return rows


def _is_unit(cell: str) -> bool:
    n = norm_unit(cell)
    if n in _ALL_UNITS:
        return True
    return bool(re.fullmatch(r"[a-zA-Zµμ%/0-9^³.]{1,14}", cell)) and n not in _FLAGS and "/" in cell


def parse_rows_deterministic(text: str) -> list[dict]:
    """LLM'siz yedek ayrıştırıcı: tablo hücrelerinden ya da düz satırlardan değer çıkarır."""
    out = []
    for cells in ocr_to_lines(text):
        row = _row_from_cells(cells) if len(cells) > 1 else _row_from_line(cells[0])
        if row:
            out.append(row)
    return out


def _row_from_cells(cells: list[str]) -> dict | None:
    name = next((c for c in cells if re.search(r"[^\W\d_]{2}", c)), None)
    if name is None:
        return None
    idx = cells.index(name)
    for i in range(idx + 1, len(cells)):
        head, _, tail = cells[i].partition(" ")  # "4,10 x10^6/µL" gibi değer+birim aynı hücrede
        value = clean_value(cells[i])
        if tail and _is_unit(tail.strip()):
            value = clean_value(head)
        try:
            parse_value(value)
        except ValueError:
            continue
        unit = next((c for c in [tail.strip(), *cells[i + 1:]] if c and _is_unit(c)), None)
        ref = next((r for c in cells[i + 1:] if (r := parse_range(c)) is not None), None)
        return _row(name, value, unit, ref)
    return None


def _row_from_line(line: str) -> dict | None:
    m = _ROW.match(line) or _ROW2.match(line)
    if not m:
        return None
    rest = m.group("rest").strip()
    unit = None
    first = rest.split()[0] if rest.split() else ""
    if first and _is_unit(first):
        unit, rest = first, rest[len(first):].strip()
    ref = parse_range(rest.split("  ")[0]) if rest else None
    if ref is None:
        ref = parse_range(re.sub(r"^[A-Za-z*]\s+", "", rest))
    return _row(m.group("name").strip(" :-"), m.group("val"), unit, ref)


_VALUE_FLAG = re.compile(
    r"^\s*(?P<q>[<>]=?|≤|≥)?\s*(?P<n>\d+(?:[.,]\d+)?)\s*(?:HH|LL|H|L|N|A|Y|D|\*+|\++|-|↑|↓|high|low|yüksek|düşük)?\s*$"
)


def clean_value(raw: str) -> str:
    """'10,9 L' / '5,9 H' gibi bayraklı sonucu sayıya indirger; anlaşılmazsa olduğu gibi bırakır."""
    s = re.sub(r"\\[()\[\]]|\$", "", html.unescape(str(raw))).strip()
    m = _VALUE_FLAG.match(s)
    return (m.group("q") or "") + m.group("n") if m else s


def clean_unit(raw: str | None) -> str | None:
    """OCR'ın bıraktığı HTML/LaTeX artıklarını birimden temizler (sup etiketi -> ^, LaTeX parantezi atılır)."""
    if raw is None:
        return None
    s = html.unescape(str(raw))
    s = re.sub(r"</?sup>", lambda m: "" if m.group(0)[1] == "/" else "^", s, flags=re.IGNORECASE)
    s = re.sub(r"<[^>]+>|\\[()\[\]]|[${}]", "", s)
    s = s.replace("\\mu", "µ").replace("\\times", "x").replace("×", "x").strip()
    return s or None


def _row(name: str, value: str, unit: str | None, ref: tuple | None) -> dict:
    return {
        "test": name.strip(),
        "value": clean_value(value),
        "unit": clean_unit(unit),
        "ref_low": None if not ref else ref[0],
        "ref_high": None if not ref else ref[1],
    }


def _in_text(value: str, text: str) -> bool:
    """LLM'in döndürdüğü sayı gerçekten OCR metninde geçiyor mu (uydurmayı eler)."""
    v = re.sub(r"^[<>]=?\s*", "", str(value)).strip()
    if not v:
        return False
    flat = text.replace(" ", "")
    return any(x in flat for x in (v, v.replace(",", "."), v.replace(".", ",")))


def parse_llm_rows(raw: str) -> list[dict]:
    """LLM çıktısındaki JSON listesini çözer; bozuksa boş liste."""
    a, b = raw.find("["), raw.rfind("]")
    if a < 0 or b <= a:
        return []
    try:
        items = json.loads(raw[a : b + 1])
    except ValueError:
        return []
    out = []
    for it in items if isinstance(items, list) else []:
        if not isinstance(it, dict) or not it.get("test") or it.get("value") in (None, ""):
            continue
        out.append({
            "test": str(it["test"]).strip(),
            "value": clean_value(str(it["value"])),
            "unit": clean_unit(str(it["unit"])) if it.get("unit") not in (None, "null") else None,
            "ref_low": it.get("ref_low"),
            "ref_high": it.get("ref_high"),
        })
    return out


def _num(x: Any) -> float | None:
    if x in (None, "", "null"):
        return None
    try:
        return parse_value(x)[0]
    except ValueError:
        return None


def finalize_rows(rows: list[dict]) -> list[dict]:
    """Satırları bilinen testlerle eşler; birim tanınıyorsa kanonik yazımı önerir."""
    out = []
    for r in rows:
        try:
            parse_value(r["value"])
        except ValueError:
            continue
        test = match_test(r["test"])
        unit = r.get("unit")
        out.append({
            "test": r["test"],
            "test_id": test.id if test else None,
            "matched_name": test.name if test else None,
            "value": r["value"],
            "unit": unit or (test.unit if test and len(unit_table(test)) == 1 else None),
            "ref_low": _num(r.get("ref_low")),
            "ref_high": _num(r.get("ref_high")),
            "known": test is not None,
        })
    return out


class VisionService:
    def __init__(
        self,
        client: VisionClient,
        extractor: Any | None,
        ocr_models: list[str],
        chat_model: str,
        max_bytes: int = 8 * 1024 * 1024,
    ):
        self.client = client
        self.extractor = extractor  # .complete(messages, temperature, max_tokens) -> str
        self.ocr_models = ocr_models
        self.chat_model = chat_model
        self.max_bytes = max_bytes

    def read_text(self, image: bytes, mime: str) -> tuple[str, str]:
        """(metin, kullanılan model). OCR modelleri sırayla, olmazsa görsel sohbet modeli."""
        errors = []
        for model in self.ocr_models:
            try:
                return self.client.ocr(image, mime, model), model
            except VisionError as e:
                errors.append(str(e))
        try:
            return self.client.chat(image, mime, self.chat_model, TRANSCRIBE_PROMPT), self.chat_model
        except VisionError as e:
            errors.append(str(e))
        raise VisionError("Görseldeki metin okunamadı; daha net ve düz bir fotoğraf deneyin.")

    def lab_report(self, image: bytes) -> dict:
        mime = validate_image(image, self.max_bytes)
        text, model = self.read_text(image, mime)
        rows: list[dict] = []
        method = "llm"
        if self.extractor is not None:
            try:
                raw = self.extractor.complete(
                    [{"role": "user", "content": EXTRACT_PROMPT.format(text=text[:12000])}],
                    temperature=0.0, max_tokens=3000,
                )
                rows = [r for r in parse_llm_rows(raw) if _in_text(r["value"], text)]
            except Exception:  # noqa: BLE001 - LLM yoksa kural tabanlı ayrıştırıcıya düş
                rows = []
        if not rows:
            method = "rules"
            rows = parse_rows_deterministic(text)
        final = finalize_rows(rows)
        warnings = []
        if not final:
            warnings.append("Görselde tahlil değeri bulunamadı. Daha net bir fotoğraf deneyin ya da değerleri elle girin.")
        elif any(not r["known"] for r in final):
            warnings.append("Bazı satırlar tanınan testlerle eşleşmedi; bunlar yorumlanmaz.")
        warnings.append("Okunan değerleri yorumdan önce kontrol edin; OCR hata yapabilir.")
        return {"rows": final, "ocr_model": model, "method": method, "warnings": warnings}

    def medicine(self, image: bytes) -> dict:
        mime = validate_image(image, self.max_bytes)
        raw = self.client.chat(image, mime, self.chat_model, MEDICINE_PROMPT, max_tokens=1200)
        return medicine_from_text(raw)


MEDICINE_PROMPT = """Bu görsel bir ilaç kutusu ya da blisteri olabilir. Üzerinde okunan bilgiyi JSON olarak ver: \
{"readable": true/false, "brand_name": "<ticari ad ya da null>", "active_ingredients": ["<etken madde>"], \
"strength": "<kutudaki güç, örn. 500 mg, ya da null>", "form": "<tablet/şurup/kapsül/... ya da null>", \
"confidence": "high|medium|low"}.
Yalnızca görselde yazanı kullan, tahmin etme; okunamıyorsa readable false yaz. Kullanım şekli, doz ya da öneri yazma. \
Sadece JSON yaz."""


def medicine_from_text(raw: str) -> dict:
    a, b = raw.find("{"), raw.rfind("}")
    data: dict = {}
    if a >= 0 and b > a:
        try:
            parsed = json.loads(raw[a : b + 1])
            data = parsed if isinstance(parsed, dict) else {}
        except ValueError:
            data = {}

    def s(key: str) -> str | None:
        v = data.get(key)
        return v.strip() if isinstance(v, str) and v.strip() and v.strip().lower() != "null" else None

    ing = data.get("active_ingredients")
    ingredients = [x.strip() for x in ing if isinstance(x, str) and x.strip()] if isinstance(ing, list) else []
    brand = s("brand_name")
    readable = bool(data.get("readable", True)) and bool(brand or ingredients)
    conf = s("confidence")
    out = {
        "readable": readable,
        "brand_name": brand,
        "active_ingredients": ingredients,
        "strength": s("strength"),
        "form": s("form"),
        "confidence": conf if conf in ("high", "medium", "low") else "low",
        "suggested_question": None,
    }
    if readable:
        label = brand or ", ".join(ingredients)
        extra = f" ({', '.join(ingredients)})" if brand and ingredients else ""
        out["suggested_question"] = f"{label}{extra} ne için kullanılır ve nelere dikkat etmeliyim?"
    return out
