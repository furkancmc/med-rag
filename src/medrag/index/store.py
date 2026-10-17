"""Vektör deposu: artımlı embedding (içerik özeti ile önbellek) ve kompakt saklama.

Dosyalar (`index_dir`):
- `ids.json`      chunk kimlikleri (sıra = vektör sırası)
- `hashes.json`   her chunk için sha1(embedding'e giden metin + model + boyut)
- `vectors.npy`   float16 (küçük indekste) ya da int8 (büyükte; `scales.npy` ile)
- `scales.npy`    yalnız int8'de: vektör başına ölçek (float32)
- `meta.json`     model, boyut, biçim

int8 neden güvenli: vektörler birim uzunlukta ve Matryoshka kesimli; vektör başına ölçekle
(max|x|/127) niceleme sonrası kosinüs hatası tipik olarak ~1e-3 altındadır, sıralama (top-k)
pratikte değişmez. Yükleyici her zaman L2-normalize float32 döndürür.
"""

import hashlib
import json
import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from .embed import Embedder, passage_text

MAX_FLOAT16_MB = 40  # float16 bundan büyük olacaksa int8'e geç
MAX_FILE_MB = 50  # tek dosya sınırı (GitHub 100 MB'tan çok altında kalmak için)


def load_chunks(data_dir: Path) -> list[dict]:
    path = data_dir / "chunks.jsonl"
    if not path.exists():
        raise FileNotFoundError(f"{path} yok. Önce 'python -m medrag.ingest build' çalıştır.")
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def passage_hash(chunk: dict, model: str = "", dimensions: int = 0) -> str:
    """Embedding girdisinin özeti: metin, model ya da boyut değişirse özet de değişir."""
    raw = f"{model}\n{dimensions}\n{passage_text(chunk)}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


def _progress(done: int, total: int) -> None:
    print(f"{time.strftime('%H:%M:%S')} embedding: {done}/{total}", flush=True)


def build_vectors(chunks: list[dict], embedder: Embedder, batch: int = 384) -> np.ndarray:
    parts = []
    for i in range(0, len(chunks), batch):
        texts = [passage_text(c) for c in chunks[i : i + batch]]
        parts.append(embedder.encode_passages(texts))
        _progress(min(i + batch, len(chunks)), len(chunks))
    return np.vstack(parts) if parts else np.zeros((0, 0), dtype=np.float32)


# --- niceleme ---


def l2_normalize(vectors: np.ndarray) -> np.ndarray:
    v = np.asarray(vectors, dtype=np.float32)
    norms = np.linalg.norm(v, axis=1, keepdims=True)
    return v / np.where(norms == 0, 1.0, norms)


def quantize_int8(vectors: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Vektör başına simetrik int8 niceleme. Döner: (int8 matris, float32 ölçekler)."""
    v = np.asarray(vectors, dtype=np.float32)
    scales = np.abs(v).max(axis=1) / 127.0
    scales = np.where(scales == 0, 1.0, scales).astype(np.float32)
    q = np.clip(np.rint(v / scales[:, None]), -127, 127).astype(np.int8)
    return q, scales


def dequantize_int8(q: np.ndarray, scales: np.ndarray) -> np.ndarray:
    return q.astype(np.float32) * scales[:, None]


def choose_format(n: int, dim: int, max_float16_mb: int = MAX_FLOAT16_MB) -> str:
    return "float16" if n * dim * 2 <= max_float16_mb * 1_000_000 else "int8"


def save_vectors(
    index_dir: Path,
    ids: list[str],
    vectors: np.ndarray,
    meta: dict | None = None,
    hashes: list[str] | None = None,
    max_float16_mb: int = MAX_FLOAT16_MB,
) -> str:
    """Vektörleri kaydeder; boyuta göre float16 ya da int8 seçer. Seçilen biçimi döner."""
    index_dir.mkdir(parents=True, exist_ok=True)
    n, dim = (vectors.shape if vectors.ndim == 2 else (0, 0))
    fmt = choose_format(n, dim, max_float16_mb)
    scales_path = index_dir / "scales.npy"
    if fmt == "int8":
        q, scales = quantize_int8(vectors)
        np.save(index_dir / "vectors.npy", q)
        np.save(scales_path, scales)
        size_mb = q.nbytes / 1e6
    else:
        np.save(index_dir / "vectors.npy", vectors.astype(np.float16))
        scales_path.unlink(missing_ok=True)
        size_mb = n * dim * 2 / 1e6
    if size_mb > MAX_FILE_MB:
        print(f"UYARI: vectors.npy ~{size_mb:.0f} MB; {MAX_FILE_MB} MB sınırını aşıyor", flush=True)
    (index_dir / "ids.json").write_text(json.dumps(ids), encoding="utf-8")
    if hashes is not None:
        (index_dir / "hashes.json").write_text(json.dumps(hashes), encoding="utf-8")
    full_meta = {**(meta or {}), "format": fmt, "count": n}
    # hangi modelle üretildi; sorgular da aynı modelle vektöre çevrilmeli
    (index_dir / "meta.json").write_text(json.dumps(full_meta, indent=2), encoding="utf-8")
    return fmt


def _read_raw(index_dir: Path) -> np.ndarray:
    """vectors.npy'yi biçimine bakmadan float32'ye açar (float16 ya da int8+ölçek)."""
    raw = np.load(index_dir / "vectors.npy")
    if raw.dtype == np.int8:
        return dequantize_int8(raw, np.load(index_dir / "scales.npy"))
    return raw.astype(np.float32)


def check_meta(index_dir: Path, model: str, dimensions: int) -> None:
    """İndeks başka bir modelle üretildiyse ValueError (yanlış modelin vektörleri yüklenmesin)."""
    meta_path = index_dir / "meta.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.exists() else {}
    if meta.get("model") != model or meta.get("dimensions") != dimensions:
        raise ValueError(
            f"{index_dir} indeksi '{meta.get('model')}' ({meta.get('dimensions')} boyut) ile "
            f"üretilmiş; ayarlardaki model '{model}' ({dimensions} boyut). Doğru indeks klasörünü "
            "seç ya da embedding'i bu modelle yeniden üret."
        )


def load_vectors(
    index_dir: Path, chunks: list[dict], model: str | None = None, dimensions: int | None = None
) -> np.ndarray:
    """Vektörleri yükler (L2-normalize float32) ve chunk sırasıyla uyuştuğunu doğrular.

    `model` verilirse `meta.json` ile model adı ve boyutu da denetlenir.
    """
    if model is not None:
        check_meta(index_dir, model, dimensions if dimensions is not None else 0)
    ids = json.loads((index_dir / "ids.json").read_text(encoding="utf-8"))
    if ids != [c["id"] for c in chunks]:
        raise ValueError(
            "Vektörler mevcut chunk listesiyle uyuşmuyor. Veri değişti, embedding'i yeniden üret."
        )
    return l2_normalize(_read_raw(index_dir))


# --- artımlı embedding ---


@dataclass
class EmbedStats:
    total: int = 0
    reused: int = 0
    computed: int = 0  # API'ye gönderilen benzersiz metin sayısı
    dropped: int = 0  # eski indekste olup artık chunk'ta bulunmayan

    def summary(self) -> str:
        return (
            f"toplam {self.total}, yeniden kullanılan {self.reused}, "
            f"yeni hesaplanan {self.computed}, silinen {self.dropped}"
        )


def load_cache(
    index_dir: Path,
    model: str,
    dimensions: int,
    chunks: list[dict] | None = None,
    trust_legacy: bool = False,
) -> dict[str, np.ndarray]:
    """Eski indeksten özet -> vektör sözlüğü. Model/boyut değiştiyse ya da yoksa boş döner.

    `hashes.json` olmayan eski indeks yalnız `trust_legacy=True` ile, chunk kimliğine güvenerek
    (metin değişmediği varsayımıyla) devralınır.
    """
    meta_path = index_dir / "meta.json"
    if not (index_dir / "ids.json").exists() or not (index_dir / "vectors.npy").exists():
        return {}
    meta = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.exists() else {}
    if (meta.get("model") and meta["model"] != model) or (
        meta.get("dimensions") and meta["dimensions"] != dimensions
    ):
        return {}
    ids = json.loads((index_dir / "ids.json").read_text(encoding="utf-8"))
    vectors = _read_raw(index_dir)
    if vectors.shape[0] != len(ids) or (vectors.size and vectors.shape[1] != dimensions):
        return {}
    hashes_path = index_dir / "hashes.json"
    if hashes_path.exists():
        hashes = json.loads(hashes_path.read_text(encoding="utf-8"))
    elif trust_legacy and chunks is not None:
        by_id = {c["id"]: c for c in chunks}
        hashes = [passage_hash(by_id[i], model, dimensions) if i in by_id else "" for i in ids]
    else:
        return {}
    return {h: vectors[i] for i, h in enumerate(hashes) if h}


def embed_incremental(
    chunks: list[dict],
    embedder: Embedder,
    index_dir: Path,
    model: str,
    dimensions: int,
    batch: int = 384,
    trust_legacy: bool = False,
) -> tuple[np.ndarray, list[str], EmbedStats]:
    """Yalnız yeni/değişen chunk'ları hesaplar, kalanını eski indeksten alır.

    Döner: (güncel chunk sırasında vektörler, özetler, istatistik).
    """
    cache = load_cache(index_dir, model, dimensions, chunks, trust_legacy)
    hashes = [passage_hash(c, model, dimensions) for c in chunks]
    stats = EmbedStats(total=len(chunks))
    todo: dict[str, dict] = {}  # benzersiz özet -> chunk
    for h, c in zip(hashes, chunks, strict=True):
        if h in cache:
            stats.reused += 1
        else:
            todo.setdefault(h, c)
    stats.computed = len(todo)
    stats.dropped = len(set(cache) - set(hashes))
    stats.reused = len(chunks) - sum(1 for h in hashes if h not in cache)
    print(
        f"önbellek: {len(cache)} eski vektör; yeniden kullanılacak {stats.reused}, "
        f"hesaplanacak {stats.computed}",
        flush=True,
    )
    fresh: dict[str, np.ndarray] = {}
    items = list(todo.items())
    for i in range(0, len(items), batch):
        part = items[i : i + batch]
        vecs = embedder.encode_passages([passage_text(c) for _, c in part])
        for (h, _), v in zip(part, vecs, strict=True):
            fresh[h] = v
        _progress(min(i + batch, len(items)), len(items))
    if not chunks:
        return np.zeros((0, 0), dtype=np.float32), hashes, stats
    rows = [fresh[h] if h in fresh else cache[h] for h in hashes]
    return l2_normalize(np.vstack(rows)), hashes, stats
