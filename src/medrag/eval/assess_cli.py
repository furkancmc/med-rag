"""Belirti değerlendirme senaryoları (gerçek API ile): simüle hasta soruları gizli tanıma göre cevaplar."""

import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from medrag.assess.models import LEVEL_ORDER, Answer, FinishRequest, Profile, StartRequest
from medrag.assess.service import AssessService
from medrag.config import get_settings
from medrag.llm import EvrenLLM
from medrag.retrieve import load_retriever

from .assess_cases import CASES, Case

OUT_PATH = Path("eval/assess_results.md")

PATIENT_PROMPT = """Sen bir hastasın. Gerçek durumun (gizli): {hidden}
Doktor/asistan sana bir soru soruyor. Sadece bu gerçek duruma uygun, kısa ve doğal şekilde cevap ver.
Gerçek durumda olmayan belirtiyi uydurma ("Hayır" de). Seçenekler verildiyse onlardan birini (çoklu ise
birkaçını ' | ' ile ayırarak) AYNEN yaz. Şiddet sorusu ise 1-10 arasında tek sayı yaz. Başka açıklama ekleme.
Soru: {question}
Seçenekler: {options}"""


class NoSourcesRetriever:
    """Embedding çağrısı yapmayan sahte arama: kaynak döndürmez."""

    def search(self, query: str, k: int = 5) -> list:
        return []


def register(sub) -> None:
    p = sub.add_parser("assess", help="belirti değerlendirme senaryolarını çalıştır")
    p.add_argument("--model", default=None, help="değerlendirme modeli (varsayılan: ayarlardaki assess_model)")
    p.add_argument("--concurrency", type=int, default=8)
    p.add_argument("--real-retriever", action="store_true", help="gerçek embedding ile kaynak ara (maliyetli)")
    p.add_argument("--out", default=str(OUT_PATH))
    p.set_defaults(func=cmd_assess)


def simulate_patient(llm: EvrenLLM, case: Case, q) -> str:
    prompt = PATIENT_PROMPT.format(
        hidden=case.hidden, question=q.text, options=" | ".join(q.options) if q.options else "(serbest cevap)"
    )
    try:
        return llm.complete([{"role": "user", "content": prompt}], temperature=0.2, max_tokens=1500)[:300]
    except RuntimeError:
        return "Bilmiyorum"


def run_case(service: AssessService, patient: EvrenLLM, case: Case) -> dict:
    t0 = time.time()
    row = {"name": case.name, "min": case.min_level, "max": case.max_level, "level": None, "error": None}
    try:
        start = service.start(StartRequest(complaint=case.complaint, **case.profile))
        if start.emergency:
            row.update(level="emergency", n_questions=0, note="kural: ilk adımda acil")
        else:
            answers = [
                Answer(id=q.id, question=q.text, answer=simulate_patient(patient, case, q)) for q in start.questions
            ]
            res = service.finish(
                FinishRequest(complaint=case.complaint, profile=Profile(**case.profile), answers=answers)
            )
            row.update(level=res.level, n_questions=len(start.questions), summary=res.summary[:160], sources=len(res.sources))
    except Exception as e:  # noqa: BLE001 - tek senaryo hatası tüm koşuyu düşürmesin
        row["error"] = f"{type(e).__name__}: {str(e)[:100]}"
    row["seconds"] = round(time.time() - t0, 1)
    return row


def verdict(row: dict) -> str:
    if row["level"] is None:
        return "HATA"
    lv = LEVEL_ORDER[row["level"]]
    if lv < LEVEL_ORDER[row["min"]]:
        return "AŞAĞI"
    if lv > LEVEL_ORDER[row["max"]]:
        return "AŞIRI"
    return "ok"


def format_report(rows: list[dict], model: str, stats: dict) -> str:
    under = [r for r in rows if r["verdict"] == "AŞAĞI"]
    over = [r for r in rows if r["verdict"] == "AŞIRI"]
    calls = stats["json_calls"] or 1
    valid_first = stats["json_valid_first"] / calls
    valid_any = (stats["json_valid_first"] + stats["json_repaired"]) / calls
    avg = sum(r["seconds"] for r in rows) / len(rows)
    lines = [
        f"# Belirti değerlendirme sonuçları (model: {model})",
        "",
        (
            f"- Senaryo: {len(rows)}; uygun: {sum(r['verdict'] == 'ok' for r in rows)}; "
            f"aşağı triyaj: {len(under)}; aşırı triyaj: {len(over)}; hata: {sum(r['verdict'] == 'HATA' for r in rows)}"
        ),
        f"- Sonuç JSON geçerlilik: ilk denemede {valid_first:.0%}, onarımla {valid_any:.0%} ({stats['json_calls']} çağrı)",
        f"- Ortalama gecikme: {avg:.1f} sn/senaryo (soru + sonuç + simüle hasta)",
        "",
        "| Senaryo | Beklenen | Sonuç | Durum | Soru | sn |",
        "|---|---|---|---|---|---|",
    ]
    for r in rows:
        exp = r["min"] if r["min"] == r["max"] else f"{r['min']}..{r['max']}"
        lines.append(
            f"| {r['name']} | {exp} | {r['level'] or r['error']} | {r['verdict']} | {r.get('n_questions', '-')} | {r['seconds']} |"
        )
    return "\n".join(lines)


def cmd_assess(args) -> None:
    settings = get_settings()
    model = args.model or settings.assess_model
    llm = EvrenLLM(settings.llm_api_url, model)
    patient = EvrenLLM(settings.llm_api_url, model)
    # Embedding maliyeti nedeniyle varsayılan: kaynaksız (sahte) arama; --real-retriever ile gerçek indeks.
    retriever = load_retriever(settings) if args.real_retriever else NoSourcesRetriever()
    service = AssessService(
        retriever, llm, settings.assess_temperature, settings.assess_max_tokens, settings.assess_sources_k
    )
    with ThreadPoolExecutor(max_workers=args.concurrency) as pool:
        rows = list(pool.map(lambda c: run_case(service, patient, c), CASES))
    for r in rows:
        r["verdict"] = verdict(r)
        print(f"{r['verdict']:6} {r['name']}: {r['level'] or r['error']} (beklenen {r['min']}..{r['max']})")
        if r["verdict"] != "ok":
            print("   özet:", r.get("summary", ""))
    report = format_report(rows, model, service.stats)
    print(report)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(report + "\n", encoding="utf-8")
    bad = [r for r in rows if r["verdict"] == "AŞAĞI" and r["min"] == "emergency"]
    raise SystemExit(1 if bad else 0)
