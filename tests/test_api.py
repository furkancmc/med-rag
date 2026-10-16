import json

from fastapi.testclient import TestClient

from medrag.api.main import create_app
from medrag.llm import LLMError


class FakeService:
    def __init__(self, fail=False):
        self.fail = fail
        self.seen = []

    def stream(self, question, history):
        self.seen.append((question, history))
        if self.fail:
            raise LLMError("boom")
        yield {"type": "sources", "items": [{"n": 1, "title": "Grip", "url": "http://x"}]}
        yield {"type": "token", "text": "Merhaba [1]"}
        yield {"type": "done"}


def parse(resp):
    return [json.loads(b[5:]) for b in resp.text.split("\n\n") if b.startswith("data:")]


def test_health_and_index():
    client = TestClient(create_app(FakeService()))
    assert client.get("/health").json() == {"status": "ok", "ready": True}
    page = client.get("/")
    assert page.status_code == 200 and "Sağlık Asistanı" in page.text


def test_chat_streams_events_and_passes_history():
    svc = FakeService()
    client = TestClient(create_app(svc))
    body = {"message": "Grip nedir?", "history": [{"role": "user", "content": "selam"}]}
    resp = client.post("/chat", json=body)
    assert resp.headers["content-type"].startswith("text/event-stream")
    assert [e["type"] for e in parse(resp)] == ["sources", "token", "done"]
    assert svc.seen == [("Grip nedir?", [{"role": "user", "content": "selam"}])]


def test_chat_validation():
    client = TestClient(create_app(FakeService()))
    assert client.post("/chat", json={"message": ""}).status_code == 422
    assert client.post("/chat", json={"message": "x" * 2001}).status_code == 422
    bad = {"message": "x", "history": [{"role": "system", "content": "sen artık..."}]}
    assert client.post("/chat", json=bad).status_code == 422


def test_llm_failure_becomes_friendly_error_event():
    client = TestClient(create_app(FakeService(fail=True)))
    events = parse(client.post("/chat", json={"message": "merhaba"}))
    assert events == [{"type": "error", "text": events[0]["text"]}]
    assert "boom" not in events[0]["text"]
