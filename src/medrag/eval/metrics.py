"""Arama metrikleri: recall@k, MRR@10 ve sorgu başına gecikme (ortalama / p95)."""

import math
import time
from collections import defaultdict
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field

KS = (1, 3, 5, 10)
MRR_CUTOFF = 10


def first_relevant_rank(hit_doc_ids: list[str], doc_id: str) -> int | None:
    """İlgili dokümanın ilk geçtiği sıra (1'den başlar), yoksa None."""
    for rank, d in enumerate(hit_doc_ids, start=1):
        if d == doc_id:
            return rank
    return None


@dataclass
class QueryRun:
    """Bir yöntemin tüm sorgulardaki sonucu: ilgili dokümanın sırası (yoksa None) ve hata sayısı."""

    ranks: list[int | None]
    errors: int = 0
    error_samples: list[str] = field(default_factory=list)


def run_queries(
    queries: list[dict],
    search: Callable[[str], list[dict]],
    workers: int = 1,
    skip_errors: bool = False,
) -> QueryRun:
    """Her soruyu `search` ile arar. `workers` > 1 ise sorgular paralel çalışır (sıra korunur).

    `skip_errors`: arama RuntimeError/OSError verirse o soru "bulunamadı" sayılır ve hata sayacı artar
    (uzun bir çalıştırma tek geçici hatada çökmesin); kapalıysa hata olduğu gibi yükselir.
    """

    def one(q: dict) -> tuple[int | None, str]:
        try:
            hits = search(q["query"])
        except (RuntimeError, OSError) as e:
            if not skip_errors:
                raise
            return None, f"{type(e).__name__}: {e}"[:160]
        return first_relevant_rank([h["doc_id"] for h in hits], q["doc_id"]), ""

    if workers > 1 and len(queries) > 1:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            outcomes = list(pool.map(one, queries))
    else:
        outcomes = [one(q) for q in queries]
    failed = [msg for _, msg in outcomes if msg]
    return QueryRun([r for r, _ in outcomes], len(failed), failed[:3])


def summarize(ranks: list[int | None]) -> dict[str, float]:
    """recall@k (doküman düzeyinde) ve MRR@10."""
    n = len(ranks) or 1
    result = {f"recall@{k}": sum(1 for r in ranks if r and r <= k) / n for k in KS}
    result["mrr@10"] = sum(1 / r for r in ranks if r and r <= MRR_CUTOFF) / n
    return result


def evaluate(
    queries: list[dict], search: Callable[[str], list[dict]], workers: int = 1
) -> dict[str, float]:
    """search(query) -> chunk listesi. recall@k (doküman düzeyinde) ve MRR@10 döner."""
    return summarize(run_queries(queries, search, workers).ranks)


def group_metrics(
    queries: list[dict], ranks: list[int | None], key: Callable[[dict], str]
) -> dict[str, dict[str, float]]:
    """Sorguları `key` ile gruplayıp (ör. kaynak/dil) her grup için metrik + soru sayısı hesaplar."""
    groups: dict[str, list[int | None]] = defaultdict(list)
    for q, r in zip(queries, ranks, strict=True):
        groups[key(q)].append(r)
    return {g: {"n": len(rs), **summarize(rs)} for g, rs in sorted(groups.items())}


def query_group(q: dict) -> str:
    """'kaynak/dil' (eski sorularda bu alanlar yoksa 'bilinmiyor')."""
    if not q.get("source"):
        return "bilinmiyor"
    return f"{q['source']}/{q.get('lang', '?')}"


# --- Gecikme ---
def percentile(values: list[float], q: float) -> float:
    """En yakın sıra (nearest-rank) yöntemiyle yüzdelik; q 0-100 arası."""
    if not values:
        return 0.0
    ordered = sorted(values)
    idx = max(0, min(len(ordered) - 1, math.ceil(q / 100 * len(ordered)) - 1))
    return ordered[idx]


def latency_stats(times: list[float]) -> dict[str, float]:
    """Saniye cinsinden ortalama ve p95 gecikme."""
    if not times:
        return {"mean": 0.0, "p95": 0.0, "n": 0}
    return {"mean": sum(times) / len(times), "p95": percentile(times, 95), "n": len(times)}


def measure_latency(
    queries: list[dict],
    search: Callable[[str], object],
    before: Callable[[], None] | None = None,
    clock: Callable[[], float] = time.perf_counter,
) -> list[float]:
    """Sorguları SIRAYLA çalıştırıp her birinin süresini ölçer. `before`, ölçüm dışında her sorgudan
    önce çağrılır (ör. önbellekleri boşaltmak için). Hatalı sorgu ölçüme katılmaz."""
    times: list[float] = []
    for q in queries:
        if before:
            before()
        start = clock()
        try:
            search(q["query"])
        except (RuntimeError, OSError):
            continue
        times.append(clock() - start)
    return times


# --- Tablo ---
def format_table(
    results: dict[str, dict[str, float]], labels: dict[str, str] | None = None
) -> str:
    """Markdown tablosu. Sonuçlarda gecikme alanları (latency_mean / latency_p95) varsa sütun eklenir."""
    cols = [f"recall@{k}" for k in KS] + ["mrr@10"]
    with_latency = any("latency_mean" in r for r in results.values())
    header = ["yöntem", *cols] + (["ort. gecikme (sn)", "p95 gecikme (sn)"] if with_latency else [])
    lines = ["| " + " | ".join(header) + " |", "|---|" + "---|" * (len(header) - 1)]
    for name, r in results.items():
        cells = [(labels or {}).get(name, name)] + [f"{r[c]:.3f}" for c in cols]
        if with_latency:
            cells += [f"{r[c]:.2f}" if c in r else "-" for c in ("latency_mean", "latency_p95")]
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)
