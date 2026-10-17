"""Yerel embedding (BAAI/bge-m3, yoğun vektör): GPU'da fp16, GPU yoksa CPU.

BGE-M3 kuralları: sorguya da pasaja da ek önek/talimat eklenmez; vektör son katmanın [CLS] çıktısıdır
ve L2-normalize edilir (1024 boyut). `torch`/`transformers` yalnızca model ilk kullanıldığında içe
aktarılır; temel kurulum bunları istemez (`pip install -e .[local]`).

Metinler uzunluğa göre sıralanıp gruplanır (dolgu azalır, hız artar; en uzun grup önce çalışır ki
bellek yetersizliği hemen görülsün). CUDA OOM olursa grup boyutu yarıya indirilip aynı grup yeniden
denenir; küçülen boyut sonraki gruplarda da korunur.
"""

import logging
import threading
from collections.abc import Callable

import numpy as np

from medrag.lru import LRUCache

from .embed import cached_encode

logger = logging.getLogger(__name__)

EncodeBatch = Callable[[list[str]], np.ndarray]


def is_oom_error(error: BaseException) -> bool:
    """CUDA/CPU bellek yetersizliği hatası mı (torch'u içe aktarmadan anlaşılır)."""
    if type(error).__name__ == "OutOfMemoryError" or isinstance(error, MemoryError):
        return True
    return isinstance(error, RuntimeError) and "out of memory" in str(error).lower()


class LocalEmbedder:
    """Sorgu ve pasajları yerel modelle vektöre çevirir. `encode_batch` test için enjekte edilebilir."""

    def __init__(
        self,
        model_name: str = "BAAI/bge-m3",
        dimensions: int = 1024,
        batch_size: int = 32,
        max_length: int = 512,
        device: str = "",
        encode_batch: EncodeBatch | None = None,
        query_cache_size: int = 1024,
        is_oom: Callable[[BaseException], bool] = is_oom_error,
    ):
        self.model_name = model_name
        self.dimensions = dimensions
        self.batch_size = max(1, batch_size)
        self.max_length = max_length
        self.device_name = device
        self._encode_batch = encode_batch
        self._is_oom = is_oom
        self._lock = threading.Lock()  # GPU tek kullanıcılı: istekler sıraya girer
        self._load_lock = threading.Lock()
        self._tokenizer = None
        self._model = None
        self._query_cache: LRUCache[str, np.ndarray] = LRUCache(query_cache_size)
        self.oom_retries = 0

    # --- model ---
    def _load(self) -> None:
        with self._load_lock:
            if self._model is not None:
                return
            import torch
            from transformers import AutoModel, AutoTokenizer

            device = self.device_name or ("cuda" if torch.cuda.is_available() else "cpu")
            dtype = torch.float16 if device.startswith("cuda") else torch.float32
            logger.info("yerel embedding modeli yükleniyor: %s (%s, %s)", self.model_name, device, dtype)
            self._tokenizer = AutoTokenizer.from_pretrained(self.model_name)
            model = AutoModel.from_pretrained(self.model_name, dtype=dtype)
            self._model = model.to(device).eval()
            self.device_name = device

    def _torch_encode(self, texts: list[str]) -> np.ndarray:
        import torch

        if self._model is None:
            self._load()
        tok = self._tokenizer(
            texts, padding=True, truncation=True, max_length=self.max_length, return_tensors="pt"
        ).to(self.device_name)
        with torch.inference_mode():
            hidden = self._model(**tok).last_hidden_state[:, 0]  # [CLS]
            hidden = torch.nn.functional.normalize(hidden.float(), dim=-1)
        return hidden.cpu().numpy()

    # --- kodlama ---
    def _run(self, texts: list[str]) -> np.ndarray:
        if not texts:
            return np.zeros((0, self.dimensions), dtype=np.float32)
        encode = self._encode_batch or self._torch_encode
        order = sorted(range(len(texts)), key=lambda i: len(texts[i]), reverse=True)
        out = np.zeros((len(texts), self.dimensions), dtype=np.float32)
        with self._lock:
            pos = 0
            while pos < len(order):
                idx = order[pos : pos + self.batch_size]
                try:
                    vecs = encode([texts[i] for i in idx])
                except Exception as e:  # yalnız OOM yakalanır, gerisi yeniden fırlar
                    if not self._is_oom(e) or self.batch_size == 1:
                        raise
                    self.batch_size = max(1, self.batch_size // 2)
                    self.oom_retries += 1
                    logger.warning("bellek yetersiz; grup boyutu %d'ye indi", self.batch_size)
                    self._free_cache()
                    continue
                out[idx] = np.asarray(vecs, dtype=np.float32)[:, : self.dimensions]
                pos += len(idx)
        norms = np.linalg.norm(out, axis=1, keepdims=True)
        return out / np.where(norms == 0, 1.0, norms)

    @staticmethod
    def _free_cache() -> None:
        try:
            import torch

            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        except ImportError:
            pass

    def encode_passages(self, texts: list[str]) -> np.ndarray:
        return self._run(texts)

    def encode_queries(self, texts: list[str]) -> np.ndarray:
        return cached_encode(texts, self._query_cache, self._run)

    def clear_cache(self) -> None:
        self._query_cache.clear()
