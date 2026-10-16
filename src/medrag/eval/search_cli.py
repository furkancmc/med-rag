"""Arama değerlendirmesi: test sorusu üretme (gen) ve yöntem karşılaştırma (run).

`run` yöntemleri (`--methods`): bm25, vector, hybrid, rerank<N>[-qwen3|-none], mq-vector,
mq-rerank[<N>][-qwen3|-none]. Kalite tüm sorularda paralel ölçülür; gecikme ayrıca, az sayıda soruda
SIRAYLA ve soğuk önbellekle ölçülür (paralel yük gecikmeyi şişirir, önbellek ise gizler).
"""

import copy
import json
import re
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from medrag.config import Settings, get_settings
from medrag.index.store import load_chunks
from medrag.llm import EvrenLLM
from medrag.rerank import TEMPLATES
from medrag.retrieve import DEFAULT_BM25_WEIGHT, Retriever, load_retriever

from .metrics import (
    format_table,
    group_metrics,
    latency_stats,
    measure_latency,
    query_group,
    run_queries,
    summarize,
)
from .queries import build_queries, load_queries, save_queries

QUERIES_PATH = Path("eval/queries.jsonl")
RESULTS_PATH = Path("eval/results.md")
RESULTS_JSON_PATH = Path("eval/results.json")
DEFAULT_METHODS = ("bm25", "vector", "rerank20", "rerank40", "rerank40-none", "mq-vector", "mq-rerank")
RERANK_RE = re.compile(r"^(mq-)?rerank(\d+)?(?:-(qwen3|none))?$")
FAILURE_EXIT_RATIO = 0.5  # reranker/genişletici çağrılarının bu oranı başarısızsa çıkış kodu 3


@dataclass(frozen=True)
class Method:
    name: str
    label: str
    mode: str = "vector"
    rerank: bool = False
    multiquery: bool = False
    rerank_pool: int | None = None
    template: str | None = None  # None → ayardaki rerank şablonu
    bm25_weight: float = DEFAULT_BM25_WEIGHT

    def search_kwargs(self) -> dict:
        kwargs = {"mode": self.mode, "rerank": self.rerank, "multiquery": self.multiquery}
        if self.rerank_pool:
            kwargs["rerank_pool"] = self.rerank_pool
        if self.mode == "hybrid":
            kwargs["bm25_weight"] = self.bm25_weight
        return kwargs


def parse_method(name: str, default_pool: int = 40) -> Method:
    """'rerank20', 'rerank40-none', 'mq-rerank', 'mq-vector', 'vector', 'bm25', 'hybrid' → Method."""
    name = name.strip().lower()
    if name == "bm25":
        return Method(name, "bm25", mode="bm25")
    if name == "vector":
        return Method(name, "vector")
    if name == "hybrid":
        return Method(name, f"hybrid (bm25 ağırlığı {DEFAULT_BM25_WEIGHT})", mode="hybrid")
    if name == "mq-vector":
        return Method(name, "çoklu sorgu + vector", multiquery=True)
    m = RERANK_RE.match(name)
    if m:
        mq, pool, template = m.group(1), int(m.group(2) or default_pool), m.group(3)
        suffix = {"qwen3": ", qwen3 şablonu", "none": ", şablonsuz"}.get(template or "", "")
        base = "çoklu sorgu + rerank" if mq else "vector + rerank"
        return Method(
            name, f"{base} (havuz {pool}{suffix})", rerank=True, multiquery=bool(mq),
            rerank_pool=pool, template=template,
        )  # fmt: skip
    raise ValueError(
        f"bilinmeyen yöntem: {name!r}. Geçerli: bm25, vector, hybrid, rerank<N>[-qwen3|-none], "
        "mq-vector, mq-rerank[<N>][-qwen3|-none], all"
    )


def parse_methods(spec: str, default_pool: int = 40) -> list[Method]:
    """Virgülle ayrılmış liste; 'all' varsayılan kümeyi açar. Tekrarlar atılır, sıra korunur."""
    names: list[str] = []
    for part in (spec or "all").split(","):
        part = part.strip()
        names += list(DEFAULT_METHODS) if part in ("all", "") else [part]
    return [parse_method(n, default_pool) for n in dict.fromkeys(names)]


def retriever_for(retriever: Retriever, method: Method) -> Retriever:
    """Şablonu zorlayan yöntemler için reranker'ı kopyalanmış bir retriever (ağır veri paylaşılır)."""
    if not method.template or retriever.reranker is None:
        return retriever
    if method.template not in TEMPLATES:
        raise ValueError(f"bilinmeyen şablon: {method.template}")
    clone = copy.copy(retriever)
    clone.reranker = copy.copy(retriever.reranker)
    clone.reranker.template = method.template
    return clone


def diagnostics_delta(before: dict, after: dict) -> dict:
    """Yöntem çalışırken reranker/genişletici çağrı ve hata sayıları."""
    out = {}
    for name, now in after.items():
        was = before.get(name, {"calls": 0, "failures": 0})
        out[name] = {
            "calls": now["calls"] - was["calls"],
            "failures": now["failures"] - was["failures"],
            "last_error": now["last_error"] if now["failures"] > was["failures"] else "",
        }
    return out


def sample_evenly(items: list, n: int) -> list:
    """Sıralı listeden eşit aralıklı n örnek (kaynak gruplarının hepsinden eleman gelsin)."""
    if n <= 0:
        return []
    if len(items) <= n:
        return list(items)
    step = len(items) / n
    return [items[int(i * step)] for i in range(n)]


def make_search(retriever, method: Method) -> Callable[[str], list[dict]]:
    """Yöntemi çalıştıran arama işlevi: soru -> ilk 10 chunk (recall@10 için)."""
    kwargs = method.search_kwargs()

    def search(query: str) -> list[dict]:
        return [h.chunk for h in retriever.search(query, k=10, **kwargs)]

    return search


def run_methods(
    retriever,
    queries: list[dict],
    methods: list[Method],
    workers: int = 8,
    latency_n: int = 20,
    log=print,
) -> dict[str, dict]:
    """Her yöntem için kalite (paralel) ve gecikme (sıralı, soğuk önbellek) ölçer."""
    results: dict[str, dict] = {}
    for number, method in enumerate(methods, 1):
        r = retriever_for(retriever, method)
        search = make_search(r, method)
        diagnostics = getattr(r, "diagnostics", dict)
        before = diagnostics()
        started = time.perf_counter()
        run = run_queries(queries, search, workers, skip_errors=True)
        quality_seconds = time.perf_counter() - started
        latency = None
        if latency_n > 0:
            clear = getattr(r, "clear_caches", None)
            times = measure_latency(sample_evenly(queries, latency_n), search, before=clear)
            latency = latency_stats(times)
        entry = {
            "label": method.label,
            "metrics": summarize(run.ranks),
            "groups": group_metrics(queries, run.ranks, query_group),
            "latency": latency,
            "quality_seconds": round(quality_seconds, 1),
            "errors": run.errors,
            "error_samples": run.error_samples,
            "diagnostics": diagnostics_delta(before, diagnostics()),
        }
        results[method.name] = entry
        m = entry["metrics"]
        lat = f", gecikme ort. {latency['mean']:.2f}s p95 {latency['p95']:.2f}s" if latency else ""
        log(
            f"[{number}/{len(methods)}] {method.label}: recall@1={m['recall@1']:.3f} "
            f"recall@5={m['recall@5']:.3f} mrr@10={m['mrr@10']:.3f} "
            f"({quality_seconds:.0f}s, hata {run.errors}){lat}"
        )
        for name, d in entry["diagnostics"].items():
            if d["failures"]:
                log(f"   UYARI {name}: {d['failures']}/{d['calls']} çağrı başarısız ({d['last_error']})")
    return results


def failure_warnings(results: dict[str, dict]) -> list[str]:
    """Reranker/genişletici çağrıları ya da sorgular başarısız olduysa okunur uyarılar."""
    out = []
    for name, e in results.items():
        for part, d in e["diagnostics"].items():
            if d["failures"]:
                out.append(
                    f"`{name}`: {part} çağrılarının {d['failures']}/{d['calls']} tanesi başarısız "
                    f"oldu (son hata: {d['last_error'] or '-'}); bu yöntemin sonucu kısmen vector sırasıdır."
                )
        if e["errors"]:
            out.append(f"`{name}`: {e['errors']} soru hata verdi ve 'bulunamadı' sayıldı ({e['error_samples']}).")
    return out


def severe_failure(results: dict[str, dict]) -> bool:
    """Herhangi bir yöntemde reranker/genişletici çağrılarının yarıdan fazlası başarısızsa True."""
    return any(
        d["calls"] and d["failures"] / d["calls"] > FAILURE_EXIT_RATIO
        for e in results.values()
        for d in e["diagnostics"].values()
    )


def build_report(
    results: dict[str, dict], n_queries: int, info: dict, now: datetime | None = None
) -> tuple[str, dict]:
    """(results.md metni, results.json nesnesi)."""
    now = now or datetime.now(UTC)
    rows, labels = {}, {}
    for name, e in results.items():
        rows[name] = dict(e["metrics"])
        labels[name] = e["label"]
        if e["latency"]:
            rows[name]["latency_mean"] = e["latency"]["mean"]
            rows[name]["latency_p95"] = e["latency"]["p95"]
    lines = [f"{n_queries} soru", "", format_table(rows, labels), "", "Notlar:"]
    lines += [
        (
            f"- Kalite {info['workers']} paralel iş parçacığıyla ölçüldü. Gecikme ayrıca "
            f"{info['latency_n']} soruda sırayla, her sorguda embedding/genişletme önbelleği "
            "boşaltılarak (soğuk) ölçüldü; chat'te göreceğin ek süre budur."
        ),
        (
            f"- Rerank: model `{info['rerank_model']}`, şablon `{info['rerank_template']}` "
            "(`-none`/`-qwen3` sonekli yöntemler şablonu zorlar), doküman başına en çok "
            f"{info['rerank_doc_chars']} karakter, zaman aşımı {info['rerank_timeout']:g} sn."
        ),
        (
            f"- Çoklu sorgu: model `{info['multiquery_model']}`, orijinal sorgu ağırlığı "
            f"{info['multiquery_original_weight']:g}."
        ),
    ]
    base = rows.get("vector")
    if base and "latency_mean" in base:
        for name, r in rows.items():
            if name not in ("vector", "bm25") and "latency_mean" in r:
                lines.append(
                    f"- `{name}` vector'e göre {r['latency_mean'] - base['latency_mean']:+.2f} sn "
                    f"(ort.), p95 {r['latency_p95'] - base['latency_p95']:+.2f} sn."
                )
    if base:
        best = max(rows, key=lambda x: rows[x]["mrr@10"])
        if best != "vector":
            b = rows[best]
            lines.append(
                f"- En yüksek MRR: {labels[best]} ({b['mrr@10']:.3f}); vector'e göre "
                f"recall@1 {b['recall@1'] - base['recall@1']:+.3f}, "
                f"recall@5 {b['recall@5'] - base['recall@5']:+.3f}, MRR {b['mrr@10'] - base['mrr@10']:+.3f}."
            )
        else:
            lines.append("- En yüksek MRR vector yönteminde; bu ayarlarla ek katmanlar fayda sağlamadı.")
    for warning in failure_warnings(results):
        lines.append(f"- **UYARI** {warning}")
    group_names = sorted({g for e in results.values() for g in e["groups"]})
    if len(group_names) > 1:
        lines += ["", "Kaynak/dil kırılımı (recall@1 / recall@5 / mrr@10):", ""]
        names = list(results)
        lines.append("| grup | soru | " + " | ".join(labels[n] for n in names) + " |")
        lines.append("|---|---|" + "---|" * len(names))
        for g in group_names:
            size = next(e["groups"][g]["n"] for e in results.values() if g in e["groups"])
            cells = []
            for n in names:
                gm = results[n]["groups"].get(g)
                cells.append(
                    f"{gm['recall@1']:.2f} / {gm['recall@5']:.2f} / {gm['mrr@10']:.2f}" if gm else "-"
                )
            lines.append(f"| {g} | {size} | " + " | ".join(cells) + " |")
    report = {
        "generated_at": now.isoformat(timespec="seconds"),
        "queries": n_queries,
        "settings": info,
        "methods": results,
    }
    return "\n".join(lines) + "\n", report


# --- Komutlar ---
def register(sub) -> None:
    gen = sub.add_parser("gen", help="Evren LLM ile değerlendirme sorularını üret")
    gen.add_argument("--n", type=int, default=500, help="üretilecek soru sayısı")
    gen.add_argument("--workers", type=int, default=16, help="paralel LLM isteği")
    gen.add_argument("--seed", type=int, default=42)
    gen.add_argument("--out", type=Path, default=QUERIES_PATH)
    gen.set_defaults(func=cmd_gen)

    run = sub.add_parser("run", help="arama yöntemlerini karşılaştır")
    run.add_argument(
        "--methods", default="all",
        help="virgülle: bm25,vector,hybrid,rerank20,rerank40,rerank40-none,mq-vector,mq-rerank "
        "(all = hybrid hariç hepsi)",
    )  # fmt: skip
    run.add_argument("--limit", type=int, default=0, help="sadece N soru (eşit aralıklı örnek); 0 = hepsi")
    run.add_argument("--workers", type=int, default=8, help="kalite ölçümünde paralel sorgu")
    run.add_argument("--latency-n", type=int, default=20, help="sıralı gecikme ölçümü soru sayısı; 0 = kapalı")
    run.add_argument("--queries", type=Path, default=QUERIES_PATH)
    run.add_argument("--out-md", type=Path, default=RESULTS_PATH)
    run.add_argument("--out-json", type=Path, default=RESULTS_JSON_PATH)
    run.add_argument("--rerank-timeout", type=float, default=60.0, help="saniye (ölçümde sahte geri düşüş olmasın)")
    run.add_argument("--rerank-template", choices=TEMPLATES, help="varsayılan: MEDRAG_RERANK_TEMPLATE")
    run.add_argument("--mq-timeout", type=float, default=60.0, help="çoklu sorgu genişletme süre sınırı (sn)")
    run.add_argument("--mq-original-weight", type=float, help="RRF'de orijinal sorgunun ağırlığı")
    run.set_defaults(func=cmd_run)


def cmd_gen(args) -> None:
    settings = get_settings()
    llm = EvrenLLM(settings.llm_api_url, settings.llm_model)
    chunks = load_chunks(settings.data_dir)
    rows = build_queries(
        chunks,
        args.n,
        lambda p: llm.complete([{"role": "user", "content": p}], temperature=0.7, max_tokens=200),
        workers=args.workers,
        seed=args.seed,
    )
    save_queries(args.out, rows)
    print(f"{len(rows)}/{args.n} soru üretildi -> {args.out}")
    groups: dict[str, int] = {}
    for r in rows:
        groups[query_group(r)] = groups.get(query_group(r), 0) + 1
    print("gruplar:", json.dumps(groups, ensure_ascii=False))
    for r in rows[:5]:
        print(" -", r["query"])


def apply_overrides(retriever: Retriever, args, settings: Settings) -> None:
    """Komut satırı seçeneklerini retriever'a uygular (ölçüm sırasında süre sınırları gevşektir)."""
    if retriever.reranker is not None:
        retriever.reranker.timeout = args.rerank_timeout
        if args.rerank_template:
            retriever.reranker.template = args.rerank_template
    retriever.multiquery_timeout = args.mq_timeout
    if args.mq_original_weight is not None:
        retriever.multiquery_original_weight = args.mq_original_weight


def settings_info(retriever: Retriever, settings: Settings, args) -> dict:
    reranker = retriever.reranker
    return {
        "workers": args.workers,
        "latency_n": args.latency_n,
        "embed_model": settings.embed_api_model,
        "rerank_model": settings.rerank_model,
        "rerank_template": getattr(reranker, "template", settings.rerank_template),
        "rerank_doc_chars": settings.rerank_doc_chars,
        "rerank_batch_size": settings.rerank_batch_size,
        "rerank_timeout": args.rerank_timeout,
        "multiquery_model": settings.multiquery_model,
        "multiquery_original_weight": retriever.multiquery_original_weight,
    }


def cmd_run(args) -> None:
    settings = get_settings()
    try:
        methods = parse_methods(args.methods, settings.rerank_pool)
        retriever = load_retriever(settings)
    except (ValueError, RuntimeError) as e:
        raise SystemExit(f"hata: {e}") from e
    apply_overrides(retriever, args, settings)
    queries = load_queries(args.queries)
    if args.limit > 0:
        queries = sample_evenly(queries, args.limit)
    print(f"{len(queries)} soru, {len(methods)} yöntem: {', '.join(m.name for m in methods)}", flush=True)
    results = run_methods(retriever, queries, methods, args.workers, args.latency_n)
    markdown, report = build_report(
        results, len(queries), settings_info(retriever, settings, args)
    )
    print(markdown)
    args.out_md.parent.mkdir(parents=True, exist_ok=True)
    args.out_md.write_text(markdown, encoding="utf-8")
    args.out_json.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if severe_failure(results):
        print("HATA: reranker/çoklu sorgu çağrılarının çoğu başarısız oldu; sonuçlar geçerli değil.")
        raise SystemExit(3)
