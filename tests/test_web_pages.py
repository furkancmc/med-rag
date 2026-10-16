"""Web arayüzü duman testleri (tarayıcı gerekmez): sayfalar, PWA dosyaları, ana öğeler."""
import json

from fastapi.testclient import TestClient

from medrag.api.main import create_app


class FakeService:
    def stream(self, question, history):
        yield {"type": "done"}


def client():
    return TestClient(create_app(FakeService()))


def test_chat_page_has_key_elements():
    html = client().get("/").text
    for needle in ('id="input"', 'id="send"', 'id="chat"', 'id="app-nav"', 'id="mic"', "/static/chat.js",
                   "/static/common.js", 'rel="manifest"', 'name="theme-color"', "apple-touch-icon", "tel:112"):
        assert needle in html, needle


def test_about_page_has_key_elements():
    r = client().get("/about")
    assert r.status_code == 200
    for needle in ("/api/meta/info", "sources-box", "KVKK", "tel:112", 'id="app-nav"', 'rel="manifest"'):
        assert needle in r.text + client().get("/static/about.js").text, needle


def test_pages_have_no_inline_script_or_style():
    for path in ("/", "/about"):
        html = client().get(path).text
        assert "<style" not in html and " style=" not in html
        assert "<script>" not in html


def test_manifest_and_icons():
    c = client()
    r = c.get("/manifest.webmanifest")
    assert r.status_code == 200 and "manifest+json" in r.headers["content-type"]
    m = r.json()
    assert m["name"] == "Sağlık Asistanı" and m["display"] == "standalone" and m["start_url"] == "/"
    purposes = {i["purpose"] for i in m["icons"]}
    assert {"any", "maskable"} <= purposes
    for icon in m["icons"]:
        resp = c.get(icon["src"])
        assert resp.status_code == 200, icon["src"]
    assert c.get("/static/icons/icon-192.png").content[:4] == b"\x89PNG"


def test_service_worker_never_caches_api():
    c = client()
    r = c.get("/sw.js")
    assert r.status_code == 200 and "javascript" in r.headers["content-type"]
    assert '"/api/"' in r.text and '"/chat"' in r.text and 'req.method !== "GET"' in r.text


def test_common_js_exports():
    js = client().get("/static/common.js").text
    for name in ("escapeHtml", "renderMarkdown", "streamSSE", "postJSON", "renderNav", "toast", "uploadFile",
                 "X-Access-Code", "medrag_access_code", "access_code_required", "/sw.js"):
        assert name in js, name


def test_manifest_is_valid_json_file():
    from medrag.api.main import STATIC_DIR

    json.loads((STATIC_DIR / "manifest.webmanifest").read_text(encoding="utf-8"))
