import json
import random
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

PROMPT = """Aşağıdaki tıbbi metin bir bilgi tabanından alındı. Bu metinde cevabı bulunan, \
sıradan bir hastanın Türkçe yazabileceği TEK bir soru yaz.

Kurallar:
- Metindeki cümleleri kopyalama, başlığı ya da makale adını aynen söyleme; günlük dil kullan.
- Tek cümle olsun.
- Sadece soruyu yaz, başka hiçbir şey yazma.

Başlık: {title}
Metin: {text}"""

# (kaynak, dil) -> örnek sayısı payı
QUOTAS = {("wikipedia", "tr"): 0.4, ("medlineplus", "en"): 0.3, ("wikipedia", "en"): 0.3}
MIN_WORDS = 60


def sample_chunks(chunks: list[dict], n: int, seed: int = 42) -> list[dict]:
    """Kaynak/dil gruplarından sabit tohumla, en az MIN_WORDS kelimelik chunk'lar seçer.

    Aynı dokümandan birden fazla soru üretilmez.
    """
    rng = random.Random(seed)
    picked: list[dict] = []
    used_docs: set[str] = set()
    for (source, lang), share in QUOTAS.items():
        pool = [
            c
            for c in chunks
            if c["source"] == source and c["lang"] == lang and len(c["text"].split()) >= MIN_WORDS
        ]
        rng.shuffle(pool)
        want = round(n * share)
        for c in pool:
            if want == 0:
                break
            if c["doc_id"] not in used_docs:
                used_docs.add(c["doc_id"])
                picked.append(c)
                want -= 1
    return picked


def clean_question(raw: str) -> str:
    line = next((ln.strip() for ln in raw.splitlines() if ln.strip()), "")
    return line.strip("\"'“”` ")


def generate_queries(
    chunks: list[dict], complete: Callable[[str], str], workers: int = 4
) -> list[dict]:
    def one(chunk: dict) -> dict | None:
        try:
            question = clean_question(complete(PROMPT.format(title=chunk["title"], text=chunk["text"])))
        except RuntimeError as e:  # LLMError dahil; tek hata tüm işi düşürmesin
            print(f"atlandı ({chunk['id']}): {e}")
            return None
        if len(question) < 10:
            return None
        return {"query": question, "chunk_id": chunk["id"], "doc_id": chunk["doc_id"]}

    with ThreadPoolExecutor(max_workers=workers) as pool:
        return [r for r in pool.map(one, chunks) if r]


def save_queries(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def load_queries(path: Path) -> list[dict]:
    return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]
