"""Yerel reranker (BAAI/bge-reranker-v2-m3): çapraz kodlayıcı, GPU'da fp16.

`ApiReranker` ile aynı `rerank(query, chunks)` sözleşmesi: hata olursa None döner, çağıran taraf
vektör sırasına geri düşer. Varsayılan KAPALI (`MEDRAG_RERANK_ENABLED=true` ve
`MEDRAG_RERANK_BACKEND=local` ile açılır). `torch`/`transformers` ilk kullanımda yüklenir.
"""

import logging
import threading

from .rerank import format_document

logger = logging.getLogger(__name__)


class LocalReranker:
    def __init__(
        self,
        model_name: str = "BAAI/bge-reranker-v2-m3",
        batch_size: int = 16,
        max_length: int = 512,
        doc_chars: int = 1500,
        device: str = "",
    ):
        self.model_name = model_name
        self.batch_size = max(1, batch_size)
        self.max_length = max_length
        self.doc_chars = doc_chars
        self.device_name = device
        self._tokenizer = None
        self._model = None
        self._lock = threading.Lock()
        self.calls = 0
        self.failures = 0
        self.last_error = ""

    def _load(self) -> None:
        import torch
        from transformers import AutoModelForSequenceClassification, AutoTokenizer

        device = self.device_name or ("cuda" if torch.cuda.is_available() else "cpu")
        dtype = torch.float16 if device.startswith("cuda") else torch.float32
        self._tokenizer = AutoTokenizer.from_pretrained(self.model_name)
        model = AutoModelForSequenceClassification.from_pretrained(self.model_name, dtype=dtype)
        self._model = model.to(device).eval()
        self.device_name = device

    def score_texts(self, query: str, docs: list[str]) -> list[float]:
        import torch

        with self._lock:
            if self._model is None:
                self._load()
            scores: list[float] = []
            for i in range(0, len(docs), self.batch_size):
                part = docs[i : i + self.batch_size]
                tok = self._tokenizer(
                    [query] * len(part), part, padding=True, truncation=True,
                    max_length=self.max_length, return_tensors="pt",
                ).to(self.device_name)  # fmt: skip
                with torch.inference_mode():
                    logits = self._model(**tok).logits.view(-1).float()
                scores.extend(logits.cpu().tolist())
            return scores

    def rerank(self, query: str, chunks: list[dict]) -> list[float | None] | None:
        if not chunks:
            return []
        self.calls += 1
        try:
            return list(self.score_texts(query, [format_document(c, self.doc_chars) for c in chunks]))
        except Exception as e:  # noqa: BLE001 - rerank bir iyileştirmedir; hatada vektör sırasına dön
            self.failures += 1
            self.last_error = f"{type(e).__name__}: {e}"[:300]
            logger.warning("yerel rerank başarısız, vektör sırası kullanılıyor: %s", self.last_error)
            return None
