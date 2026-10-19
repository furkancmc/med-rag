"""Çoklu sorgu (LLM sorgu genişletme) ölçümü: queries_v2 belge düzeyinde etiketleriyle vektör vs çoklu sorgu.

Kullanım: python scripts/multiquery_study.py eval/results_v2_multiquery.md [--limit N] [--workers 3]
"""

import argparse
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from rerank_study import KS, load_labels, mean, metrics

from medrag.config import Settings
from medrag.retrieve import load_retriever


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("out")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--workers", type=int, default=3)
    args = ap.parse_args()
    queries = [q for q in load_labels() if not q["oos"] and q["rel_docs"]]
    if args.limit:
        step = max(1, len(queries) // args.limit)
        queries = queries[::step][: args.limit]
    retr = load_retriever(Settings())

    def run(q: dict) -> dict:
        row = {"lang": q["lang"], "source": q["source"]}
        for name, mq in (("vektör", False), ("çoklu sorgu", True)):
            hits = retr.search(q["query"], k=10, mode="vector", rerank=False, multiquery=mq)
            row[name] = metrics([h.chunk for h in hits], q)
        return row

    with ThreadPoolExecutor(args.workers) as pool:
        rows = list(pool.map(run, queries))
    cols = [f"doc@{k}" for k in KS] + ["mrr", "ndcg@5"]
    lines = [
        "# Çoklu sorgu çalışması (queries_v2)", "",
        f"{len(rows)} soru (eşit aralıklı örnek). Genişletici: `deepseek-v4.1-flash`; RRF birleştirme. Metrikler `rerank_study.py` ile aynı.", "",
        "| yöntem | " + " | ".join(cols) + " |", "|---|" + "---|" * len(cols),
    ]
    for name in ("vektör", "çoklu sorgu"):
        lines.append(f"| {name} | " + " | ".join(f"{mean([r[name] for r in rows], c):.3f}" for c in cols) + " |")
    groups = defaultdict(list)
    for r in rows:
        groups[(r["source"], r["lang"])].append(r)
    lines += ["", "## Kaynak/dil kırılımı (doc@1 / doc@5)", "", "| grup | soru | vektör | çoklu sorgu |", "|---|---|---|---|"]
    for g, rs in sorted(groups.items()):
        cells = [f"{mean([r[n] for r in rs], 'doc@1'):.2f} / {mean([r[n] for r in rs], 'doc@5'):.2f}" for n in ("vektör", "çoklu sorgu")]
        lines.append(f"| {g[0]}/{g[1]} | {len(rs)} | " + " | ".join(cells) + " |")
    Path(args.out).write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
