import re

from medrag.index.tokenize import normalize

from .sentences import split_keep

# --- İlaç dozu kalıpları ---------------------------------------------------------------------
# Eşleştirme `normalize()` edilmiş metinde yapılır (küçük harf, aksansız: "İki" -> "iki", "çay" -> "cay").

# Sayı + ilaç birimi ("500 mg", "3 tablet", "2,5 ml"). Tahlil değerleri dozla karışmasın diye
# "mg/dL", "mg/L", "mL/dk" gibi oranlar hariç.
_SUFFIX = r"(?:ler|lar|leri|lari|ten|tan|den|dan|nin|nun|ini|unu|lik|luk|le|la|ni|nu|yi|yu|ya|ye|in|un|si|su|i|u|a|e)?"
_UNIT_WORD = (
    r"(?:tablet|hap|kapsul|draje|damla|puf|olce[kg]|sase|ampul|fitil|supozituvar|flakon"
    r"|(?:cay|yemek|tatli)\s+kasig|kasi[kg])"
)
_UNIT_SHORT = r"(?:mg|mcg|[µμu]g|iu|unite|birim|cc|ml(?!\s*/))\b(?!\s*/\s*(?:d?l|ml)\b)"
_DIGIT_DOSE = re.compile(
    rf"\b\d+(?:[.,/⁄]\d+)?\s*(?:{_UNIT_SHORT}|(?:adet\s+)?{_UNIT_WORD}{_SUFFIX}\b)"
)

# Yazıyla sayı + ilaç birimi ("iki tablet", "yarım tablet", "bir çay kaşığı", "bir buçuk ölçek").
_NUM = r"(?:bir|iki|uc|dort|bes|alti|yedi|sekiz|dokuz|on|yirmi|otuz|kirk|elli|yuz|yarim|ceyrek)"
_NUMBER = rf"{_NUM}(?:\s+bucuk)?(?:(?:\s*-\s*|\s+(?:ila|veya|ya\s+da)\s+|\s+){_NUM}(?:\s+bucuk)?){{0,2}}"
_WORD_DOSE = re.compile(rf"\b{_NUMBER}\s+(?:adet\s+)?{_UNIT_WORD}{_SUFFIX}\b")
# "Bir tablet kullanmadan önce doktora danışın" gibi genel uyarılarda "bir" belirsiz tanımlık sayılır.
# Yalnızca "kullanmadan/almadan ... önce" kalıbıyla birlikte geçiyorsa doz sayılmaz.
_BEFORE_TAKING = re.compile(
    rf"bir\s+(?:adet\s+)?{_UNIT_WORD}{_SUFFIX}\s+(?:\w+\s+){{0,2}}"
    r"(?:kullanmadan|almadan|icmeden|baslamadan|yutmadan|uygulamadan|denemeden)\s+once\b"
)

# Eski ad: yalnızca rakamlı kalıplar (ham metin üzerinde ASCII dışı büyük harfler için `find_dose` kullan).
DOSE_RE = _DIGIT_DOSE

NOTICE = (
    "İlaç miktarı ve kullanım sıklığı kişiden kişiye değiştiği için bu bilgiyi vermiyorum; "
    "doz konusunda hekiminize veya eczacınıza danışın."
)
SENTENCE_END = re.compile(r"[.!?](?=\s)")


def find_dose(text: str) -> str | None:
    """Metinde doz ifadesi varsa ilk eşleşmeyi (özgün metinden) döner; yoksa None."""
    norm = normalize(text)
    same_length = len(norm) == len(text)
    for m in _DIGIT_DOSE.finditer(norm):
        return text[m.start() : m.end()] if same_length else m.group(0)
    for m in _WORD_DOSE.finditer(norm):
        if m.group(0).startswith("bir ") and _BEFORE_TAKING.match(norm, m.start()):
            continue
        return text[m.start() : m.end()] if same_length else m.group(0)
    return None


def has_dose(text: str) -> bool:
    return find_dose(text) is not None


def _drop_dose_sentences(text: str, notice_given: bool) -> tuple[str, bool]:
    """Doz içeren cümleleri atar; ilkinin yerine tek bir açıklama cümlesi koyar."""
    out: list[str] = []
    for sentence, sep in split_keep(text):
        if sentence.strip() and has_dose(sentence):
            if not notice_given:
                out.append(NOTICE + sep)
                notice_given = True
        else:
            out.append(sentence + sep)
    return "".join(out), notice_given


def redact_doses(text: str) -> str:
    """Tek seferlik (akışsız) kullanım: doz içeren cümleleri atar."""
    return _drop_dose_sentences(text, False)[0]


class SentenceGuard:
    """Akan cevabı cümle sınırlarında denetleyen süzgeçlerin ortak tabanı.

    `feed()` yalnızca tamamlanmış cümleleri, `flush()` kalan kuyruğu verir. Alt sınıflar `_clean`
    ile cümle grubunu süzer. Süzgeçler birbirine bağlanabilir (çıktı, bir sonrakinin girdisidir).
    """

    def __init__(self) -> None:
        self.buffer = ""

    def _clean(self, text: str) -> str:
        raise NotImplementedError

    def feed(self, piece: str) -> str:
        self.buffer += piece
        cut = self.buffer.rfind("\n")
        for m in SENTENCE_END.finditer(self.buffer):
            cut = max(cut, m.end() - 1)
        if cut < 0:
            return ""
        out, self.buffer = self.buffer[: cut + 1], self.buffer[cut + 1 :]
        return self._clean(out)

    def flush(self) -> str:
        out, self.buffer = self.buffer, ""
        return self._clean(out)


class DoseGuard(SentenceGuard):
    """Akan cevabı cümle sınırlarında denetler. Sayı ile birim farklı parçalara bölünse bile yakalar.

    Sistem promptu doz vermemeyi söylese de kaynaklardaki genel üst sınırlar cevaba sızabilir.
    Doz içeren cümle atılır, yerine cevap boyunca yalnızca bir kez açıklama cümlesi konur.
    """

    def __init__(self) -> None:
        super().__init__()
        self.notice_given = False

    def _clean(self, text: str) -> str:
        out, self.notice_given = _drop_dose_sentences(text, self.notice_given)
        return out


# --- Acil modda hastalık adı süzgeci ----------------------------------------------------------
# Acil durumda model teşhis adı vermemeli ("kalp krizi olabilir"). Prompt kuralı yetmediği için
# bu cümleler koddan çıkarılır; "112'yi arayın, hareket etmeyin" gibi eylem cümleleri kalır.
DIAGNOSIS_PATTERNS = [
    r"kalp\s+kriz\w*", r"kalp\s+(?:damar\s+)?tikanik\w*", r"miyokard\w*", r"\b(?:en|in)farktus\w*",
    r"\banjina\w*", r"koroner\w*", r"kalp\s+yetmezlig\w*", r"kalp\s+dur\w*", r"\baritmi\w*",
    r"\binme(?:nin|ye|yi|de|den|ler\w*)?\b", r"\bfelc\w*", r"\bstrok\w*", r"serebrovaskuler\w*",
    r"beyin\s+(?:kanama|damar|enfarkt)\w*", r"iskemik\s+atak\w*", r"\bsvo\b", r"\bsvh\b",
    r"anafilaks\w*", r"anafilakt\w*",
    r"pulmoner\s+emboli\w*", r"akciger\s+emboli\w*", r"\bemboli\w*", r"derin\s+ven\s+tromboz\w*",
    r"menenjit\w*", r"ensefalit\w*", r"\bsepsis\w*", r"\bsepsi\b", r"kan\s+zehirlen\w*",
    r"apandisit\w*", r"peritonit\w*", r"pnomotoraks\w*", r"aort\s+(?:diseksiyon|anevrizma|yirtil)\w*",
    r"ektopik\s+gebelik\w*", r"\beklampsi\w*", r"\bpreeklampsi\w*", r"ketoasidoz\w*",
    r"hipoglisemi\w*", r"astim\s+atag\w*", r"\bzaturre\w*", r"\bpnomoni\w*", r"epilepsi\w*",
    r"mide\s+kanamasi", r"organ\s+yetmezlig\w*", r"\bsok\s+(?:durumu|tablosu)\w*",
]
DIAGNOSIS_RE = re.compile("|".join(f"(?:{p})" for p in DIAGNOSIS_PATTERNS))

SAFE_EMERGENCY_SENTENCE = (
    "Lütfen beklemeden 112'yi arayın; yardım gelene kadar sakin kalmaya çalışın, mümkünse "
    "hareket etmeyin ve yanınızda birinin bulunmasını sağlayın."
)


def mentions_diagnosis(text: str) -> str | None:
    """Metinde belirli bir hastalık/teşhis adı geçiyorsa eşleşmeyi, yoksa None döner."""
    m = DIAGNOSIS_RE.search(normalize(text))
    return m.group(0) if m else None


class DiagnosisGuard(SentenceGuard):
    """Acil modda teşhis adı geçen cümleleri atar, eylem cümlelerini korur.

    Cevap tamamen boşalırsa (ya da yalnızca doz açıklaması kalırsa) kısa, güvenli bir eylem cümlesi
    eklenir; böylece acil durumda kullanıcı asla boş cevapla kalmaz.
    """

    def __init__(self) -> None:
        super().__init__()
        self.kept = False  # anlamlı (doz açıklaması dışında) bir cümle iletildi mi
        self.emitted = False

    def _clean(self, text: str) -> str:
        out: list[str] = []
        for sentence, sep in split_keep(text):
            if sentence.strip() and mentions_diagnosis(sentence):
                continue
            if sentence.strip() and sentence.strip() != NOTICE:
                self.kept = True
            out.append(sentence + sep)
        result = "".join(out)
        self.emitted = self.emitted or bool(result.strip())
        return result

    def flush(self) -> str:
        had_output = self.emitted
        out = super().flush()
        if self.kept:
            return out
        self.kept = self.emitted = True
        if out.strip():
            return out + "\n" + SAFE_EMERGENCY_SENTENCE
        return (" " if had_output else "") + SAFE_EMERGENCY_SENTENCE


class GuardChain:
    """Süzgeçleri art arda bağlar: her birinin çıktısı bir sonrakinin girdisidir."""

    def __init__(self, *guards: SentenceGuard) -> None:
        self.guards = guards

    def feed(self, piece: str) -> str:
        for guard in self.guards:
            piece = guard.feed(piece) if piece else ""
        return piece

    def flush(self) -> str:
        carry = ""
        for guard in self.guards:
            carry = (guard.feed(carry) if carry else "") + guard.flush()
        return carry
