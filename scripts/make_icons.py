"""PWA simgelerini üretir (web/static/icons/*.png). Playwright ile SVG'yi PNG'ye çizer.

Kullanım: python scripts/make_icons.py [edge|chrome|chromium]
"""
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

OUT = Path(__file__).resolve().parent.parent / "src" / "medrag" / "web" / "static" / "icons"
CROSS = '<path d="M216 120h80v96h96v80h-96v96h-80v-96h-96v-80h96z" fill="#fff"/>'


def svg(maskable: bool) -> str:
    rx = 0 if maskable else 112
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512">'
        f'<rect width="512" height="512" rx="{rx}" fill="#0f766e"/>{CROSS}</svg>'
    )


JOBS = [
    ("icon-192.png", 192, False),
    ("icon-512.png", 512, False),
    ("icon-maskable-512.png", 512, True),
    ("apple-touch-icon.png", 180, True),  # iOS köşeleri kendisi yuvarlar
]


def main() -> None:
    channel = sys.argv[1] if len(sys.argv) > 1 else "msedge"
    OUT.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        kwargs = {} if channel == "chromium" else {"channel": channel}
        browser = p.chromium.launch(**kwargs)
        for name, size, maskable in JOBS:
            page = browser.new_page(viewport={"width": size, "height": size})
            page.set_content(
                '<body style="margin:0;background:transparent">'
                f'<div style="width:{size}px;height:{size}px">{svg(maskable)}</div>'
            )
            page.evaluate(
                "s => { const e = document.querySelector('svg'); e.setAttribute('width', s); e.setAttribute('height', s); }",
                size,
            )
            page.screenshot(path=str(OUT / name), omit_background=True)
            page.close()
        browser.close()
    print("yazıldı:", [j[0] for j in JOBS])


if __name__ == "__main__":
    main()
