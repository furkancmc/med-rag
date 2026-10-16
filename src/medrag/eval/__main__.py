import argparse
from pathlib import Path

from medrag.config import get_settings
from medrag.index.embed import CachingEmbedder
from medrag.index.store import load_chunks
from medrag.llm import EvrenLLM
from medrag.retrieve import load_retriever

from .metrics import evaluate, format_table
from .queries import generate_queries, load_queries, sample_chunks, save_queries

QUERIES_PATH = Path("eval/queries.jsonl")
RESULTS_PATH = Path("eval/results.md")


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m medrag.eval")
    sub = parser.add_subparsers(dest="cmd", required=True)
    gen = sub.add_parser("gen", help="Evren LLM ile değerlendirme sorularını üret")
    gen.add_argument("--n", type=int, default=150)
    sub.add_parser("run", help="bm25 / vector / hybrid yöntemlerini karşılaştır")
    args = parser.parse_args()
    settings = get_settings()

    if args.cmd == "gen":
        llm = EvrenLLM(settings.llm_api_url, settings.llm_model)
        sample = sample_chunks(load_chunks(settings.data_dir), args.n)
        rows = generate_queries(
            sample, lambda p: llm.complete([{"role": "user", "content": p}], temperature=0.7, max_tokens=120)
        )
        save_queries(QUERIES_PATH, rows)
        print(f"{len(rows)}/{len(sample)} soru üretildi -> {QUERIES_PATH}")
        for r in rows[:5]:
            print(" -", r["query"])
    else:
        retriever = load_retriever(settings)
        retriever.embedder = CachingEmbedder(retriever.embedder)
        queries = load_queries(QUERIES_PATH)
        results = {}
        for mode in ("bm25", "vector", "hybrid"):
            results[mode] = evaluate(
                queries, lambda q, m=mode: [h.chunk for h in retriever.search(q, k=10, mode=m)]
            )
        table = format_table(results)
        print(table)
        RESULTS_PATH.write_text(f"{len(queries)} soru\n\n{table}\n", encoding="utf-8")


if __name__ == "__main__":
    main()
