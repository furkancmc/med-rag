"""Gerçek uygulamaya telefon boyutunda soru sorup tüm sayfaların ekran görüntüsünü alır.

Kullanım: python scripts/screens.py <çıktı_klasörü> [base_url]   (varsayılan http://127.0.0.1:8000)
Sohbet: normal / acil / doz soruları; ayrıca /assess, /labs, /about başlangıç ekranları; açık ve koyu tema.
"""
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

QUESTIONS = {
    "normal": "Diyabetin belirtileri nelerdir?",
    "acil": "Göğsümde şiddetli bir ağrı var ve sol kolum uyuşuyor",
    "doz": "Parasetamolü günde kaç mg almalıyım?",
}
PAGES = {"assess": "/assess", "labs": "/labs", "about": "/about"}

out = Path(sys.argv[1])
base = (sys.argv[2] if len(sys.argv) > 2 else "http://127.0.0.1:8000").rstrip("/")
out.mkdir(parents=True, exist_ok=True)


def wait_answer(page):
    # Gönder düğmesi akış boyunca "Durdur" olur; bitince yeniden "Gönder".
    page.wait_for_function(
        "document.getElementById('send').getAttribute('aria-label') === 'Gönder'"
        " && document.querySelectorAll('.msg.bot').length > 0",
        timeout=120000,
    )
    page.wait_for_timeout(600)


with sync_playwright() as p:
    browser = p.chromium.launch()
    for scheme in ("light", "dark"):
        for name, question in QUESTIONS.items():
            page = browser.new_page(viewport={"width": 390, "height": 844}, color_scheme=scheme)
            page.goto(base + "/")
            page.fill("#input", question)
            page.click("#send")
            page.wait_for_selector(".msg.bot", timeout=30000)
            wait_answer(page)
            page.screenshot(path=str(out / f"{name}-{scheme}.png"))
            page.close()
        for name, path in PAGES.items():
            page = browser.new_page(viewport={"width": 390, "height": 844}, color_scheme=scheme)
            page.goto(base + path)
            page.wait_for_load_state("networkidle")
            page.wait_for_timeout(500)
            page.screenshot(path=str(out / f"{name}-{scheme}.png"), full_page=(name == "about"))
            page.close()
    browser.close()
print("ekran görüntüleri:", sorted(x.name for x in out.iterdir()))
