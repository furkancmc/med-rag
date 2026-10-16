import json

import pytest
from fastapi.testclient import TestClient

from medrag.api.main import create_app
from medrag.api.routes.vision import get_vision_service
from medrag.vision import (
    ImageError,
    VisionClient,
    VisionError,
    VisionService,
    medicine_from_text,
    ocr_to_lines,
    parse_llm_rows,
    parse_rows_deterministic,
    sniff_image,
    validate_image,
)

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
JPG = b"\xff\xd8\xff\xe0" + b"\x00" * 32
WEBP = b"RIFF\x00\x00\x00\x00WEBPVP8 " + b"\x00" * 16

MD_TABLE = """| Test | Sonuç | Birim | Referans |
|---|---|---|---|
| Hemoglobin | 11,2 | g/dL | 12.0 - 16.0 |
| Glukoz (Açlık) | 108 | mg/dL | 70 - 100 |
| TSH | 5,6 | mIU/L | 0.4 - 4.0 |
| Tanımsız Test | 3 | xx | |"""
HTML_TABLE = ("<table><thead><tr><td>Test</td><td>Sonuç</td><td>Birim</td><td>Referans</td></tr></thead><tbody>"
              "<tr><td>Ferritin</td><td>8</td><td>ng/mL</td><td>15 - 150</td></tr>"
              "<tr><td>CRP</td><td>&lt;0,5</td><td>mg/L</td><td>&lt;5</td></tr></tbody></table>")
PLAIN = "Hemoglobin 11,2 g/dL 12.0-16.0\nLDL Kolesterol 162 mg/dL < 130\nHasta: Ali Veli\nTarih 12.03.2026"


def test_sniff_and_validate():
    assert sniff_image(PNG) == "image/png" and sniff_image(JPG) == "image/jpeg" and sniff_image(WEBP) == "image/webp"
    assert sniff_image(b"GIF89a....") is None and sniff_image(b"%PDF-1.4") is None
    assert validate_image(PNG, 100) == "image/png"
    for data, status in ((b"", 422), (b"x" * 10, 415), (PNG + b"0" * 100, 413)):
        with pytest.raises(ImageError) as e:
            validate_image(data, 100)
        assert e.value.status == status


def test_ocr_to_lines_markdown_and_html():
    assert ["Hemoglobin", "11,2", "g/dL", "12.0 - 16.0"] in ocr_to_lines(MD_TABLE)
    lines = ocr_to_lines(HTML_TABLE)
    assert ["Ferritin", "8", "ng/mL", "15 - 150"] in lines and ["CRP", "<0,5", "mg/L", "<5"] in lines


def test_deterministic_parser():
    rows = {r["test"]: r for r in parse_rows_deterministic(MD_TABLE)}
    assert rows["Hemoglobin"] == {"test": "Hemoglobin", "value": "11,2", "unit": "g/dL", "ref_low": 12.0, "ref_high": 16.0}
    assert rows["TSH"]["ref_high"] == 4.0 and rows["Glukoz (Açlık)"]["ref_low"] == 70.0
    assert "Test" not in rows  # başlık satırı
    html_rows = {r["test"]: r for r in parse_rows_deterministic(HTML_TABLE)}
    assert html_rows["CRP"]["value"] == "<0,5" and html_rows["CRP"]["ref_high"] == 5.0
    plain = {r["test"]: r for r in parse_rows_deterministic(PLAIN)}
    assert plain["Hemoglobin"]["unit"] == "g/dL" and plain["Hemoglobin"]["ref_high"] == 16.0
    assert plain["LDL Kolesterol"]["ref_high"] == 130.0


def test_parse_llm_rows():
    raw = 'Tamam:\n```json\n[{"test":"TSH","value":5.6,"unit":"mIU/L","ref_low":0.4,"ref_high":"4,0"},{"bad":1},' \
          '{"test":"X","value":null}]\n```'
    rows = parse_llm_rows(raw)
    assert len(rows) == 1 and rows[0]["value"] == "5.6" and rows[0]["unit"] == "mIU/L"
    assert parse_llm_rows("hiç json yok") == [] and parse_llm_rows("[bozuk") == []
    assert parse_llm_rows("{}") == []


class FakeClient(VisionClient):
    def __init__(self, ocr_text=MD_TABLE, fail_ocr=(), chat_text="metin", fail_chat=False):
        super().__init__("http://x", api_key="k", post=lambda *_: {})
        self.ocr_text, self.fail_ocr, self.chat_text, self.fail_chat = ocr_text, set(fail_ocr), chat_text, fail_chat
        self.calls = []

    def ocr(self, image, mime, model):
        self.calls.append(("ocr", model))
        if model in self.fail_ocr:
            raise VisionError("ocr yok")
        return self.ocr_text

    def chat(self, image, mime, model, prompt, max_tokens=2000):
        self.calls.append(("chat", model))
        if self.fail_chat:
            raise VisionError("chat yok")
        return self.chat_text


class FakeExtractor:
    def __init__(self, out=None, fail=False):
        self.out, self.fail = out, fail

    def complete(self, messages, temperature=0.0, max_tokens=0):
        if self.fail:
            raise RuntimeError("x")
        return self.out


def service(client=None, extractor=None):
    return VisionService(client or FakeClient(), extractor, ["deepseek-ocr-2", "dots-ocr"], "qwen3-vl-30b", 1000)


def test_lab_report_llm_path_filters_hallucinations():
    out = json.dumps([
        {"test": "Hemoglobin", "value": "11,2", "unit": "g/dL", "ref_low": 12, "ref_high": 16},
        {"test": "Ferritin", "value": "999", "unit": "ng/mL"},  # OCR metninde yok: uydurma
    ])
    res = service(extractor=FakeExtractor(out)).lab_report(PNG)
    assert res["method"] == "llm" and res["ocr_model"] == "deepseek-ocr-2"
    assert [r["test_id"] for r in res["rows"]] == ["hemoglobin"]
    assert res["rows"][0]["ref_low"] == 12.0 and res["rows"][0]["known"] is True


def test_lab_report_falls_back_to_rules():
    res = service(extractor=FakeExtractor(fail=True)).lab_report(PNG)
    assert res["method"] == "rules"
    by = {r["test"]: r for r in res["rows"]}
    assert by["TSH"]["test_id"] == "tsh" and by["Tanımsız Test"]["known"] is False
    assert any("eşleşmedi" in w for w in res["warnings"]) and any("kontrol" in w for w in res["warnings"])
    res2 = service(extractor=FakeExtractor("hiç json yok")).lab_report(PNG)
    assert res2["method"] == "rules" and res2["rows"]


def test_ocr_model_fallbacks():
    c = FakeClient(fail_ocr={"deepseek-ocr-2"})
    res = service(c).lab_report(PNG)
    assert res["ocr_model"] == "dots-ocr" and c.calls == [("ocr", "deepseek-ocr-2"), ("ocr", "dots-ocr")]
    c = FakeClient(fail_ocr={"deepseek-ocr-2", "dots-ocr"}, chat_text=MD_TABLE)
    res = service(c).lab_report(PNG)
    assert res["ocr_model"] == "qwen3-vl-30b" and res["rows"]
    with pytest.raises(VisionError):
        service(FakeClient(fail_ocr={"deepseek-ocr-2", "dots-ocr"}, fail_chat=True)).lab_report(PNG)


def test_lab_report_no_values_warns():
    res = service(FakeClient(ocr_text="Sayın hasta, sonuçlarınız hazırdır.")).lab_report(PNG)
    assert res["rows"] == [] and "bulunamadı" in res["warnings"][0]


def test_medicine_parsing():
    out = medicine_from_text('```json\n{"readable": true, "brand_name": "Parol", "active_ingredients": ["Parasetamol"],'
                             ' "strength": "500 mg", "form": "tablet", "confidence": "high"}\n```')
    assert out["brand_name"] == "Parol" and out["active_ingredients"] == ["Parasetamol"] and out["confidence"] == "high"
    assert "Parol" in out["suggested_question"] and "mg alın" not in out["suggested_question"]
    bad = medicine_from_text("okunamadı")
    assert bad["readable"] is False and bad["suggested_question"] is None
    assert medicine_from_text('{"readable": false, "brand_name": "X"}')["suggested_question"] is None


def test_real_client_payload_shapes():
    seen = []

    def post(path, payload):
        seen.append((path, payload))
        return {"text": "abc"} if path == "/ocr" else {"choices": [{"message": {"content": " yanıt "}}]}

    c = VisionClient("http://x/v1/", api_key="k", post=post)
    assert c.ocr(PNG, "image/png", "deepseek-ocr-2") == "abc"
    assert seen[0][0] == "/ocr" and seen[0][1]["image"].startswith("data:image/png;base64,")
    assert c.chat(PNG, "image/png", "qwen3-vl-30b", "p") == "yanıt"
    part = seen[1][1]["messages"][0]["content"][1]
    assert part["type"] == "image_url" and part["image_url"]["url"].startswith("data:image/png;base64,")
    empty = VisionClient("http://x", api_key="k", post=lambda *_: {"text": " "})
    with pytest.raises(VisionError):
        empty.ocr(PNG, "image/png", "m")


# --- HTTP katmanı ---


def api(svc):
    app = create_app()
    app.dependency_overrides[get_vision_service] = lambda: svc
    return TestClient(app)


def test_upload_endpoints_validation():
    c = api(service(extractor=FakeExtractor(fail=True)))
    ok = c.post("/api/vision/lab-report", files={"file": ("a.png", PNG, "image/png")})
    assert ok.status_code == 200 and ok.json()["rows"]
    # istemci image/png dese de içerik sahte ise reddedilir
    fake = c.post("/api/vision/lab-report", files={"file": ("a.png", b"not an image", "image/png")})
    assert fake.status_code == 415
    pdf = c.post("/api/vision/lab-report", files={"file": ("a.pdf", b"%PDF-1.4 ...", "application/pdf")})
    assert pdf.status_code == 415
    big = c.post("/api/vision/lab-report", files={"file": ("a.jpg", JPG + b"0" * 2000, "image/jpeg")})
    assert big.status_code == 413
    empty = c.post("/api/vision/lab-report", files={"file": ("a.jpg", b"", "image/jpeg")})
    assert empty.status_code == 422
    assert c.post("/api/vision/lab-report").status_code == 422  # dosya alanı yok


def test_upload_endpoints_service_failure_is_502():
    c = api(service(FakeClient(fail_ocr={"deepseek-ocr-2", "dots-ocr"}, fail_chat=True)))
    r = c.post("/api/vision/lab-report", files={"file": ("a.webp", WEBP, "image/webp")})
    assert r.status_code == 502 and "okunamadı" in r.json()["detail"]


def test_medicine_endpoint():
    txt = '{"readable": true, "brand_name": "Augmentin", "active_ingredients": ["amoksisilin", "klavulanik asit"],' \
          ' "strength": "1000 mg", "form": "tablet", "confidence": "medium"}'
    c = api(service(FakeClient(chat_text=txt)))
    r = c.post("/api/vision/medicine", files={"file": ("k.jpg", JPG, "image/jpeg")})
    assert r.status_code == 200 and r.json()["brand_name"] == "Augmentin"
    assert r.json()["suggested_question"].startswith("Augmentin")
    assert c.post("/api/vision/medicine", files={"file": ("k.txt", b"merhaba", "text/plain")}).status_code == 415
