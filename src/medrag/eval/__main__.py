import argparse
from pathlib import Path

from medrag.chat.service import ChatService
from medrag.config import get_settings
from medrag.index.embed import CachingEmbedder
from medrag.index.store import load_chunks
from medrag.llm import EvrenLLM
from medrag.retrieve import load_retriever

from .metrics import evaluate, format_table
from .queries import generate_queries, load_queries, sample_chunks, save_queries
from .safety import CASES, format_report, run_case

QUERIES_PATH = Path("eval/queries.jsonl")
RESULTS_PATH = Path("eval/results.md")
SAFETY_PATH = Path("eval/safety_results.md")


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m medrag.eval")
    sub = parser.add_subparsers(dest="cmd", required=True)
    gen = sub.add_parser("gen", help="Evren LLM ile değerlendirme sorularını üret")
    gen.add_argument("--n", type=int, default=150)
    sub.add_parser("run", help="bm25 / vector / hybrid yöntemlerini karşılaştır")
    sub.add_parser("safety", help="güvenlik ve kaynağa sadakat senaryolarını çalıştır")
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
    elif args.cmd == "safety":
        llm = EvrenLLM(settings.llm_api_url, settings.llm_model)
        service = ChatService(load_retriever(settings), llm, settings.top_k)

        def judge(prompt: str) -> str:
            return llm.complete([{"role": "user", "content": prompt}], temperature=0.0, max_tokens=800)

        reports = []
        for case in CASES:
            answer = service.answer(case.question)
            report = run_case(case, answer, judge)
            reports.append(report)
            print(("GEÇTİ " if report["passed"] else "KALDI "), case.name)
            if not report["passed"]:
                print("   soru:", case.question)
                print("   cevap:", answer["text"][:400].replace("\n", " "))
        table = format_report(reports)
        print(table)
        SAFETY_PATH.write_text(table + "\n", encoding="utf-8")
        raise SystemExit(0 if all(r["passed"] for r in reports) else 1)
    else:
        retriever = load_retriever(settings)
        retriever.embedder = CachingEmbedder(retriever.embedder)
        queries = load_queries(QUERIES_PATH)
        results = {}
        runs = [("bm25", "bm25", 0.0), ("vector", "vector", 0.0)]
        runs += [(f"hybrid (bm25 ağırlığı {w})", "hybrid", w) for w in (0.05, 0.1, 0.2, 0.3, 0.5, 1.0)]
        for name, mode, weight in runs:
            results[name] = evaluate(
                queries,
                lambda q, m=mode, w=weight: [
                    h.chunk for h in retriever.search(q, k=10, mode=m, bm25_weight=w)
                ],
            )
        table = format_table(results)
        print(table)
        RESULTS_PATH.write_text(f"{len(queries)} soru\n\n{table}\n", encoding="utf-8")


if __name__ == "__main__":
    main()
