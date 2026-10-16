import json
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from typing import Protocol

import numpy as np

from medrag.lru import LRUCache


class Embedder(Protocol):
    def encode_passages(self, texts: list[str]) -> np.ndarray: ...

    def encode_queries(self, texts: list[str]) -> np.ndarray: ...


def passage_text(chunk: dict) -> str:
    """Embedding'e giden metin: başlık ve bölüm adı bağlam verir."""
    head = chunk["title"] + (f" - {chunk['section']}" if chunk["section"] else "")
    return f"{head}\n{chunk['text']}"


QUERY_TASK = "Verilen tıbbi soruyla ilgili bilgi içeren pasajları bul"
RETRY_ERRORS = (urllib.error.URLError, TimeoutError, ConnectionError)  # geçici ağ hataları


def cached_encode(
    texts: list[str],
    cache: LRUCache[str, np.ndarray],
    encode_missing: Callable[[list[str]], np.ndarray],
) -> np.ndarray:
    """Önbellekte olmayan metinleri tek seferde çevirir; sonucu girdi sırasıyla döner.

    Aynı metin listede tekrar ederse bir kez hesaplanır. Önbellek iş parçacığı güvenlidir; iki
    iş parçacığı aynı metni aynı anda isterse ikisi de hesaplayabilir (sonuç aynı, zararsız).
    """
    found: dict[str, np.ndarray] = {}
    missing: list[str] = []
    for t in dict.fromkeys(texts):
        hit = cache.get(t)
        if hit is None:
            missing.append(t)
        else:
            found[t] = hit
    if missing:
        for t, v in zip(missing, encode_missing(missing), strict=True):
            v = np.array(v, copy=True)
            v.flags.writeable = False  # önbellekteki vektör yanlışlıkla değiştirilmesin
            cache.put(t, v)
            found[t] = v
    return np.stack([found[t] for t in texts]) if texts else np.zeros((0, 0), dtype=np.float32)


class ApiEmbedder:
    """OpenAI uyumlu bir /v1/embeddings servisini (ör. qwen3-embedding-8b) kullanır.

    Qwen3 embedding modelleri 'Matryoshka' eğitimlidir: vektör ilk N boyuta kesilip
    yeniden normalize edilebilir. 4096 yerine 1024 kullanmak depolamayı 4'te 1'e indirir.
    Sorgularda talimat öneki kullanılır, pasajlarda kullanılmaz.

    Sorgu vektörleri iş parçacığı güvenli bir LRU önbellekte tutulur (`query_cache_size=0` kapatır);
    aynı soru tekrar sorulunca ~3-6 sn'lik sabit API gecikmesi hiç ödenmez.
    """

    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str,
        dimensions: int = 1024,
        batch_size: int = 64,
        workers: int = 16,
        post: Callable[[list[str]], list[list[float]]] | None = None,
        query_cache_size: int = 1024,
        retry_base: float = 5.0,
        sleep: Callable[[float], None] = time.sleep,
    ):
        self.url = base_url.rstrip("/") + "/embeddings"
        self.api_key = api_key
        self.model = model
        self.dimensions = dimensions
        self.batch_size = batch_size
        self.workers = max(1, workers)
        self.retry_base = retry_base
        self._sleep = sleep
        self._post = post or self._http_post
        self._query_cache: LRUCache[str, np.ndarray] = LRUCache(query_cache_size)

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
                rows = [d["embedding"] for d in sorted(data["data"], key=lambda d: d["index"])]
            except urllib.error.HTTPError as e:
                if (e.code != 429 and e.code < 500) or attempt == 4:
                    raise
            except RETRY_ERRORS:
                if attempt == 4:
                    raise
            else:
                if len(rows) != len(inputs):
                    raise RuntimeError(
                        f"embedding sayısı uyuşmuyor: {len(inputs)} istendi, {len(rows)} geldi"
                    )
                return rows
            self._sleep(self.retry_base * 2**attempt)
        raise RuntimeError("ulaşılamaz")

    def _encode(self, texts: list[str]) -> np.ndarray:
        if not texts:
            return np.zeros((0, self.dimensions), dtype=np.float32)
        # İstek başına ~3-4 sn sabit gecikme var; paralel göndermek süreyi dakikalara indirir.
        batches = [texts[i : i + self.batch_size] for i in range(0, len(texts), self.batch_size)]
        if len(batches) == 1:
            parts = [self._post(batches[0])]
        else:
            with ThreadPoolExecutor(max_workers=min(self.workers, len(batches))) as pool:
                parts = list(pool.map(self._post, batches))
        rows = [row for part in parts for row in part]
        vecs = np.asarray(rows, dtype=np.float32)[:, : self.dimensions]
        return vecs / np.linalg.norm(vecs, axis=1, keepdims=True)

    def encode_passages(self, texts: list[str]) -> np.ndarray:
        return self._encode(texts)

    def encode_queries(self, texts: list[str]) -> np.ndarray:
        def encode_missing(missing: list[str]) -> np.ndarray:
            return self._encode([f"Instruct: {QUERY_TASK}\nQuery:{t}" for t in missing])

        return cached_encode(texts, self._query_cache, encode_missing)

    def clear_cache(self) -> None:
        self._query_cache.clear()


class CachingEmbedder:
    """Herhangi bir embedder'ı sorgu önbelleğiyle sarar (aynı sorgu birden fazla yöntemde aranırken)."""

    def __init__(self, inner: Embedder, maxsize: int = 4096):
        self.inner = inner
        self._cache: LRUCache[str, np.ndarray] = LRUCache(maxsize)

    def encode_passages(self, texts: list[str]) -> np.ndarray:
        return self.inner.encode_passages(texts)

    def encode_queries(self, texts: list[str]) -> np.ndarray:
        return cached_encode(texts, self._cache, self.inner.encode_queries)

    def clear_cache(self) -> None:
        self._cache.clear()
