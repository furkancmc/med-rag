"""Güvenlik ve kaynağa sadakat senaryoları (gerçek API ile)."""

from pathlib import Path

from medrag.chat.service import ChatService
from medrag.config import get_settings
from medrag.llm import EvrenLLM
from medrag.retrieve import load_retriever

from .safety import CASES, format_report, run_case

SAFETY_PATH = Path("eval/safety_results.md")


def register(sub) -> None:
    safety = sub.add_parser("safety", help="güvenlik ve kaynağa sadakat senaryolarını çalıştır")
    safety.set_defaults(func=cmd_safety)


def cmd_safety(args) -> None:
    settings = get_settings()
    llm = EvrenLLM(settings.llm_api_url, settings.llm_model)
    service = ChatService(load_retriever(settings), llm, settings.top_k)

    def judge(prompt: str) -> str:
        return llm.complete(
            [{"role": "user", "content": prompt}], temperature=0.0, max_tokens=800
        )

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
