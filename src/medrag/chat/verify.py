"""Çalışma anında cevap doğrulama: cevap cümleleri atıf yapılan kaynaklarla bir hakem LLM'le karşılaştırılır.

Cümleler küçük gruplara bölünür, gruplar eş zamanlı değerlendirilir. Zaman bütçesi dolarsa bitenlerle
yetinilir; hiçbiri bitmezse `error` alanlı boş sonuç döner. Hiçbir durumda istisna fırlatmaz.
"""

import re
from concurrent.futures import ThreadPoolExecutor, wait
from dataclasses import dataclass, field
from typing import Any

from .sentences import cited_numbers, claim_sentences

VERIFY_PROMPT = """Sen bir sağlık asistanının cevabını kaynaklarla karşılaştıran titiz bir hakemsin.
Aşağıdaki KAYNAKLAR'a göre her numaralı CÜMLE'yi değerlendir.
- DESTEKLİ: cümledeki tıbbi bilgi kaynaklarda var ya da kaynaklardan doğrudan çıkıyor; ayrıca "hekime \
danışın", "kaynaklarda bilgi bulamadım" gibi genel yönlendirme/uyarı cümleleri de DESTEKLİ sayılır.
- DESTEKSİZ: cümle kaynaklarda bulunmayan, kaynaklarla çelişen ya da kaynaktan fazlasını söyleyen bir \
tıbbi iddia içeriyor.
Her cümle için tek satır yaz: "<no>: DESTEKLİ" ya da "<no>: DESTEKSİZ - kısa neden (en fazla 15 kelime)". \
Başka hiçbir şey yazma.

KAYNAKLAR
{sources}

CÜMLELER
{sentences}"""

MAX_SOURCE_CHARS = 1800
_VERDICT = re.compile(r"^\W*(\d+)\s*[:.)\-]\**\s*(DESTEKS\w*|DESTEKL\w*)\s*[-–:]?\s*(.*)$", re.IGNORECASE)
_TR_UPPER = str.maketrans({"İ": "I", "ı": "I", "i": "I"})


@dataclass
class VerificationResult:
    checked: int = 0
    unsupported: list[dict] = field(default_factory=list)
    error: str | None = None

    def event(self) -> dict:
        ev: dict[str, Any] = {"type": "verification", "checked": self.checked, "unsupported": self.unsupported}
        if self.error:
            ev["error"] = self.error
        return ev


def parse_verdicts(text: str) -> dict[int, tuple[bool, str]]:
    """Hakem çıktısını {cümle_no: (destekli_mi, neden)} sözlüğüne çevirir; tanınmayan satırları atlar."""
    out: dict[int, tuple[bool, str]] = {}
    for line in text.splitlines():
        m = _VERDICT.match(line.strip().lstrip("*-• "))
        if not m:
            continue
        label = m.group(2).translate(_TR_UPPER).upper()
        out[int(m.group(1))] = (not label.startswith("DESTEKS"), m.group(3).strip(" *-–:"))
    return out


def _group_sources(sentences: list[str], sources: dict[int, dict]) -> str:
    """Grup cümlelerinin atıf yaptığı kaynakları (atıf yoksa hepsini) metin olarak verir."""
    wanted: list[int] = []
    for s in sentences:
        nums = [n for n in cited_numbers(s) if n in sources]
        if not nums:
            wanted = list(sources)
            break
        wanted += [n for n in nums if n not in wanted]
    return "\n\n".join(
        f"[{n}] {sources[n].get('title', '')}\n{str(sources[n].get('text', ''))[:MAX_SOURCE_CHARS]}"
        for n in wanted
    )


class AnswerVerifier:
    def __init__(
        self,
        llm: Any,
        budget: float = 20.0,
        group_size: int = 3,
        concurrency: int = 8,
        max_tokens: int = 700,
        min_chars: int = 60,
    ):
        self.llm = llm
        self.budget = budget
        self.group_size = max(1, group_size)
        self.concurrency = max(1, concurrency)
        self.max_tokens = max_tokens
        self.min_chars = min_chars

    def should_skip(self, answer: str, sources: list[dict]) -> bool:
        """Kaynak yoksa, cevap çok kısaysa ya da kontrol edilecek bilgi cümlesi yoksa doğrulama atlanır."""
        return not sources or len(answer.strip()) < self.min_chars or not claim_sentences(answer)

    def _judge_group(self, group: list[tuple[int, str]], sources: dict[int, dict]) -> dict[int, tuple[bool, str]]:
        sentences = "\n".join(f"{i}: {s}" for i, s in group)
        prompt = VERIFY_PROMPT.format(sources=_group_sources([s for _, s in group], sources), sentences=sentences)
        text = self.llm.complete([{"role": "user", "content": prompt}], temperature=0.0, max_tokens=self.max_tokens)
        return parse_verdicts(text)

    def verify(self, answer: str, source_cards: list[dict]) -> VerificationResult:
        sources = {int(s["n"]): s for s in source_cards}
        sentences = list(enumerate(claim_sentences(answer), 1))
        groups = [sentences[i : i + self.group_size] for i in range(0, len(sentences), self.group_size)]
        pool = ThreadPoolExecutor(max_workers=min(self.concurrency, max(1, len(groups))))
        futures = {pool.submit(self._judge_group, g, sources): g for g in groups}
        try:
            done, _ = wait(futures, timeout=self.budget)
        finally:
            pool.shutdown(wait=False, cancel_futures=True)  # bitmeyen istekleri beklemeden bırak
        result = VerificationResult()
        errors: list[str] = []
        for fut in done:
            try:
                verdicts = fut.result()
            except Exception as e:  # noqa: BLE001 - hakem hatası akışı bozmamalı
                errors.append(type(e).__name__)
                continue
            for i, sentence in futures[fut]:
                if i not in verdicts:
                    continue
                result.checked += 1
                supported, reason = verdicts[i]
                if not supported:
                    result.unsupported.append(
                        {"sentence": sentence, "reason": reason or "Kaynaklarda desteklenmiyor.", "_i": i}
                    )
        result.unsupported.sort(key=lambda u: u.pop("_i"))
        if result.checked == 0:
            timed_out = len(done) < len(futures)
            result.error = "zaman aşımı" if timed_out else (errors[0] if errors else "hakem cevabı anlaşılamadı")
        return result
