"""OCR ölçümü: scripts/ocr_set.py çıktısını VisionService ile okutur, manifest ile karşılaştırır.

Kullanım: python scripts/ocr_eval.py scratch/ocr eval/ocr_real_results.md \
    --report-models ocr:deepseek-ocr-2,ocr:dots-ocr,chat:qwen3-vl-30b,chat:gemma-4-31b \
    --box-models qwen3-vl-30b,gemma-4-31b [--limit N]
`ocr:<model>`: OCR modeli + metin çıkarımı; `chat:<model>`: görsel sohbet modeli metni okur, aynı çıkarım.
"""

import argparse
import json
import os
import re
import time
import unicodedata
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from medrag.config import Settings
from medrag.labs.interpret import parse_value
from medrag.llm import EvrenLLM, parse_extra_params
from medrag.vision import VisionClient, VisionError, VisionService


def load_env() -> None:
    for line in Path(".env").read_text(encoding="utf-8").splitlines():
        if "=" in line and not line.startswith("#"):
            k, v = line.strip().split("=", 1)
            os.environ.setdefault(k, v)


def service(kind: str, model: str) -> VisionService:
    s = Settings()
    extractor = EvrenLLM(
        s.vision_api_url, s.vision_extract_model, extra_params=parse_extra_params(s.vision_extract_extra_params)
    )
    client = VisionClient(s.vision_api_url)
    if kind == "ocr":
        svc = VisionService(client, extractor, [model], "-")
    else:
        svc = VisionService(client, extractor, [], model)
    return svc


def norm(text: str) -> str:
    text = unicodedata.normalize("NFKD", (text or "").lower().replace("ı", "i"))
    return re.sub(r"[^a-z0-9%]+", " ", "".join(c for c in text if not unicodedata.combining(c))).strip()


def unit_eq(a: str | None, b: str) -> bool:
    fix = lambda x: (x or "").lower().replace("µ", "u").replace(" ", "")
    return fix(a) == fix(b)


def score_report(truth: list[dict], rows: list[dict]) -> dict:
    by_id: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        if r.get("test_id"):
            by_id[r["test_id"]].append(r)
    ok_v = ok_u = missed = 0
    for t in truth:
        cands = by_id.get(t["test_id"], [])
        if not cands:
            missed += 1
            continue
        want = parse_value(t["value"])[0]
        hit = next((c for c in cands if _safe_val(c["value"]) == want), None)
        ok_v += hit is not None
        ok_u += bool(hit and unit_eq(hit.get("unit"), t["unit"]))
    truth_vals = {(t["test_id"], parse_value(t["value"])[0]) for t in truth}
    invented = sum(1 for r in rows if r.get("test_id") and (r["test_id"], _safe_val(r["value"])) not in truth_vals)
    return {"n": len(truth), "value_ok": ok_v, "unit_ok": ok_u, "missed": missed, "invented": invented}


def _safe_val(v: str) -> float | None:
    try:
        return parse_value(v)[0]
    except ValueError:
        return None


def score_box(truth: dict, got: dict) -> dict:
    brand = norm(got.get("brand_name") or "") == norm(truth["brand"])
    want_tokens = set(norm(truth["active"]).split()) - {"ve", "klorur", "hidroklorur", "sodyum"}
    got_tokens = set(norm(" ".join(got.get("active_ingredients") or [])).split())
    active = bool(want_tokens) and want_tokens <= got_tokens
    strength = norm(got.get("strength") or "").replace(" ", "").startswith(norm(truth["strength"]).replace(" ", ""))
    return {"brand": brand, "active": active, "strength": strength}


def run_report(item: dict, kind: str, model: str, root: Path) -> dict:
    svc = service(kind, model)
    t = time.time()
    try:
        res = svc.lab_report((root / item["file"]).read_bytes())
        sc = score_report(item["rows"], res["rows"])
    except (VisionError, Exception) as e:  # noqa: BLE001 - tek görselin hatası ölçümü durdurmasın
        sc = {"n": len(item["rows"]), "value_ok": 0, "unit_ok": 0, "missed": len(item["rows"]), "invented": 0, "error": str(e)[:120]}
    sc.update(file=item["file"], level=item["level"], layout=item["layout"], seconds=round(time.time() - t, 1))
    return sc


def run_box(item: dict, model: str, root: Path) -> dict:
    svc = service("chat", model)
    t = time.time()
    try:
        got = svc.medicine((root / item["file"]).read_bytes())
        sc = score_box(item["truth"], got)
    except Exception as e:  # noqa: BLE001
        sc = {"brand": False, "active": False, "strength": False, "error": str(e)[:120]}
    sc.update(file=item["file"], level=item["level"], seconds=round(time.time() - t, 1))
    return sc


def pct(a: int, b: int) -> str:
    return f"{100 * a / b:.0f}%" if b else "-"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("root")
    ap.add_argument("out")
    ap.add_argument("--report-models", default="ocr:deepseek-ocr-2,ocr:dots-ocr,chat:qwen3-vl-30b,chat:gemma-4-31b")
    ap.add_argument("--box-models", default="qwen3-vl-30b,gemma-4-31b")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--workers", type=int, default=4)
    args = ap.parse_args()
    load_env()
    root = Path(args.root)
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    reports = [m for m in manifest if m["kind"] == "report"]
    boxes = [m for m in manifest if m["kind"] == "box"]
    if args.limit:
        reports, boxes = reports[: args.limit], boxes[: args.limit]
    raw: dict[str, list[dict]] = {}
    lines = ["# OCR ölçümü: bozulmuş (telefon fotoğrafı taklidi) görseller", ""]
    lines += [
        f"{len(reports)} tahlil raporu (4 düzen) ve {len(boxes)} ilaç kutusu; her görsele hafif/orta/ağır düzeyde 1-4 bozulma "
        "(perspektif, gölge, parlama, buruşma, bulanıklık, düşük ışık, kırpma) + JPEG sıkıştırma uygulandı. "
        "Sentetik görsellerdir; gerçek fotoğraf doğruluğu bunun altında olabilir.",
        "", "## Tahlil raporu", "",
        "| Model | Düzey | Görsel | Değer doğru | Birim doğru | Kaçan satır | Uydurma satır | Ort. süre (sn) |", "|---|---|---|---|---|---|---|---|",
    ]
    for spec in args.report_models.split(","):
        kind, model = spec.split(":")
        with ThreadPoolExecutor(args.workers) as pool:
            res = list(pool.map(lambda it: run_report(it, kind, model, root), reports))
        raw[spec] = res
        for level in ("hafif", "orta", "ağır", "tümü"):
            sub = [r for r in res if level == "tümü" or r["level"] == level]
            n = sum(r["n"] for r in sub)
            lines.append(
                f"| {spec} | {level} | {len(sub)} | {pct(sum(r['value_ok'] for r in sub), n)} | {pct(sum(r['unit_ok'] for r in sub), n)} | "
                f"{sum(r['missed'] for r in sub)} | {sum(r['invented'] for r in sub)} | {sum(r['seconds'] for r in sub) / max(1, len(sub)):.1f} |"
            )
        print(lines[-1])
    lines += ["", "## İlaç kutusu", "", "| Model | Düzey | Görsel | Marka | Etken madde | Güç | Ort. süre (sn) |", "|---|---|---|---|---|---|---|"]
    for model in args.box_models.split(","):
        with ThreadPoolExecutor(args.workers) as pool:
            res = list(pool.map(lambda it: run_box(it, model, root), boxes))
        raw[f"box:{model}"] = res
        for level in ("hafif", "orta", "ağır", "tümü"):
            sub = [r for r in res if level == "tümü" or r["level"] == level]
            lines.append(
                f"| {model} | {level} | {len(sub)} | {pct(sum(r['brand'] for r in sub), len(sub))} | {pct(sum(r['active'] for r in sub), len(sub))} | "
                f"{pct(sum(r['strength'] for r in sub), len(sub))} | {sum(r['seconds'] for r in sub) / max(1, len(sub)):.1f} |"
            )
        print(lines[-1])
    errs = sum(1 for v in raw.values() for r in v if r.get("error"))
    lines += ["", f"İstek hatası olan görsel sayısı (toplam): {errs}. Ayrıntı: `scratch/ocr/results.json` (repoya alınmaz)."]
    (root / "results.json").write_text(json.dumps(raw, ensure_ascii=False, indent=1), encoding="utf-8")
    Path(args.out).write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"yazıldı: {args.out}")


if __name__ == "__main__":
    main()
