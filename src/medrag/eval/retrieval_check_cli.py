"""Gerçek API ile hızlı ön kontrol: reranker cevap biçimi ve şablon etkisi, çoklu sorgu çıktısı.

`python -m medrag.eval retrieval-check` küçük bir örnekle şunları yazdırır (anahtar asla yazılmaz):
1. `/v1/rerank` ham cevap biçimi ve puan anahtarı; alakalı doküman her şablonda (`qwen3`, `none`) en üstte mi
2. Gerçek sorularda altın dokümanın vektör sırası → rerank sonrası sırası (iki şablon için)
3. 20 ve 40 dokümanlık isteklerin süresi
4. Çoklu sorgu: LLM'in ham çıktısı ve ayrıştırılan yeniden yazımlar
"""

import copy
import json
import time
from collections.abc import Callable
from pathlib import Path

from medrag.config import get_settings
from medrag.llm import EvrenLLM, parse_extra_params
from medrag.multiquery import EXPAND_PROMPT, parse_expansions
from medrag.rerank import TEMPLATES, ApiReranker, parse_scores
from medrag.retrieve import Retriever, expansion_completer, load_retriever

from .metrics import first_relevant_rank
from .queries import load_queries
from .search_cli import QUERIES_PATH, sample_evenly

PROBE_QUERY = "Şeker hastalığının belirtileri nelerdir?"
PROBE_DOCS = [
    {"title": "Diabetes", "section": "Symptoms",
     "text": "Common symptoms of diabetes are increased thirst, frequent urination, extreme hunger, "
     "unexplained weight loss, fatigue and blurred vision."},
    {"title": "Grip", "section": "Belirtiler",
     "text": "Grip ateş, öksürük, boğaz ağrısı, kas ağrısı ve halsizlik ile seyreden viral bir hastalıktır."},
    {"title": "Asthma", "section": "Treatment",
     "text": "Asthma is treated with inhalers that open the airways and reduce inflammation."},
]  # fmt: skip


def with_template(reranker: ApiReranker, template: str) -> ApiReranker:
    clone = copy.copy(reranker)
    clone.template = template
    return clone


def probe_raw(reranker: ApiReranker, log: Callable[[str], None] = print) -> dict[str, bool]:
    """Sabit üç dokümanla ham cevabı gösterir; alakalı doküman (0) en yüksek puanı alıyor mu."""
    verdicts: dict[str, bool] = {}
    docs = [f"{d['title']} - {d['section']}\n{d['text']}" for d in PROBE_DOCS]
    for template in TEMPLATES:
        r = with_template(reranker, template)
        started = time.perf_counter()
        try:
            raw = r.request_raw(PROBE_QUERY, docs)
            scores = parse_scores(raw, len(docs))
        except Exception as e:  # noqa: BLE001 - teşhis aracı: her hatayı olduğu gibi göster
            log(f"[ham/{template}] HATA {type(e).__name__}: {e}")
            verdicts[template] = False
            continue
        took = time.perf_counter() - started
        keys = sorted(raw) if isinstance(raw, dict) else type(raw).__name__
        first = (raw.get("results") or raw.get("data") or [None])[0] if isinstance(raw, dict) else None
        ok = scores[0] is not None and all(s is None or s < scores[0] for s in scores[1:])
        verdicts[template] = ok
        log(f"[ham/{template}] {took:.1f}s üst anahtarlar={keys} ilk sonuç={json.dumps(first, ensure_ascii=False)[:200]}")
        log(f"[ham/{template}] puanlar={scores} alakalı doküman en üstte: {'EVET' if ok else 'HAYIR'}")
    return verdicts


def gold_positions(
    retriever: Retriever, queries: list[dict], template: str, pool: int, log: Callable[[str], None]
) -> tuple[list[int | None], list[int | None]]:
    """Her soru için altın dokümanın (vektör sırası, rerank sonrası sırası)."""
    clone = copy.copy(retriever)
    assert clone.reranker is not None
    clone.reranker = with_template(clone.reranker, template)
    before: list[int | None] = []
    after: list[int | None] = []
    for q in queries:
        vec = clone.search(q["query"], k=pool, rerank=False)
        started = time.perf_counter()
        rer = clone.search(q["query"], k=pool, rerank=True, rerank_pool=pool)
        took = time.perf_counter() - started
        b = first_relevant_rank([h.chunk["doc_id"] for h in vec], q["doc_id"])
        a = first_relevant_rank([h.chunk["doc_id"] for h in rer], q["doc_id"])
        before.append(b)
        after.append(a)
        log(f"[örnek/{template}] vektör sırası={b} → rerank sırası={a} ({took:.1f}s) {q['query'][:60]!r}")
    return before, after


def mean_rank(ranks: list[int | None], missing: int) -> float:
    return sum(r or missing for r in ranks) / max(1, len(ranks))


def probe_latency(retriever: Retriever, query: str, log: Callable[[str], None]) -> None:
    for pool in (20, 40):
        retriever.clear_caches()
        retriever.search(query, k=5, rerank=False)  # embedding önbelleğini ısıt: yalnızca rerank süresi
        started = time.perf_counter()
        retriever.search(query, k=5, rerank=True, rerank_pool=pool)
        log(f"[süre] rerank havuz {pool}: {time.perf_counter() - started:.2f}s (embedding önbellekte)")


def probe_multiquery(complete: Callable[[str], str], queries: list[str], log: Callable[[str], None]) -> int:
    """LLM'in ham çıktısını ve ayrıştırılan yeniden yazımları gösterir; kaç sorguda sonuç çıktığını döner."""
    good = 0
    for q in queries:
        started = time.perf_counter()
        try:
            raw = complete(EXPAND_PROMPT.format(query=q))
        except Exception as e:  # noqa: BLE001 - teşhis aracı
            log(f"[çoklu sorgu] HATA {type(e).__name__}: {e}")
            continue
        variants = parse_expansions(raw, q)
        good += bool(variants)
        log(f"[çoklu sorgu] {time.perf_counter() - started:.1f}s soru={q!r}")
        log(f"   ham={raw[:300]!r}")
        log(f"   ayrıştırılan={variants}")
    return good


def register(sub) -> None:
    check = sub.add_parser("retrieval-check", help="reranker ve çoklu sorguyu gerçek API ile hızlıca dene")
    check.add_argument("-n", type=int, default=10, help="gerçek örnek soru sayısı")
    check.add_argument("--queries", type=Path, default=QUERIES_PATH)
    check.set_defaults(func=cmd_check)


def cmd_check(args) -> None:
    settings = get_settings()
    try:
        retriever = load_retriever(settings)
    except RuntimeError as e:
        raise SystemExit(f"hata: {e}") from e
    reranker = retriever.reranker
    assert isinstance(reranker, ApiReranker)
    reranker.timeout = 60.0
    print(f"rerank: {settings.rerank_api_url} model={settings.rerank_model} varsayılan şablon={settings.rerank_template}")
    verdicts = probe_raw(reranker)

    queries = sample_evenly(load_queries(args.queries), args.n) if args.queries.exists() else []
    summary = {}
    for template in TEMPLATES:
        if not queries:
            break
        before, after = gold_positions(retriever, queries, template, settings.rerank_pool, print)
        missing = settings.rerank_pool + 1
        summary[template] = (mean_rank(before, missing), mean_rank(after, missing))
        print(
            f"[özet/{template}] altın doküman ortalama sırası: vektör {summary[template][0]:.2f} → "
            f"rerank {summary[template][1]:.2f} (düşük iyi; havuzda yoksa {missing} sayıldı)"
        )
    if queries:
        probe_latency(retriever, queries[0]["query"], print)
        llm = EvrenLLM(
            settings.llm_api_url,
            settings.multiquery_model,
            extra_params=parse_extra_params(settings.multiquery_extra_params),
        )
        probe_multiquery(
            expansion_completer(llm, settings.multiquery_max_tokens),
            [PROBE_QUERY, *[q["query"] for q in queries[:2]]],
            print,
        )
    best = min(summary, key=lambda t: summary[t][1]) if summary else None
    if best:
        print(f"ÖNERİ: ortalama altın sırası en düşük şablon: {best} (MEDRAG_RERANK_TEMPLATE={best})")
    if not any(verdicts.values()):
        raise SystemExit("HATA: hiçbir şablonda rerank düzgün çalışmadı (yukarıdaki ham çıktılara bak)")
