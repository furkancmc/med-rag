from types import SimpleNamespace

from fastapi.testclient import TestClient

from medrag.api.main import create_app
from medrag.api.routes.labs import get_lab_service
from medrag.labs.service import LabService


class FakeRetriever:
    def __init__(self):
        self.queries = []

    def search(self, query, k=5):
        self.queries.append(query)
        chunk = {"title": "Anemi", "section": "Nedenler", "url": "http://x/anemi", "source": "MedlinePlus",
                 "license": "PD", "text": "Demir eksikliği anemiye yol açabilir."}
        return [SimpleNamespace(chunk=chunk, score=1.0)]


class FakeLLM:
    def __init__(self, text="**Özet**\nDemir eksikliği olabilir [1]. Günde 500 mg alın.", fail=False):
        self.text, self.fail, self.calls = text, fail, []

    def complete(self, messages, temperature=0.3, max_tokens=1024):
        self.calls.append(messages)
        if self.fail:
            raise RuntimeError("boom")
        return self.text


def client(llm=None, retriever=None):
    app = create_app()
    svc = LabService(retriever, llm)
    app.dependency_overrides[get_lab_service] = lambda: svc
    return TestClient(app), svc


def test_catalog_endpoint():
    c, _ = client()
    data = c.get("/api/labs/tests").json()["tests"]
    assert len(data) >= 25
    glu = next(t for t in data if t["id"] == "glucose")
    assert "mmol/L" in glu["units"] and glu["url"].startswith("https://")
    assert next(t for t in data if t["id"] == "hemoglobin")["sex_specific"] is True


def test_interpret_normal_skips_llm():
    llm = FakeLLM()
    c, _ = client(llm, FakeRetriever())
    body = {"values": [{"test": "Glukoz", "value": "90", "unit": "mg/dL"}]}
    data = c.post("/api/labs/interpret", json=body).json()
    assert data["results"][0]["status"] == "normal"
    assert data["urgent"] is False and data["sources"] == [] and llm.calls == []
    assert "hekim" in data["disclaimer"]


def test_interpret_abnormal_uses_sources_and_redacts_dose():
    llm, ret = FakeLLM(), FakeRetriever()
    c, _ = client(llm, ret)
    body = {"sex": "female", "age": 30, "values": [
        {"test": "Hemoglobin", "value": "10,5", "unit": "g/dL"},
        {"test": "Ferritin", "value": "4", "unit": "ng/mL"},
        {"test": "Bilinmez", "value": "1"},
    ]}
    data = c.post("/api/labs/interpret", json=body).json()
    statuses = [r["status"] for r in data["results"]]
    assert statuses == ["low", "low", "unknown"]
    assert data["sources"][0]["n"] == 1 and data["sources"][0]["url"] == "http://x/anemi"
    assert "500 mg" not in data["explanation"] and "Demir eksikliği" in data["explanation"]
    assert len(ret.queries) == 2
    prompt = llm.calls[0][1]["content"]
    assert "Hemoglobin" in prompt and "DÜŞÜK" in prompt and "kadın" in prompt


def test_interpret_critical_sets_urgent():
    c, _ = client(FakeLLM("Acil değerlendirme gerekir."), FakeRetriever())
    data = c.post("/api/labs/interpret", json={"values": [{"test": "Potasyum", "value": "7", "unit": "mmol/L"}]}).json()
    assert data["urgent"] is True and "acil" in data["urgent_message"].lower()
    assert data["results"][0]["status"] == "critical"


def test_interpret_llm_failure_falls_back():
    c, _ = client(FakeLLM(fail=True), FakeRetriever())
    data = c.post("/api/labs/interpret", json={"values": [{"test": "Glukoz", "value": "130", "unit": "mg/dL"}]}).json()
    assert data["results"][0]["status"] == "high"
    assert "üretilemedi" in data["explanation"] and data["sources"] == []


def test_interpret_without_llm_or_retriever():
    c, _ = client(None, None)
    data = c.post("/api/labs/interpret", json={"values": [{"test": "TSH", "value": "9", "unit": "mIU/L"}]}).json()
    assert data["results"][0]["status"] == "high" and data["explanation"]


def test_interpret_validation():
    c, _ = client()
    assert c.post("/api/labs/interpret", json={"values": []}).status_code == 422
    assert c.post("/api/labs/interpret", json={"values": [{"test": "", "value": "1"}]}).status_code == 422
    assert c.post("/api/labs/interpret", json={"sex": "x", "values": [{"test": "TSH", "value": 1}]}).status_code == 422
    assert c.post("/api/labs/interpret", json={"values": [{"test": "TSH", "value": "9" * 50}]}).status_code == 422
    big = {"values": [{"test": "TSH", "value": 1}] * 61}
    assert c.post("/api/labs/interpret", json=big).status_code == 422
    ok = {"sex": "erkek", "values": [{"test": "TSH", "value": 1, "unit": "mIU/L"}]}
    assert c.post("/api/labs/interpret", json=ok).status_code == 200


def test_labs_page_served():
    c, _ = client()
    page = c.get("/labs")
    assert page.status_code == 200 and 'id="app-nav"' in page.text
