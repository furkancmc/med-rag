"""Gerçekçi bozulmalı OCR test seti üretir (tahlil raporu + ilaç kutusu); doğru cevaplar manifest.json'a yazılır.

Kullanım: python scripts/ocr_set.py [çıktı_klasörü] [rapor_sayısı] [kutu_sayısı]
Bozulmalar (telefon fotoğrafı taklidi): perspektif eğimi, gölge, flaş parlaması, bulanıklık/hareket, düşük ışık,
JPEG sıkıştırma, buruşma, kenar kırpma. Masa/arka plan üzerine yerleştirilir.
"""

import io
import json
import random
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont

from medrag.labs.reference import TESTS

FONTS = {
    "sans": "C:/Windows/Fonts/arial.ttf",
    "bold": "C:/Windows/Fonts/arialbd.ttf",
    "narrow": "C:/Windows/Fonts/ARIALN.TTF",
    "serif": "C:/Windows/Fonts/times.ttf",
    "calibri": "C:/Windows/Fonts/calibri.ttf",
}
LAB_NAMES = {  # Türkçe rapor adları (reference.py adları kısmen İngilizce)
    "hemoglobin": "Hemoglobin", "hematocrit": "Hematokrit", "wbc": "Lökosit", "platelet": "Trombosit",
    "rbc": "Eritrosit", "mcv": "MCV", "glucose": "Glukoz (Açlık)", "hba1c": "HbA1c", "cholesterol": "Total Kolesterol",
    "ldl": "LDL Kolesterol", "hdl": "HDL Kolesterol", "triglyceride": "Trigliserit", "creatinine": "Kreatinin",
    "urea": "Üre", "bun": "BUN", "uric_acid": "Ürik Asit", "alt": "ALT", "ast": "AST", "ggt": "GGT", "alp": "ALP",
    "bilirubin": "Total Bilirubin", "albumin": "Albümin", "tsh": "TSH", "ft4": "Serbest T4", "ferritin": "Ferritin",
    "iron": "Demir", "b12": "Vitamin B12", "folate": "Folat", "vitamin_d": "D Vitamini", "crp": "CRP",
    "sodium": "Sodyum", "potassium": "Potasyum", "chloride": "Klor", "calcium": "Kalsiyum",
}
DRUGS = [  # (marka, etken madde, güç, form)
    ("PAROL", "parasetamol", "500 mg", "tablet"), ("ASPİRİN", "asetilsalisilik asit", "500 mg", "tablet"),
    ("MAJEZİK", "flurbiprofen", "100 mg", "film tablet"), ("NUROFEN", "ibuprofen", "400 mg", "film tablet"),
    ("AUGMENTİN", "amoksisilin + klavulanik asit", "1000 mg", "film tablet"),
    ("CİPRASİD", "siprofloksasin", "500 mg", "film tablet"), ("DEPAKİN", "valproat sodyum", "500 mg", "tablet"),
    ("GLUCOPHAGE", "metformin hidroklorür", "1000 mg", "film tablet"), ("NEXİUM", "esomeprazol", "40 mg", "tablet"),
    ("LİPİTOR", "atorvastatin", "20 mg", "film tablet"), ("SUPRADYN", "multivitamin", "1 tablet", "efervesan tablet"),
    ("VENTOLİN", "salbutamol", "100 mcg", "inhaler"), ("DEKSAMETAZON", "deksametazon", "8 mg", "ampul"),
    ("BEPANTHOL", "dekspantenol", "%5", "krem"), ("CORYZA", "paracetamol + klorfeniramin", "500 mg", "tablet"),
]


def font(name: str, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(FONTS.get(name, FONTS["sans"]), size)


# --- Tahlil raporu ---
def pick_rows(rnd: random.Random, n: int) -> list[dict]:
    tests = rnd.sample([t for t in TESTS if t.id in LAB_NAMES], n)
    rows = []
    for t in tests:
        rng = t.ranges.get("female") or t.ranges.get("all") or next(iter(t.ranges.values()))
        lo, hi = rng
        base_lo = lo if lo is not None else (hi * 0.4)
        base_hi = hi if hi is not None else (lo * 2.0)
        val = rnd.uniform(base_lo * 0.7, base_hi * 1.3)
        digits = 0 if val >= 100 else (1 if val >= 10 else 2)
        value = f"{val:.{digits}f}".replace(".", rnd.choice([",", ","]))
        ref = (
            f"{lo:g} - {hi:g}" if lo is not None and hi is not None
            else (f"< {hi:g}" if hi is not None else f"> {lo:g}")
        ).replace(".", ",")
        flag = "H" if hi is not None and val > hi else ("L" if lo is not None and val < lo else "")
        rows.append({"test_id": t.id, "name": LAB_NAMES[t.id], "value": value, "unit": t.unit.replace("10^3/µL", "10^3/uL"),
                     "ref": ref, "flag": flag})
    return rows


def render_report(rows: list[dict], layout: int, rnd: random.Random) -> Image.Image:
    fname = rnd.choice(["sans", "calibri", "narrow", "serif"])
    size = rnd.choice([24, 26, 28])
    f, fb = font(fname, size), font("bold", size)
    W, rowh = 1000, size * 2
    H = 260 + rowh * (len(rows) + 2)
    bg = rnd.choice(["white", "#fdfcf5", "#f7f9fc"])
    img = Image.new("RGB", (W, H), bg)
    d = ImageDraw.Draw(img)
    lab = rnd.choice(["ÖZEL ŞEHİR LABORATUVARI", "MERKEZ TIP BİYOKİMYA LABORATUVARI", "ANADOLU TANI MERKEZİ"])
    d.text((30, 24), lab, fill="#10305a", font=fb)
    d.text((30, 24 + size + 10), f"Hasta: Deneme Hasta   Protokol: {rnd.randrange(100000, 999999)}   Tarih: {rnd.randrange(1, 28):02d}.0{rnd.randrange(1, 9)}.2026",
           fill="black", font=f)
    y0 = 140
    if layout == 0:  # klasik tablo
        xs = (30, 380, 540, 700)
        for j, h in enumerate(("Test", "Sonuç", "Birim", "Referans")):
            d.text((xs[j], y0), h, fill="black", font=fb)
        d.line([(24, y0 + size + 8), (W - 24, y0 + size + 8)], fill="black", width=2)
        for i, r in enumerate(rows):
            y = y0 + size + 24 + rowh * i
            for j, c in enumerate((r["name"], r["value"], r["unit"], r["ref"])):
                d.text((xs[j], y), c, fill="black", font=fb if (j == 1 and r["flag"]) else f)
    elif layout == 1:  # nokta dolgulu satırlar, birim ve referans parantezde
        for i, r in enumerate(rows):
            y = y0 + rowh * i
            d.text((30, y), r["name"], fill="black", font=f)
            d.text((430, y), f"{r['value']} {r['unit']}", fill="black", font=fb)
            d.text((720, y), f"({r['ref']})", fill="#444444", font=f)
    elif layout == 2:  # e-Nabız tarzı: bayraklı, renkli, durum sütunu
        xs = (30, 340, 480, 620, 800)
        for j, h in enumerate(("TETKİK", "SONUÇ", "BİRİM", "REFERANS ARALIĞI", "DURUM")):
            d.rectangle([xs[j] - 6, y0 - 4, (xs[j + 1] if j < 4 else W - 20) - 8, y0 + size + 6], fill="#dfe8f3")
            d.text((xs[j], y0), h, fill="#10305a", font=fb)
        for i, r in enumerate(rows):
            y = y0 + size + 24 + rowh * i
            col = "#b3261e" if r["flag"] else "black"
            for j, c in enumerate((r["name"], r["value"], r["unit"], r["ref"], {"H": "Yüksek ▲", "L": "Düşük ▼", "": "Normal"}[r["flag"]])):
                d.text((xs[j], y), c, fill=col if j in (1, 4) else "black", font=fb if (j == 1 and r["flag"]) else f)
            d.line([(24, y + size + 10), (W - 24, y + size + 10)], fill="#cccccc", width=1)
    else:  # bölüm başlıklı, iki satırlı kayıt
        d.text((30, y0), "BİYOKİMYA (SERUM)", fill="#10305a", font=fb)
        for i, r in enumerate(rows):
            y = y0 + size + 18 + rowh * i
            d.text((50, y), f"{r['name']}:  {r['value']}  {r['unit']}", fill="black", font=fb if r["flag"] else f)
            d.text((620, y), f"Ref: {r['ref']}", fill="#555555", font=f)
    return img


# --- İlaç kutusu ---
def render_box(drug: tuple, rnd: random.Random) -> Image.Image:
    brand, active, strength, form = drug
    W, H = 900, 560
    c1 = rnd.choice(["#0b5cab", "#c0392b", "#1e8449", "#7d3c98", "#d68910", "#117a8b"])
    img = Image.new("RGB", (W, H), "white")
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, W, 140], fill=c1)
    d.text((40, 28), brand, fill="white", font=font("bold", rnd.choice([76, 84])))
    d.text((40, 170), f"{strength}  {form}", fill="black", font=font("bold", 48))
    d.text((40, 245), active, fill="#222222", font=font("sans", 38))
    d.text((40, 310), "Oral kullanım için" if form != "krem" else "Haricen kullanılır", fill="#444444", font=font("sans", 28))
    d.text((40, 360), "20 adet" if "tablet" in form else "1 adet", fill="#444444", font=font("sans", 28))
    d.text((40, 480), f"Seri No: {rnd.randrange(10000, 99999)}   SKT: 0{rnd.randrange(1, 9)}/2028", fill="#555555", font=font("narrow", 24))
    for k in range(40):  # barkod benzeri çizgiler
        x = 560 + k * 7
        d.rectangle([x, 380, x + rnd.choice([2, 3, 5]), 500], fill="black")
    return img


# --- Bozulmalar ---
def perspective(img: Image.Image, rnd: random.Random, s: float) -> Image.Image:
    w, h = img.size
    j = lambda m: rnd.uniform(-m, m) * s  # noqa: E731
    dx, dy = w * 0.07, h * 0.07
    quad = (j(dx) + dx * s, j(dy) + dy * s, j(dx) + dx * s, h - j(dy) - dy * s, w - j(dx) - dx * s, h - j(dy) * 0.5 - dy * s, w - j(dx) - dx * s, j(dy) + dy * s)
    return img.transform((w, h), Image.QUAD, quad, Image.BICUBIC, fillcolor="#9a8f80")


def shadow(img: Image.Image, rnd: random.Random, s: float) -> Image.Image:
    a = np.asarray(img).astype(np.float32)
    h, w = a.shape[:2]
    ang = rnd.uniform(0, 3.14)
    gx = (np.cos(ang) * np.linspace(-1, 1, w))[None, :] + (np.sin(ang) * np.linspace(-1, 1, h))[:, None]
    mask = 1 - s * 0.55 * np.clip((gx + 0.4) / 1.4, 0, 1)
    return Image.fromarray(np.clip(a * mask[..., None], 0, 255).astype(np.uint8))


def glare(img: Image.Image, rnd: random.Random, s: float) -> Image.Image:
    a = np.asarray(img).astype(np.float32)
    h, w = a.shape[:2]
    cx, cy = rnd.uniform(0.2, 0.8) * w, rnd.uniform(0.2, 0.8) * h
    yy, xx = np.mgrid[0:h, 0:w]
    g = np.exp(-(((xx - cx) / (w * 0.22)) ** 2 + ((yy - cy) / (h * 0.16)) ** 2)) * 255 * s * 0.9
    return Image.fromarray(np.clip(a + g[..., None], 0, 255).astype(np.uint8))


def wrinkle(img: Image.Image, rnd: random.Random, s: float) -> Image.Image:
    a = np.asarray(img)
    h, w = a.shape[:2]
    ph, amp = rnd.uniform(0, 6.28), 3 + 6 * s
    shift = (np.sin(np.linspace(0, rnd.uniform(3, 6), h) + ph) * amp).astype(int)
    out = np.empty_like(a)
    for i in range(h):
        out[i] = np.roll(a[i], shift[i], axis=0)
    shade = 1 - 0.12 * s * np.abs(np.sin(np.linspace(0, 9, h)))[:, None, None]
    return Image.fromarray(np.clip(out * shade, 0, 255).astype(np.uint8))


def motion_blur(img: Image.Image, rnd: random.Random, s: float) -> Image.Image:
    k = 3 + int(8 * s)
    kernel = np.zeros((k, k))
    kernel[k // 2, :] = 1 / k
    return img.filter(ImageFilter.Kernel((k, k), kernel.flatten().tolist(), scale=1)) if k <= 5 else img.filter(ImageFilter.GaussianBlur(0.6 + 1.6 * s))


def lowlight(img: Image.Image, rnd: random.Random, s: float) -> Image.Image:
    img = ImageEnhance.Brightness(img).enhance(1 - 0.55 * s)
    a = np.asarray(img).astype(np.float32) + np.random.default_rng(rnd.randrange(10**6)).normal(0, 10 * s, (img.height, img.width, 1))
    return Image.fromarray(np.clip(a, 0, 255).astype(np.uint8))


def crop_edges(img: Image.Image, rnd: random.Random, s: float) -> Image.Image:
    w, h = img.size
    return img.crop((int(w * 0.04 * s * rnd.random()), int(h * 0.03 * s * rnd.random()), w - int(w * 0.05 * s * rnd.random()), h - int(h * 0.04 * s * rnd.random())))


EFFECTS = {"perspektif": perspective, "gölge": shadow, "parlama": glare, "buruşma": wrinkle, "bulanık": motion_blur, "düşük ışık": lowlight, "kırpma": crop_edges}
LEVELS = {"hafif": 0.45, "orta": 0.8, "ağır": 1.25}


def degrade(img: Image.Image, rnd: random.Random, level: str) -> tuple[Image.Image, list[str]]:
    s = LEVELS[level]
    n = {"hafif": 1, "orta": 2, "ağır": 4}[level]
    names = rnd.sample(list(EFFECTS), n)
    pad = Image.new("RGB", (img.width + 160, img.height + 160), rnd.choice(["#8d7f6e", "#6d7a86", "#a69b8c"]))  # masa
    pad.paste(img, (80, 80))
    out = pad
    for name in names:
        out = EFFECTS[name](out, rnd, s)
    buf = io.BytesIO()
    out.save(buf, "JPEG", quality={"hafif": 80, "orta": 55, "ağır": 35}[level])
    return Image.open(io.BytesIO(buf.getvalue())).convert("RGB"), names


def main() -> None:
    out = Path(sys.argv[1] if len(sys.argv) > 1 else "scratch/ocr")
    n_rep = int(sys.argv[2]) if len(sys.argv) > 2 else 48
    n_box = int(sys.argv[3]) if len(sys.argv) > 3 else 45
    out.mkdir(parents=True, exist_ok=True)
    manifest = []
    levels = list(LEVELS)
    for i in range(n_rep):
        rnd = random.Random(1000 + i)
        rows = pick_rows(rnd, rnd.choice([8, 10, 12]))
        img, fx = degrade(render_report(rows, i % 4, rnd), rnd, levels[i % 3])
        name = f"report_{i:03d}.jpg"
        img.save(out / name, quality=95)
        manifest.append({"file": name, "kind": "report", "layout": i % 4, "level": levels[i % 3], "effects": fx, "rows": rows})
    for i in range(n_box):
        rnd = random.Random(5000 + i)
        drug = DRUGS[i % len(DRUGS)]
        img, fx = degrade(render_box(drug, rnd), rnd, levels[i % 3])
        name = f"box_{i:03d}.jpg"
        img.save(out / name, quality=95)
        manifest.append({"file": name, "kind": "box", "level": levels[i % 3], "effects": fx,
                         "truth": {"brand": drug[0], "active": drug[1], "strength": drug[2], "form": drug[3]}})
    (out / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{n_rep} rapor + {n_box} kutu -> {out}")


if __name__ == "__main__":
    main()
