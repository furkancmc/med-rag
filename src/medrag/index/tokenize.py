import re
import unicodedata

TOKEN = re.compile(r"[a-z0-9]+")
PREFIX = 5  # Türkçe için basit "ilk 5 harf" kökleme; ekli kelimeleri birbirine yaklaştırır


def normalize(text: str) -> str:
    """Küçük harfe çevirir ve aksanları atar (ş->s, ğ->g, ı->i, İ->i).

    Kullanıcı Türkçe karakter yazmasa da eşleşme bozulmaz.
    """
    text = text.replace("ı", "i").replace("İ", "i")
    text = unicodedata.normalize("NFKD", text.casefold())
    return "".join(c for c in text if not unicodedata.combining(c))


def tokenize(text: str) -> list[str]:
    return [t[:PREFIX] for t in TOKEN.findall(normalize(text))]
