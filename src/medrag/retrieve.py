"""Arama hattı: vektör (varsayılan) → isteğe bağlı çoklu sorgu → isteğe bağlı reranker.

`Retriever.search(query, k)` imzası sohbet servisi için sabittir. `load_retriever(settings)` ayarlara göre
hattı kurar; reranker varsayılan olarak AÇIK, çoklu sorgu KAPALIdır (ölçülene kadar). Her ikisi de
hata/zaman aşımında sessizce vektör sırasına döner. Bir arama için `rerank=` / `multiquery=` ile ayar
geçersiz kılınabilir (değerlendirme bunu kullanır).
"""

import logging
import os
import threading
import time
from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

import numpy as np

from .config import ConfigError, Settings
from .index.bm25 import BM25
from .index.embed import ApiEmbedder, Embedder
from .index.store import load_chunks, load_vectors
from .index.tokenize import tokenize
from .ingest.build import build_chunks
from .multiquery import QueryExpander, trim_truncated
from .rerank import ApiReranker, Reranker

logger = logging.getLogger(__name__)

RRF_K = 60  # sıralama birleştirmede standart sabit
# Ölçüm (eval/results.md, 150 soru): vektör recall@5 0.85; BM25 0.46; hybrid her ağırlıkta vektörden
# kötü (en iyisi 0.05 ağırlıkla 0.81). Bu yüzden varsayılan yöntem vektör. Hybrid isteğe bağlı kalır.
DEFAULT_MODE = "vector"
DEFAULT_BM25_WEIGHT = 0.05
MODES = ("vector", "bm25", "hybrid")
EXPANSION_MAX_TOKENS = 3000  # düşünen modeller (deepseek) önce akıl yürütme tokenı harcar


@dataclass
class Hit:
    chunk: dict
    score: float


def bm25_text(chunk: dict) -> str:
    return f"{chunk['title']} {chunk['section']} {chunk['text']}"


def rrf_fuse(
    rankings: Sequence[Sequence[int]], weights: Sequence[float] | None = None, k: int = RRF_K
) -> list[tuple[int, float]]:
    """Reciprocal Rank Fusion: sıralamaları ağırlıklı olarak birleştirir, (indeks, puan) listesi döner."""
    weights = weights if weights is not None else [1.0] * len(rankings)
    fused: dict[int, float] = {}
    for ranking, weight in zip(rankings, weights, strict=True):
        for rank, i in enumerate(ranking):
            fused[i] = fused.get(i, 0.0) + weight / (k + rank + 1)
    return sorted(fused.items(), key=lambda x: x[1], reverse=True)


class Retriever:
    def __init__(
        self,
        chunks: list[dict],
        vectors: np.ndarray,
        embedder: Embedder,
        *,
        reranker: Reranker | None = None,
        expander: QueryExpander | None = None,
        rerank_enabled: bool = True,
        rerank_pool: int = 40,
        multiquery_enabled: bool = False,
        multiquery_timeout: float = 15.0,
        multiquery_original_weight: float = 1.0,
    ):
        self.chunks = chunks
        self.vectors = vectors
        self.embedder = embedder
        self.bm25 = BM25([tokenize(bm25_text(c)) for c in chunks])
        self.reranker = reranker
        self.expander = expander
        self.rerank_enabled = rerank_enabled and reranker is not None
        self.rerank_pool = rerank_pool
        self.multiquery_enabled = multiquery_enabled and expander is not None
        self.multiquery_timeout = multiquery_timeout
        self.multiquery_original_weight = multiquery_original_weight
        self._executor: ThreadPoolExecutor | None = None
        self._executor_lock = threading.Lock()

    # --- Aday üretimi ---
    def _bm25_ranking(self, query: str, n: int) -> list[int]:
        return [i for i, _ in self.bm25.search(tokenize(query), n)]

    def _top(self, q: np.ndarray, n: int) -> list[tuple[int, float]]:
        """Sorgu vektörüne kosinüs benzerliği en yüksek n chunk: (indeks, benzerlik)."""
        scores = self.vectors @ q
        n = min(n, len(scores))
        if n <= 0:
            return []
        top = np.argpartition(-scores, n - 1)[:n] if n < len(scores) else np.arange(len(scores))
        top = top[np.argsort(-scores[top], kind="stable")]
        return [(int(i), float(scores[i])) for i in top]

    def _vector_ranking(self, query: str, n: int) -> list[int]:
        q = self.embedder.encode_queries([query])[0]
        return [i for i, _ in self._top(q, n)]

    def _get_executor(self) -> ThreadPoolExecutor:
        with self._executor_lock:
            if self._executor is None:
                self._executor = ThreadPoolExecutor(max_workers=8, thread_name_prefix="medrag-mq")
            return self._executor

    def _multiquery_candidates(self, query: str, n: int) -> list[tuple[int, float]]:
        """Orijinal + genişletilmiş sorguların vektör sıralamaları RRF ile birleşir.

        Genişletme (LLM) ile orijinal sorgunun embedding'i aynı anda başlar; genişletme
        `multiquery_timeout` içinde gelmezse ya da hata verirse sadece orijinal sorgu kullanılır.
        """
        assert self.expander is not None
        started = time.monotonic()
        pending = self._get_executor().submit(self.expander.expand, query)
        base = self.embedder.encode_queries([query])[0]
        try:
            budget = max(0.0, self.multiquery_timeout - (time.monotonic() - started))
            extras = pending.result(timeout=budget)
        except Exception as e:  # noqa: BLE001 - genişletme bir iyileştirmedir; orijinal sorguyla sürer
            logger.info("çoklu sorgu genişletme kullanılamadı: %s", type(e).__name__)
            extras = []
        vectors = [base]
        if extras:
            try:
                vectors += list(self.embedder.encode_queries(extras))
            except (RuntimeError, OSError) as e:
                logger.warning("genişletilmiş sorgular vektöre çevrilemedi: %s", type(e).__name__)
        rankings = [self._top(v, n) for v in vectors]
        if len(rankings) == 1:
            return rankings[0]
        weights = [self.multiquery_original_weight] + [1.0] * (len(rankings) - 1)
        return rrf_fuse([[i for i, _ in r] for r in rankings], weights)[:n]

    def _candidates(
        self, query: str, n: int, mode: str, multiquery: bool, pool: int, bm25_weight: float
    ) -> list[tuple[int, float]]:
        if mode == "bm25":
            return [(i, s) for i, s in self.bm25.search(tokenize(query), n)]
        if mode == "vector":
            if multiquery:
                return self._multiquery_candidates(query, n)
            q = self.embedder.encode_queries([query])[0]
            return self._top(q, n)
        pool = max(pool, n)  # hybrid: iki sıralamayı RRF ile birleştir
        rankings = [self._bm25_ranking(query, pool), self._vector_ranking(query, pool)]
        return rrf_fuse(rankings, [bm25_weight, 1.0])[:n]

    # --- Reranker ---
    def _rerank(
        self, query: str, cands: list[tuple[int, float]], k: int
    ) -> list[tuple[int, float]]:
        """Adayları reranker ile sıralar. Reranker hata verirse vektör sırası korunur."""
        assert self.reranker is not None
        scores = self.reranker.rerank(query, [self.chunks[i] for i, _ in cands])
        if scores is None or len(scores) != len(cands):
            return cands[:k]
        valid = [s for s in scores if s is not None]
        floor = min(valid) if valid else 0.0  # puansız kalanlar en sona, kendi sırasıyla
        order = sorted(range(len(cands)), key=lambda j: (scores[j] is None, -(scores[j] or 0.0), j))
        return [(cands[j][0], floor if scores[j] is None else scores[j]) for j in order[:k]]

    def search(
        self,
        query: str,
        k: int = 5,
        mode: str = DEFAULT_MODE,
        pool: int = 50,
        bm25_weight: float = DEFAULT_BM25_WEIGHT,
        rerank: bool | None = None,
        multiquery: bool | None = None,
        rerank_pool: int | None = None,
    ) -> list[Hit]:
        """En ilgili k parçayı döner.

        `rerank` / `multiquery`: None → ayarlardaki varsayılan (yalnızca `vector` modunda geçerli);
        True/False → bu arama için zorla aç/kapat. `rerank_pool`: reranker'a giden aday sayısı.
        """
        if mode not in MODES:
            raise ValueError(f"bilinmeyen mod: {mode}")
        use_rerank = self.rerank_enabled and mode == "vector" if rerank is None else rerank
        use_mq = self.multiquery_enabled and mode == "vector" if multiquery is None else multiquery
        if use_rerank and self.reranker is None:
            raise ValueError("rerank istendi ama reranker tanımlı değil")
        if use_mq and (self.expander is None or mode != "vector"):
            raise ValueError("çoklu sorgu için sorgu genişletici ve vektör modu gerekir")
        n = max(k, rerank_pool or self.rerank_pool) if use_rerank else k
        cands = self._candidates(query, n, mode, bool(use_mq), pool, bm25_weight)
        if use_rerank and cands:
            cands = self._rerank(query, cands, k)
        return [Hit(self.chunks[i], score) for i, score in cands[:k]]

    def diagnostics(self) -> dict:
        """Reranker ve genişleticinin çağrı/hata sayaçları (değerlendirme raporu için)."""
        out: dict = {}
        for name, part in (("rerank", self.reranker), ("multiquery", self.expander)):
            if part is not None and hasattr(part, "failures"):
                out[name] = {
                    "calls": part.calls,
                    "failures": part.failures,
                    "last_error": part.last_error,
                }
        return out

    def clear_caches(self) -> None:
        """Sorgu embedding'i ve genişletme önbelleklerini boşaltır (soğuk gecikme ölçümü için)."""
        for part in (self.embedder, self.expander):
            clear = getattr(part, "clear_cache", None)
            if clear:
                clear()


# --- Kurulum ---
def make_embedder(settings: Settings, api_key: str) -> ApiEmbedder:
    return ApiEmbedder(
        settings.embed_api_url,
        api_key,
        settings.embed_api_model,
        settings.embed_dimensions,
        workers=settings.embed_workers,
        query_cache_size=settings.embed_query_cache_size,
        retry_base=1.0,  # sorgu yolu etkileşimli: kısa geri çekilme (indeks üretimi 5 sn kullanır)
    )


def make_reranker(settings: Settings, api_key: str) -> ApiReranker:
    return ApiReranker(
        settings.rerank_api_url,
        api_key,
        settings.rerank_model,
        batch_size=settings.rerank_batch_size,
        timeout=settings.rerank_timeout,
        template=settings.rerank_template,
        instruction=settings.rerank_instruction,
        doc_chars=settings.rerank_doc_chars,
        workers=settings.embed_workers,
    )


def make_expander(settings: Settings, api_key: str) -> QueryExpander:
    """Düşünmesi kapalı, kısa zaman aşımlı LLM ile genişletici; her hatada orijinal sorguya düşülür."""
    from .llm import EvrenLLM, parse_extra_params

    llm = EvrenLLM(
        settings.llm_api_url,
        settings.multiquery_model,
        api_key,
        extra_params=parse_extra_params(settings.multiquery_extra_params),
        timeout=settings.multiquery_timeout,
        max_retries=2,
        backoff=1.0,
    )
    return QueryExpander(expansion_completer(llm, settings.multiquery_max_tokens))


def expansion_completer(llm, max_tokens: int = EXPANSION_MAX_TOKENS):
    """`prompt -> metin`: cevap `length` ile kesildiyse eksik kalan son satır atılır."""

    def complete(prompt: str) -> str:
        comp = llm.complete_detailed(
            [{"role": "user", "content": prompt}], temperature=0.2, max_tokens=max_tokens
        )
        return trim_truncated(comp.content) if comp.finish_reason == "length" else comp.content

    return complete


def load_retriever(settings: Settings) -> Retriever:
    api_key = os.environ.get("EVREN_API_KEY")
    if not api_key:
        raise ConfigError("EVREN_API_KEY ortam değişkeni tanımlı değil")
    if not (settings.data_dir / "chunks.jsonl").exists():
        build_chunks(settings.data_dir)  # data/raw'dan deterministik olarak üretilir
    chunks = load_chunks(settings.data_dir)
    vectors = load_vectors(settings.index_dir, chunks)
    # Reranker ve genişletici her zaman kurulur (ağ çağrısı yapmazlar); `*_enabled` yalnızca
    # varsayılan davranışı belirler, `search(rerank=..., multiquery=...)` ile aramada değiştirilebilir.
    return Retriever(
        chunks,
        vectors,
        make_embedder(settings, api_key),
        reranker=make_reranker(settings, api_key),
        expander=make_expander(settings, api_key),
        rerank_enabled=settings.rerank_enabled,
        rerank_pool=settings.rerank_pool,
        multiquery_enabled=settings.multiquery_enabled,
        multiquery_timeout=settings.multiquery_timeout,
        multiquery_original_weight=settings.multiquery_original_weight,
    )
