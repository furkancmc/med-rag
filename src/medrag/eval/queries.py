"""Değerlendirme sorularının üretimi: kaynak/dil gruplarına uyum sağlayan kotalar, yüksek eşzamanlılık,
tekrar eden soruların elenmesi.

Satır biçimi (eski `eval/queries.jsonl` ile uyumlu): `{"query", "chunk_id", "doc_id"}`; yeni satırlarda
ek olarak `source` ve `lang` bulunur (kaynak/dil kırılımı için).
"""

import json
import math
import random
import re
import unicodedata
from collections import defaultdict
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

PROMPT = """Aşağıdaki tıbbi metin bir bilgi tabanından alındı. Bu metinde cevabı bulunan, \
sıradan bir hastanın Türkçe yazabileceği TEK bir soru yaz.

Kurallar:
- Soru her zaman Türkçe olsun (metin İngilizce olsa bile).
- Metindeki cümleleri kopyalama, başlığı ya da makale adını aynen söyleme; günlük dil kullan.
- Tek cümle olsun.
- Sadece soruyu yaz, başka hiçbir şey yazma.

Başlık: {title}
Metin: {text}"""

MIN_WORDS = 60
DEDUPE_JACCARD = 0.8  # kelime kümesi benzerliği bu eşiğin üstündeki sorular tekrar sayılır
TURKISH_LETTERS = set("çğıöşüÇĞİÖŞÜ")
ENGLISH_WORDS = frozenset(
    {
        *("the", "of", "and", "is", "are", "was", "what", "how", "why", "when", "which", "who"),
        *("do", "does", "did", "can", "could", "should", "in", "to", "for", "with", "my", "i"),
        *("it", "this", "that", "be", "have", "has", "or", "on", "at", "by", "from", "about"),
    }
)
ENGLISH_STARTERS = frozenset(
    {"what", "how", "why", "when", "which", "who", "is", "are", "can", "does", "do"}
)
Group = tuple[str, str]  # (kaynak, dil)


# --- Kotalar ---
def compute_quotas(capacity: dict[Group, int], n: int) -> dict[Group, int]:
    """n soruyu gruplara dağıtır: pay ≈ √(gruptaki doküman sayısı), grup kapasitesini aşmaz.

    Dengeli kapsama sağlar (büyük bir kaynak her şeyi doldurmaz, küçük kaynak da yok sayılmaz).
    Kapasite yetmezse artan pay kapasitesi olan gruplara dağıtılır; toplam kapasite n'den azsa hepsi alınır.
    """
    groups = sorted(g for g, c in capacity.items() if c > 0)
    if n <= 0 or not groups:
        return {}
    if n >= sum(capacity[g] for g in groups):
        return {g: capacity[g] for g in groups}
    quotas = {g: 0 for g in groups}
    open_groups = list(groups)
    remaining = n
    while remaining > 0 and open_groups:
        total = sum(math.sqrt(capacity[g]) for g in open_groups)
        shares = {g: remaining * math.sqrt(capacity[g]) / total for g in open_groups}
        capped = [g for g in open_groups if quotas[g] + shares[g] >= capacity[g]]
        if capped:  # kapasitesi dolan gruplar tavana oturur, kalan pay diğerlerine gider
            for g in capped:
                remaining -= capacity[g] - quotas[g]
                quotas[g] = capacity[g]
                open_groups.remove(g)
            continue
        floors = {g: int(shares[g]) for g in open_groups}
        left = remaining - sum(floors.values())
        by_remainder = sorted(open_groups, key=lambda g: (shares[g] - floors[g], g), reverse=True)
        for i, g in enumerate(by_remainder):
            quotas[g] += floors[g] + (1 if i < left else 0)
        remaining = 0
    return {g: q for g, q in quotas.items() if q > 0}


def eligible_by_group(chunks: list[dict]) -> dict[Group, dict[str, list[dict]]]:
    """(kaynak, dil) -> doküman -> soru üretmeye uygun (yeterince uzun) chunk'lar."""
    groups: dict[Group, dict[str, list[dict]]] = defaultdict(lambda: defaultdict(list))
    for c in chunks:
        if len(c["text"].split()) >= MIN_WORDS:
            groups[(c["source"], c["lang"])][c["doc_id"]].append(c)
    return groups


def sample_chunks(
    chunks: list[dict], n: int, seed: int = 42, exclude_docs: set[str] | None = None
) -> list[dict]:
    """Kaynak/dil gruplarından sabit tohumla en az MIN_WORDS kelimelik chunk'lar seçer.

    Gruplar chunk listesinden kendiliğinden bulunur (yeni kaynaklar eklenince kod değişmez); kotalar
    `compute_quotas` ile belirlenir. Aynı dokümandan birden fazla soru üretilmez. `exclude_docs`:
    daha önce denenmiş dokümanlar (eksik kalanı tamamlarken tekrar seçilmesin).
    """
    exclude_docs = exclude_docs or set()
    groups = {
        g: {d: cs for d, cs in docs.items() if d not in exclude_docs}
        for g, docs in eligible_by_group(chunks).items()
    }
    quotas = compute_quotas({g: len(docs) for g, docs in groups.items()}, n)
    picked: list[dict] = []
    for group in sorted(quotas):
        rng = random.Random(f"{seed}:{group[0]}:{group[1]}")  # grup başına bağımsız, kararlı
        doc_ids = sorted(groups[group])
        rng.shuffle(doc_ids)
        for doc_id in doc_ids[: quotas[group]]:
            picked.append(rng.choice(groups[group][doc_id]))
    return picked


# --- Soru temizleme ve eleme ---
def clean_question(raw: str) -> str:
    line = next((ln.strip() for ln in raw.splitlines() if ln.strip()), "")
    return line.strip("\"'“”` ")


def is_turkish(question: str) -> bool:
    """Kaba kontrol: soru İngilizceye kaymadıysa True (Türkçe harf varsa kesin Türkçe sayılır).

    Türkçede ek çeşitliliği büyük olduğundan Türkçeyi sözcükle tanımak yerine İngilizce işaretleri aranır:
    sık İngilizce sözcük en az 2 kez geçiyorsa ya da soru İngilizce soru sözcüğüyle başlıyorsa elenir.
    """
    if any(ch in TURKISH_LETTERS for ch in question):
        return True
    tokens = normalize_question(question).split()
    hits = sum(1 for t in tokens if t in ENGLISH_WORDS)
    return not (hits >= 2 or (tokens and tokens[0] in ENGLISH_STARTERS))


def normalize_question(text: str) -> str:
    """Tekrar kontrolü için: Türkçe büyük/küçük harf, noktalama ve boşluk farkları yok sayılır."""
    text = unicodedata.normalize("NFC", text).replace("İ", "i").replace("I", "ı").lower()
    return " ".join(re.sub(r"[^\w\s]", " ", text).split())


def dedupe_queries(rows: list[dict]) -> list[dict]:
    """Aynı (ya da neredeyse aynı) soruları eler; ilk gelen kalır, sıra korunur."""
    kept: list[dict] = []
    token_sets: list[set[str]] = []
    for row in rows:
        tokens = set(normalize_question(row["query"]).split())
        if any(
            tokens == t or len(tokens & t) / max(1, len(tokens | t)) >= DEDUPE_JACCARD
            for t in token_sets
        ):
            continue
        kept.append(row)
        token_sets.append(tokens)
    return kept


def generate_queries(
    chunks: list[dict], complete: Callable[[str], str], workers: int = 16
) -> list[dict]:
    """Her chunk için bir Türkçe soru üretir (paralel; sıra korunur). Başarısız olanlar atlanır."""

    def one(chunk: dict) -> dict | None:
        try:
            question = clean_question(
                complete(PROMPT.format(title=chunk["title"], text=chunk["text"]))
            )
        except (RuntimeError, OSError) as e:  # LLMError ve ağ hataları; tek hata tüm işi düşürmesin
            print(f"atlandı ({chunk['id']}): {e}")
            return None
        if not 10 <= len(question) <= 400 or not is_turkish(question):
            return None
        row = {"query": question, "chunk_id": chunk["id"], "doc_id": chunk["doc_id"]}
        if chunk.get("source"):
            row["source"] = chunk["source"]
            row["lang"] = chunk.get("lang", "")
        return row

    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        return [r for r in pool.map(one, chunks) if r]


def build_queries(
    chunks: list[dict],
    n: int,
    complete: Callable[[str], str],
    workers: int = 16,
    seed: int = 42,
    rounds: int = 3,
) -> list[dict]:
    """n soruya ulaşmak için üretir; elenenler (hata, İngilizce, tekrar) yeni dokümanlarla tamamlanır."""
    rows: list[dict] = []
    tried: set[str] = set()
    for attempt in range(rounds):
        sample = sample_chunks(chunks, n - len(rows), seed + attempt, tried)
        if not sample:
            break
        tried |= {c["doc_id"] for c in sample}
        rows = dedupe_queries(rows + generate_queries(sample, complete, workers))
        print(f"tur {attempt + 1}: {len(rows)}/{n} soru", flush=True)
        if len(rows) >= n:
            break
    return rows[:n]


def save_queries(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def load_queries(path: Path) -> list[dict]:
    return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]
