"""README için OCR örnek görselleri: aynı içeriğin normal ve hafif/orta/ağır bozulmuş hâlleri (docs/screens/ocr/)."""

import random
from pathlib import Path

from ocr_set import DRUGS, degrade, pick_rows, render_box, render_report
from PIL import Image

OUT = Path("docs/screens/ocr")
WIDTH = 640


def save(img: Image.Image, name: str) -> None:
    img = img.convert("RGB")
    img = img.resize((WIDTH, round(img.height * WIDTH / img.width)), Image.LANCZOS)
    img.save(OUT / name, quality=80, optimize=True)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    samples = [("rapor-tablo", lambda r: render_report(pick_rows(r, 8), 0, r), 11),
               ("rapor-enabiz", lambda r: render_report(pick_rows(r, 8), 2, r), 21),
               ("kutu-parol", lambda r: render_box(DRUGS[0], r), 31),
               ("kutu-nurofen", lambda r: render_box(DRUGS[3], r), 41)]
    for name, make, seed in samples:
        save(make(random.Random(seed)), f"{name}-normal.jpg")
        for level in ("hafif", "orta", "ağır"):
            base = make(random.Random(seed))  # aynı içerik
            img, _ = degrade(base, random.Random(seed + 7), level)
            save(img, f"{name}-{level.replace('ğ', 'g').replace('ı', 'i')}.jpg")
    print(sorted(p.name for p in OUT.iterdir()))


if __name__ == "__main__":
    main()
