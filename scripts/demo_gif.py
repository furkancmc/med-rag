"""Çalışan uygulamada birkaç modülü gezip kısa bir GIF üretir (Playwright + Pillow).

Kullanım: python scripts/demo_gif.py <çıktı.gif> [base_url]   (varsayılan http://127.0.0.1:8765)
Önce `python scripts/dev_server.py --port 8765` çalışmalı. Sohbet sahte servisten, belirti/tahlil/görsel okuma
gerçek API'den gelir (anahtar `.env`'de olmalı). Bekleme süreleri GIF'e girmez: yalnızca durum değişimlerinden kare alınır.
"""
import io
import sys
from pathlib import Path

from PIL import Image
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
OCR = ROOT / "docs" / "screens" / "ocr"
out = Path(sys.argv[1])
base = (sys.argv[2] if len(sys.argv) > 2 else "http://127.0.0.1:8765").rstrip("/")
WAIT = 240_000

frames: list[tuple[Image.Image, int]] = []


def snap(page, ms=1400, full=False):
    png = page.screenshot(full_page=full)
    img = Image.open(io.BytesIO(png)).convert("RGB")
    img = img.resize((320, round(img.height * 320 / img.width)), Image.LANCZOS)
    frames.append((img, ms))


def chat(page, text):
    page.goto(base + "/")
    page.wait_for_load_state("networkidle")
    snap(page)
    page.fill("#input", text)
    snap(page, 900)
    page.click("#send")
    page.wait_for_selector(".msg.bot", timeout=30_000)
    page.wait_for_function(
        "document.getElementById('send').getAttribute('aria-label') === 'Gönder'", timeout=WAIT)
    page.wait_for_timeout(500)
    snap(page, 2200)


def answer_question(page):
    box = page.locator("#qinput")
    if box.locator("[aria-pressed=true], input:checked").count():
        return  # varsayılan seçim zaten işaretli
    if box.locator(".scale").count():
        box.locator(".scale button", has_text="3").first.click(timeout=5000)
        return
    if box.locator("button.chip").count():  # kırmızı bayrak içermeyen, son ("hayır/hiçbiri") seçenek
        box.locator("button.chip").last.click(timeout=5000)
        return
    box.locator("textarea, input").first.fill("İki gündür, hafif")


def assess(page):
    page.goto(base + "/assess")
    page.wait_for_load_state("networkidle")
    page.fill("#complaint", "İki gündür başım ağrıyor ve hafif ateşim var")
    page.fill("#age", "34")
    snap(page, 1300)
    page.click("#start-btn")
    page.wait_for_selector("#step-2:not([hidden])", timeout=WAIT)
    page.wait_for_timeout(400)
    snap(page, 1500)
    for _ in range(6):
        answer_question(page)
        snap(page, 900)
        last = page.locator("#next-btn").inner_text().strip().lower()
        page.click("#next-btn")
        if last.startswith("sonucu"):
            break
        page.wait_for_timeout(300)
    page.wait_for_selector("#step-3:not([hidden])", timeout=WAIT)
    page.wait_for_timeout(500)
    snap(page, 2600)


def labs(page):
    page.goto(base + "/labs")
    page.wait_for_load_state("networkidle")
    for name, value in (("Hemoglobin", "10,8"), ("Glukoz", "126")):
        page.fill("#picker", name)
        page.click("#add-test")
        page.locator('#rows [data-f="value"]').last.fill(value)
    snap(page, 1800)
    page.click("#interpret")
    page.wait_for_selector("#out:not([hidden])", timeout=WAIT)
    page.wait_for_function("document.getElementById('explain').innerText.trim().length > 20", timeout=WAIT)
    page.wait_for_timeout(500)
    snap(page, 2600)
    page.locator("#res").scroll_into_view_if_needed()
    snap(page, 2200)


def lab_photo(page):
    page.goto(base + "/labs")
    page.wait_for_load_state("networkidle")
    page.click("#tab-photo")
    page.set_input_files("#lab-file", str(OCR / "rapor-tablo-hafif.jpg"))
    page.wait_for_selector("#lab-preview:not([hidden])")
    snap(page, 1500)
    page.click("#lab-read")
    page.wait_for_function("document.querySelectorAll('#rows > *').length > 0", timeout=WAIT)
    page.wait_for_timeout(500)
    page.locator("#rows").scroll_into_view_if_needed()
    snap(page, 2600)


def medicine(page):
    page.goto(base + "/labs")
    page.wait_for_load_state("networkidle")
    page.locator("#med-file").scroll_into_view_if_needed()
    page.set_input_files("#med-file", str(OCR / "kutu-parol-hafif.jpg"))
    page.click("#med-read")
    page.wait_for_selector("#med-out:not([hidden])", timeout=WAIT)
    page.wait_for_timeout(500)
    page.locator("#med-out").scroll_into_view_if_needed()
    snap(page, 2800)


with sync_playwright() as p:
    browser = p.chromium.launch(channel="msedge")
    ctx = browser.new_context(viewport={"width": 390, "height": 844}, color_scheme="light", bypass_csp=True)
    page = ctx.new_page()
    chat(page, "Diyabetin belirtileri nelerdir?")
    chat(page, "Göğsümde şiddetli bir ağrı var ve sol kolum uyuşuyor")
    for step in (assess, labs, lab_photo, medicine):
        try:
            step(page)
        except Exception as e:  # bir modül başarısız olsa da diğerleri GIF'e girsin
            print("ATLANDI:", step.__name__, type(e).__name__, str(e)[:200])
    browser.close()

h = max(f.height for f, _ in frames)
canvas = []
for img, _ in frames:
    c = Image.new("RGB", (320, h), (255, 255, 255))
    c.paste(img, (0, 0))
    canvas.append(c.quantize(colors=128, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE))
canvas[0].save(out, save_all=True, append_images=canvas[1:], duration=[d for _, d in frames], loop=0, optimize=True)
print("GIF:", out, len(frames), "kare", round(out.stat().st_size / 1024), "KB")
