import json
from pathlib import Path

import numpy as np

from .embed import Embedder, passage_text


def load_chunks(data_dir: Path) -> list[dict]:
    path = data_dir / "chunks.jsonl"
    if not path.exists():
        raise FileNotFoundError(f"{path} yok. Önce 'python -m medrag.ingest build' çalıştır.")
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def build_vectors(chunks: list[dict], embedder: Embedder, batch: int = 256) -> np.ndarray:
    parts = []
    for i in range(0, len(chunks), batch):
        texts = [passage_text(c) for c in chunks[i : i + batch]]
        parts.append(embedder.encode_passages(texts))
        print(f"embedding: {min(i + batch, len(chunks))}/{len(chunks)}", flush=True)
    return np.vstack(parts) if parts else np.zeros((0, 0), dtype=np.float32)


def save_vectors(index_dir: Path, ids: list[str], vectors: np.ndarray) -> None:
    index_dir.mkdir(parents=True, exist_ok=True)
    np.save(index_dir / "vectors.npy", vectors.astype(np.float16))  # yarı boyut, kalite kaybı ihmal edilebilir
    (index_dir / "ids.json").write_text(json.dumps(ids), encoding="utf-8")


def load_vectors(index_dir: Path, chunks: list[dict]) -> np.ndarray:
    """Vektörleri yükler ve chunk sırasıyla uyuştuğunu doğrular."""
    ids = json.loads((index_dir / "ids.json").read_text(encoding="utf-8"))
    if ids != [c["id"] for c in chunks]:
        raise ValueError(
            "Vektörler mevcut chunk listesiyle uyuşmuyor. Veri değişti, embedding'i yeniden üret."
        )
    return np.load(index_dir / "vectors.npy").astype(np.float32)
