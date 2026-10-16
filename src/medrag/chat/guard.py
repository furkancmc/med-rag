import re

# İlaç dozu kalıpları: sayı + ilaç birimi. Tahlil değerleri (mg/dL, mmol/L) dozla karışmasın diye hariç.
DOSE_RE = re.compile(
    r"\b\d+(?:[.,]\d+)?\s*(?:mg|mcg|µg|tablet|hap|damla|kapsül|ünite|iu)\b(?!\s*/\s*(?:d?l|dl)\b)",
    re.IGNORECASE,
)
REDACTED = "[doz bilgisi için hekime veya eczacıya danışın]"
SENTENCE_END = re.compile(r"[.!?](?=\s)")


def redact_doses(text: str) -> str:
    return DOSE_RE.sub(REDACTED, text)


class DoseGuard:
    """Akan cevabı cümle sınırlarında denetler. Sayı ile birim farklı parçalara bölünse bile yakalar.

    Sistem promptu doz vermemeyi söylese de kaynaklardaki genel üst sınırlar cevaba sızabilir;
    bu yüzden çıktı da denetlenir.
    """

    def __init__(self) -> None:
        self.buffer = ""

    def feed(self, piece: str) -> str:
        self.buffer += piece
        cut = self.buffer.rfind("\n")
        for m in SENTENCE_END.finditer(self.buffer):
            cut = max(cut, m.end() - 1)
        if cut < 0:
            return ""
        out, self.buffer = self.buffer[: cut + 1], self.buffer[cut + 1 :]
        return redact_doses(out)

    def flush(self) -> str:
        out, self.buffer = self.buffer, ""
        return redact_doses(out)
