"""Reranker çalışması (queries_v2, belge düzeyinde hakem etiketli): havuz boyutu, metin uzunluğu, dil/kaynak kırılımı, gecikme.

Her soru için vektör aramayla ilk 40 aday bir kez alınır; her `doc_chars` ayarı için 40 adayın hepsi puanlanır.
Havuz P < 40 varyantları, aynı puanlardan ilk P adayla türetilir (kesin eşdeğer, ek maliyet yok).

Kullanım: python scripts/rerank_study.py eval/results_v2_rerank.md [--limit N]
"""

import argparse
import json
import math
import time
from collections import defaultdict
from pathlib import Path

import numpy as np

from medrag.config import Settings
from medrag.rerank import format_document
from medrag.rerank_local import LocalReranker
from medrag.retrieve import load_retriever

KS = (1, 3, 5)
POOLS = (8, 10, 15, 20, 40)
CHARS = (600, 1000, 1500)


def load_labels() -> list[dict]:
    """Etiketler repoda: eval/queries_v2.jsonl (hakem çıktısı)."""
    out = []
    for line in Path("eval/queries_v2.jsonl").read_text(encoding="utf-8").splitlines():
        q = json.loads(line)
        q["rel_chunks"] = set(q["relevant_chunks"])
        q["rel_docs"] = set(q["relevant_docs"])
        out.append(q)
    return out


def doc_ranking(chunks: list[dict]) -> list[str]:
    seen, docs = set(), []
    for c in chunks:
        if c["doc_id"] not in seen:
            seen.add(c["doc_id"])
            docs.append(c["doc_id"])
    return docs


def metrics(rank_chunks: list[dict], q: dict) -> dict:
    docs = doc_ranking(rank_chunks)
    m = {}
    for k in KS:
        m[f"doc@{k}"] = float(any(d in q["rel_docs"] for d in docs[:k]))
        m[f"chunk@{k}"] = float(any(c["id"] in q["rel_chunks"] for c in rank_chunks[:k]))
    rr = next((1 / (i + 1) for i, d in enumerate(docs[:10]) if d in q["rel_docs"]), 0.0)
    m["mrr"] = rr
    gains = [1.0 if d in q["rel_docs"] else 0.0 for d in docs[:5]]
    dcg = sum(g / math.log2(i + 2) for i, g in enumerate(gains))
    ideal = sum(1 / math.log2(i + 2) for i in range(min(len(q["rel_docs"]), 5)))
    m["ndcg@5"] = dcg / ideal if ideal else 0.0
    return m


def mean(rows: list[dict], key: str) -> float:
    return sum(r[key] for r in rows) / len(rows) if rows else 0.0


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("out")
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()
    queries = [q for q in load_labels() if not q["oos"] and q["rel_docs"]]
    if args.limit:
        queries = queries[: args.limit]
    print("değerlendirilen soru:", len(queries))
    retr = load_retriever(Settings())
    rer = LocalReranker(doc_chars=1500)
    cand_lists = []
    for q in queries:
        hits = retr.search(q["query"], k=40, rerank=False, multiquery=False, mode="vector")
        cand_lists.append([h.chunk for h in hits])
    results: dict[str, list[dict]] = defaultdict(list)  # yöntem -> soru başına metrikler
    scores_by_chars: dict[int, list[list[float]]] = {}
    for chars in CHARS:
        t = time.time()
        allscores = []
        for q, cands in zip(queries, cand_lists):
            allscores.append(rer.score_texts(q["query"], [format_document(c, chars) for c in cands]))
        scores_by_chars[chars] = allscores
        print(f"puanlandı doc_chars={chars}: {time.time() - t:.0f} sn")
    for qi, q in enumerate(queries):
        base = cand_lists[qi]
        results["vektör"].append({**metrics(base, q), "lang": q["lang"], "source": q["source"]})
        for chars in CHARS:
            for pool in POOLS:
                sc = scores_by_chars[chars][qi][:pool]
                order = np.argsort(-np.array(sc), kind="stable")
                ranked = [base[j] for j in order] + base[pool:]
                results[f"rerank havuz {pool}, {chars} karakter"].append(
                    {**metrics(ranked, q), "lang": q["lang"], "source": q["source"]}
                )
    # Gecikme: sıralı, ısınmış model; GPU ve CPU
    lat_q = [(q, c) for q, c in zip(queries[:25], cand_lists[:25])]
    lat_lines = []
    for device in ("cuda", "cpu"):
        r2 = LocalReranker(doc_chars=1000, device=device)
        r2.score_texts("ısınma", ["ısınma metni"])
        for pool in (8, 15, 40):
            ts = []
            for q, cands in lat_q:
                t = time.time()
                r2.score_texts(q["query"], [format_document(c, 1000) for c in cands[:pool]])
                ts.append(time.time() - t)
            lat_lines.append(f"| {device} | {pool} | {np.median(ts) * 1000:.0f} | {np.percentile(ts, 95) * 1000:.0f} |")
        del r2
    cols = [f"doc@{k}" for k in KS] + ["mrr", "ndcg@5"] + [f"chunk@{k}" for k in (1, 5)]
    lines = [
        "# Reranker çalışması (queries_v2, belge düzeyinde hakem etiketli)", "",
        f"{len(queries)} soru. Etiket: `deepseek-v4.1-flash` hakemi, vektör+BM25 adayları arasından 'soruyu doğrudan cevaplayan' parçaları işaretledi. "
        "`doc@k`: ilk k BELGEDE en az bir ilgili belge var; `chunk@k`: ilk k parçada hakemin işaretlediği bir parça var. "
        "Reranker: `BAAI/bge-reranker-v2-m3` (yerel). Aday havuzu vektör aramasının ilk P'si.", "",
        "| yöntem | " + " | ".join(cols) + " |", "|---|" + "---|" * len(cols),
    ]
    for name, rows in results.items():
        lines.append(f"| {name} | " + " | ".join(f"{mean(rows, c):.3f}" for c in cols) + " |")
    lines += ["", "## Dil/kaynak kırılımı (doc@1 / doc@5 / mrr)", ""]
    groups = sorted({(r["source"], r["lang"]) for r in results["vektör"]})
    pick = ["vektör", "rerank havuz 15, 1000 karakter", "rerank havuz 40, 1500 karakter"]
    lines += ["| grup | soru | " + " | ".join(pick) + " |", "|---|---|" + "---|" * len(pick)]
    for g in groups:
        cells = []
        for name in pick:
            sub = [r for r in results[name] if (r["source"], r["lang"]) == g]
            cells.append(f"{mean(sub, 'doc@1'):.2f} / {mean(sub, 'doc@5'):.2f} / {mean(sub, 'mrr'):.2f}")
        n = sum(1 for r in results["vektör"] if (r["source"], r["lang"]) == g)
        lines.append(f"| {g[0]}/{g[1]} | {n} | " + " | ".join(cells) + " |")
    lines += ["", "## Gecikme (25 soru, tek tek, ısınmış model, 1000 karakter)", "", "| cihaz | havuz | medyan ms | p95 ms |", "|---|---|---|---|", *lat_lines]
    Path(args.out).write_text("\n".join(lines) + "\n", encoding="utf-8")
    (Path(args.out).with_suffix(".json")).write_text(
        json.dumps({k: {c: mean(v, c) for c in cols} for k, v in results.items()}, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    print("\n".join(lines))


if __name__ == "__main__":
    main()
