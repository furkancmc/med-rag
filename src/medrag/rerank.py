"""Reranker: vektör aramadan gelen adayları Evren API'nin `/v1/rerank` uç noktasıyla yeniden sıralar.

İstek: `POST /v1/rerank {"model", "query", "documents": [str]}`.
Cevap: `{"results": [{"index": int, "relevance_score": float}, ...]}` (puan anahtarı `score` da olabilir).
Her (soru, doküman) çifti ayrı puanlanır; 4096 token bağlamına sığması için doküman metni kısaltılır.
Herhangi bir hatada `rerank()` None döner ve çağıran taraf vektör sırasına geri düşer (çökme yok).
"""

import json
import logging
import math
import threading
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from typing import Protocol

logger = logging.getLogger(__name__)

DEFAULT_INSTRUCTION = (
    "Given a patient's medical question in Turkish, judge whether the passage "
    "(Turkish or English) contains information that answers the question"
)
# Qwen3-Reranker'ın resmi istem şablonu (vLLM örneğindeki gibi): sorgu ve doküman ayrı sarılır.
QWEN3_PREFIX = (
    "<|im_start|>system\nJudge whether the Document meets the requirements based on the Query and "
    'the Instruct provided. Note that the answer can only be "yes" or "no".<|im_end|>\n'
    "<|im_start|>user\n"
)
QWEN3_SUFFIX = "<|im_end|>\n<|im_start|>assistant\n<think>\n\n</think>\n\n"
TEMPLATES = ("qwen3", "none")
MAX_QUERY_CHARS = 600
MAX_ATTEMPTS = 4


class RerankError(RuntimeError):
    pass


class Reranker(Protocol):
    def rerank(self, query: str, chunks: list[dict]) -> list[float | None] | None:
        """Her chunk için puan (aynı sırada). Puansız kalan None; tümü başarısızsa None döner."""
        ...


def truncate(text: str, limit: int) -> str:
    """Kelimeyi ortadan bölmeden `limit` karaktere kısaltır."""
    text = text.strip()
    if len(text) <= limit:
        return text
    cut = text[:limit]
    head, sep, _ = cut.rpartition(" ")
    return (head if sep and len(head) > limit // 2 else cut).rstrip() + " …"


def format_document(chunk: dict, max_chars: int = 1500) -> str:
    """Rerank'e giden metin: başlık, bölüm ve kısaltılmış parça metni."""
    head = chunk.get("title", "") + (f" - {chunk['section']}" if chunk.get("section") else "")
    return f"{head}\n{truncate(chunk.get('text', ''), max_chars)}".strip()


def apply_template(query: str, docs: list[str], template: str, instruction: str) -> tuple[str, list[str]]:
    """Şablona göre sorgu ve dokümanları sarar. 'none': ham metin."""
    query = truncate(query, MAX_QUERY_CHARS)
    if template == "none":
        return query, docs
    if template != "qwen3":
        raise ValueError(f"bilinmeyen rerank şablonu: {template} (qwen3 | none)")
    wrapped_query = f"{QWEN3_PREFIX}<Instruct>: {instruction}\n<Query>: {query}\n"
    return wrapped_query, [f"<Document>: {d}{QWEN3_SUFFIX}" for d in docs]


def _number(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    return None if math.isnan(value) else float(value)


def parse_scores(data: object, n: int) -> list[float | None]:
    """`/rerank` cevabından n doküman için puan listesi çıkarır; eksik olan None kalır.

    `relevance_score` ya da `score` kabul edilir; `index` yoksa ve sonuç sayısı n ise sıra esas alınır.
    Geçerli tek bir puan bile yoksa RerankError.
    """
    items = None
    if isinstance(data, dict):
        items = data.get("results")
        if items is None:
            items = data.get("data")
    elif isinstance(data, list):
        items = data
    if not isinstance(items, list):
        raise RerankError(f"beklenmeyen rerank cevabı: {str(data)[:200]}")
    scores: list[float | None] = [None] * n
    for pos, item in enumerate(items):
        if not isinstance(item, dict):
            continue
        idx = item.get("index")
        if isinstance(idx, bool) or not isinstance(idx, int):
            idx = pos if len(items) == n else None
        if idx is None or not 0 <= idx < n:
            continue
        score = _number(item.get("relevance_score"))
        if score is None:
            score = _number(item.get("score"))
        if score is not None:
            scores[idx] = score
    if all(s is None for s in scores):
        raise RerankError(f"rerank cevabında geçerli puan yok: {str(data)[:200]}")
    return scores


class ApiReranker:
    """OpenAI/Cohere tarzı `/rerank` servisini (qwen3-reranker-8b) kullanır.

    Büyük aday havuzu `batch_size`'lık gruplara bölünüp paralel gönderilir. Toplam süre
    `timeout` saniyeyi (yeniden denemeler dahil) aşamaz; aşılırsa ya da herhangi bir hata olursa
    `rerank()` None döner ve ilk hata bir kez loglanır. Anahtar asla loglanmaz.
    """

    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str = "qwen3-reranker-8b",
        batch_size: int = 20,
        timeout: float = 20.0,
        template: str = "qwen3",
        instruction: str = "",
        doc_chars: int = 1500,
        workers: int = 16,
        post: Callable[[dict], object] | None = None,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ):
        if template not in TEMPLATES:
            raise ValueError(f"bilinmeyen rerank şablonu: {template} ({' | '.join(TEMPLATES)})")
        self.url = base_url.rstrip("/") + "/rerank"
        self.api_key = api_key
        self.model = model
        self.batch_size = max(1, batch_size)
        self.timeout = timeout
        self.template = template
        self.instruction = instruction or DEFAULT_INSTRUCTION
        self.doc_chars = doc_chars
        self.workers = max(1, workers)
        self._post = post
        self._clock = clock
        self._sleep = sleep
        self._lock = threading.Lock()
        self._warned = False
        self.calls = 0
        self.failures = 0
        self.last_error = ""

    # --- HTTP ---
    def _request(self, payload: dict) -> urllib.request.Request:
        return urllib.request.Request(
            self.url,
            data=json.dumps(payload).encode(),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
        )

    def _http_post(self, payload: dict, deadline: float) -> object:
        req = self._request(payload)
        last = "bilinmeyen hata"
        for attempt in range(MAX_ATTEMPTS):
            remaining = deadline - self._clock()
            if remaining <= 0:
                raise RerankError(f"rerank zaman aşımı ({last})")
            try:
                with urllib.request.urlopen(req, timeout=remaining) as resp:
                    return json.loads(resp.read())
            except urllib.error.HTTPError as e:
                last = f"HTTP {e.code}"
                if e.code != 429 and e.code < 500:  # 4xx kalıcı hata: yeniden denemenin anlamı yok
                    body = e.read()[:200].decode("utf-8", "replace")
                    raise RerankError(f"rerank isteği reddedildi: {last} {body}") from e
            except (urllib.error.URLError, TimeoutError, ConnectionError, ValueError) as e:
                last = f"{type(e).__name__}: {e}"[:200]
            if attempt < MAX_ATTEMPTS - 1:
                self._sleep(min(0.5 * 2**attempt, max(0.0, deadline - self._clock())))
        raise RerankError(f"rerank başarısız ({last})")

    def request_raw(self, query: str, docs: list[str], deadline: float | None = None) -> object:
        """Tek istek gönderip ham (ayrıştırılmamış) cevabı döner; teşhis ve `_score_batch` kullanır."""
        q, wrapped = apply_template(query, docs, self.template, self.instruction)
        payload = {"model": self.model, "query": q, "documents": wrapped}
        if self._post:
            return self._post(payload)
        return self._http_post(payload, deadline or self._clock() + self.timeout)

    def _score_batch(self, query: str, docs: list[str], deadline: float) -> list[float | None]:
        return parse_scores(self.request_raw(query, docs, deadline), len(docs))

    # --- Genel arayüz ---
    def score_texts(self, query: str, docs: list[str]) -> list[float | None]:
        """Metinleri puanlar (hata olursa RerankError). Gruplar paralel, toplam süre sınırlı."""
        if not docs:
            return []
        deadline = self._clock() + self.timeout
        batches = [docs[i : i + self.batch_size] for i in range(0, len(docs), self.batch_size)]
        executor = ThreadPoolExecutor(max_workers=min(self.workers, len(batches)))
        try:
            futures = [executor.submit(self._score_batch, query, b, deadline) for b in batches]
            scores: list[float | None] = []
            for fut in futures:
                try:
                    scores.extend(fut.result(timeout=max(0.0, deadline - self._clock())))
                except TimeoutError as e:
                    raise RerankError("rerank zaman aşımı") from e
            return scores
        finally:
            executor.shutdown(wait=False, cancel_futures=True)

    def rerank(self, query: str, chunks: list[dict]) -> list[float | None] | None:
        if not chunks:
            return []
        docs = [format_document(c, self.doc_chars) for c in chunks]
        with self._lock:
            self.calls += 1
        try:
            scores = self.score_texts(query, docs)
        except Exception as e:  # noqa: BLE001 - rerank bir iyileştirmedir; her hatada vektör sırasına dön
            self._note_failure(e)
            return None
        self._warned = False  # düzeldi; sonraki kesinti yeniden loglansın
        return scores

    def _note_failure(self, error: Exception) -> None:
        reason = f"{type(error).__name__}: {error}"[:300]
        with self._lock:
            self.failures += 1
            self.last_error = reason
            first = not self._warned
            self._warned = True
        if first:
            logger.warning("rerank başarısız, vektör sırası kullanılıyor: %s", reason)
