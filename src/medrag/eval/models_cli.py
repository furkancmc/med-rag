"""Sohbet modellerini karşılaştırır: güvenlik başarısı, kaynağa sadakat, Türkçe kalitesi, gecikme.

Not: Her aday model için tüm güvenlik senaryoları çalışır; varsayılan aday listesi bilinçli olarak
yalnızca `deepseek-v4.1-flash`tır (maliyet). Diğer adaylar `--models` ile verilir.
"""

import statistics
from pathlib import Path

from medrag.config import get_settings
from medrag.llm import EvrenLLM, parse_extra_params

from .safety import CASES, JUDGE_PROMPT, VERDICT
from .safety_cli import load_local_retriever, make_judge, run_cases

OUT_PATH = Path("eval/model_comparison.md")
KNOWN = ["auto", "deepseek-v4-flash", "deepseek-v4.1-flash", "glm-5.3", "qwen3.8-flash-next", "mimo-v2.6-pro"]
TURKISH_RUBRIC = (
    "Cevap akıcı, doğal ve dilbilgisi açısından doğru Türkçe ile yazılmış mı (anlamsız çeviri kokan "
    "ifadeler, yabancı dil karışması ya da bozuk cümleler yok mu)?"
)


def register(sub) -> None:
    p = sub.add_parser("models", help="sohbet modellerini güvenlik, sadakat, Türkçe ve gecikme açısından karşılaştır")
    p.add_argument("--models", default="deepseek-v4.1-flash", help=f"virgülle ayrılmış model adları (örn. {','.join(KNOWN)})")
    p.add_argument("--judge-model", default="deepseek-v4.1-flash", help="hakem model")
    p.add_argument("--workers", type=int, default=8)
    p.set_defaults(func=cmd_models)


def p95(values: list[float]) -> float:
    if not values:
        return float("nan")
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(0.95 * len(ordered)))]


def turkish_score(report: dict, judge) -> bool | None:
    if not report.get("answer"):
        return None
    prompt = JUDGE_PROMPT.format(rubric=TURKISH_RUBRIC, question=report["question"][:500], answer=report["answer"], sources="")
    verdicts = VERDICT.findall(judge(prompt))
    return verdicts[-1].upper() == "EVET" if verdicts else None


def summarize(model: str, reports: list[dict], judge) -> dict:
    faith = [ok for r in reports for name, ok, _ in r["results"] if name == "faithful"]
    turkish = [t for t in (turkish_score(r, judge) for r in reports) if t is not None]
    first = [r["first_token_s"] for r in reports if r.get("first_token_s") is not None]
    total = [r["total_s"] for r in reports if r.get("total_s") is not None]
    return {
        "model": model,
        "safety": f"{sum(r['passed'] for r in reports)}/{len(reports)}",
        "faithful": f"{sum(faith)}/{len(faith)}",
        "turkish": f"{sum(turkish)}/{len(turkish)}",
        "first_mean": statistics.fmean(first) if first else float("nan"),
        "first_p95": p95(first),
        "total_mean": statistics.fmean(total) if total else float("nan"),
        "total_p95": p95(total),
    }


def format_models(rows: list[dict]) -> str:
    lines = [
        "| model | güvenlik | sadakat | Türkçe | ilk token ort/p95 (s) | toplam ort/p95 (s) |",
        "|---|---|---|---|---|---|",
    ]
    for r in rows:
        lines.append(
            f"| {r['model']} | {r['safety']} | {r['faithful']} | {r['turkish']} | "
            f"{r['first_mean']:.1f} / {r['first_p95']:.1f} | {r['total_mean']:.1f} / {r['total_p95']:.1f} |"
        )
    return "\n".join(lines)


def cmd_models(args) -> None:
    settings = get_settings()
    base = EvrenLLM(settings.llm_api_url, args.judge_model, extra_params=parse_extra_params(settings.verify_extra_params))
    judge = make_judge(base)
    retriever = load_local_retriever(settings)
    rows = []
    for model in [m.strip() for m in args.models.split(",") if m.strip()]:
        llm = EvrenLLM(settings.llm_api_url, model, extra_params=parse_extra_params(settings.llm_extra_params))
        print(f"== {model}", flush=True)
        reports = run_cases(retriever, llm, judge, CASES, settings.top_k, args.workers)
        rows.append(summarize(model, reports, judge))
        print(format_models(rows[-1:]), flush=True)
    text = "# Model karşılaştırması\n\n" + format_models(rows) + (
        f"\n\nHakem: {args.judge_model}. Arama: yerel BM25. Senaryo sayısı: {len(CASES)}.\n"
    )
    OUT_PATH.write_text(text, encoding="utf-8")
    print(text)
