import re

# İlaç dozu kalıpları: sayı + ilaç birimi. Tahlil değerleri (mg/dL, mmol/L) dozla karışmasın diye hariç.
DOSE_RE = re.compile(
    r"\b\d+(?:[.,]\d+)?\s*(?:mg|mcg|µg|tablet|hap|damla|kapsül|ünite|iu)\b(?!\s*/\s*(?:d?l|dl)\b)",
    re.IGNORECASE,
)
NOTICE = (
    "İlaç miktarı ve kullanım sıklığı kişiden kişiye değiştiği için bu bilgiyi vermiyorum; "
    "doz konusunda hekiminize veya eczacınıza danışın."
)
SENTENCE_END = re.compile(r"[.!?](?=\s)")
SPLIT = re.compile(r"(?<=[.!?])(\s+)|(\n)")


def has_dose(text: str) -> bool:
    return DOSE_RE.search(text) is not None


def _drop_dose_sentences(text: str, notice_given: bool) -> tuple[str, bool]:
    """Doz içeren cümleleri atar; ilkinin yerine tek bir açıklama cümlesi koyar."""
    out: list[str] = []
    parts = [p for p in SPLIT.split(text) if p is not None]
    i = 0
    while i < len(parts):
        sentence = parts[i]
        sep = parts[i + 1] if i + 1 < len(parts) and parts[i + 1].strip() == "" else ""
        step = 2 if sep or (i + 1 < len(parts) and parts[i + 1] == "") else 1
        if sentence.strip() and has_dose(sentence):
            if not notice_given:
                out.append(NOTICE + sep)
                notice_given = True
        else:
            out.append(sentence + sep)
        i += step
    return "".join(out), notice_given


def redact_doses(text: str) -> str:
    """Tek seferlik (akışsız) kullanım: doz içeren cümleleri atar."""
    return _drop_dose_sentences(text, False)[0]


class DoseGuard:
    """Akan cevabı cümle sınırlarında denetler. Sayı ile birim farklı parçalara bölünse bile yakalar.

    Sistem promptu doz vermemeyi söylese de kaynaklardaki genel üst sınırlar cevaba sızabilir.
    Doz içeren cümle atılır, yerine cevap boyunca yalnızca bir kez açıklama cümlesi konur.
    """

    def __init__(self) -> None:
        self.buffer = ""
        self.notice_given = False

    def _clean(self, text: str) -> str:
        out, self.notice_given = _drop_dose_sentences(text, self.notice_given)
        return out

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
