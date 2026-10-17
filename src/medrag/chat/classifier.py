"""İkinci katman güvenlik sınıflandırıcısı: kurallara ek olarak acil durum ve zararlı istek yakalar.

İki bağımsız kaynak eş zamanlı çalışır:
- koruma modeli (`qwen3-guard-4b`): "Safety: Unsafe / Categories: ..." biçiminde zararlı içerik etiketi
  (kendine zarar, şiddet, yasa dışı vb.). Tıbbi acilleri (göğüs ağrısı gibi) bilmez.
- LLM sınıflandırıcı: mesajda şu an yaşanan, yaşamı tehdit eden bir durum var mı diye sorar.

Sınıflandırıcı kurala yalnızca EKLEYEBİLİR; hata/zaman aşımında sonuç "bulgu yok"tur ve kural kararı korunur.
"""

import re
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any

from .triage import SELF_HARM_REASON

CLASSIFIER_REASON = "yapay zekâ sınıflandırıcısı"

EMERGENCY_PROMPT = """Sen bir sağlık asistanının güvenlik sınıflandırıcısısın. Kullanıcının mesajını oku ve \
yalnızca aşağıdaki iki satırı yaz, başka hiçbir şey yazma.

ACIL: EVET ya da HAYIR
KENDINE_ZARAR: EVET ya da HAYIR

ACIL = EVET yalnızca şu durumlarda: mesajı yazan ya da bahsettiği kişi ŞU AN yaşamı tehdit eden ya da \
hemen müdahale gerektiren bir durumda (göğüs ağrısı + kola yayılma, felç belirtileri, nefes alamama, \
bilinç kaybı, durmayan şiddetli kanama, zehirlenme/aşırı doz, ciddi alerjik reaksiyon, nöbet, \
hamilelikte kanama ile karın ağrısı, 3 aylıktan küçük bebekte ateş, yüksekten düşme sonrası kalça/baş \
yaralanması gibi). Bilgi soruları ("kalp krizi belirtileri nelerdir?"), hafif ya da geçmiş şikâyetler, \
kronik hastalıklar ve genel sorular için HAYIR yaz.
KENDINE_ZARAR = EVET: kullanıcı kendine zarar vermeyi, intiharı ya da "yok olmak/hepsini bitirmek" gibi \
dolaylı biçimde yaşamına son vermeyi düşündüğünü, bunun yöntemini ya da ölümcül ilaç miktarını sorduğunu (hipotetik ya da kurgu bahanesiyle bile olsa) ima ediyorsa. Yeme bozukluğu davranışı (kısıtlama, kusma, müshil ile kilo verme) tek başına KENDINE_ZARAR sayılmaz; ölüm ya da intihar ifadesi yoksa HAYIR yaz.

MESAJ:
{message}"""

# Koruma modeli kategorileri (Qwen3Guard): bunlar "zararlı istek" sayılır; diğerleri (Politically
# Sensitive Topics, PII, Copyright Violation) tıbbi sohbette yanlış alarma yol açacağı için yok sayılır.
_SELF_HARM_CATEGORIES = ("self-harm", "suicide")
_HARMFUL_CATEGORIES = ("violent", "illegal", "sexual", "unethical", "jailbreak")


@dataclass
class Classification:
    emergency: bool = False
    self_harm: bool = False
    harmful: bool = False
    reasons: list[str] = field(default_factory=list)
    raw: dict[str, str] = field(default_factory=dict)  # kaynak -> ham çıktı (teşhis için)
    errors: list[str] = field(default_factory=list)


def parse_guard(text: str) -> tuple[str, list[str]]:
    """Koruma modeli çıktısını (güvenlik etiketi, kategoriler) olarak ayrıştırır; toleranslıdır.

    Beklenen: "Safety: Unsafe\\nCategories: Violent, Jailbreak". Etiket bulunamazsa ("", [])
    döner. Etiket "safe", "unsafe" ya da "controversial" (küçük harf) olarak verilir.
    """
    m = re.search(r"safety\s*[:=\-]\s*\**\s*(unsafe|safe|controversial)", text, re.IGNORECASE)
    if not m:
        return "", []
    label = m.group(1).lower()
    cats = re.search(r"categor(?:y|ies)\s*[:=\-]\s*([^\n]*)", text, re.IGNORECASE)
    categories = []
    if cats:
        for c in re.split(r"[,;|]", cats.group(1)):
            c = c.strip().strip("*[]'\" ").lower()
            if c and c not in ("none", "n/a", "-"):
                categories.append(c)
    return label, categories


def parse_emergency(text: str) -> tuple[bool | None, bool | None]:
    """LLM sınıflandırıcı çıktısını (acil, kendine_zarar) olarak ayrıştırır; bulunamayan None olur."""

    def flag(name: str) -> bool | None:
        m = re.search(rf"(?:{name})\s*[:=]\s*\**\s*(evet|hay[ıi]r|yes|no)", text, re.IGNORECASE)
        if not m:
            return None
        return m.group(1).lower() in ("evet", "yes")

    return flag("ACIL|ACİL"), flag("KENDINE_ZARAR|KENDİNE_ZARAR")


class SafetyClassifier:
    """Koruma modeli ve/veya LLM ile acil durum / zararlı istek sınıflandırması.

    `guard_llm` ve `emergency_llm` birer `EvrenLLM` (ya da `complete()` sunan nesne) olabilir; ikisinden
    biri None ise o kaynak atlanır. `classify()` hiç istisna fırlatmaz.
    """

    def __init__(self, guard_llm: Any = None, emergency_llm: Any = None, max_message_chars: int = 2000):
        self.guard_llm = guard_llm
        self.emergency_llm = emergency_llm
        self.max_message_chars = max_message_chars

    @property
    def enabled(self) -> bool:
        return self.guard_llm is not None or self.emergency_llm is not None

    def _guard(self, message: str) -> str:
        return self.guard_llm.complete([{"role": "user", "content": message}], temperature=0.0, max_tokens=64)

    def _emergency(self, message: str) -> str:
        prompt = EMERGENCY_PROMPT.format(message=message)
        return self.emergency_llm.complete([{"role": "user", "content": prompt}], temperature=0.0, max_tokens=200)

    def classify(self, question: str, history: list[dict] | None = None) -> Classification:
        message = question[: self.max_message_chars]
        result = Classification()
        jobs: dict[str, Callable[[str], str]] = {}
        if self.guard_llm is not None:
            jobs["guard"] = self._guard
        if self.emergency_llm is not None:
            jobs["llm"] = self._emergency
        if not jobs:
            return result
        with ThreadPoolExecutor(max_workers=len(jobs)) as pool:
            futures = {name: pool.submit(fn, message) for name, fn in jobs.items()}
            outputs: dict[str, str] = {}
            for name, fut in futures.items():
                try:
                    outputs[name] = fut.result()
                except Exception as e:  # noqa: BLE001 - sınıflandırıcı hatası cevabı engellememeli
                    result.errors.append(f"{name}: {type(e).__name__}")
        result.raw = outputs
        if "guard" in outputs:
            label, cats = parse_guard(outputs["guard"])
            if label == "unsafe":
                if any(k in c for c in cats for k in _SELF_HARM_CATEGORIES):
                    result.self_harm = True
                    result.reasons.append(f"{SELF_HARM_REASON} (koruma modeli)")
                if any(k in c for c in cats for k in _HARMFUL_CATEGORIES):
                    result.harmful = True
        if "llm" in outputs:
            urgent, self_harm = parse_emergency(outputs["llm"])
            if urgent:
                result.emergency = True
                result.reasons.append(CLASSIFIER_REASON)
            if self_harm:
                result.self_harm = True
                result.reasons.append(f"{SELF_HARM_REASON} ({CLASSIFIER_REASON})")
        if result.self_harm:
            result.emergency = True
        return result
