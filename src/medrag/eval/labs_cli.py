"""Tahlil yorumu ve görsel okuma değerlendirmesi.

  python -m medrag.eval labs-sanity            # kural tabanlı yorum (API gerekmez)
  python -m medrag.eval labs-ocr               # sentetik rapor görselleri: OCR modelleri + çıkarım doğruluğu
  python -m medrag.eval labs-raw               # ham model çıktıları (hata ayıklama)

`labs-ocr` ve `labs-raw` gerçek API çağırır (EVREN_API_KEY) ve Pillow ister (iş akışında kurulur).
"""

import io
import random
import time
from pathlib import Path

from medrag.labs.interpret import interpret_value, match_test, parse_value

SANITY = [  # (test, değer, birim, cinsiyet, beklenen durum)
    ("Hemoglobin", "11,2", "g/dL", "female", "low"),
    ("Hemoglobin", "12,5", "g/dL", "male", "low"),
    ("Glukoz", "5,4", "mmol/L", None, "normal"),
    ("Glukoz", "126", "mg/dL", None, "high"),
    ("LDL Kolesterol", "162", "mg/dL", None, "high"),
    ("HDL", "38", "mg/dL", "male", "low"),
    ("TSH", "5,6", "mIU/L", None, "high"),
    ("Potasyum", "6,9", "mmol/L", None, "critical"),
    ("Sodyum", "118", "mmol/L", None, "critical"),
    ("Kreatinin", "88,4", "µmol/L", "male", "normal"),
    ("Ferritin", "8", "ng/mL", "female", "low"),
    ("Lökosit", "7500", "/mm3", None, "normal"),
    ("HbA1c", "48", "mmol/mol", None, "high"),
    ("Glukoz", "108", "bilinmeyen", None, "unknown"),
]

# Sentetik rapor için (test adı, değer, birim, referans metni)
REPORT_ROWS = [
    ("Hemoglobin", "11,2", "g/dL", "12.0 - 16.0"),
    ("Hematokrit", "34,5", "%", "36 - 46"),
    ("Lökosit", "7,8", "10^3/uL", "4.5 - 11.0"),
    ("Trombosit", "245", "10^3/uL", "150 - 450"),
    ("Glukoz (Açlık)", "108", "mg/dL", "70 - 100"),
    ("Total Kolesterol", "212", "mg/dL", "< 200"),
    ("LDL Kolesterol", "141", "mg/dL", "< 130"),
    ("Kreatinin", "0,8", "mg/dL", "0.5 - 0.9"),
    ("ALT", "22", "U/L", "< 35"),
    ("TSH", "5,6", "mIU/L", "0.4 - 4.0"),
    ("Ferritin", "8", "ng/mL", "15 - 150"),
    ("D Vitamini", "14", "ng/mL", "30 - 100"),
]
FONTS = ["C:/Windows/Fonts/arial.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
         "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf"]


def _font(size: int):
    from PIL import ImageFont

    for f in FONTS:
        if Path(f).exists():
            return ImageFont.truetype(f, size)
    return ImageFont.load_default()


def make_report(variant: str = "clean") -> bytes:
    """Gerçekçi bir tahlil tablosu çizer. variant: clean | rotated | noisy."""
    from PIL import Image, ImageDraw, ImageFilter

    font = _font(26)
    img = Image.new("RGB", (1000, 120 + 56 * (len(REPORT_ROWS) + 1)), "white")
    d = ImageDraw.Draw(img)
    d.text((24, 20), "ÖRNEK LABORATUVARI - Biyokimya / Hemogram", fill="black", font=font)
    d.text((24, 60), "Hasta: Deneme Hasta    Tarih: 12.03.2026", fill="black", font=font)
    xs = (24, 360, 520, 680)
    for j, h in enumerate(("Test", "Sonuç", "Birim", "Referans")):
        d.text((xs[j], 110), h, fill="black", font=font)
    d.line([(20, 146), (980, 146)], fill="black", width=2)
    for i, row in enumerate(REPORT_ROWS):
        for j, cell in enumerate(row):
            d.text((xs[j], 160 + 56 * i), cell, fill="black", font=font)
    if variant == "rotated":
        img = img.rotate(2.5, expand=True, fillcolor="white", resample=Image.BICUBIC)
    elif variant == "noisy":
        rnd = random.Random(7)
        px = img.load()
        for _ in range(img.width * img.height // 25):
            x, y = rnd.randrange(img.width), rnd.randrange(img.height)
            g = rnd.randrange(120, 255)
            px[x, y] = (g, g, g)
        img = img.filter(ImageFilter.GaussianBlur(0.8)).rotate(-1.5, expand=True, fillcolor="white")
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


def score(rows: list[dict]) -> tuple[int, int, int]:
    """(doğru değer, doğru birim, çıkarılan satır) — doğru sayılması için test eşleşmeli."""
    by_id = {r["test_id"]: r for r in rows if r.get("test_id")}
    ok_v = ok_u = 0
    for name, value, unit, _ in REPORT_ROWS:
        t = match_test(name)
        got = by_id.get(t.id) if t else None
        if not got:
            continue
        try:
            if parse_value(got["value"])[0] == parse_value(value)[0]:
                ok_v += 1
        except ValueError:
            pass
        if got.get("unit") and got["unit"].lower().replace("u", "µ") == unit.lower().replace("u", "µ"):
            ok_u += 1
    return ok_v, ok_u, len(rows)


def cmd_sanity(args) -> None:
    bad = 0
    for test, value, unit, sex, expected in SANITY:
        r = interpret_value(test, value, unit, sex=sex)
        flag = "OK " if r.status == expected else "HATA"
        bad += r.status != expected
        print(f"{flag} {test} {value} {unit} ({sex}) -> {r.status} (beklenen {expected})")
    print(f"\n{len(SANITY) - bad}/{len(SANITY)} doğru")
    if bad:
        raise SystemExit(1)


def _service(ocr_model: str | None = None):
    from medrag.config import Settings
    from medrag.llm import EvrenLLM
    from medrag.vision import VisionClient, VisionService

    s = Settings()
    models = [ocr_model] if ocr_model else [m.strip() for m in s.vision_ocr_models.split(",")]
    return VisionService(VisionClient(s.vision_api_url), EvrenLLM(s.vision_api_url, s.vision_extract_model),
                         models, s.vision_chat_model), s


def cmd_ocr(args) -> None:
    from medrag.vision import VisionError

    variants = ["clean", "rotated", "noisy"]
    images = {v: make_report(v) for v in variants}
    models = [m.strip() for m in args.models.split(",")]
    total = len(REPORT_ROWS)
    lines = ["# Tahlil fotoğrafı okuma sonuçları (sentetik raporlar)", "",
             f"Her görselde {total} test satırı var. Doğruluk: doğru okunan değer / {total}.", "",
             "| OCR modeli | Görsel | Değer doğru | Birim doğru | Çıkarılan satır | Yöntem | Süre (sn) |",
             "|---|---|---|---|---|---|---|"]
    for model in models:
        svc, _ = _service(model)
        svc.chat_model = "-"  # yedek sohbet modeli devre dışı: yalnızca bu OCR ölçülür
        for v, data in images.items():
            t = time.time()
            try:
                res = svc.lab_report(data)
                ok_v, ok_u, n = score(res["rows"])
                lines.append(f"| {model} | {v} | {ok_v}/{total} | {ok_u}/{total} | {n} | {res['method']} | {time.time() - t:.1f} |")
            except VisionError as e:
                lines.append(f"| {model} | {v} | HATA | - | - | - | {time.time() - t:.1f} ({e}) |")
            print(lines[-1])
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"\nyazıldı: {out}")


def cmd_raw(args) -> None:
    """OCR modellerinin ve görsel modelin ham çıktılarını yazdırır (anahtar yazdırılmaz)."""
    from medrag.vision import TRANSCRIBE_PROMPT, VisionError, sniff_image

    img = make_report("clean")
    svc, s = _service()
    mime = sniff_image(img) or "image/png"
    for model in [m.strip() for m in s.vision_ocr_models.split(",")]:
        print(f"=== OCR {model} ===")
        try:
            print(svc.client.ocr(img, mime, model)[:1500])
        except VisionError as e:
            print("HATA:", e)
    print(f"=== sohbet {s.vision_chat_model} ===")
    try:
        print(svc.client.chat(img, mime, s.vision_chat_model, TRANSCRIBE_PROMPT)[:1500])
    except VisionError as e:
        print("HATA:", e)


def register(sub) -> None:
    p = sub.add_parser("labs-sanity", help="Kural tabanlı tahlil yorumu kontrolü (API'siz)")
    p.set_defaults(func=cmd_sanity)
    p = sub.add_parser("labs-ocr", help="Sentetik tahlil görselleriyle OCR + çıkarım doğruluğu")
    p.add_argument("--models", default="deepseek-ocr-2,dots-ocr")
    p.add_argument("--out", default="eval/labs_results.md")
    p.set_defaults(func=cmd_ocr)
    p = sub.add_parser("labs-raw", help="Ham görsel/OCR model çıktıları")
    p.set_defaults(func=cmd_raw)

