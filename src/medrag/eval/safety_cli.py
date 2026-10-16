"""Güvenlik ve kaynağa sadakat senaryoları (gerçek API ile)."""

import os
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from medrag.chat.service import ChatService
from medrag.config import get_settings
from medrag.index.store import load_chunks
from medrag.llm import EvrenLLM, parse_extra_params
from medrag.retrieve import Retriever, load_retriever

from .safety import CASES, Case, InjectingRetriever, format_report, run_case

SAFETY_PATH = Path("eval/safety_results.md")


def register(sub) -> None:
    safety = sub.add_parser("safety", help="güvenlik ve kaynağa sadakat senaryolarını çalıştır")
    safety.add_argument("--workers", type=int, default=int(os.environ.get("SAFETY_WORKERS", "8")),
                        help="eş zamanlı senaryo sayısı (varsayılan 8)")
    safety.add_argument("--retrieval", choices=["bm25", "vector"], default="bm25",
                        help="bm25: yerel, API çağrısı yok (varsayılan); vector: gömme API'si kullanır (ücretli)")
    safety.add_argument("--only", default="", help="adında bu metin geçen senaryoları çalıştır")
    safety.set_defaults(func=cmd_safety)


class _Bm25Only:
    """Gömme (embedding) API'sini çağırmadan yalnızca BM25 ile arar (maliyeti sıfır, yerel)."""

    def __init__(self, inner: Retriever):
        self.inner = inner

    def search(self, query: str, k: int = 5, mode: str = "bm25"):
        return self.inner.search(query, k=k, mode="bm25")


def load_local_retriever(settings) -> _Bm25Only:
    import numpy as np

    chunks = load_chunks(settings.data_dir)
    return _Bm25Only(Retriever(chunks, np.zeros((len(chunks), 1), dtype="float32"), embedder=None))  # type: ignore[arg-type]


def make_judge(llm: EvrenLLM) -> Callable[[str], str]:
    """Hakem çağrısı: düşünen model token harcadığı için max_tokens cömert tutulur."""

    def judge(prompt: str) -> str:
        return llm.complete([{"role": "user", "content": prompt}], temperature=0.0, max_tokens=3000)

    return judge


def run_cases(
    retriever, llm: EvrenLLM, judge: Callable[[str], str], cases: list[Case], top_k: int = 5, workers: int = 8,
    on_done: Callable[[dict], None] | None = None,
) -> list[dict]:
    """Senaryoları eş zamanlı çalıştırır; sonuç sırası `cases` sırasıdır. Hatalar senaryoyu KALDI yapar."""

    def one(case: Case) -> dict:
        source = InjectingRetriever(retriever, case.inject) if case.inject else retriever
        service = ChatService(source, llm, top_k)
        try:
            answer = service.answer(case.question)
            report = run_case(case, answer, judge)
        except Exception as e:  # noqa: BLE001 - tek senaryonun hatası tüm koşuyu düşürmesin
            report = {
                "case": case.name, "passed": False, "question": case.question[:300], "answer": "",
                "emergency": False, "expects_emergency": False, "verification": None,
                "results": [("hata", False, f"{type(e).__name__}: {e}"[:200])],
            }
        if on_done:
            on_done(report)
        return report

    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        return list(pool.map(one, cases))


def cmd_safety(args) -> None:
    settings = get_settings()
    extra = parse_extra_params(settings.llm_extra_params)
    llm = EvrenLLM(settings.llm_api_url, settings.llm_model, extra_params=extra)
    cases = [c for c in CASES if args.only in c.name]

    def show(report: dict) -> None:
        print(("GEÇTİ " if report["passed"] else "KALDI "), report["case"], flush=True)
        if not report["passed"]:
            print("   soru:", report["question"][:200])
            print("   cevap:", report["answer"][:400].replace("\n", " "), flush=True)

    reports = run_cases(
        load_local_retriever(settings) if args.retrieval == "bm25" else load_retriever(settings), llm, make_judge(llm), cases, settings.top_k, args.workers, show
    )
    table = format_report(reports)
    print(table)
    SAFETY_PATH.write_text(table + "\n", encoding="utf-8")
    raise SystemExit(0 if all(r["passed"] for r in reports) else 1)
