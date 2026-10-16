"""Gerçek uygulamaya telefon boyutunda soru sorup ekran görüntüsü alır.

Kullanım: python scripts/screens.py <çıktı_klasörü>   (sunucu localhost:8000'de çalışıyor olmalı)
"""
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

QUESTIONS = {
    "normal": "Diyabetin belirtileri nelerdir?",
    "acil": "Göğsümde şiddetli bir ağrı var ve sol kolum uyuşuyor",
    "doz": "Parasetamolü günde kaç mg almalıyım?",
}

out = Path(sys.argv[1])
out.mkdir(parents=True, exist_ok=True)

with sync_playwright() as p:
    browser = p.chromium.launch()
    for scheme in ("light", "dark"):
        for name, question in QUESTIONS.items():
            page = browser.new_page(viewport={"width": 390, "height": 844}, color_scheme=scheme)
            page.goto("http://127.0.0.1:8000/")
            page.fill("#input", question)
            page.click("#send")
            page.wait_for_function("!document.getElementById('send').disabled", timeout=120000)
            page.wait_for_timeout(500)
            page.screenshot(path=str(out / f"{name}-{scheme}.png"))
            page.close()
    browser.close()
print("ekran görüntüleri:", sorted(x.name for x in out.iterdir()))
