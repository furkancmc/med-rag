"""Cümle bölme yardımcıları (doz filtresi, acil mod filtresi ve doğrulama ortak kullanır)."""

import re

# Nokta/ünlem/soru işaretinden sonra (varsa [1] [2] atıfları cümleye dahil) boşluk gelince cümle biter.
BOUNDARY = re.compile(r"(?<=[.!?])((?:[ \t]*\[\d+\])*)([ \t]+)")
# Bunlardan sonraki nokta cümle sonu değildir ("vb. ve", "örn. grip", "Dr. Ayşe").
ABBREVIATIONS = ("vb", "vs", "örn", "dr", "prof", "doç", "sn", "dk", "bkz", "krş")
BULLET = re.compile(r"^\s*(?:[-*•–]|\d{1,2}[.)])\s+")
HEADING = re.compile(r"^#+\s*")
CITATION = re.compile(r"\[(\d+)\]")


def _is_abbreviation(before: str) -> bool:
    word = re.search(r"([^\W\d_]+)\.$", before)
    return bool(word) and word.group(1).lower() in ABBREVIATIONS


def split_keep(text: str) -> list[tuple[str, str]]:
    """Metni (cümle, kendisinden sonraki ayraç) çiftlerine böler.

    Ayraç boşluk ya da satır sonudur; `"".join(s + sep ...)` özgün metni birebir geri verir.
    Satır sonları her zaman cümle sınırıdır (madde işaretli satırlar ayrı cümle sayılır).
    """
    result: list[tuple[str, str]] = []
    lines = text.split("\n")
    for i, line in enumerate(lines):
        end_sep = "\n" if i < len(lines) - 1 else ""
        start = 0
        for m in BOUNDARY.finditer(line):
            nxt = line[m.end() : m.end() + 1]
            if _is_abbreviation(line[start : m.start()]) or (nxt and nxt.islower()):
                continue
            result.append((line[start : m.end(1)], m.group(2)))
            start = m.end()
        result.append((line[start:], end_sep))
    return result


def clean_sentence(sentence: str) -> str:
    """Madde işaretini ve başlık imini atar; sonuç özgün metnin bir alt dizisi olarak kalır."""
    return HEADING.sub("", BULLET.sub("", sentence.strip())).strip()


def claim_sentences(text: str, min_words: int = 4) -> list[str]:
    """Metindeki temiz cümleleri verir; başlık, kısa parça ve yalnız atıf içerenleri atar."""
    out = []
    for sentence, _ in split_keep(text):
        s = clean_sentence(sentence)
        words = [w for w in CITATION.sub("", s).split() if any(c.isalpha() for c in w)]
        if len(words) < min_words or s.endswith(":"):
            continue
        out.append(s)
    return out


def cited_numbers(sentence: str) -> list[int]:
    return [int(n) for n in CITATION.findall(sentence)]
