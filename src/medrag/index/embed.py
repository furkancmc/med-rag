import json
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from typing import Protocol

import numpy as np


class Embedder(Protocol):
    def encode_passages(self, texts: list[str]) -> np.ndarray: ...

    def encode_queries(self, texts: list[str]) -> np.ndarray: ...


def passage_text(chunk: dict) -> str:
    """Embedding'e giden metin: başlık ve bölüm adı bağlam verir."""
    head = chunk["title"] + (f" - {chunk['section']}" if chunk["section"] else "")
    return f"{head}\n{chunk['text']}"


class E5Embedder:
    """multilingual-e5-small (CPU'da çalışır). e5 modelleri 'query: ' / 'passage: ' ön eki ister."""

    def __init__(self, model_name: str = "intfloat/multilingual-e5-small"):
        from sentence_transformers import SentenceTransformer  # opsiyonel bağımlılık

        self.model = SentenceTransformer(model_name, device="cpu")

    def _encode(self, texts: list[str], prefix: str) -> np.ndarray:
        vecs = self.model.encode(
            [prefix + t for t in texts],
            batch_size=32,
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        return np.asarray(vecs, dtype=np.float32)

    def encode_passages(self, texts: list[str]) -> np.ndarray:
        return self._encode(texts, "passage: ")

    def encode_queries(self, texts: list[str]) -> np.ndarray:
        return self._encode(texts, "query: ")


QUERY_TASK = "Verilen tıbbi soruyla ilgili bilgi içeren pasajları bul"


class ApiEmbedder:
    """OpenAI uyumlu bir /v1/embeddings servisini (ör. qwen3-embedding-8b) kullanır.

    Qwen3 embedding modelleri 'Matryoshka' eğitimlidir: vektör ilk N boyuta kesilip
    yeniden normalize edilebilir. 4096 yerine 1024 kullanmak depolamayı 4'te 1'e indirir.
    Sorgularda talimat öneki kullanılır, pasajlarda kullanılmaz.
    """

    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str,
        dimensions: int = 1024,
        batch_size: int = 32,
        post: Callable[[list[str]], list[list[float]]] | None = None,
    ):
        self.url = base_url.rstrip("/") + "/embeddings"
        self.api_key = api_key
        self.model = model
        self.dimensions = dimensions
        self.batch_size = batch_size
        self._post = post or self._http_post

    def _http_post(self, inputs: list[str]) -> list[list[float]]:
        body = json.dumps({"model": self.model, "input": inputs}).encode()
        req = urllib.request.Request(
            self.url,
            data=body,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
        )
        for attempt in range(5):
            try:
                with urllib.request.urlopen(req, timeout=120) as resp:
                    data = json.loads(resp.read())
                return [d["embedding"] for d in sorted(data["data"], key=lambda d: d["index"])]
            except urllib.error.HTTPError as e:
                if (e.code != 429 and e.code < 500) or attempt == 4:
                    raise
                time.sleep(5 * 2**attempt)
        raise RuntimeError("ulaşılamaz")

    def _encode(self, texts: list[str]) -> np.ndarray:
        rows: list[list[float]] = []
        for i in range(0, len(texts), self.batch_size):
            rows += self._post(texts[i : i + self.batch_size])
        vecs = np.asarray(rows, dtype=np.float32)[:, : self.dimensions]
        return vecs / np.linalg.norm(vecs, axis=1, keepdims=True)

    def encode_passages(self, texts: list[str]) -> np.ndarray:
        return self._encode(texts)

    def encode_queries(self, texts: list[str]) -> np.ndarray:
        return self._encode([f"Instruct: {QUERY_TASK}\nQuery:{t}" for t in texts])
