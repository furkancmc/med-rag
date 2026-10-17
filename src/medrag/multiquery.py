"""Çoklu sorgu genişletme: bir LLM soruyu İngilizceye çevirir ve 1-2 Türkçe yeniden yazım üretir.

Kaynakların yarısı İngilizce olduğu için çeviri, farklı sözcükle yazılmış sorular için yeniden yazımlar
aramanın kapsamını artırır. Sonuçlar `retrieve.rrf_fuse` ile birleşir. LLM hatası ya da bozuk cevap
durumunda genişletme boş döner; arama sadece orijinal sorguyla sürer (çökme yok).
"""

import json
import logging
import re
import threading
import unicodedata
from collections.abc import Callable

from .lru import LRUCache

logger = logging.getLogger(__name__)

EXPAND_PROMPT = """Aşağıdaki Türkçe sağlık sorusunu bir tıbbi bilgi tabanında (Türkçe ve İngilizce \
makaleler) aramak için yeniden yaz.

Tam olarak 3 satır yaz:
1. satır: sorunun İngilizce çevirisi (tıbbi terimleri İngilizce kullan)
2. satır: aynı sorunun farklı sözcüklerle Türkçe yeniden yazımı
3. satır: aynı sorunun, tıbbi terimler kullanan kısa bir Türkçe yeniden yazımı

Numara, tırnak ya da açıklama ekleme; sadece 3 satır.

Soru: {query}"""

MAX_QUERY_CHARS = 500  # LLM'e giden soru uzunluğu sınırı
MAX_VARIANT_CHARS = 300
THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)
LABEL_RE = re.compile(
    r"^\s*(?:[-*•]+|\d+[.)])?\s*(?:(?:english|ingilizce|turkish|türkçe|yeniden yazım|rewrite|"
    r"translation|çeviri)(?:\s*\d+)?\s*[:\-–]\s*)?",
    re.IGNORECASE,
)


def _normalize(text: str) -> str:
    """Tekrar kontrolü için: Türkçe büyük/küçük harf, noktalama ve boşluk farkları yok sayılır."""
    text = unicodedata.normalize("NFC", text).replace("İ", "i").replace("I", "ı").lower()
    return " ".join(re.sub(r"[^\w\s]", " ", text).split())


def _strings(value: object) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [s for v in value for s in _strings(v)]
    if isinstance(value, dict):
        return [s for v in value.values() for s in _strings(v)]
    return []


def _json_candidates(raw: str) -> list[str] | None:
    """Cevapta JSON (nesne ya da liste) varsa içindeki metinleri sırayla döner."""
    start = min((i for i in (raw.find("{"), raw.find("[")) if i >= 0), default=-1)
    if start < 0:
        return None
    try:
        value, _ = json.JSONDecoder().raw_decode(raw[start:])
    except ValueError:
        return None
    found = _strings(value)
    return found or None


def trim_truncated(raw: str) -> str:
    """`finish_reason=length` ile kesilmiş cevapta yarım kalmış son satırı atar (tek satırsa dokunmaz)."""
    lines = [ln for ln in (raw or "").strip().splitlines() if ln.strip()]
    return "\n".join(lines[:-1] if len(lines) > 1 else lines)


def parse_expansions(raw: str, original: str, max_variants: int = 3) -> list[str]:
    """LLM cevabından yeniden yazımları çıkarır: düz satırlar ya da JSON; orijinalin kopyaları atılır."""
    raw = THINK_RE.sub("", raw or "").replace("```json", "").replace("```", "").strip()
    candidates = _json_candidates(raw)
    if candidates is None:
        candidates = [LABEL_RE.sub("", line, count=1) for line in raw.splitlines()]
    seen = {_normalize(original)}
    out: list[str] = []
    for cand in candidates:
        text = cand.strip().strip("\"'“”`").strip()
        key = _normalize(text)
        if len(text) < 5 or len(text) > MAX_VARIANT_CHARS or not key or key in seen:
            continue
        seen.add(key)
        out.append(text)
        if len(out) >= max_variants:
            break
    return out


class QueryExpander:
    """`complete(prompt) -> str` ile soruyu genişletir; sonuçlar LRU önbellekte tutulur.

    `expand()` asla hata fırlatmaz: LLM çağrısı başarısız olursa [] döner ve ilk hata loglanır.
    """

    def __init__(
        self,
        complete: Callable[[str], str],
        max_variants: int = 3,
        cache_size: int = 256,
    ):
        self._complete = complete
        self.max_variants = max_variants
        self._cache: LRUCache[str, list[str]] = LRUCache(cache_size)
        self._lock = threading.Lock()
        self._warned = False
        self.calls = 0
        self.failures = 0
        self.last_error = ""

    def expand(self, query: str) -> list[str]:
        query = query.strip()
        if not query:
            return []
        cached = self._cache.get(query)
        if cached is not None:
            return list(cached)
        with self._lock:
            self.calls += 1
        try:
            raw = self._complete(EXPAND_PROMPT.format(query=query[:MAX_QUERY_CHARS]))
        except Exception as e:  # noqa: BLE001 - genişletme bir iyileştirmedir; her hatada orijinal sorguyla devam
            self._note_failure(e)
            return []
        variants = parse_expansions(raw, query, self.max_variants)
        if variants:  # boş sonuç önbelleğe alınmaz; sonraki istek yeniden denesin
            self._cache.put(query, variants)
        else:
            self._note_failure(ValueError(f"yeniden yazım çıkarılamadı: {raw[:120]!r}"))
        return variants

    def _note_failure(self, error: Exception) -> None:
        reason = f"{type(error).__name__}: {error}"[:300]
        with self._lock:
            self.failures += 1
            self.last_error = reason
            first = not self._warned
            self._warned = True
        if first:
            logger.warning("çoklu sorgu genişletme başarısız, orijinal sorgu kullanılıyor: %s", reason)

    def clear_cache(self) -> None:
        self._cache.clear()
